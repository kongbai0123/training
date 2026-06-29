import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from src.config import PROJECTS_DIR
from src.training.output_compare_service import CNNOutputCompareService, OutputCompareServiceError


class CNNOutputComparePhase3CTests(unittest.TestCase):
    def setUp(self):
        self.project_id = f"proj_output_compare_{uuid4().hex[:8]}"
        self.project_root = PROJECTS_DIR / self.project_id
        if self.project_root.exists():
            shutil.rmtree(self.project_root, ignore_errors=True)
        (self.project_root / "dataset").mkdir(parents=True)
        self.project = {
            "project_id": self.project_id,
            "project_name": "output compare",
            "task_type": "semantic_segmentation",
            "dataset_path": (self.project_root / "dataset").as_posix(),
        }
        self.input_image = self.project_root / "dataset" / "sample.jpg"
        self.input_image.write_bytes(b"fake-image")
        self._write_run_weight("run_a")
        self._write_run_weight("run_b")

    def tearDown(self):
        if self.project_root.exists():
            shutil.rmtree(self.project_root, ignore_errors=True)

    def _write_run_weight(self, run_id: str):
        run_dir = self.project_root / "training" / "runs" / run_id
        weights = run_dir / "weights"
        weights.mkdir(parents=True, exist_ok=True)
        (weights / "best.pt").write_bytes(b"fake-weights")
        (run_dir / "train_config.json").write_text('{"model":"yolov8n-seg.pt"}', encoding="utf-8")

    def test_compare_image_outputs_runs_existing_inference_engine_for_each_model(self):
        def fake_inference(project, model, input_path, settings):
            run_id = model["run_id"]
            return {
                "job_id": f"job_{run_id}",
                "summary": {
                    "run_id": run_id,
                    "prediction_count": 1,
                    "detected_classes": [run_id],
                    "inference_time_ms": 12.5,
                    "mask_area_ratio": 0.2,
                },
                "predictions": [{"class_name": run_id, "confidence": 0.9}],
                "urls": {"annotated_image": f"/fake/{run_id}.jpg"},
                "paths": {"annotated_image": f"/fake/{run_id}.jpg"},
            }

        with patch("src.training.output_compare_service.InferenceEngine.run_image_inference", side_effect=fake_inference) as mocked:
            payload = CNNOutputCompareService.compare_image_outputs(
                project=self.project,
                run_ids=["run_a", "run_b"],
                input_path=self.input_image,
                settings={"device": "cpu"},
            )

        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(payload["architecture"], "cnn")
        self.assertEqual(payload["kind"], "image_output")
        self.assertEqual([item["run_id"] for item in payload["outputs"]], ["run_a", "run_b"])
        self.assertEqual(payload["summary"]["prediction_count_by_run"]["run_a"], 1)
        self.assertIn("run_b", payload["summary"]["all_detected_classes"])

    def test_requires_two_to_four_runs(self):
        with self.assertRaises(OutputCompareServiceError):
            CNNOutputCompareService.compare_image_outputs(self.project, ["run_a"], self.input_image, {})
        with self.assertRaises(OutputCompareServiceError):
            CNNOutputCompareService.compare_image_outputs(self.project, ["a", "b", "c", "d", "e"], self.input_image, {})

    def test_rejects_missing_model_weight_for_selected_run(self):
        with self.assertRaisesRegex(OutputCompareServiceError, "No CNN model weights"):
            CNNOutputCompareService.compare_image_outputs(self.project, ["run_a", "missing"], self.input_image, {})


if __name__ == "__main__":
    unittest.main()
