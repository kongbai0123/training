from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from typing import Any

from src.app_paths import CONFIG_DIR, UPDATE_DOWNLOADS_DIR, UPDATES_DIR
from src.config import BASE_DIR, VERSION_INFO
from src.task_jobs import TaskReporter, task_job_manager
from src.update.blockers import active_update_blockers
from src.update.downloader import download_release_asset
from src.update.github_client import GitHubReleaseClient, ReleaseAsset, UpdateCandidate
from src.update.manifest import verify_update_archive
from src.update.storage import (
    UPDATE_CACHE_LIMIT_BYTES,
    cleanup_expired_parts,
    cleanup_update_storage,
    projected_cache_bytes,
    update_storage_report,
)
from src.update.versioning import ProductVersion, VersionInfo, ensure_update_compatible


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class UpdateService:
    def __init__(
        self,
        *,
        downloads_dir: Path = UPDATE_DOWNLOADS_DIR,
        state_file: Path | None = None,
        public_key_path: Path | None = None,
        release_client: GitHubReleaseClient | None = None,
        current_version: VersionInfo | None = None,
        update_root: Path | None = None,
    ):
        self.downloads_dir = downloads_dir.resolve()
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.update_root = (update_root or self.downloads_dir.parent).resolve()
        self.update_root.mkdir(parents=True, exist_ok=True)
        self.state_file = (state_file or CONFIG_DIR / "software_update_state.json").resolve()
        self.public_key_path = (
            public_key_path or BASE_DIR / "updates" / "keys" / "update_public_key.pem"
        ).resolve()
        self.release_client = release_client or GitHubReleaseClient()
        self.current_version = current_version or VersionInfo.from_mapping(VERSION_INFO)
        self._lock = threading.RLock()
        self._state = self._load_state()
        cleanup_expired_parts(self.update_root)

    def _load_state(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("schema_version") == 1:
                return payload
        except Exception:
            pass
        return {
            "schema_version": 1,
            "last_checked_at": "",
            "candidate": None,
            "ready_package": None,
            "last_error": "",
        }

    def _save_state(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_name(self.state_file.name + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(self._state, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.state_file)

    def status(self) -> dict[str, Any]:
        with self._lock:
            ready = deepcopy(self._state.get("ready_package"))
            if ready and not Path(str(ready.get("path") or "")).is_file():
                ready = None
                self._state["ready_package"] = None
                self._save_state()
            changed = False
            if ready:
                try:
                    if VersionInfo.from_mapping(
                        {
                            "product": self.current_version.product,
                            "app_version": str(ready.get("app_version") or ""),
                            "runtime_version": str(ready.get("runtime_version") or ""),
                            "package_format_version": self.current_version.package_format_version,
                            "update_channel": self.current_version.update_channel,
                        }
                    ).app_version <= self.current_version.app_version:
                        ready = None
                        self._state["ready_package"] = None
                        changed = True
                except ValueError:
                    ready = None
                    self._state["ready_package"] = None
                    changed = True
            candidate = deepcopy(self._state.get("candidate"))
            if candidate:
                try:
                    if ProductVersion.parse(str(candidate.get("version") or "")) <= self.current_version.app_version:
                        candidate = None
                        self._state["candidate"] = None
                        changed = True
                except ValueError:
                    candidate = None
                    self._state["candidate"] = None
                    changed = True
            if changed:
                cleanup_update_storage(self.update_root)
                self._state["last_cleanup_at"] = _utc_now()
                self._save_state()
            blockers = active_update_blockers()
            return {
                "current": {
                    "app_version": str(self.current_version.app_version),
                    "runtime_version": self.current_version.runtime_version,
                    "package_format_version": self.current_version.package_format_version,
                    "channel": self.current_version.update_channel,
                },
                "last_checked_at": self._state.get("last_checked_at") or "",
                "candidate": candidate,
                "ready_package": ready,
                "last_error": self._state.get("last_error") or "",
                "last_cleanup_at": self._state.get("last_cleanup_at") or "",
                "storage": update_storage_report(self.update_root),
                "blockers": blockers,
                "can_apply": bool(ready and not blockers),
            }

    def check_for_updates(self) -> dict[str, Any]:
        try:
            candidate = self.release_client.latest_stable(self.current_version)
            with self._lock:
                self._state["last_checked_at"] = _utc_now()
                self._state["candidate"] = candidate.as_dict() if candidate else None
                self._state["last_error"] = ""
                self._save_state()
            return self.status()
        except Exception as exc:
            with self._lock:
                self._state["last_checked_at"] = _utc_now()
                self._state["last_error"] = str(exc)
                self._save_state()
            raise

    def start_check(self) -> dict[str, Any]:
        def handler(reporter: TaskReporter):
            reporter.update(
                phase="checking",
                message="Checking the latest signed GitHub release",
                progress=20,
                indeterminate=False,
            )
            result = self.check_for_updates()
            reporter.update(
                phase="checked",
                message="Update check completed",
                progress=100,
                indeterminate=False,
            )
            return result

        return task_job_manager.submit(
            kind="software_update_check",
            title="Check for software updates",
            handler=handler,
            message="Waiting to check GitHub Releases",
        )

    def _candidate_asset(self) -> ReleaseAsset:
        candidate = self._state.get("candidate")
        raw = candidate.get("asset") if isinstance(candidate, dict) else None
        if not isinstance(raw, dict):
            raise ValueError("Check for updates before starting a download.")
        return ReleaseAsset(
            asset_id=int(raw["asset_id"]),
            name=str(raw["name"]),
            url=str(raw["url"]),
            size=int(raw["size"]),
            digest=str(raw.get("digest") or ""),
        )

    def start_download(self) -> dict[str, Any]:
        with self._lock:
            asset = self._candidate_asset()
            candidate = deepcopy(self._state.get("candidate"))
            ready = deepcopy(self._state.get("ready_package"))
        if ready and ready.get("app_version") == (candidate or {}).get("version"):
            raise ValueError("This update package is already downloaded and verified.")
        destination = self.downloads_dir / Path(asset.name).name
        projected = projected_cache_bytes(self.update_root, destination, asset.size)
        if projected > UPDATE_CACHE_LIMIT_BYTES:
            raise ValueError("The 2 GiB update cache limit would be exceeded; clean update storage first.")

        def handler(reporter: TaskReporter):
            def progress(values: dict[str, Any]) -> None:
                reporter.update(
                    phase="downloading",
                    message="Downloading signed application update",
                    progress=float(values["progress"]),
                    indeterminate=False,
                    current=int(values["downloaded_bytes"]),
                    total=int(values["total_bytes"]),
                )
                if reporter.is_cancelled():
                    raise InterruptedError("Update download was cancelled.")

            path = download_release_asset(asset, destination, progress=progress)
            reporter.update(
                phase="verifying",
                message="Verifying signature and package contents",
                progress=98,
                indeterminate=False,
            )
            verified = verify_update_archive(path, self.public_key_path)
            target = VersionInfo.from_mapping(
                {
                    "product": verified.manifest["product"],
                    "app_version": verified.manifest["target_app_version"],
                    "runtime_version": verified.manifest["runtime_version"],
                    "package_format_version": verified.manifest["format_version"],
                    "update_channel": self.current_version.update_channel,
                }
            )
            ensure_update_compatible(
                self.current_version,
                target,
                list(verified.manifest["supported_from"]),
            )
            ready = {
                "path": path.as_posix(),
                "app_version": str(target.app_version),
                "runtime_version": target.runtime_version,
                "archive_sha256": verified.archive_sha256,
                "archive_bytes": verified.archive_bytes,
                "verified_at": _utc_now(),
            }
            with self._lock:
                self._state["ready_package"] = ready
                self._state["last_error"] = ""
                self._save_state()
            return ready

        return task_job_manager.submit(
            kind="software_update_download",
            title=f"Download Vision Training Studio {self._state['candidate']['version']}",
            handler=handler,
            message="Update download queued",
        )

    def start_latest_download(self) -> dict[str, Any]:
        def handler(reporter: TaskReporter):
            reporter.update(
                phase="checking",
                message="Checking the latest signed GitHub release",
                progress=5,
                indeterminate=False,
            )
            try:
                candidate = self.release_client.latest_stable(self.current_version)
            except Exception as exc:
                with self._lock:
                    self._state["last_checked_at"] = _utc_now()
                    self._state["last_error"] = str(exc)
                    self._save_state()
                raise
            with self._lock:
                self._state["last_checked_at"] = _utc_now()
                self._state["candidate"] = candidate.as_dict() if candidate else None
                self._state["last_error"] = ""
                self._save_state()
            if not candidate:
                reporter.update(
                    phase="checked",
                    message="The installed version is up to date",
                    progress=100,
                    indeterminate=False,
                )
                return self.status()
            if not candidate.asset:
                reporter.update(
                    phase="checked",
                    message="A new version is available and requires the full installer",
                    progress=100,
                    indeterminate=False,
                )
                return self.status()
            with self._lock:
                existing_ready = deepcopy(self._state.get("ready_package"))
            if (
                existing_ready
                and existing_ready.get("app_version") == str(candidate.version)
                and Path(str(existing_ready.get("path") or "")).is_file()
            ):
                raise ValueError("This update package is already downloaded and verified.")

            destination = self.downloads_dir / Path(candidate.asset.name).name
            projected = projected_cache_bytes(self.update_root, destination, candidate.asset.size)
            if projected > UPDATE_CACHE_LIMIT_BYTES:
                raise ValueError(
                    "The 2 GiB update cache limit would be exceeded; clean update storage first."
                )

            def progress(values: dict[str, Any]) -> None:
                reporter.update(
                    phase="downloading",
                    message="Downloading signed application update",
                    progress=5 + float(values["progress"]) * 0.9,
                    indeterminate=False,
                    current=int(values["downloaded_bytes"]),
                    total=int(values["total_bytes"]),
                )
                if reporter.is_cancelled():
                    raise InterruptedError("Update download was cancelled.")

            try:
                path = download_release_asset(candidate.asset, destination, progress=progress)
                reporter.update(
                    phase="verifying",
                    message="Verifying signature and package contents",
                    progress=97,
                    indeterminate=False,
                )
                ready = self.register_imported_package(path, source="github_release")
            except Exception as exc:
                with self._lock:
                    self._state["last_error"] = str(exc)
                    self._save_state()
                raise
            reporter.update(
                phase="verified",
                message="Update verified and ready to install",
                progress=100,
                indeterminate=False,
            )
            return ready

        return task_job_manager.submit(
            kind="software_update_download",
            title="Check and download the latest software update",
            handler=handler,
            message="Waiting to check GitHub Releases",
        )

    def register_imported_package(
        self,
        archive: Path,
        *,
        source: str = "offline_import",
    ) -> dict[str, Any]:
        verified = verify_update_archive(archive, self.public_key_path)
        target = VersionInfo.from_mapping(
            {
                "product": verified.manifest["product"],
                "app_version": verified.manifest["target_app_version"],
                "runtime_version": verified.manifest["runtime_version"],
                "package_format_version": verified.manifest["format_version"],
                "update_channel": self.current_version.update_channel,
            }
        )
        ensure_update_compatible(self.current_version, target, list(verified.manifest["supported_from"]))
        ready = {
            "path": archive.resolve().as_posix(),
            "app_version": str(target.app_version),
            "runtime_version": target.runtime_version,
            "archive_sha256": verified.archive_sha256,
            "archive_bytes": verified.archive_bytes,
            "verified_at": _utc_now(),
            "source": source,
        }
        with self._lock:
            self._state["ready_package"] = ready
            self._state["last_error"] = ""
            self._save_state()
        return ready

    def import_budget(self, filename: str) -> int:
        current = int(update_storage_report(self.update_root)["cache_bytes"])
        return max(0, UPDATE_CACHE_LIMIT_BYTES - current)

    def cleanup_storage(
        self,
        *,
        discard_ready: bool = False,
        remove_backup: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            ready = deepcopy(self._state.get("ready_package"))
            preserved: list[Path] = []
            if ready and not discard_ready:
                ready_path = Path(str(ready.get("path") or ""))
                if ready_path.is_file():
                    preserved.append(ready_path)
            report = cleanup_update_storage(
                self.update_root,
                preserve_downloads=preserved,
                remove_all_backups=remove_backup,
            )
            if discard_ready:
                self._state["ready_package"] = None
            self._state["last_cleanup_at"] = _utc_now()
            self._save_state()
        result = self.status()
        result["cleanup"] = report
        return result

    def launch_ready_update(self) -> dict[str, Any]:
        blockers = active_update_blockers()
        if blockers:
            names = ", ".join(item["title"] for item in blockers[:3])
            raise ValueError(f"Finish or stop active work before updating: {names}")
        if not getattr(sys, "frozen", False) and os.environ.get("VTS_ALLOW_SOURCE_UPDATE") != "1":
            raise ValueError("Applying updates is disabled in source-development mode.")
        with self._lock:
            ready = deepcopy(self._state.get("ready_package"))
        archive = Path(str((ready or {}).get("path") or "")).resolve()
        if not archive.is_file():
            raise ValueError("No verified update package is ready.")
        install_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else BASE_DIR
        updater = install_dir / "VisionTrainingStudioUpdater.exe"
        if not updater.is_file():
            raise FileNotFoundError("The standalone updater is not installed; use the full setup package.")
        current_version_file = BASE_DIR / "version.json"
        parent_pid = os.getppid()
        command = [
            str(updater),
            "--archive",
            str(archive),
            "--install-dir",
            str(install_dir),
            "--current-version-file",
            str(current_version_file),
            "--public-key",
            str(self.public_key_path),
            "--update-root",
            str(UPDATES_DIR),
            "--parent-pid",
            str(parent_pid),
        ]
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            command,
            cwd=str(install_dir),
            creationflags=creationflags,
            close_fds=True,
        )

        def close_application() -> None:
            time.sleep(1.25)
            try:
                os.kill(parent_pid, signal.SIGTERM)
            except OSError:
                pass
            os._exit(0)

        threading.Thread(target=close_application, daemon=True, name="software-update-shutdown").start()
        return {
            "status": "restart_scheduled",
            "target_app_version": ready["app_version"],
            "message": "The application will close and apply the verified update.",
        }


UPDATE_SERVICE = UpdateService()
