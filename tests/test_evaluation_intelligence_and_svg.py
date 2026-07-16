import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib
from fastapi.testclient import TestClient

matplotlib.use("Agg", force=True)

from app import app
from src.api.routes.evaluation import _build_smart_assessment, _list_vector_plot_exports
from src.training.vector_plot_capture import capture_vector_plots


class EvaluationIntelligenceAndSvgTests(unittest.TestCase):
    def test_assessment_uses_metrics_training_config_and_dataset_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run_eval"
            run_dir.mkdir()
            run_dir.joinpath("train_config.json").write_text(
                json.dumps({"model": "yolov8n-seg.pt", "epochs": 30, "imgsz": 320, "batch_size": 4, "patience": 10, "device": "gpu"}),
                encoding="utf-8",
            )
            run_dir.joinpath("run_summary.json").write_text(json.dumps({"best_epoch": 3}), encoding="utf-8")
            project = {
                "task_type": "semantic_segmentation",
                "class_names": ["a", "b", "c", "d", "e", "f"],
                "annotation_progress": {"total": 120},
            }
            results = {
                "epochs_completed": 25,
                "metrics": {"map50": 0.9, "map50_95": 0.55, "precision": 0.45, "recall": 0.9, "f1": 0.6},
                "raw": {"val/seg_loss": [0.8, 0.6, 0.5, 0.55, 0.7]},
            }

            assessment = _build_smart_assessment(project, run_dir, results)

            codes = {item["code"] for item in assessment["signals"]}
            self.assertIn("moderate_f1", codes)
            self.assertIn("precision_below_recall", codes)
            self.assertIn("localization_gap", codes)
            self.assertIn("early_best_epoch", codes)
            self.assertEqual(assessment["context"]["model"], "yolov8n-seg.pt")
            self.assertEqual(assessment["context"]["total_images"], 120)

    def test_matplotlib_capture_writes_a_true_svg_sibling(self):
        import matplotlib.pyplot as plt

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            png_path = root / "curve.png"
            with capture_vector_plots(root):
                figure, axes = plt.subplots()
                axes.plot([1, 2, 3], [0.2, 0.5, 0.9])
                figure.savefig(png_path)
                plt.close(figure)

            svg_path = root / "curve.svg"
            self.assertTrue(png_path.is_file())
            self.assertTrue(svg_path.is_file())
            svg = svg_path.read_text(encoding="utf-8")
            self.assertIn("<svg", svg)
            self.assertNotIn("data:image/png", svg)

    def test_vector_export_mapping_and_svg_download(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            run_dir = root / "training" / "runs" / "run_done"
            run_dir.mkdir(parents=True)
            run_dir.joinpath("metrics.json").write_text("{}", encoding="utf-8")
            run_dir.joinpath("results.png").write_bytes(b"png")
            run_dir.joinpath("results.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")
            self.assertEqual(_list_vector_plot_exports(run_dir, ["results.png"]), {"results.png": "results.svg"})

            project = {
                "project_id": "proj_eval",
                "dataset_path": str(root / "dataset"),
                "layout": {"mode": "v3"},
                "training_runs": [{"run_id": "run_done", "status": "completed", "completed_at": "2026-07-02T10:00:00"}],
            }
            with patch("src.api.routes.evaluation.ProjectManager.get_project", return_value=project):
                response = TestClient(app).get("/api/projects/proj_eval/evaluation/plot/results.svg?run_id=run_done")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "image/svg+xml")
            self.assertIn('filename="results.svg"', response.headers.get("content-disposition", ""))
            self.assertIn(b"<svg", response.content)

    def test_evaluation_ui_replaces_static_checklist_and_prefers_svg(self):
        root = Path(__file__).resolve().parents[1]
        html = root.joinpath("static", "index.html").read_text(encoding="utf-8")
        script = root.joinpath("static", "pages", "evaluation.js").read_text(encoding="utf-8")
        self.assertNotIn("CNN 評估檢查重點", html)
        self.assertIn('id="evaluation-recommendation-list"', html)
        self.assertIn("renderEvaluationAssessment(data.assessment)", script)
        self.assertIn("data.plot_exports || {}", script)
        self.assertIn('vectorFilename ? "SVG"', script)


if __name__ == "__main__":
    unittest.main()
