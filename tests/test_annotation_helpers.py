import json
import tempfile
import unittest
from pathlib import Path

from src.annotation_helpers import (
    build_labelme_annotation_payload,
    normalize_labelme_image_paths,
    should_auto_convert_yolo_to_labelme,
    update_project_image_annotation_state,
)


class AnnotationHelpersTests(unittest.TestCase):
    def test_should_auto_convert_yolo_to_labelme_for_detection_and_segmentation(self):
        self.assertTrue(should_auto_convert_yolo_to_labelme({"task_type": "object_detection"}))
        self.assertTrue(should_auto_convert_yolo_to_labelme({"task_type": "semantic_segmentation"}))
        self.assertFalse(should_auto_convert_yolo_to_labelme({"task_type": "classification"}))

    def test_build_labelme_payload_converts_normalized_bbox_to_rectangle(self):
        payload, shapes = build_labelme_annotation_payload(
            "frame.jpg",
            [{"category": "defect", "type": "bbox", "bbox": [0.5, 0.5, 0.25, 0.5]}],
            200,
            100,
        )

        self.assertEqual(payload["imagePath"], "frame.jpg")
        self.assertEqual(payload["imageWidth"], 200)
        self.assertEqual(payload["imageHeight"], 100)
        self.assertEqual(shapes[0]["label"], "defect")
        self.assertEqual(shapes[0]["shape_type"], "rectangle")
        self.assertEqual(shapes[0]["points"], [[75.0, 25.0], [125.0, 75.0]])

    def test_update_project_image_annotation_state_updates_progress_and_normalized_bbox(self):
        project = {
            "images": [
                {"filename": "frame.jpg", "status": "pending"},
                {"filename": "other.jpg", "status": "skipped"},
            ]
        }
        shapes = [
            {
                "label": "defect",
                "shape_type": "rectangle",
                "points": [[75.0, 25.0], [125.0, 75.0]],
            }
        ]

        progress = update_project_image_annotation_state(
            project,
            "frame.jpg",
            "annotated",
            "line_a",
            "video_01.mp4",
            200,
            100,
            shapes,
        )

        self.assertEqual(progress, {"total": 2, "annotated": 1, "flagged": 0, "skipped": 1})
        image = project["images"][0]
        self.assertEqual(image["scene"], "line_a")
        self.assertEqual(image["source_video"], "video_01.mp4")
        self.assertEqual(image["annotations"][0]["bbox"], [0.5, 0.5, 0.25, 0.5])

    def test_normalize_labelme_image_paths_updates_existing_image_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images_dir = root / "images"
            labelme_dir = root / "labelme"
            images_dir.mkdir()
            labelme_dir.mkdir()
            (images_dir / "frame.jpg").write_bytes(b"image")
            json_path = labelme_dir / "frame.json"
            json_path.write_text(json.dumps({"imagePath": "../old/frame.jpg", "imageData": "inline"}), encoding="utf-8")

            normalized = normalize_labelme_image_paths(images_dir, labelme_dir)

            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(normalized, 1)
            self.assertEqual(data["imagePath"], (images_dir / "frame.jpg").resolve().as_posix())
            self.assertIsNone(data["imageData"])


if __name__ == "__main__":
    unittest.main()
