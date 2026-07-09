import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app
from src.rag_workbench import RagWorkbenchService
from src.project_assistant import ProjectAssistantService
from src.project_assistant_service import ProjectAssistantService as ProjectAssistantServiceImpl
from src.project_layout import ProjectLayout


class ProjectAssistantContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "project_assistant"
        self.original_paths = {
            "ROOT": ProjectAssistantService.ROOT,
            "KB_DIR": ProjectAssistantService.KB_DIR,
            "DOCS_DIR": ProjectAssistantService.DOCS_DIR,
            "RUNS_DIR": ProjectAssistantService.RUNS_DIR,
            "ARTIFACTS_DIR": ProjectAssistantService.ARTIFACTS_DIR,
            "EXPORTS_DIR": ProjectAssistantService.EXPORTS_DIR,
            "STATE_PATH": ProjectAssistantService.STATE_PATH,
            "SANDBOX_PATH": ProjectAssistantService.SANDBOX_PATH,
        }
        ProjectAssistantService.ROOT = self.root
        ProjectAssistantService.KB_DIR = self.root / "knowledge_base"
        ProjectAssistantService.DOCS_DIR = ProjectAssistantService.KB_DIR / "documents"
        ProjectAssistantService.RUNS_DIR = self.root / "runs"
        ProjectAssistantService.ARTIFACTS_DIR = self.root / "artifacts"
        ProjectAssistantService.EXPORTS_DIR = self.root / "exports"
        ProjectAssistantService.STATE_PATH = self.root / "state.json"
        ProjectAssistantService.SANDBOX_PATH = self.root / "sandbox.json"
        ProjectAssistantService.ensure()

    def tearDown(self):
        for key, value in self.original_paths.items():
            setattr(ProjectAssistantService, key, value)
        self.tmp.cleanup()

    def test_knowledge_base_ingestion_records_readiness_stages_and_chunks(self):
        result = ProjectAssistantService.ingest_document(
            "manual.md",
            "Pump pressure diagnostics mention vibration and pressure drift. " * 20,
        )

        self.assertEqual(result["document"]["index_state"], "indexed")
        self.assertEqual(
            [stage["stage"] for stage in result["document"]["ingestion"]],
            ["upload", "parse", "chunk", "embed", "index"],
        )
        self.assertGreater(result["document"]["chunk_count"], 0)
        self.assertEqual(result["status"]["knowledge_base"]["index_state"], "ready")

    def test_legacy_workbench_import_alias_points_to_project_assistant_service(self):
        self.assertIs(ProjectAssistantService, RagWorkbenchService)
        self.assertIs(ProjectAssistantServiceImpl, ProjectAssistantService)
        self.assertEqual(ProjectAssistantService.__module__, "src.project_assistant_service")

    def test_project_assistant_settings_default_to_local_search_and_can_disable(self):
        settings = ProjectAssistantService.get_settings()

        self.assertEqual(settings["mode"], "local_search_only")
        self.assertFalse(settings["requires_llm"])
        self.assertTrue(settings["generation_enabled"])

        updated = ProjectAssistantService.update_settings({"mode": "disabled"})
        self.assertEqual(updated["mode"], "disabled")
        run = ProjectAssistantService.chat("Should not search while disabled")
        self.assertEqual(run["failure_type"], "assistant_disabled")
        self.assertFalse(run["sources"])

    def test_retrieval_returns_structured_sources_and_mark_feedback(self):
        ProjectAssistantService.ingest_document(
            "source.txt",
            "The compressor failure is associated with pressure drift and load spikes.",
        )

        retrieval = ProjectAssistantService.retrieve("pressure drift failure", top_k=3)

        self.assertEqual(retrieval["profile_id"], "lexical_default")
        self.assertGreaterEqual(len(retrieval["results"]), 1)
        source = retrieval["results"][0]
        self.assertIn("chunk_id", source)
        self.assertIn("score", source)
        self.assertIn("content", source)

        mark = ProjectAssistantService.mark_retrieval("pressure drift failure", source["chunk_id"], "bad", "not enough context")
        self.assertEqual(mark["relevance"], "bad")

    def test_project_assistant_filters_sources_to_active_project(self):
        ProjectAssistantService.ingest_document(
            "project-a-report.md",
            "Alpha project export contract requires schema and scaler.",
            metadata={"project_id": "project_a"},
        )
        ProjectAssistantService.ingest_document(
            "project-b-report.md",
            "Beta project export contract requires a confusion matrix.",
            metadata={"project_id": "project_b"},
        )

        retrieval = ProjectAssistantService.retrieve(
            "export contract requires",
            top_k=5,
            filters={"project_id": "project_a"},
        )

        self.assertEqual(len(retrieval["results"]), 1)
        self.assertEqual(retrieval["results"][0]["source"], "project-a-report.md")

    def test_project_assistant_api_requires_active_project_scope(self):
        client = TestClient(app)
        unscoped_ingest = client.post(
            "/api/project-assistant/knowledge-base/documents",
            json={"filename": "unscoped.md", "content": "This should not become global assistant knowledge."},
        )
        self.assertEqual(unscoped_ingest.status_code, 400)

        client.post(
            "/api/project-assistant/knowledge-base/documents?project_id=project_a",
            json={"filename": "project-a-report.md", "content": "Alpha project pressure drift diagnostics."},
        )
        client.post(
            "/api/project-assistant/knowledge-base/documents?project_id=project_b",
            json={"filename": "project-b-report.md", "content": "Beta project export contract diagnostics."},
        )

        unscoped = client.get("/api/project-assistant/knowledge-base")
        self.assertEqual(unscoped.status_code, 200)
        self.assertEqual(unscoped.json()["documents"], [])
        self.assertEqual(unscoped.json()["chunks"], [])

        no_project_retrieval = client.post(
            "/api/project-assistant/retrieval/query",
            json={"query": "diagnostics"},
        )
        self.assertEqual(no_project_retrieval.status_code, 400)

        project_a_docs = client.get("/api/project-assistant/knowledge-base?project_id=project_a").json()
        project_b_docs = client.get("/api/project-assistant/knowledge-base?project_id=project_b").json()
        self.assertEqual([item["filename"] for item in project_a_docs["documents"]], ["project-a-report.md"])
        self.assertEqual([item["filename"] for item in project_b_docs["documents"]], ["project-b-report.md"])

        no_project_chat = client.post("/api/project-assistant/chat", json={"message": "diagnostics"})
        self.assertEqual(no_project_chat.status_code, 400)

        project_a_chat = client.post(
            "/api/project-assistant/chat?project_id=project_a",
            json={"message": "pressure drift diagnostics"},
        )
        self.assertEqual(project_a_chat.status_code, 200)
        self.assertEqual(project_a_chat.json()["sources"][0]["source"], "project-a-report.md")

        project_a_runs = client.get("/api/project-assistant/agent-runs?project_id=project_a").json()["runs"]
        project_b_runs = client.get("/api/project-assistant/agent-runs?project_id=project_b").json()["runs"]
        self.assertEqual(len(project_a_runs), 1)
        self.assertEqual(project_b_runs, [])

    def test_sync_project_artifacts_indexes_active_project_evidence_without_duplicates(self):
        project = self._make_sequence_project("project_sync")
        run_dir = Path(project["dataset_path"]).parent / "training" / "runs" / "run_lstm_1"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "metrics.json").write_text(json.dumps({
            "architecture": "rnn",
            "task_type": "sequence_regression",
            "primary_metric": "val/mae",
            "best_metrics": {"val/mae": 0.12, "val/rmse": 0.18},
            "history": [{"epoch": 1, "train/loss": 0.4, "val/loss": 0.3, "val/mae": 0.12}],
        }), encoding="utf-8")
        (run_dir / "metric_schema.json").write_text(json.dumps({"primary": "val/mae"}), encoding="utf-8")
        export_dir = Path(project["dataset_path"]).parent / "exports" / "export_rnn_1"
        export_dir.mkdir(parents=True, exist_ok=True)
        (export_dir / "summary.json").write_text(json.dumps({
            "export_id": "export_rnn_1",
            "export_type": "rnn_model_package",
            "run_id": "run_lstm_1",
            "package_path": "exports/export_rnn_1/rnn_model_package.zip",
            "files": [{"path": "inference_contract.json", "size_bytes": 128}],
        }), encoding="utf-8")
        ProjectAssistantService.ingest_document(
            "manual-note.md",
            "Manual note about deployment review.",
            metadata={"project_id": "project_sync"},
        )

        first = ProjectAssistantService.sync_project_artifacts(project)
        second = ProjectAssistantService.sync_project_artifacts(project)
        kb = ProjectAssistantService.list_documents(project_id="project_sync")
        documents = kb["documents"]
        auto_docs = [doc for doc in documents if (doc.get("metadata") or {}).get("auto_indexed")]
        manual_docs = [doc for doc in documents if not (doc.get("metadata") or {}).get("auto_indexed")]
        retrieval = ProjectAssistantService.retrieve(
            "val mae inference contract deployment review",
            top_k=8,
            filters={"project_id": "project_sync"},
        )

        self.assertEqual(first["document_count"], 4)
        self.assertEqual(second["removed_auto_documents"], 4)
        self.assertEqual(len(auto_docs), 4)
        self.assertEqual([doc["filename"] for doc in manual_docs], ["manual-note.md"])
        self.assertTrue(any(result["source"] == "training-runs-and-metrics.md" for result in retrieval["results"]))
        self.assertTrue(any(result["source"] == "manual-note.md" for result in retrieval["results"]))

    def test_sync_project_artifacts_api_uses_project_manager_scope(self):
        client = TestClient(app)
        project = self._make_sequence_project("project_api_sync")

        with patch("src.api.routes.project_assistant.ProjectManager.get_project", return_value=project):
            response = client.post("/api/project-assistant/projects/project_api_sync/sync-artifacts")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["project_id"], "project_api_sync")
        self.assertEqual(payload["document_count"], 4)
        docs = client.get("/api/project-assistant/knowledge-base?project_id=project_api_sync").json()["documents"]
        self.assertEqual(len([doc for doc in docs if doc["metadata"].get("auto_indexed")]), 4)

    def test_chat_uses_clean_conversation_state_and_saves_agent_run(self):
        ProjectAssistantService.ingest_document(
            "guide.txt",
            "Citation coverage means the answer links back to the source chunk.",
        )
        dirty_state = [
            {"role": "assistant", "content": "Valid prior answer", "meta": {"button_text": "Copy"}},
            {"role": "ui", "content": "Accept Reject Button"},
            {"role": "assistant", "html": "<button>Reject</button>"},
        ]

        run = ProjectAssistantService.chat("What is citation coverage?", dirty_state)

        self.assertTrue(run["sources"])
        self.assertEqual(run["metrics"]["citation_coverage"], 1.0)
        self.assertEqual([step["step"] for step in run["agent_trace"]], ["parse", "retrieve", "validate", "final"])
        roles = [item["role"] for item in run["conversation_state"]]
        self.assertNotIn("ui", roles)
        serialized = str(run["conversation_state"])
        self.assertNotIn("Accept Reject Button", serialized)
        self.assertNotIn("<button>", serialized)

        runs = ProjectAssistantService.list_agent_runs()["runs"]
        self.assertEqual(runs[0]["run_id"], run["run_id"])

    def test_sandbox_preview_composes_html_css_and_js_and_exports_artifact(self):
        ProjectAssistantService.update_sandbox_file("index.html", "<html><head></head><body><div id=\"app\">Hi</div></body></html>")
        ProjectAssistantService.update_sandbox_file("css/style.css", "#app { color: red; }")
        sandbox = ProjectAssistantService.update_sandbox_file("js/app.js", "window.__projectAssistantPreview = true;")

        preview = sandbox["preview_html"]
        self.assertIn("#app { color: red; }", preview)
        self.assertIn("window.__projectAssistantPreview = true;", preview)
        self.assertFalse(sandbox["policy"]["os_isolation"])

        artifact = ProjectAssistantService.export_sandbox()
        self.assertTrue(Path(artifact["path"]).exists())
        self.assertEqual(artifact["type"], "sandbox_project_zip")

    def test_evaluation_report_summarizes_project_assistant_runs(self):
        ProjectAssistantService.ingest_document("eval.md", "Project Assistant evaluation checks source hit rate and latency.")
        ProjectAssistantService.chat("How do we evaluate assistant answers?")
        ProjectAssistantService.chat("No matching phrase qwertyuiop")

        report = ProjectAssistantService.evaluation_report(golden_set=[
            {"query": "How do we evaluate assistant answers?", "expected_source": "eval.md", "expected_answer": "source hit rate"}
        ])

        self.assertEqual(report["run_count"], 2)
        self.assertEqual(report["golden_case_count"], 1)
        self.assertEqual(report["golden_source_hits"], 1)
        self.assertIn("source_hit_rate", report)
        self.assertTrue(Path(report["report_path"]).exists())

    def test_file_upload_and_sse_stream_contracts(self):
        client = TestClient(app)
        upload = client.post(
            "/api/project-assistant/knowledge-base/upload?project_id=upload_project",
            files={"file": ("upload.md", b"Streamed assistant answers send sources events.", "text/markdown")},
        )
        self.assertEqual(upload.status_code, 200)
        self.assertGreaterEqual(upload.json()["document"]["chunk_count"], 1)

        stream = client.post(
            "/api/project-assistant/chat/stream?project_id=upload_project",
            json={"message": "What does streamed assistant response send?", "conversation_state": []},
        )
        self.assertEqual(stream.status_code, 200)
        body = stream.text
        self.assertIn("event: sources", body)
        self.assertIn("event: final", body)

    def test_api_routes_expose_project_assistant_contract(self):
        client = TestClient(app)
        response = client.get("/api/project-assistant/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("knowledge_base", payload)
        self.assertIn("chat", payload["navigation"])

    def _make_sequence_project(self, project_id: str):
        project_dir = self.root / "projects" / project_id
        project = {
            "project_id": project_id,
            "project_name": "Sync Project",
            "task_type": "sequence_regression",
            "dataset_path": str((project_dir / "dataset").resolve()),
            "layout": {"mode": "v3", "version": "v3"},
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-02T00:00:00",
            "rnn_config": {
                "feature_columns": ["pressure", "flow"],
                "target_column": "temperature",
                "time_column": "timestamp",
                "sequence_column": "machine_id",
                "task_head": "regression",
            },
            "training_config": {"architecture": "rnn", "model": "lstm", "epochs": 3},
            "training_runs": [{"run_id": "run_lstm_1", "status": "completed", "created_at": "2026-01-02T00:00:00"}],
            "current": {"training_run_id": "run_lstm_1", "export_id": "export_rnn_1"},
            "imports_history": [{"type": "sequence_csv", "filename": "sensor.csv"}],
        }
        ProjectLayout(project_dir, project).ensure_v3_tree()
        sequence_manifest = project_dir / "sequences" / "sequence_manifest.json"
        sequence_manifest.write_text(json.dumps({"sequence_count": 8, "columns": ["timestamp", "pressure", "flow"]}), encoding="utf-8")
        return project


if __name__ == "__main__":
    unittest.main()
