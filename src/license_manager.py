from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Set
import hashlib
import json
import os
import platform
import subprocess

from src.app_paths import LICENSES_DIR, APP_DATA_CONFIG


@dataclass(frozen=True)
class LicenseStatus:
    source: str
    valid: bool
    expired: bool
    status: str
    features: Set[str]
    grace_days: int
    clock_rollback_detected: bool
    reason: str
    license_path: Optional[str]
    expiry: Optional[str]


def _parse_iso8601(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def get_machine_fingerprint() -> str:
    base_parts = [
        platform.node(),
        platform.system(),
        platform.release(),
        os.environ.get("USERNAME", ""),
        os.environ.get("COMPUTERNAME", ""),
        os.environ.get("USERPROFILE", ""),
    ]

    # Best effort: collect a stable Windows machine identifier when available.
    machine_guid = ""
    try:
        if os.name == "nt":
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\Microsoft\\Cryptography") as key:
                machine_guid, _ = winreg.QueryValueEx(key, "MachineGuid")
    except Exception:
        machine_guid = ""

    if not machine_guid:
        try:
            machine_guid = str(subprocess.check_output(["wmic", "csproduct", "get", "uuid"], stderr=subprocess.DEVNULL))
        except Exception:
            machine_guid = ""

    if machine_guid:
        base_parts.append(machine_guid)

    seed = "|".join(filter(None, base_parts))
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


class LicenseManager:
    def __init__(self, env: str = "development") -> None:
        self.env = env.lower()
        self.license_file = LICENSES_DIR / "license.json"

    def _read_payload(self) -> Optional[Dict[str, Any]]:
        if not self.license_file.exists():
            return None
        with self.license_file.open("r", encoding="utf-8") as f:
            return json.load(f)

    def validate(self, request_features: Optional[Set[str]] = None) -> LicenseStatus:
        request_features = request_features or set()
        payload = self._read_payload()
        now = datetime.now(timezone.utc)

        if self.env in {"development", "dev", "debug"}:
            return LicenseStatus(
                source="development",
                valid=True,
                expired=False,
                status="development",
                features={"training", "auto_labeling", "export_onnx", "inference", "commercial"},
                grace_days=0,
                clock_rollback_detected=False,
                reason="Development mode: local enforcement skipped",
                license_path=str(self.license_file) if self.license_file.exists() else None,
                expiry=None,
            )

        if payload is None:
            return LicenseStatus(
                source="missing",
                valid=False,
                expired=False,
                status="missing",
                features=set(),
                grace_days=0,
                clock_rollback_detected=False,
                reason="License file not found",
                license_path=None,
                expiry=None,
            )

        status = str(payload.get("status", "missing")).lower()
        expires_at = str(payload.get("expires_at", "")).strip()
        edition = payload.get("edition", "local")
        product = payload.get("product", "Vision Training Studio")
        features = set(payload.get("features", []))
        signature = payload.get("signature")
        machine_hint = payload.get("machine_id")
        last_validated = payload.get("last_validated_at")
        grace_window = int(payload.get("grace_period_days", 3))
        current_machine = get_machine_fingerprint()

        if status not in {"valid", "active", "grace"}:
            return LicenseStatus(
                source="invalid",
                valid=False,
                expired=False,
                status="invalid",
                features=set(),
                grace_days=grace_window,
                clock_rollback_detected=False,
                reason=f"License status invalid: {status}",
                license_path=str(self.license_file),
                expiry=expires_at,
            )

        expiry_time = _parse_iso8601(expires_at)
        if expires_at and expiry_time is None:
            return LicenseStatus(
                source="invalid",
                valid=False,
                expired=False,
                status="invalid",
                features=set(),
                grace_days=grace_window,
                clock_rollback_detected=False,
                reason="Invalid expires_at format",
                license_path=str(self.license_file),
                expiry=expires_at,
            )

        checked_at = _parse_iso8601(str(last_validated))
        if checked_at and checked_at > now + timedelta(minutes=30):
            return LicenseStatus(
                source="invalid",
                valid=False,
                expired=False,
                status="clock_rollback",
                features=set(),
                grace_days=grace_window,
                clock_rollback_detected=True,
                reason="Clock rollback detected. Validation blocked.",
                license_path=str(self.license_file),
                expiry=expires_at,
            )

        if not signature:
            return LicenseStatus(
                source="invalid",
                valid=False,
                expired=False,
                status="invalid",
                features=set(),
                grace_days=grace_window,
                clock_rollback_detected=False,
                reason="Missing signature",
                license_path=str(self.license_file),
                expiry=expires_at,
            )

        if machine_hint is None:
            return LicenseStatus(
                source="invalid",
                valid=False,
                expired=False,
                status="invalid",
                features=set(),
                grace_days=grace_window,
                clock_rollback_detected=False,
                reason="Missing machine_id",
                license_path=str(self.license_file),
                expiry=expires_at,
            )

        expect = hashlib.sha256(
                f"{product}|{edition}|{expires_at}|{machine_hint}|{','.join(sorted(features))}|{APP_DATA_CONFIG.get('mode', '')}".encode(
                    "utf-8"
                )
            ).hexdigest()
        if signature != expect:
            return LicenseStatus(
                source="invalid",
                valid=False,
                expired=False,
                status="invalid",
                features=set(),
                grace_days=grace_window,
                clock_rollback_detected=False,
                reason="License signature mismatch",
                license_path=str(self.license_file),
                expiry=expires_at,
            )
        if machine_hint != current_machine:
            return LicenseStatus(
                source="invalid",
                valid=False,
                expired=False,
                status="invalid",
                features=set(),
                grace_days=grace_window,
                clock_rollback_detected=False,
                reason="Machine fingerprint mismatch",
                license_path=str(self.license_file),
                expiry=expires_at,
            )

        if expiry_time and now > expiry_time + timedelta(days=grace_window):
            return LicenseStatus(
                source="expired",
                valid=False,
                expired=True,
                status="expired",
                features=set(),
                grace_days=grace_window,
                clock_rollback_detected=False,
                reason="License expired",
                license_path=str(self.license_file),
                expiry=expires_at,
            )

        if expiry_time and now >= expiry_time:
            return LicenseStatus(
                source="expired",
                valid=True,
                expired=True,
                status="grace",
                features=features,
                grace_days=grace_window,
                clock_rollback_detected=False,
                reason=f"Expired but within grace window ({grace_window}d)",
                license_path=str(self.license_file),
                expiry=expires_at,
            )

        missing = request_features - features if request_features else set()
        if missing:
            return LicenseStatus(
                source="valid",
                valid=False,
                expired=False,
                status="feature_restricted",
                features=features,
                grace_days=grace_window,
                clock_rollback_detected=False,
                reason=f"Missing feature: {sorted(missing)[0]}",
                license_path=str(self.license_file),
                expiry=expires_at,
            )

        return LicenseStatus(
            source="valid",
            valid=True,
            expired=False,
            status=status,
            features=features,
            grace_days=grace_window,
            clock_rollback_detected=False,
            reason="License valid",
            license_path=str(self.license_file),
            expiry=expires_at,
        )


def build_license_report() -> Dict[str, Any]:
    manager = LicenseManager(APP_DATA_CONFIG.get("mode", "development"))
    result = manager.validate()
    return {
        "license_status": result.status,
        "valid": result.valid,
        "expired": result.expired,
        "grace_days": result.grace_days,
        "clock_rollback_detected": result.clock_rollback_detected,
        "reason": result.reason,
        "features": sorted(result.features),
        "path": result.license_path,
        "machine": get_machine_fingerprint()[:12],
    }
