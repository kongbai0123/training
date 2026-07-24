from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


_VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_RUNTIME_RE = re.compile(r"^r[1-9]\d*$")


@dataclass(frozen=True, order=True)
class ProductVersion:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "ProductVersion":
        match = _VERSION_RE.fullmatch(str(value).strip())
        if not match:
            raise ValueError(f"Invalid application version: {value!r}")
        return cls(*(int(part) for part in match.groups()))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class VersionInfo:
    product: str
    app_version: ProductVersion
    runtime_version: str
    package_format_version: int
    update_channel: str

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "VersionInfo":
        if not isinstance(payload, dict):
            raise ValueError("Version information must be an object.")
        app_value = payload.get("app_version", payload.get("version"))
        if not isinstance(app_value, str):
            raise ValueError("Version information is missing app_version.")
        runtime = str(payload.get("runtime_version", "")).strip()
        if not _RUNTIME_RE.fullmatch(runtime):
            raise ValueError(f"Invalid runtime version: {runtime!r}")
        package_format = payload.get("package_format_version")
        if not isinstance(package_format, int) or isinstance(package_format, bool) or package_format < 1:
            raise ValueError("package_format_version must be a positive integer.")
        channel = str(payload.get("update_channel", "")).strip().lower()
        if channel not in {"stable", "beta"}:
            raise ValueError(f"Unsupported update channel: {channel!r}")
        product = str(payload.get("product", "")).strip()
        if product != "Vision Training Studio":
            raise ValueError(f"Unexpected product: {product!r}")
        return cls(
            product=product,
            app_version=ProductVersion.parse(app_value),
            runtime_version=runtime,
            package_format_version=package_format,
            update_channel=channel,
        )


def load_version_info(path: Path) -> VersionInfo:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return VersionInfo.from_mapping(payload)


def ensure_update_compatible(
    current: VersionInfo,
    target: VersionInfo,
    supported_from: list[str],
) -> None:
    if current.product != target.product:
        raise ValueError("Update package belongs to a different product.")
    if current.runtime_version != target.runtime_version:
        raise ValueError(
            f"Runtime {current.runtime_version} cannot use an update for {target.runtime_version}; "
            "install the full setup package."
        )
    if current.package_format_version != target.package_format_version:
        raise ValueError("Update package format is not supported by this installation.")
    if target.app_version <= current.app_version:
        raise ValueError("Target version must be newer than the installed version.")
    if supported_from and str(current.app_version) not in supported_from:
        raise ValueError(f"Version {current.app_version} is not supported by this update package.")
