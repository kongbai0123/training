import json
import tempfile
import unittest
from pathlib import Path

from src.training.compare_service import CompareService, CompareServiceError
from src.training.metric_schema import build_yolo_metric_schema


YOLO_SEG_METRICS = {
    "metrics/mAP50-95(M)": [0.10, 0.30, 0.42],
    "metrics/mAP50(M)": [0.20, 0.44, 0.61],
    "metrics/precision(M)": [0.40, 0.55, 0.67],
    "metrics/recall(M)": [0.33, 0.51, 0.63],
    "train/box_loss": [1.30, 0.90, 0.70],
    "train/seg_loss": [1.40, 1.00, 0.80],
    "val/box_loss": [1.50, 1.10, 0.90],
    "val/seg_loss": [1.60, 1.20, 1.00],
}

YOLO_DET_METRICS = {
    "metrics/mAP50-95(B)": [0.11, 0.22],
    "metrics/mAP50(B)": [0.30, 0.41],
    "metrics/precision(B)": [0.50, 0.58],
    "metrics/recall(B)": [0.44, 0.52],
    "train/box_loss": [1.20, 0.80],
    "val/box_loss": [1.30, 0.90],
}


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def make_project(root: Path, task_type: str = "semantic_segmentation"):
    project_dir = root / "proj_compare"
    dataset_dir = project_dir / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    return {
        "project_id": "proj_compare",
        "project_name": "Compare",
        "task_type": task_type,
        "dataset_path": dataset_dir.as_posix(),
    }


def write_yolo_run(
    project,
    run_id,
    *,
    status="completed",
    task_type="semantic_segmentation",
    model="yolov8n-seg.pt",
    metrics=None,
    with_backend=True,
    with_schema=True,
):
    project_dir = Path(project["dataset_path"]).parent
    run_dir = project_dir / "training" / "runs" / run_id
    metrics = metrics or YOLO_SEG_METRICS
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "weights").mkdir(parents=True, exist_ok=True)
    (run_dir / "weights" / "best.pt").write_bytes(b"fake-weights")

    write_json(
        run_dir / "metrics.json",
        {
            "epochs": list(range(1, len(next(iter(metrics.values()))) + 1)),
            "raw": metrics,
            "smooth": {},
        },
    )
    write_json(
        run_dir / "run_summary.json",
        {
            "run_id": run_id,
            "status": status,
            "task_type": task_type,
            "best_epoch": 2,
            "best_metrics": {key: values[-1] for key, values in metrics.items()},
            "platform_score": metrics.get("metrics/mAP50-95(M)", [0.0])[-1],
            "completed_at": "2026-06-29T10:00:00",
        },
    )
    write_json(
        run_dir / "train_config.json",
        {
            "model": model,
            "epochs": len(next(iter(metrics.values()))),
            "batch_size": 2,
            "imgsz": 320,
            "lr0": 0.01,
        },
    )
    if with_backend:
        write_json(
            run_dir / "backend.json",
            {
                "contract_version": "1.0",
                "run_id": run_id,
                "architecture": "cnn",
                "backend": "ultralytics_yolo",
                "task_type": task_type,
                "status": status,
                "created_at": "2026-06-29T09:00:00",
                "completed_at": "2026-06-29T10:00:00",
                "generated_at": "2026-06-29T10:00:01",
            },
        )
    if with_schema:
        schema_task = "detection" if "(B)" in next(iter(metrics.keys())) else "segmentation"
        write_json(run_dir / "metric_schema.json", build_yolo_metric_schema(schema_task))
    return run_dir


def write_legacy_results_only_run(project, run_id):
    project_dir = Path(project["dataset_path"]).parent
    run_dir = project_dir / "training" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.csv").write_text(
        "epoch,metrics/mAP50-95(M),metrics/mAP50(M),metrics/precision(M),metrics/recall(M),train/box_loss,train/seg_loss,val/box_loss,val/seg_loss\n"
        "1,0.1,0.2,0.3,0.4,1.2,1.3,1.4,1.5\n"
        "2,0.2,0.3,0.4,0.5,1.0,1.1,1.2,1.3\n",
        encoding="utf-8",
    )
    return run_dir


class CompareServicePhase3ATest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = make_project(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_completed_cnn_runs_ignores_failed(self):
        write_yolo_run(self.project, "run_a")
        write_yolo_run(self.project, "run_failed", status="failed")

        payload = CompareService.list_comparable_runs(self.project, "cnn")

        self.assertEqual([run["run_id"] for run in payload["runs"]], ["run_a"])
        self.assertEqual(payload["runs"][0]["primary_metric"]["key"], "metrics/mAP50-95(M)")

    def test_list_completed_cnn_runs_ignores_orphan_dirs_when_project_has_run_records(self):
        write_yolo_run(self.project, "run_registered")
        write_yolo_run(self.project, "run_orphan")
        self.project["training_runs"] = [{"run_id": "run_registered", "status": "completed"}]

        payload = CompareService.list_comparable_runs(self.project, "cnn")

        self.assertEqual([run["run_id"] for run in payload["runs"]], ["run_registered"])

    def test_list_completed_cnn_runs_excludes_smoke_probe_test_runs(self):
        write_yolo_run(self.project, "run_real")
        write_yolo_run(self.project, "run_smoke_001")
        write_yolo_run(self.project, "run_probe_001")
        write_yolo_run(self.project, "run_workers0_test")
        self.project["training_runs"] = [
            {"run_id": "run_real", "status": "completed"},
            {"run_id": "run_smoke_001", "status": "completed"},
            {"run_id": "run_probe_001", "status": "completed"},
            {"run_id": "run_workers0_test", "status": "completed"},
        ]

        payload = CompareService.list_comparable_runs(self.project, "cnn")

        self.assertEqual([run["run_id"] for run in payload["runs"]], ["run_real"])

    def test_compare_rejects_orphan_run_when_project_has_run_records(self):
        write_yolo_run(self.project, "run_registered")
        write_yolo_run(self.project, "run_orphan")
        self.project["training_runs"] = [{"run_id": "run_registered", "status": "completed"}]

        with self.assertRaises(CompareServiceError):
            CompareService.compare_runs(self.project, "cnn", ["run_registered", "run_orphan"])

    def test_compare_two_completed_segmentation_runs(self):
        write_yolo_run(self.project, "run_a")
        write_yolo_run(self.project, "run_b")

        payload = CompareService.compare_runs(self.project, "cnn", ["run_a", "run_b"], "run_a")

        self.assertEqual(payload["architecture"], "cnn")
        self.assertEqual(payload["task_family"], "segmentation")
        self.assertEqual(payload["baseline_run_id"], "run_a")
        self.assertIn("selected_runs", payload)
        self.assertIn("metric_groups", payload)
        self.assertIn("series", payload)
        self.assertIn("summary", payload)
        self.assertIn("recommendation", payload)
        self.assertIn("run_a", payload["series"]["metrics/mAP50-95(M)"]["runs"])

    def test_rejects_too_few_and_too_many_runs(self):
        with self.assertRaises(CompareServiceError):
            CompareService.compare_runs(self.project, "cnn", ["run_a"])
        with self.assertRaises(CompareServiceError):
            CompareService.compare_runs(self.project, "cnn", ["run_a", "run_b", "run_c", "run_d", "run_e"])

    def test_rejects_mixed_architecture(self):
        write_yolo_run(self.project, "run_a")
        run_dir = write_yolo_run(self.project, "run_rnn")
        write_json(
            run_dir / "backend.json",
            {
                "run_id": "run_rnn",
                "architecture": "rnn",
                "backend": "pytorch_lstm",
                "task_type": "sequence_regression",
                "status": "completed",
            },
        )

        with self.assertRaises(CompareServiceError):
            CompareService.compare_runs(self.project, "cnn", ["run_a", "run_rnn"])

    def test_rejects_incompatible_task_family(self):
        write_yolo_run(self.project, "run_seg")
        write_yolo_run(
            self.project,
            "run_det",
            task_type="object_detection",
            model="yolov8n.pt",
            metrics=YOLO_DET_METRICS,
        )

        with self.assertRaises(CompareServiceError):
            CompareService.compare_runs(self.project, "cnn", ["run_seg", "run_det"])

    def test_legacy_run_without_contract_files_still_compares(self):
        write_yolo_run(self.project, "run_legacy_a", with_backend=False, with_schema=False)
        write_yolo_run(self.project, "run_legacy_b", with_backend=False, with_schema=False)

        payload = CompareService.compare_runs(self.project, "cnn", ["run_legacy_a", "run_legacy_b"])

        self.assertEqual(payload["task_family"], "segmentation")
        self.assertEqual(payload["selected_runs"][0]["architecture"], "cnn")
        self.assertIn("metrics/mAP50-95(M)", payload["series"])

    def test_results_csv_only_legacy_run_is_listed_as_completed(self):
        write_legacy_results_only_run(self.project, "train")

        payload = CompareService.list_comparable_runs(self.project, "cnn")

        self.assertEqual([run["run_id"] for run in payload["runs"]], ["train"])
        self.assertEqual(payload["runs"][0]["status"], "completed")
        self.assertEqual(payload["runs"][0]["primary_metric"]["key"], "metrics/mAP50-95(M)")

    def test_missing_metric_adds_warning_instead_of_crashing(self):
        incomplete_metrics = {"metrics/mAP50(M)": [0.2, 0.3]}
        write_yolo_run(self.project, "run_a", metrics=incomplete_metrics, with_schema=True)
        write_yolo_run(self.project, "run_b", metrics=incomplete_metrics, with_schema=True)

        payload = CompareService.compare_runs(self.project, "cnn", ["run_a", "run_b"])

        self.assertTrue(any("missing" in warning.lower() for warning in payload["summary"]["warnings"]))


if __name__ == "__main__":
    unittest.main()
