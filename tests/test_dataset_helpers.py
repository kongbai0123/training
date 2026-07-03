import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from src.dataset_helpers import (
    add_project_images,
    new_image_metadata,
    import_zip_upload,
    process_image_upload_batch,
    process_mixed_dataset_files_upload,
    resolve_project_image_path,
    run_dataset_quality_check,
)
from src.project_layout import ProjectLayout


class _Upload:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.file = BytesIO(content)


class DatasetHelpersTests(unittest.TestCase):
    def test_new_image_metadata_uses_portable_defaults(self):
        metadata = new_image_metadata("frame.jpg", source_video="line.mp4", sha256="abc")

        self.assertEqual(metadata["filename"], "frame.jpg")
        self.assertEqual(metadata["status"], "unannotated")
        self.assertEqual(metadata["source_video"], "line.mp4")
        self.assertEqual(metadata["sha256"], "abc")
        self.assertEqual(metadata["annotations"], [])
        self.assertEqual(metadata["quality"], {})

    def test_add_project_images_skips_existing_and_updates_total(self):
        project = {
            "images": [new_image_metadata("existing.jpg")],
            "annotation_progress": {"total": 1},
        }

        added = add_project_images(project, [("existing.jpg", "old"), ("new.jpg", "new")])

        self.assertEqual(added, ["new.jpg"])
        self.assertEqual([image["filename"] for image in project["images"]], ["existing.jpg", "new.jpg"])
        self.assertEqual(project["annotation_progress"]["total"], 2)

    def test_resolve_project_image_path_rejects_path_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = ProjectLayout(Path(tmp))
            project = {"images": []}

            self.assertIsNone(resolve_project_image_path(layout, project, "../outside.jpg"))
            self.assertIsNone(resolve_project_image_path(layout, project, "nested/image.jpg"))

    def test_resolve_project_image_path_prefers_raw_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = ProjectLayout(Path(tmp))
            image_dir = layout.resolve_raw_images_dir().path
            image_dir.mkdir(parents=True, exist_ok=True)
            image_path = image_dir / "frame.jpg"
            image_path.write_bytes(b"image")

            resolved = resolve_project_image_path(layout, {"images": []}, "frame.jpg")

            self.assertEqual(resolved, image_path)

    def test_process_image_upload_batch_uploads_renames_and_skips_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_dir = Path(tmp) / "images"
            image_dir.mkdir()
            existing_path = image_dir / "existing.jpg"
            existing_path.write_bytes(b"same")
            project = {
                "images": [new_image_metadata("existing.jpg")],
                "annotation_progress": {"total": 1},
            }

            result = process_image_upload_batch(
                project,
                image_dir,
                [
                    _Upload("existing.jpg", b"same"),
                    _Upload("existing.jpg", b"different"),
                    _Upload("copy.jpg", b"different"),
                    _Upload("notes.txt", b"not-image"),
                ],
                batch_id="batch_fixed",
            )

            self.assertEqual(result["batch_id"], "batch_fixed")
            self.assertEqual(result["uploaded_count"], 1)
            self.assertEqual(result["duplicate_same_hash"], 2)
            self.assertEqual(result["renamed_same_name_diff_hash"], 1)
            self.assertEqual(result["invalid_count"], 1)
            self.assertEqual(result["skipped_count"], 2)
            self.assertEqual(project["annotation_progress"]["total"], 2)
            self.assertEqual(project["imports_history"][0]["type"], "images_upload")
            stored_names = [image["filename"] for image in project["images"]]
            self.assertEqual(stored_names[0], "existing.jpg")
            self.assertTrue(stored_names[1].startswith("existing__"))
            self.assertTrue((image_dir / stored_names[1]).exists())

    def test_run_dataset_quality_check_marks_near_duplicates_and_writes_health_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = ProjectLayout(Path(tmp))
            image_dir = layout.resolve_raw_images_dir().path
            image_dir.mkdir(parents=True, exist_ok=True)
            (image_dir / "a.jpg").write_bytes(b"a")
            (image_dir / "b.jpg").write_bytes(b"b")
            project = {
                "images": [
                    new_image_metadata("a.jpg"),
                    new_image_metadata("b.jpg"),
                    new_image_metadata("missing.jpg"),
                ]
            }

            with patch("src.dataset_helpers.DatasetUtils.analyze_image_quality", return_value={"status": "green", "warnings": []}), patch(
                "src.dataset_helpers.DatasetUtils.dhash", side_effect=["aaaa", "aaab"]
            ), patch("src.dataset_helpers.DatasetUtils.hamming_distance", return_value=1), patch(
                "src.dataset_helpers.DatasetUtils.get_dataset_health", return_value={"score": 80, "warnings": [], "summary": {}}
            ):
                health = run_dataset_quality_check(project, layout)

            self.assertEqual(health["score"], 80)
            self.assertEqual(project["dataset_health"], health)
            self.assertTrue(project["images"][0]["quality"]["is_duplicate"])
            self.assertEqual(project["images"][0]["quality"]["status"], "yellow")
            self.assertIn("Possible duplicate image", project["images"][0]["quality"]["warnings"])
            self.assertEqual(project["images"][2]["quality"], {})

    def test_process_mixed_dataset_files_upload_routes_files_and_updates_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = ProjectLayout(Path(tmp))
            project = {"images": [], "annotation_progress": {"total": 0}}

            result = process_mixed_dataset_files_upload(
                project,
                layout,
                [
                    _Upload("frame.jpg", b"image"),
                    _Upload("frame.json", b"{}"),
                    _Upload("frame.txt", b"0 0.5 0.5 1 1"),
                    _Upload("ignore.csv", b"skip"),
                ],
            )

            self.assertEqual(result["imported_images"], 1)
            self.assertEqual(result["imported_jsons"], 1)
            self.assertEqual(result["imported_txts"], 1)
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(project["images"][0]["filename"], "frame.jpg")
            self.assertEqual(project["annotation_progress"]["total"], 1)
            self.assertTrue((layout.resolve_raw_images_dir().path / "frame.jpg").exists())
            self.assertTrue((layout.resolve_current_labelme_dir().path / "frame.json").exists())
            self.assertTrue((layout.resolve_current_yolo_labels_dir().path / "frame.txt").exists())

    def test_import_zip_upload_cleans_temp_folder_after_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = {"dataset_path": tmp}
            upload = _Upload("dataset.zip", b"zip-bytes")

            with patch("src.dataset_helpers.DatasetUtils.import_zip_package", return_value={"imported_images_count": 1}) as mocked:
                result = import_zip_upload("proj_zip", project, upload)

            self.assertEqual(result["imported_images_count"], 1)
            temp_dir = Path(tmp) / ".tmp_zip_upload"
            self.assertFalse(temp_dir.exists())
            self.assertEqual(mocked.call_args.args[0], "proj_zip")
            self.assertEqual(Path(mocked.call_args.args[1]).name, "upload.zip")


if __name__ == "__main__":
    unittest.main()
