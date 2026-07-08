import json
import shutil
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient

import app
from src.config import PROJECTS_DIR
from src.project_manager import ProjectManager


class AutoLabelingE2ETests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app.app)
        self.project = ProjectManager.create_project("auto label e2e", "object_detection", ["defect"])
        self.project_id = self.project["project_id"]
        self.project_root = PROJECTS_DIR / self.project_id

    def tearDown(self):
        if self.project_root.exists():
            shutil.rmtree(self.project_root, ignore_errors=True)

    def test_upload_image_then_auto_label_job_writes_labelme_draft_without_touching_current(self):
        image_bytes = self._png_bytes()
        upload_response = self.client.post(
            f"/api/projects/{self.project_id}/upload-images",
            files=[("files", ("sample.png", image_bytes, "image/png"))],
        )
        self.assertEqual(upload_response.status_code, 200, upload_response.text)
        self.assertEqual(upload_response.json()["uploaded_count"], 1)

        model = {
            "model_id": "model-best",
            "run_id": "run_best",
            "weight_type": "best",
            "task_type": "object_detection",
            "internal_weight_path": (self.project_root / "training" / "runs" / "run_best" / "weights" / "best.pt").as_posix(),
        }

        def fake_inference(project, model, input_path, settings):
            preview_path = Path(input_path).with_name("sample_overlay.jpg")
            preview = np.zeros((64, 96, 3), dtype=np.uint8)
            preview[15:55, 10:50] = (0, 255, 0)
            cv2.imwrite(str(preview_path), preview)
            return {
                "job_id": "job_fake_inference",
                "summary": {"prediction_count": 1, "average_confidence": 0.91, "classes": ["defect"]},
                "predictions": [
                    {
                        "class_id": 0,
                        "class_name": "defect",
                        "confidence": 0.91,
                        "bbox_xyxy": [10, 15, 50, 55],
                    }
                ],
                "paths": {"annotated_image": preview_path.as_posix()},
            }

        with patch("src.auto_labeling_service.ModelRegistry.resolve_model", return_value=model), \
             patch("src.auto_labeling_service.InferenceEngine.run_image_inference", side_effect=fake_inference) as mocked:
            job_response = self.client.post(
                f"/api/projects/{self.project_id}/auto-labeling/jobs",
                json={"model_id": "model-best", "source": "unlabeled", "job_id": "al_e2e", "max_images": 5},
            )

        self.assertEqual(job_response.status_code, 200, job_response.text)
        self.assertEqual(mocked.call_count, 1)
        payload = job_response.json()
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(payload["processed_count"], 1)
        self.assertEqual(payload["draft_count"], 1)
        self.assertEqual(payload["items"][0]["filename"], "sample.png")
        self.assertTrue(payload["items"][0]["draft_labelme_url"].endswith("/drafts/labelme/sample.json"))
        self.assertTrue(payload["items"][0]["preview_url"].endswith("/previews/sample.jpg"))

        draft_json = self.project_root / "annotations" / "drafts" / "auto_label" / "al_e2e" / "labelme" / "sample.json"
        current_json = self.project_root / "annotations" / "current" / "labelme" / "sample.json"
        self.assertTrue(draft_json.exists())
        self.assertFalse(current_json.exists())

        data = json.loads(draft_json.read_text(encoding="utf-8"))
        self.assertEqual(data["imagePath"], "sample.png")
        self.assertEqual(data["imageWidth"], 96)
        self.assertEqual(data["imageHeight"], 64)
        self.assertTrue(data["flags"]["auto_label"])
        self.assertEqual(data["flags"]["inference_job_id"], "job_fake_inference")
        self.assertEqual(data["shapes"][0]["label"], "defect")
        self.assertEqual(data["shapes"][0]["shape_type"], "rectangle")
        self.assertEqual(data["shapes"][0]["points"], [[10.0, 15.0], [50.0, 55.0]])

        summary_response = self.client.get(f"/api/projects/{self.project_id}/auto-labeling/jobs/al_e2e")
        self.assertEqual(summary_response.status_code, 200, summary_response.text)
        self.assertEqual(summary_response.json()["items"][0]["filename"], "sample.png")

        labelme_response = self.client.get(payload["items"][0]["draft_labelme_url"])
        self.assertEqual(labelme_response.status_code, 200, labelme_response.text)
        self.assertEqual(labelme_response.json()["shapes"][0]["label"], "defect")

        preview_response = self.client.get(payload["items"][0]["preview_url"])
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        self.assertGreater(len(preview_response.content), 0)

        review_response = self.client.post(
            f"/api/projects/{self.project_id}/auto-labeling/jobs/al_e2e/review",
            json={"filename": "sample.png", "action": "accept"},
        )
        self.assertEqual(review_response.status_code, 200, review_response.text)
        review_payload = review_response.json()
        self.assertEqual(review_payload["review_status"], "accepted")
        self.assertEqual(review_payload["copied"], ["labelme/sample.json"])
        self.assertTrue(current_json.exists())

        current_data = json.loads(current_json.read_text(encoding="utf-8"))
        self.assertFalse(current_data["flags"]["requires_review"])
        self.assertEqual(current_data["flags"]["auto_label_review_status"], "accepted")
        updated_project = ProjectManager.get_project(self.project_id)
        self.assertEqual(updated_project["annotation_progress"]["annotated"], 1)
        self.assertEqual(updated_project["images"][0]["status"], "annotated")

        summary_after_review = self.client.get(f"/api/projects/{self.project_id}/auto-labeling/jobs/al_e2e").json()
        self.assertEqual(summary_after_review["items"][0]["review_status"], "accepted")
        self.assertEqual(summary_after_review["accepted_count"], 1)

    def test_auto_label_job_prefers_segmentation_polygon_points_for_labelme_draft(self):
        image_bytes = self._png_bytes()
        upload_response = self.client.post(
            f"/api/projects/{self.project_id}/upload-images",
            files=[("files", ("seg.png", image_bytes, "image/png"))],
        )
        self.assertEqual(upload_response.status_code, 200, upload_response.text)

        model = {
            "model_id": "model-seg",
            "run_id": "run_seg",
            "weight_type": "best",
            "task_type": "semantic_segmentation",
            "internal_weight_path": (self.project_root / "training" / "runs" / "run_seg" / "weights" / "best.pt").as_posix(),
        }

        def fake_segmentation_inference(project, model, input_path, settings):
            return {
                "job_id": "job_fake_segmentation",
                "summary": {"prediction_count": 1, "average_confidence": 0.93},
                "predictions": [
                    {
                        "class_id": 0,
                        "class_name": "defect",
                        "confidence": 0.93,
                        "bbox_xyxy": [10, 15, 50, 55],
                        "polygon_points": [[10, 15], [50, 15], [50, 55], [10, 55]],
                    }
                ],
                "paths": {},
            }

        with patch("src.auto_labeling_service.ModelRegistry.resolve_model", return_value=model), \
             patch("src.auto_labeling_service.InferenceEngine.run_image_inference", side_effect=fake_segmentation_inference):
            job_response = self.client.post(
                f"/api/projects/{self.project_id}/auto-labeling/jobs",
                json={"model_id": "model-seg", "source": "unlabeled", "job_id": "al_seg_e2e", "max_images": 5},
            )

        self.assertEqual(job_response.status_code, 200, job_response.text)
        draft_json = self.project_root / "annotations" / "drafts" / "auto_label" / "al_seg_e2e" / "labelme" / "seg.json"
        data = json.loads(draft_json.read_text(encoding="utf-8"))

        self.assertEqual(data["shapes"][0]["label"], "defect")
        self.assertEqual(data["shapes"][0]["shape_type"], "polygon")
        self.assertEqual(data["shapes"][0]["points"], [[10.0, 15.0], [50.0, 15.0], [50.0, 55.0], [10.0, 55.0]])

        review_response = self.client.post(
            f"/api/projects/{self.project_id}/auto-labeling/jobs/al_seg_e2e/review",
            json={"filename": "seg.png", "action": "reject"},
        )
        self.assertEqual(review_response.status_code, 200, review_response.text)
        self.assertEqual(review_response.json()["review_status"], "rejected")
        self.assertFalse((self.project_root / "annotations" / "current" / "labelme" / "seg.json").exists())

        updated_project = ProjectManager.get_project(self.project_id)
        self.assertEqual(updated_project["annotation_progress"]["flagged"], 1)
        self.assertEqual(updated_project["images"][0]["status"], "flagged")

    def test_auto_label_job_without_eligible_images_does_not_leave_empty_draft_job(self):
        model = {
            "model_id": "model-best",
            "run_id": "run_best",
            "weight_type": "best",
            "task_type": "object_detection",
            "internal_weight_path": (self.project_root / "training" / "runs" / "run_best" / "weights" / "best.pt").as_posix(),
        }

        with patch("src.auto_labeling_service.ModelRegistry.resolve_model", return_value=model):
            job_response = self.client.post(
                f"/api/projects/{self.project_id}/auto-labeling/jobs",
                json={"model_id": "model-best", "source": "unlabeled", "job_id": "al_empty", "max_images": 5},
            )

        self.assertEqual(job_response.status_code, 400, job_response.text)
        self.assertFalse((self.project_root / "auto_labeling" / "jobs" / "al_empty").exists())

        status_response = self.client.get(f"/api/projects/{self.project_id}/auto-labeling/status")
        self.assertEqual(status_response.status_code, 200, status_response.text)
        job_ids = [job["job_id"] for job in status_response.json()["jobs"]]
        self.assertNotIn("al_empty", job_ids)

    @staticmethod
    def _png_bytes() -> BytesIO:
        image = np.zeros((64, 96, 3), dtype=np.uint8)
        image[15:55, 10:50] = (255, 255, 255)
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise RuntimeError("Failed to encode test PNG")
        return BytesIO(encoded.tobytes())


if __name__ == "__main__":
    unittest.main()
