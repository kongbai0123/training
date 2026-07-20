import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import app
from src.task_jobs import TaskJobManager


ROOT = Path(__file__).resolve().parents[1]


class TaskJobManagerTests(unittest.TestCase):
    def test_background_task_reports_phases_and_result(self):
        manager = TaskJobManager(max_jobs=20)

        def handler(reporter):
            reporter.update(
                phase="converting",
                message="Converting fixture",
                progress=45,
                indeterminate=False,
                current=1,
                total=2,
            )
            return {"artifact": "fixture.onnx"}

        created = manager.submit(kind="export", title="Fixture export", handler=handler)
        deadline = time.time() + 3
        status = created
        while time.time() < deadline:
            status = manager.get(created["job_id"])
            if status["status"] == "completed":
                break
            time.sleep(0.01)

        self.assertEqual(status["status"], "completed")
        self.assertEqual(status["phase"], "completed")
        self.assertEqual(status["progress"], 100.0)
        self.assertFalse(status["indeterminate"])
        self.assertEqual(status["result"], {"artifact": "fixture.onnx"})
        self.assertIn("converting", [item["phase"] for item in status["history"]])
        self.assertTrue(status["started_at"])
        self.assertTrue(status["completed_at"])

    def test_task_status_api_returns_shared_contract(self):
        from src.task_jobs import task_job_manager

        created = task_job_manager.submit(
            kind="load",
            title="API fixture",
            handler=lambda reporter: {"ok": True},
        )
        client = TestClient(app)
        deadline = time.time() + 3
        response = None
        while time.time() < deadline:
            response = client.get(f"/api/tasks/{created['job_id']}")
            if response.json().get("status") == "completed":
                break
            time.sleep(0.01)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for field in ("job_id", "kind", "title", "status", "phase", "message", "progress", "indeterminate", "result", "error"):
            self.assertIn(field, payload)
        self.assertEqual(payload["result"], {"ok": True})

    def test_task_websocket_delivers_terminal_result(self):
        from src.task_jobs import task_job_manager

        def handler(reporter):
            reporter.update(phase="validating", progress=25, indeterminate=False)
            return {"ok": "websocket"}

        created = task_job_manager.submit(kind="sync", title="WebSocket fixture", handler=handler)
        client = TestClient(app)
        terminal = None
        with client.websocket_connect(f"/api/tasks/{created['job_id']}/ws") as socket:
            for _ in range(10):
                payload = socket.receive_json()
                if payload.get("status") in {"completed", "failed", "cancelled"}:
                    terminal = payload
                    break
        self.assertIsNotNone(terminal)
        self.assertEqual(terminal["status"], "completed")
        self.assertEqual(terminal["result"], {"ok": "websocket"})


class UnifiedTaskProgressStaticTests(unittest.TestCase):
    def test_api_requests_use_delayed_shared_task_lifecycle(self):
        api = (ROOT / "static" / "api.js").read_text(encoding="utf-8")
        task = (ROOT / "static" / "core" / "task_progress.js").read_text(encoding="utf-8")
        bootstrap = (ROOT / "static" / "core" / "bootstrap.js").read_text(encoding="utf-8")

        self.assertIn("beginApiTask(url, options, method)", api)
        self.assertIn("const DEFAULT_DELAY_MS = 500", task)
        self.assertIn("task-progress-inline", task)
        self.assertIn("aria-busy", task)
        self.assertIn("initTaskProgressFramework();", bootstrap)

    def test_file_uploads_have_real_transport_progress(self):
        api = (ROOT / "static" / "api.js").read_text(encoding="utf-8")
        self.assertIn("export function apiUpload", api)
        self.assertIn('xhr.upload.addEventListener("progress"', api)
        self.assertIn("event.loaded * 100", api)
        self.assertIn('xhr.upload.addEventListener("load"', api)
        self.assertIn('tUpload("task.upload.processing"', api)

    def test_long_operations_use_job_status_and_websocket(self):
        routes = (ROOT / "src" / "api" / "routes" / "tasks.py").read_text(encoding="utf-8")
        task = (ROOT / "static" / "core" / "task_progress.js").read_text(encoding="utf-8")
        datasets = (ROOT / "src" / "api" / "routes" / "datasets.py").read_text(encoding="utf-8")
        annotations = (ROOT / "src" / "api" / "routes" / "annotation_labelme.py").read_text(encoding="utf-8")
        export = (ROOT / "src" / "api" / "routes" / "training_orchestration.py").read_text(encoding="utf-8")
        inference = (ROOT / "src" / "api" / "routes" / "inference.py").read_text(encoding="utf-8")
        auto_labeling = (ROOT / "src" / "api" / "routes" / "auto_labeling.py").read_text(encoding="utf-8")
        augmentation = (ROOT / "src" / "api" / "routes" / "augmentation.py").read_text(encoding="utf-8")
        split = (ROOT / "src" / "api" / "routes" / "dataset_split.py").read_text(encoding="utf-8")
        models = (ROOT / "src" / "api" / "routes" / "models.py").read_text(encoding="utf-8")
        assistant = (ROOT / "src" / "api" / "routes" / "project_assistant.py").read_text(encoding="utf-8")

        self.assertIn('@router.get("/api/tasks/{job_id}")', routes)
        self.assertIn('@router.websocket("/api/tasks/{job_id}/ws")', routes)
        self.assertIn("export function followServerTask", task)
        self.assertIn("/api/tasks/${encodeURIComponent(jobId)}/ws", task)
        self.assertIn('import-local/jobs', datasets)
        self.assertIn('import-video/jobs', datasets)
        self.assertIn('upload-video/jobs', datasets)
        self.assertIn('import-zip/jobs', datasets)
        self.assertIn('import-annotations/jobs', annotations)
        self.assertIn('labelme/sync/jobs', annotations)
        self.assertIn('quality-check/jobs', datasets)
        self.assertIn('export/jobs', export)
        self.assertIn('compare/output-image/jobs', export)
        self.assertIn('inference/image/jobs', inference)
        self.assertIn('inference/sequence/jobs', inference)
        self.assertIn('auto-labeling/tasks', auto_labeling)
        self.assertIn('apply-augmentation/jobs', augmentation)
        self.assertIn('split/jobs', split)
        self.assertIn('@router.websocket("/api/models/install/jobs/{job_id}/ws")', models)
        self.assertIn('sync-artifacts/jobs', assistant)

    def test_feature_pages_do_not_bypass_shared_api_transport(self):
        offenders = []
        allowed = {
            ROOT / "static" / "api.js",
            ROOT / "static" / "core" / "task_progress.js",
        }
        for path in (ROOT / "static").rglob("*.js"):
            if "vendor" in path.parts or path in allowed:
                continue
            if "fetch(" in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(offenders, [])

    def test_feature_pages_do_not_emit_ad_hoc_progress_events(self):
        offenders = []
        allowed = {ROOT / "static" / "pages" / "training.js"}
        for path in (ROOT / "static" / "pages").glob("*.js"):
            if path in allowed:
                continue
            if 'eventBus.emit("progress:' in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(offenders, [])

    def test_upload_call_sites_use_api_upload(self):
        expected = {
            "static/pages/dataset.js",
            "static/pages/labelme.js",
            "static/pages/auto_labeling.js",
            "static/pages/inference.js",
            "static/pages/model_compare.js",
            "static/pages/training.js",
            "static/pages/training_modes.js",
            "static/pages/project_assistant_impl.js",
            "static/core/model_setup.js",
        }
        for relative in expected:
            source = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(relative=relative):
                self.assertIn("apiUpload", source)
