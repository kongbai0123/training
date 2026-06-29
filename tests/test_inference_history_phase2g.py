import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from src.config import PROJECTS_DIR
from src.inference_history import InferenceHistory


class InferenceHistoryPhase2GTests(unittest.TestCase):
    def setUp(self):
        self.project_id = f"proj_inference_history_{uuid4().hex[:8]}"
        self.project_root = PROJECTS_DIR / self.project_id
        if self.project_root.exists():
            shutil.rmtree(self.project_root, ignore_errors=True)
        self.jobs_dir = self.project_root / "inference" / "jobs"
        self.jobs_dir.mkdir(parents=True)
        self.project = {
            "project_id": self.project_id,
            "project_name": "history test",
            "dataset_path": (self.project_root / "dataset").as_posix(),
        }

    def tearDown(self):
        if self.project_root.exists():
            shutil.rmtree(self.project_root, ignore_errors=True)

    def test_list_jobs_classifies_rnn_sequence_and_cnn_image_jobs(self):
        self._write_job(
            "seq_job_20260629_010101_abcdef",
            {
                "project_id": self.project_id,
                "job_id": "seq_job_20260629_010101_abcdef",
                "architecture": "rnn",
                "backend": "pytorch_lstm",
                "model_id": "model-rnn",
                "sequence_count": 2,
                "predicted_labels": ["normal"],
                "inference_time_ms": 12.3,
                "created_at": "2026-06-29T01:01:01",
            },
        )
        self._write_job(
            "job_20260629_010000_123456",
            {
                "project_id": self.project_id,
                "job_id": "job_20260629_010000_123456",
                "model_id": "model-cnn",
                "prediction_count": 1,
                "detected_classes": ["road"],
                "inference_time_ms": 8.4,
                "created_at": "2026-06-29T01:00:00",
            },
        )

        jobs = InferenceHistory.list_jobs(self.project)["jobs"]
        by_id = {job["job_id"]: job for job in jobs}

        self.assertEqual(by_id["seq_job_20260629_010101_abcdef"]["mode"], "rnn")
        self.assertEqual(by_id["seq_job_20260629_010101_abcdef"]["kind"], "sequence")
        self.assertEqual(by_id["job_20260629_010000_123456"]["mode"], "cnn")
        self.assertEqual(by_id["job_20260629_010000_123456"]["kind"], "image")
        self.assertEqual(jobs[0]["job_id"], "seq_job_20260629_010101_abcdef")

    def test_get_job_returns_prediction_rows_and_file_links(self):
        job_id = "seq_job_20260629_010101_abcdef"
        self._write_job(
            job_id,
            {
                "project_id": self.project_id,
                "job_id": job_id,
                "architecture": "rnn",
                "backend": "pytorch_lstm",
                "model_id": "model-rnn",
                "sequence_count": 1,
                "created_at": "2026-06-29T01:01:01",
            },
            predictions=[{"sequence_id": "seq_1", "prediction": "normal", "confidence": 0.9}],
        )

        detail = InferenceHistory.get_job(self.project, job_id)

        self.assertEqual(detail["mode"], "rnn")
        self.assertEqual(detail["predictions"][0]["sequence_id"], "seq_1")
        urls = {file["name"]: file["url"] for file in detail["files"]}
        self.assertIn("prediction.json", urls)
        self.assertIn(f"/api/projects/{self.project_id}/inference/jobs/{job_id}/files/prediction.json", urls["prediction.json"])

    def test_get_job_rejects_missing_job(self):
        with self.assertRaises(FileNotFoundError):
            InferenceHistory.get_job(self.project, "missing_job")

    def _write_job(self, job_id: str, summary: dict, predictions=None):
        job_dir = self.jobs_dir / job_id
        job_dir.mkdir(parents=True)
        (job_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        (job_dir / "config.json").write_text(json.dumps({"model_id": summary.get("model_id")}), encoding="utf-8")
        (job_dir / "prediction.json").write_text(json.dumps({"predictions": predictions or []}), encoding="utf-8")
        (job_dir / "predictions.csv").write_text("sequence_id,prediction\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
