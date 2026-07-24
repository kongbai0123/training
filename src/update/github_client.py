from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.update.versioning import ProductVersion, VersionInfo


DEFAULT_REPOSITORY = "kongbai0123/training"
GITHUB_API = "https://api.github.com"
_UPDATE_NAME_RE = re.compile(
    r"^VisionTrainingStudio_Update_(?P<version>\d+\.\d+\.\d+)_runtime-(?P<runtime>r[1-9]\d*)\.vtsupdate$"
)


@dataclass(frozen=True)
class ReleaseAsset:
    asset_id: int
    name: str
    url: str
    size: int
    digest: str


@dataclass(frozen=True)
class UpdateCandidate:
    version: ProductVersion
    runtime_version: str
    tag: str
    release_url: str
    published_at: str
    notes: str
    immutable: bool
    asset: ReleaseAsset
    full_installer: ReleaseAsset | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": str(self.version),
            "runtime_version": self.runtime_version,
            "tag": self.tag,
            "release_url": self.release_url,
            "published_at": self.published_at,
            "notes": self.notes,
            "immutable": self.immutable,
            "asset": self.asset.__dict__,
            "full_installer": self.full_installer.__dict__ if self.full_installer else None,
        }


class GitHubReleaseClient:
    def __init__(
        self,
        repository: str = DEFAULT_REPOSITORY,
        opener: Callable[..., Any] | None = None,
    ):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Invalid GitHub repository identifier.")
        self.repository = repository
        self.opener = opener or urlopen

    def latest_stable(self, current: VersionInfo) -> UpdateCandidate | None:
        request = Request(
            f"{GITHUB_API}/repos/{self.repository}/releases/latest",
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2026-03-10",
                "User-Agent": "VisionTrainingStudio-Updater",
            },
        )
        with self.opener(request, timeout=10) as response:
            if getattr(response, "status", 200) != 200:
                raise ConnectionError(f"GitHub release check returned HTTP {response.status}.")
            payload = json.loads(response.read().decode("utf-8"))
        return self._candidate_from_release(payload, current)

    def _candidate_from_release(
        self,
        payload: dict[str, Any],
        current: VersionInfo,
    ) -> UpdateCandidate | None:
        if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
            return None
        tag = str(payload.get("tag_name") or "")
        tag_version = ProductVersion.parse(tag.removeprefix("v"))
        if tag_version <= current.app_version:
            return None
        update_asset: ReleaseAsset | None = None
        installer: ReleaseAsset | None = None
        for raw in payload.get("assets") or []:
            asset = self._parse_asset(raw)
            match = _UPDATE_NAME_RE.fullmatch(asset.name)
            if match:
                if (
                    ProductVersion.parse(match.group("version")) == tag_version
                    and match.group("runtime") == current.runtime_version
                ):
                    update_asset = asset
            elif asset.name == f"VisionTrainingStudio_Setup_{tag_version}.exe":
                installer = asset
        if not update_asset:
            return None
        return UpdateCandidate(
            version=tag_version,
            runtime_version=current.runtime_version,
            tag=tag,
            release_url=str(payload.get("html_url") or ""),
            published_at=str(payload.get("published_at") or ""),
            notes=str(payload.get("body") or ""),
            immutable=bool(payload.get("immutable")),
            asset=update_asset,
            full_installer=installer,
        )

    def _parse_asset(self, raw: dict[str, Any]) -> ReleaseAsset:
        if not isinstance(raw, dict):
            raise ValueError("GitHub returned an invalid release asset.")
        url = str(raw.get("browser_download_url") or "")
        parsed = urlparse(url)
        expected_prefix = f"/{self.repository}/releases/download/"
        if parsed.scheme != "https" or parsed.hostname != "github.com" or not parsed.path.startswith(expected_prefix):
            raise ValueError("GitHub returned an untrusted release asset URL.")
        digest = str(raw.get("digest") or "")
        if digest and not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
            raise ValueError("GitHub returned an invalid release asset digest.")
        return ReleaseAsset(
            asset_id=int(raw.get("id") or 0),
            name=str(raw.get("name") or ""),
            url=url,
            size=int(raw.get("size") or 0),
            digest=digest.lower(),
        )
