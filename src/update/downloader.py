from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import threading
import time
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.update.github_client import ReleaseAsset


ProgressCallback = Callable[[dict[str, Any]], None]
ALLOWED_INITIAL_HOSTS = frozenset({"github.com"})


def _validate_download_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_INITIAL_HOSTS:
        raise ValueError("Updates must be downloaded from an approved HTTPS release URL.")


def download_release_asset(
    asset: ReleaseAsset,
    destination: Path,
    *,
    opener: Callable[..., Any] | None = None,
    progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    minimum_free_bytes: int = 128 * 1024 * 1024,
) -> Path:
    _validate_download_url(asset.url)
    if asset.size <= 0:
        raise ValueError("Release asset does not declare a valid size.")
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(destination.parent).free
    required = asset.size + minimum_free_bytes
    if free < required:
        raise OSError(f"Not enough disk space for the update; required={required}, available={free}.")
    part = destination.with_name(destination.name + ".part")
    downloaded = part.stat().st_size if part.exists() else 0
    if downloaded > asset.size:
        part.unlink()
        downloaded = 0

    request_headers = {"User-Agent": "VisionTrainingStudio-Updater"}
    if downloaded:
        request_headers["Range"] = f"bytes={downloaded}-"
    request = Request(asset.url, headers=request_headers)
    open_url = opener or urlopen
    started = time.monotonic()
    mode = "ab" if downloaded else "wb"
    with open_url(request, timeout=30) as response:
        status = getattr(response, "status", 200)
        if downloaded and status != 206:
            downloaded = 0
            mode = "wb"
        elif status not in {200, 206}:
            raise ConnectionError(f"Update download returned HTTP {status}.")
        with part.open(mode) as stream:
            while True:
                if cancel_event and cancel_event.is_set():
                    raise InterruptedError("Update download was cancelled.")
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                stream.write(chunk)
                downloaded += len(chunk)
                if downloaded > asset.size:
                    raise ValueError("Downloaded update is larger than the declared release asset.")
                if progress:
                    elapsed = max(0.001, time.monotonic() - started)
                    speed = downloaded / elapsed
                    progress(
                        {
                            "downloaded_bytes": downloaded,
                            "total_bytes": asset.size,
                            "progress": round(downloaded * 100 / asset.size, 2),
                            "bytes_per_second": round(speed),
                            "remaining_seconds": round((asset.size - downloaded) / speed, 1) if speed else None,
                        }
                    )
            stream.flush()
            os.fsync(stream.fileno())
    if part.stat().st_size != asset.size:
        raise ValueError("Downloaded update size does not match the release asset.")
    if asset.digest:
        digest = hashlib.sha256()
        with part.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        if f"sha256:{digest.hexdigest()}" != asset.digest:
            raise ValueError("Downloaded update checksum does not match GitHub.")
    os.replace(part, destination)
    return destination
