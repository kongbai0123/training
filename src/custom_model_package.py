from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional


class CustomModelPackageValidator:
    """Static validator for Custom Model Package ZIP files.

    This class never extracts, imports, or executes package code. It only reads
    ZIP metadata and manifest text to decide whether the system can understand
    the package contract.
    """

    MANIFEST_CANDIDATES = (
        "manifest.yaml", "manifest.yml", "model_manifest.yaml", "model_manifest.yml",
        "model_manifest.json", "manifest.json",
    )
    EXECUTABLE_SUFFIXES = {".exe", ".bat", ".cmd", ".ps1", ".sh", ".dll", ".so", ".dylib", ".pyd"}
    ALLOWED_ARCHITECTURES = {"cnn", "rnn", "xgboost", "transformer", "classical", "custom"}
    ALLOWED_FRAMEWORKS = {"pytorch", "tensorflow", "onnx", "sklearn", "xgboost", "python", "cpp", "custom"}
    SAFE_WRITE_POLICIES = {"none", "false", "project", "project_only", "artifacts_only"}
    MAX_FILES = 600
    MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
    SUSPICIOUS_TOKENS = (
        "subprocess", "os.system", "socket", "requests", "urllib", "eval(", "exec(",
        "pickle.load", "shutil.rmtree", "ctypes",
    )

    @classmethod
    def validate_zip(cls, package_path: Path) -> Dict[str, Any]:
        package_path = Path(package_path)
        checks: List[Dict[str, Any]] = []
        errors: List[str] = []
        warnings: List[str] = []
        blocked: List[str] = []

        def add_check(name: str, status: str, detail: str = "") -> None:
            checks.append({"name": name, "status": status, "passed": status == "passed", "detail": detail})

        result: Dict[str, Any] = {
            "status": "invalid_manifest",
            "understood": False,
            "trainable": False,
            "execution_enabled": False,
            "manifest_path": None,
            "manifest": {},
            "normalized_manifest": {},
            "package_summary": {
                "file_count": 0,
                "package_bytes": package_path.stat().st_size if package_path.exists() else 0,
                "uncompressed_bytes": 0,
                "suffix_counts": {},
            },
            "security_policy": {"allow_network": False, "allow_shell": False, "allow_write": "project_only", "execution_phase": "validation_only"},
            "checks": checks,
            "errors": errors,
            "warnings": warnings,
            "blocked_reasons": blocked,
        }

        if not package_path.exists() or not package_path.is_file():
            errors.append("Package file does not exist.")
            add_check("zip_file_exists", "failed")
            return cls._finalize(result)
        if package_path.suffix.lower() != ".zip":
            errors.append("Custom model package must be a .zip file.")
            add_check("zip_extension", "failed")
            return cls._finalize(result)

        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                infos = [info for info in zf.infolist() if not info.is_dir()]
                add_check("zip_readable", "passed", "ZIP metadata read; no extraction performed.")
                names: Dict[str, zipfile.ZipInfo] = {}
                path_errors: List[str] = []
                symlinks: List[str] = []
                for info in infos:
                    safe_name = cls._safe_zip_name(info.filename)
                    if not safe_name:
                        path_errors.append(f"Unsafe ZIP entry path: {info.filename!r}")
                        continue
                    if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                        symlinks.append(safe_name)
                    names[safe_name] = info

                if path_errors:
                    blocked.extend(path_errors)
                    add_check("zip_path_safety", "blocked", "; ".join(path_errors[:3]))
                else:
                    add_check("zip_path_safety", "passed")
                if symlinks:
                    blocked.append("ZIP symlinks are not allowed: " + ", ".join(symlinks[:8]))
                    add_check("zip_symlink_safety", "blocked", ", ".join(symlinks[:8]))
                else:
                    add_check("zip_symlink_safety", "passed")

                suffix_counts: Dict[str, int] = {}
                total_uncompressed = 0
                for name, info in names.items():
                    suffix = PurePosixPath(name).suffix.lower() or "<none>"
                    suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
                    total_uncompressed += int(info.file_size or 0)
                result["package_summary"] = {
                    "file_count": len(names),
                    "package_bytes": package_path.stat().st_size,
                    "uncompressed_bytes": total_uncompressed,
                    "suffix_counts": dict(sorted(suffix_counts.items())),
                }
                add_check("zip_file_count_limit", "passed" if len(names) <= cls.MAX_FILES else "failed", str(len(names)))
                if len(names) > cls.MAX_FILES:
                    errors.append(f"Package contains too many files: {len(names)} > {cls.MAX_FILES}.")
                add_check("zip_uncompressed_size_limit", "passed" if total_uncompressed <= cls.MAX_UNCOMPRESSED_BYTES else "failed", str(total_uncompressed))
                if total_uncompressed > cls.MAX_UNCOMPRESSED_BYTES:
                    errors.append("Package uncompressed size exceeds the validation limit.")

                executables = [name for name in names if PurePosixPath(name).suffix.lower() in cls.EXECUTABLE_SUFFIXES]
                if executables:
                    blocked.append("Executable or shell payloads are blocked in Phase P1-A: " + ", ".join(executables[:8]))
                    add_check("no_executable_payloads", "blocked", ", ".join(executables[:8]))
                else:
                    add_check("no_executable_payloads", "passed")

                manifest_path = cls._find_manifest(names)
                result["manifest_path"] = manifest_path
                if not manifest_path:
                    errors.append("Manifest not found. Expected one of: " + ", ".join(cls.MANIFEST_CANDIDATES))
                    add_check("manifest_present", "failed")
                    cls._scan_python(zf, names, warnings, checks)
                    return cls._finalize(result)
                add_check("manifest_present", "passed", manifest_path)

                try:
                    text = zf.read(manifest_path).decode("utf-8")
                    manifest = cls._parse_manifest(manifest_path, text)
                    if not isinstance(manifest, dict):
                        raise ValueError("manifest root must be a mapping/object")
                    result["manifest"] = manifest
                    add_check("manifest_parse", "passed")
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"Manifest parse failed: {exc}")
                    add_check("manifest_parse", "failed", str(exc))
                    cls._scan_python(zf, names, warnings, checks)
                    return cls._finalize(result)

                normalized = cls._validate_manifest(manifest, names, errors, warnings, blocked, checks)
                result["normalized_manifest"] = normalized
                result["security_policy"] = normalized.get("security", result["security_policy"])
                cls._scan_python(zf, names, warnings, checks)
        except zipfile.BadZipFile:
            errors.append("Invalid ZIP file.")
            add_check("zip_readable", "failed", "BadZipFile")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Package validation failed: {exc}")
            add_check("package_validation", "failed", str(exc))
        return cls._finalize(result)

    @staticmethod
    def _finalize(result: Dict[str, Any]) -> Dict[str, Any]:
        if result["blocked_reasons"]:
            result["status"] = "blocked"
            result["understood"] = not bool(result["errors"])
        elif result["errors"]:
            result["status"] = "invalid_manifest"
            result["understood"] = False
        else:
            result["status"] = "valid_manifest_execution_disabled"
            result["understood"] = True
        result["trainable"] = False
        result["execution_enabled"] = False
        return result

    @staticmethod
    def _safe_zip_name(raw_name: str) -> Optional[str]:
        name = str(raw_name or "").replace("\\", "/").strip()
        if not name or name.startswith("/") or name.startswith("~"):
            return None
        parts = PurePosixPath(name).parts
        if not parts or ":" in parts[0] or any(part in {"", ".", ".."} for part in parts):
            return None
        return "/".join(parts)

    @classmethod
    def _find_manifest(cls, names: Dict[str, zipfile.ZipInfo]) -> Optional[str]:
        lowered = {name.lower(): name for name in names}
        for candidate in cls.MANIFEST_CANDIDATES:
            if candidate in lowered:
                return lowered[candidate]
        for name in names:
            if PurePosixPath(name).name.lower() in cls.MANIFEST_CANDIDATES:
                return name
        return None

    @classmethod
    def _parse_manifest(cls, path: str, text: str) -> Dict[str, Any]:
        if PurePosixPath(path).suffix.lower() == ".json":
            return json.loads(text)
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(text)
            return data if data is not None else {}
        except ImportError:
            return cls._parse_simple_yaml(text)

    @staticmethod
    def _parse_simple_yaml(text: str) -> Dict[str, Any]:
        root: Dict[str, Any] = {}
        current: Optional[str] = None
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].rstrip()
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip(" "))
            stripped = line.strip()
            if indent == 0 and stripped.endswith(":"):
                current = stripped[:-1].strip()
                root[current] = {}
            elif indent == 0 and ":" in stripped:
                key, value = stripped.split(":", 1)
                root[key.strip()] = CustomModelPackageValidator._parse_scalar(value.strip())
                current = None
            elif indent > 0 and current and ":" in stripped:
                key, value = stripped.split(":", 1)
                section = root.setdefault(current, {})
                if not isinstance(section, dict):
                    raise ValueError(f"YAML section is not a mapping: {current}")
                section[key.strip()] = CustomModelPackageValidator._parse_scalar(value.strip())
            else:
                raise ValueError("Unsupported YAML syntax; install PyYAML or use JSON manifest.")
        return root

    @staticmethod
    def _parse_scalar(value: str) -> Any:
        value = value.strip()
        if value.lower() in {"true", "false"}:
            return value.lower() == "true"
        if value.lower() in {"null", "none", ""}:
            return None
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                return []
            return [CustomModelPackageValidator._parse_scalar(item.strip()) for item in inner.split(",")]
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value.strip('"\'')

    @classmethod
    def _validate_manifest(
        cls,
        manifest: Dict[str, Any],
        names: Dict[str, zipfile.ZipInfo],
        errors: List[str],
        warnings: List[str],
        blocked: List[str],
        checks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        def add_check(name: str, status: str, detail: str = "") -> None:
            checks.append({"name": name, "status": status, "passed": status == "passed", "detail": detail})

        model = cls._as_dict(manifest.get("model"))
        entrypoints = cls._as_dict(manifest.get("entrypoints"))
        input_spec = cls._as_dict(manifest.get("input"))
        output_spec = cls._as_dict(manifest.get("output"))
        metrics = cls._as_dict(manifest.get("metrics"))
        security = cls._as_dict(manifest.get("security"))

        normalized = {
            "model": {
                "name": str(model.get("name") or "").strip(),
                "architecture": str(model.get("architecture") or "").strip().lower(),
                "task_type": str(model.get("task_type") or "").strip(),
                "framework": str(model.get("framework") or "").strip().lower(),
            },
            "entrypoints": {"trainer": entrypoints.get("trainer"), "predictor": entrypoints.get("predictor")},
            "input": input_spec,
            "output": output_spec,
            "metrics": {"required": cls._as_list(metrics.get("required")), "optional": cls._as_list(metrics.get("optional"))},
            "security": {
                "allow_network": bool(security.get("allow_network", False)),
                "allow_shell": bool(security.get("allow_shell", False)),
                "allow_write": str(security.get("allow_write", "project_only") or "project_only"),
                "execution_phase": "validation_only",
            },
        }

        missing = [key for key in ("name", "architecture", "task_type", "framework") if not normalized["model"].get(key)]
        if missing:
            errors.append("model contract missing required fields: " + ", ".join(missing))
            add_check("model_contract", "failed", ", ".join(missing))
        elif normalized["model"]["architecture"] not in cls.ALLOWED_ARCHITECTURES:
            errors.append("Unsupported model architecture: " + normalized["model"]["architecture"])
            add_check("model_contract", "failed", "unsupported architecture")
        elif normalized["model"]["framework"] not in cls.ALLOWED_FRAMEWORKS:
            errors.append("Unsupported model framework: " + normalized["model"]["framework"])
            add_check("model_contract", "failed", "unsupported framework")
        else:
            add_check("model_contract", "passed")

        entry_values = [v for v in normalized["entrypoints"].values() if v]
        if not entry_values:
            errors.append("At least one entrypoint is required: entrypoints.trainer or entrypoints.predictor.")
            add_check("entrypoint_contract", "failed")
        else:
            bad = []
            for value in entry_values:
                if not cls._entrypoint_module_exists(str(value), names):
                    bad.append(str(value))
            if bad:
                errors.append("Entrypoint module file not found in package: " + ", ".join(bad))
                add_check("entrypoint_contract", "failed", ", ".join(bad))
            else:
                add_check("entrypoint_contract", "passed")

        if not input_spec.get("type"):
            errors.append("input.type is required.")
            add_check("input_contract", "failed")
        else:
            shape = input_spec.get("shape")
            if shape is not None and not all(isinstance(v, (int, float)) for v in cls._as_list(shape)):
                errors.append("input.shape must be a list of numbers when provided.")
                add_check("input_contract", "failed", "invalid shape")
            else:
                add_check("input_contract", "passed")
        if not output_spec.get("type"):
            errors.append("output.type is required.")
            add_check("output_contract", "failed")
        else:
            add_check("output_contract", "passed")

        if normalized["entrypoints"].get("trainer") and not normalized["metrics"]["required"]:
            errors.append("metrics.required is required for trainable adapters.")
            add_check("metrics_contract", "failed")
        else:
            required = set(str(x) for x in normalized["metrics"]["required"])
            if normalized["entrypoints"].get("trainer") and {"train/loss", "val/loss"} - required:
                warnings.append("Recommended metrics are missing: train/loss and val/loss.")
            add_check("metrics_contract", "passed")

        if normalized["security"].get("allow_network"):
            blocked.append("security.allow_network=true is not allowed in validation-only phase.")
        if normalized["security"].get("allow_shell"):
            blocked.append("security.allow_shell=true is not allowed.")
        if normalized["security"].get("allow_write", "").lower() not in cls.SAFE_WRITE_POLICIES:
            blocked.append("security.allow_write must be one of: " + ", ".join(sorted(cls.SAFE_WRITE_POLICIES)))
        add_check("security_policy", "blocked" if blocked else "passed", "; ".join(blocked[-3:]) if blocked else "")
        return normalized

    @classmethod
    def _entrypoint_module_exists(cls, entrypoint: str, names: Dict[str, zipfile.ZipInfo]) -> bool:
        entrypoint = entrypoint.strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*[:.][A-Za-z_][A-Za-z0-9_]*$", entrypoint):
            return False
        module = entrypoint.split(":", 1)[0].rsplit(".", 1)[0]
        module_path = module.replace(".", "/")
        return f"{module_path}.py" in names or f"{module_path}/__init__.py" in names

    @classmethod
    def _scan_python(cls, zf: zipfile.ZipFile, names: Dict[str, zipfile.ZipInfo], warnings: List[str], checks: List[Dict[str, Any]]) -> None:
        hit_count = 0
        for name, info in names.items():
            if PurePosixPath(name).suffix.lower() != ".py" or info.file_size > 256 * 1024:
                continue
            try:
                text = zf.read(name).decode("utf-8", errors="ignore")
            except Exception:
                continue
            hits = [token for token in cls.SUSPICIOUS_TOKENS if token in text]
            if hits:
                hit_count += len(hits)
                warnings.append(f"Static source warning in {name}: {', '.join(hits[:5])}")
        checks.append({"name": "python_static_scan", "status": "warning" if hit_count else "passed", "passed": True, "detail": f"{hit_count} suspicious token hits"})

    @staticmethod
    def _as_dict(value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _as_list(value: Any) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]
