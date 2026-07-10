from __future__ import annotations

import argparse
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


FORBIDDEN_ROOTS = {
    "projects",
    "models",
    "logs",
    "config",
    "licenses",
    "cache",
    "tmp",
    "components",
    "exports",
}


def build_portable_archive(dist: Path, output: Path, version_file: Path) -> dict[str, object]:
    dist = dist.resolve()
    output = output.resolve()
    if not (dist / "VisionTrainingStudio.exe").is_file():
        raise FileNotFoundError(f"VisionTrainingStudio.exe not found in {dist}")

    forbidden = [name for name in sorted(FORBIDDEN_ROOTS) if (dist / name).exists()]
    if forbidden:
        raise ValueError(f"Dist is not factory clean; remove user-data directories: {', '.join(forbidden)}")

    version = json.loads(version_file.read_text(encoding="utf-8"))
    files = [path for path in sorted(dist.rglob("*")) if path.is_file() and path.name != "portable.mode"]
    total_bytes = sum(path.stat().st_size for path in files)
    archive_root = "VisionTrainingStudio"
    manifest = {
        "product": version.get("product", "Vision Training Studio"),
        "version": version.get("version", "unknown"),
        "build": version.get("build", "unknown"),
        "mode": "portable",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "uncompressed_bytes": total_bytes,
        "user_data_policy": "portable.mode stores user data beside the executable",
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=output.name + ".", suffix=".part", dir=output.parent)
    os.close(fd)
    temp_output = Path(temp_name)
    try:
        with zipfile.ZipFile(
            temp_output,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=1,
            allowZip64=True,
        ) as archive:
            archive.writestr(f"{archive_root}/portable.mode", "portable\n")
            archive.writestr(
                f"{archive_root}/portable_manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            )
            for path in files:
                relative = path.relative_to(dist).as_posix()
                archive.write(path, f"{archive_root}/{relative}")

        with zipfile.ZipFile(temp_output, "r") as archive:
            names = set(archive.namelist())
            required = {
                f"{archive_root}/VisionTrainingStudio.exe",
                f"{archive_root}/portable.mode",
                f"{archive_root}/portable_manifest.json",
            }
            missing = sorted(required - names)
            if missing:
                raise ValueError(f"Portable archive is incomplete: {', '.join(missing)}")
            forbidden_entries = [
                name
                for name in names
                if len(Path(name).parts) > 1 and Path(name).parts[1].casefold() in FORBIDDEN_ROOTS
            ]
            if forbidden_entries:
                raise ValueError(f"Portable archive contains user data: {forbidden_entries[0]}")
            bad_member = archive.testzip()
            if bad_member:
                raise ValueError(f"Portable archive CRC failed: {bad_member}")

        temp_output.replace(output)
    finally:
        temp_output.unlink(missing_ok=True)

    return {
        **manifest,
        "archive": output.as_posix(),
        "archive_bytes": output.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a factory-clean portable Vision Training Studio ZIP.")
    parser.add_argument("--dist", type=Path, default=Path("dist/VisionTrainingStudio"))
    parser.add_argument("--version-file", type=Path, default=Path("version.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    version = json.loads(args.version_file.read_text(encoding="utf-8"))
    output = args.output or Path("release_artifacts") / (
        f"VisionTrainingStudio_{version.get('version', 'unknown')}_Windows_x64_portable.zip"
    )
    result = build_portable_archive(args.dist, output, args.version_file)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
