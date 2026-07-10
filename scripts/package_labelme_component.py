from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    dist = Path(args.dist).resolve()
    entrypoint = dist / "LabelMe.exe"
    if not entrypoint.is_file():
        raise SystemExit(f"LabelMe.exe not found in {dist}")
    conflicting_qt_runtimes = [
        dist / "_internal" / "PyQt5" / "Qt5" / "bin" / name
        for name in ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")
    ]
    present_conflicts = [path.name for path in conflicting_qt_runtimes if path.exists()]
    if present_conflicts:
        raise SystemExit(
            "Conflicting PyQt VC runtime copies must be removed before packaging: "
            + ", ".join(present_conflicts)
        )
    manifest = {
        "component_id": "labelme",
        "version": args.version,
        "platforms": ["windows-x64"],
        "entrypoint": "LabelMe/LabelMe.exe",
        "sha256": {"LabelMe/LabelMe.exe": sha256(entrypoint)},
        "capabilities": {
            "manual_annotation": True,
            "offline_ready": True,
            "ai_model_weights_bundled": False,
        },
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("component.json", json.dumps(manifest, indent=2))
        for path in sorted(dist.rglob("*")):
            if path.is_file():
                archive.write(path, Path("LabelMe") / path.relative_to(dist))
    print(output)


if __name__ == "__main__":
    main()
