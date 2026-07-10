from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import src.managed_labelme as managed_labelme
from src.labelme_adapter import LabelMeAdapter
from src.project_layout import ProjectLayout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_smoke(archive: Path, work_root: Path) -> dict[str, object]:
    archive = archive.resolve()
    work_root = work_root.resolve()
    if not archive.is_file():
        raise FileNotFoundError(f"LabelMe component archive not found: {archive}")
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    fake_home = work_root / "home"
    fake_home.mkdir()
    (fake_home / ".labelmerc").write_text("", encoding="utf-8")
    component_dir = work_root / "components" / "labelme"
    temp_dir = work_root / "installer-tmp"
    temp_dir.mkdir()

    original_component_dir = managed_labelme.LABELME_COMPONENT_DIR
    original_temp_dir = managed_labelme.TMP_DIR
    try:
        managed_labelme.LABELME_COMPONENT_DIR = component_dir
        managed_labelme.TMP_DIR = temp_dir
        install_status = managed_labelme.install_labelme_component_archive(archive)
    finally:
        managed_labelme.LABELME_COMPONENT_DIR = original_component_dir
        managed_labelme.TMP_DIR = original_temp_dir

    executable = Path(str(install_status["managed_executable"]))
    if not executable.is_file() or not install_status.get("offline_ready"):
        raise RuntimeError("Managed LabelMe archive did not install as an offline-ready component.")

    project_root = work_root / "project"
    project = {
        "project_id": "labelme_offline_smoke",
        "name": "LabelMe Offline Smoke",
        "dataset_path": str(project_root / "dataset"),
        "layout": {"mode": "v3", "version": "v3"},
        "layout_version": "v3",
        "architecture": "cnn",
        "task_type": "instance_segmentation",
        "class_names": ["smoke_object"],
        "images": [],
    }
    ProjectLayout(project_root, project).ensure_v3_tree()

    environment = os.environ.copy()
    environment.update({
        "HOME": str(fake_home),
        "USERPROFILE": str(fake_home),
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "127.0.0.1,localhost,::1",
    })
    completed = subprocess.run(
        [str(executable), "--component-smoke", str(project_root)],
        cwd=executable.parent,
        env=environment,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Managed LabelMe component smoke failed: "
            + (completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}")
        )

    label_path = project_root / "annotations" / "current" / "labelme" / "offline_sample.json"
    image_path = project_root / "dataset" / "images" / "raw" / "offline_sample.png"
    if not label_path.is_file() or not image_path.is_file():
        raise RuntimeError("Managed LabelMe did not persist the smoke image and JSON annotation.")
    label_payload = json.loads(label_path.read_text(encoding="utf-8"))
    if len(label_payload.get("shapes", [])) != 1:
        raise RuntimeError("Managed LabelMe JSON does not contain the expected shape.")

    sync_report = LabelMeAdapter.sync_labelme_annotations(project)
    if sync_report.get("annotated") != 1 or sync_report.get("unknown_classes"):
        raise RuntimeError(f"LabelMe project sync failed: {sync_report}")
    conversion = LabelMeAdapter.convert_labelme(project, "yolo_segmentation")
    yolo_path = project_root / "annotations" / "current" / "yolo" / "offline_sample.txt"
    if conversion.get("converted_count") != 1 or not yolo_path.is_file() or not yolo_path.read_text(encoding="utf-8").startswith("0 "):
        raise RuntimeError(f"LabelMe YOLO conversion failed: {conversion}")

    with zipfile.ZipFile(archive) as component_zip:
        if component_zip.testzip() is not None:
            raise RuntimeError("LabelMe component archive failed CRC validation.")

    return {
        "status": "pass",
        "archive": archive.as_posix(),
        "archive_sha256": _sha256(archive),
        "component_version": install_status.get("version"),
        "offline_ready": install_status.get("offline_ready"),
        "gui_initialized": True,
        "labelme_json_saved": True,
        "project_sync": sync_report,
        "yolo_segmentation": yolo_path.read_text(encoding="utf-8").strip(),
        "external_proxy": environment["HTTPS_PROXY"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the managed LabelMe component offline lifecycle.")
    parser.add_argument(
        "--archive",
        type=Path,
        default=Path("release_artifacts/components/labelme-runtime-windows-x64.zip"),
    )
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    if args.work_dir:
        work_root = args.work_dir
        cleanup = not args.keep
    else:
        work_root = Path(tempfile.mkdtemp(prefix="vts-labelme-smoke-"))
        cleanup = True
    try:
        result = run_smoke(args.archive, work_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        if cleanup and work_root.exists():
            shutil.rmtree(work_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
