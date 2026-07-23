from __future__ import annotations

import os
import threading
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

from src.app_paths import MODELS_DIR
from src.model_system.install_state import file_sha256


ALLOWED_DOWNLOAD_HOSTS = {
    "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com",
    "download.pytorch.org", "huggingface.co", "cdn-lfs.huggingface.co", "cas-bridge.xethub.hf.co",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ModelInstallManager:
    def __init__(self, *, models_dir: Optional[Path] = None, opener: Optional[Callable[..., Any]] = None):
        self.models_dir = Path(models_dir or MODELS_DIR).resolve()
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.opener = opener or urllib.request.urlopen
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._cancel_events: Dict[str, threading.Event] = {}
        self._lock = threading.RLock()

    def start(self, model: Dict[str, Any], *, background: bool = True) -> Dict[str, Any]:
        model_id = str(model.get("model_id") or "").strip()
        if str(model.get("format") or "").lower() == "hf_snapshot":
            return self._start_hf_snapshot(model, background=background)
        url = str(model.get("download_url") or "").strip()
        filename = Path(str(model.get("weight") or "")).name
        if not model_id or not url or not filename:
            raise ValueError("Model does not provide an installable download contract")
        self._validate_download_url(url)
        if Path(filename).suffix.lower() != ".pt":
            raise ValueError("Only .pt model downloads are supported")

        job_id = f"model_install_{uuid.uuid4().hex[:12]}"
        job = {
            "job_id": job_id,
            "model_id": model_id,
            "display_name": model.get("display_name") or model_id,
            "filename": filename,
            "download_url": url,
            "expected_sha256": str(model.get("sha256") or "").lower(),
            "expected_bytes": int(model.get("download_size") or 0),
            "downloaded_bytes": 0,
            "progress": 0.0,
            "status": "queued",
            "error": "",
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }
        cancel_event = threading.Event()
        with self._lock:
            active = next((
                existing for existing in self._jobs.values()
                if existing.get("model_id") == model_id and existing.get("status") in {"queued", "downloading"}
            ), None)
            if active:
                raise ValueError("This model already has an active installation")
            self._jobs[job_id] = job
            self._cancel_events[job_id] = cancel_event

        if background:
            threading.Thread(target=self._download, args=(job_id,), daemon=True, name=job_id).start()
        else:
            self._download(job_id)
        return self.get(job_id)

    def _start_hf_snapshot(self, model: Dict[str, Any], *, background: bool) -> Dict[str, Any]:
        model_id = str(model.get("model_id") or "").strip()
        hub_id = str(model.get("hub_id") or "").strip()
        directory_name = Path(str(model.get("weight") or "")).name
        if not model_id or not hub_id or not directory_name or "/" not in hub_id:
            raise ValueError("Model does not provide a valid Hugging Face snapshot contract")
        job_id = f"model_install_{uuid.uuid4().hex[:12]}"
        job = {
            "job_id": job_id,
            "model_id": model_id,
            "display_name": model.get("display_name") or model_id,
            "filename": directory_name,
            "hub_id": hub_id,
            "install_kind": "hf_snapshot",
            "downloaded_bytes": 0,
            "progress": 0.0,
            "status": "queued",
            "error": "",
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }
        with self._lock:
            active = next((existing for existing in self._jobs.values() if existing.get("model_id") == model_id and existing.get("status") in {"queued", "downloading"}), None)
            if active:
                raise ValueError("This model already has an active installation")
            self._jobs[job_id] = job
            self._cancel_events[job_id] = threading.Event()
        if background:
            threading.Thread(target=self._download_hf_snapshot, args=(job_id,), daemon=True, name=job_id).start()
        else:
            self._download_hf_snapshot(job_id)
        return self.get(job_id)

    def _download_hf_snapshot(self, job_id: str) -> None:
        job = self.get(job_id)
        target = (self.models_dir / job["filename"]).resolve()
        self._update(job_id, status="downloading", progress=5.0)
        try:
            from huggingface_hub import snapshot_download

            snapshot_download(
                repo_id=job["hub_id"],
                local_dir=target,
                allow_patterns=["*.json", "*.safetensors", "*.txt"],
            )
            if not (target / "config.json").exists():
                raise ValueError("Downloaded snapshot does not contain config.json")
            total = sum(path.stat().st_size for path in target.rglob("*") if path.is_file())
            self._update(job_id, status="completed", progress=100.0, downloaded_bytes=total, expected_bytes=total, installed_path=target.as_posix())
        except Exception as exc:
            self._update(job_id, status="failed", error=str(exc))

    def get(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return dict(self._jobs[job_id])

    def cancel(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            event = self._cancel_events.get(job_id)
            if not event or job_id not in self._jobs:
                raise KeyError(job_id)
            event.set()
            if self._jobs[job_id]["status"] == "queued":
                self._update(job_id, status="cancelled")
        return self.get(job_id)

    def active_snapshot(self) -> list[Dict[str, Any]]:
        with self._lock:
            return [
                dict(job)
                for job in self._jobs.values()
                if job.get("status") in {"queued", "downloading", "cancelling"}
            ]

    def retry(self, job_id: str, *, background: bool = True) -> Dict[str, Any]:
        previous = self.get(job_id)
        if previous["status"] not in {"failed", "cancelled"}:
            raise ValueError("Only failed or cancelled installs can be retried")
        if previous.get("install_kind") == "hf_snapshot":
            return self._start_hf_snapshot({
                "model_id": previous["model_id"], "display_name": previous["display_name"],
                "weight": previous["filename"], "hub_id": previous["hub_id"], "format": "hf_snapshot",
            }, background=background)
        return self.start({
            "model_id": previous["model_id"],
            "display_name": previous["display_name"],
            "weight": previous["filename"],
            "download_url": previous["download_url"],
            "sha256": previous["expected_sha256"],
            "download_size": previous["expected_bytes"],
        }, background=background)

    def _download(self, job_id: str) -> None:
        job = self.get(job_id)
        target = (self.models_dir / job["filename"]).resolve()
        part = target.with_suffix(target.suffix + ".part")
        cancel_event = self._cancel_events[job_id]
        self._update(job_id, status="downloading")
        try:
            request = urllib.request.Request(job["download_url"], headers={"User-Agent": "VisionTrainingStudio/1.0"})
            with self.opener(request, timeout=60) as response, part.open("wb") as output:
                final_url = response.geturl() if hasattr(response, "geturl") else job["download_url"]
                self._validate_download_url(final_url)
                header_total = int(response.headers.get("Content-Length") or 0)
                expected = job["expected_bytes"] or header_total
                while True:
                    if cancel_event.is_set():
                        raise _InstallCancelled()
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded = output.tell()
                    progress = min(99.0, downloaded * 100 / expected) if expected else 0.0
                    self._update(job_id, downloaded_bytes=downloaded, expected_bytes=expected, progress=round(progress, 1))

            actual_sha = file_sha256(part)
            expected_sha = job["expected_sha256"]
            if expected_sha and actual_sha.lower() != expected_sha:
                raise ValueError("Downloaded model checksum does not match the manifest")
            os.replace(part, target)
            self._update(
                job_id,
                status="completed",
                progress=100.0,
                downloaded_bytes=target.stat().st_size,
                actual_sha256=actual_sha,
                installed_path=target.as_posix(),
            )
        except _InstallCancelled:
            part.unlink(missing_ok=True)
            self._update(job_id, status="cancelled", error="")
        except Exception as exc:
            part.unlink(missing_ok=True)
            self._update(job_id, status="failed", error=str(exc))

    def _update(self, job_id: str, **values: Any) -> None:
        with self._lock:
            self._jobs[job_id].update(values)
            self._jobs[job_id]["updated_at"] = _utc_now()

    @staticmethod
    def _validate_download_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS:
            raise ValueError("Model downloads must use an approved HTTPS host")


class _InstallCancelled(Exception):
    pass


MODEL_INSTALL_MANAGER = ModelInstallManager()
