import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import app
from src.rag_workbench import RagWorkbenchService
from src.project_assistant import ProjectAssistantService


class RagWorkbenchContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "rag_workbench"
        self.original_paths = {
            "ROOT": RagWorkbenchService.ROOT,
            "KB_DIR": RagWorkbenchService.KB_DIR,
            "DOCS_DIR": RagWorkbenchService.DOCS_DIR,
            "RUNS_DIR": RagWorkbenchService.RUNS_DIR,
            "ARTIFACTS_DIR": RagWorkbenchService.ARTIFACTS_DIR,
            "EXPORTS_DIR": RagWorkbenchService.EXPORTS_DIR,
            "STATE_PATH": RagWorkbenchService.STATE_PATH,
            "SANDBOX_PATH": RagWorkbenchService.SANDBOX_PATH,
        }
        RagWorkbenchService.ROOT = self.root
        RagWorkbenchService.KB_DIR = self.root / "knowledge_base"
        RagWorkbenchService.DOCS_DIR = RagWorkbenchService.KB_DIR / "documents"
        RagWorkbenchService.RUNS_DIR = self.root / "runs"
        RagWorkbenchService.ARTIFACTS_DIR = self.root / "artifacts"
        RagWorkbenchService.EXPORTS_DIR = self.root / "exports"
        RagWorkbenchService.STATE_PATH = self.root / "state.json"
        RagWorkbenchService.SANDBOX_PATH = self.root / "sandbox.json"
        RagWorkbenchService.ensure()

    def tearDown(self):
        for key, value in self.original_paths.items():
            setattr(RagWorkbenchService, key, value)
        self.tmp.cleanup()

    def test_knowledge_base_ingestion_records_readiness_stages_and_chunks(self):
        result = RagWorkbenchService.ingest_document(
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

    def test_project_assistant_settings_default_to_local_search_and_can_disable(self):
        self.assertIs(ProjectAssistantService, RagWorkbenchService)
        settings = RagWorkbenchService.get_settings()

        self.assertEqual(settings["mode"], "local_search_only")
        self.assertFalse(settings["requires_llm"])
        self.assertTrue(settings["generation_enabled"])

        updated = RagWorkbenchService.update_settings({"mode": "disabled"})
        self.assertEqual(updated["mode"], "disabled")
        run = RagWorkbenchService.chat("Should not search while disabled")
        self.assertEqual(run["failure_type"], "assistant_disabled")
        self.assertFalse(run["sources"])

    def test_retrieval_returns_structured_sources_and_mark_feedback(self):
        RagWorkbenchService.ingest_document(
            "source.txt",
            "The compressor failure is associated with pressure drift and load spikes.",
        )

        retrieval = RagWorkbenchService.retrieve("pressure drift failure", top_k=3)

        self.assertEqual(retrieval["profile_id"], "lexical_default")
        self.assertGreaterEqual(len(retrieval["results"]), 1)
        source = retrieval["results"][0]
        self.assertIn("chunk_id", source)
        self.assertIn("score", source)
        self.assertIn("content", source)

        mark = RagWorkbenchService.mark_retrieval("pressure drift failure", source["chunk_id"], "bad", "not enough context")
        self.assertEqual(mark["relevance"], "bad")

    def test_project_assistant_filters_sources_to_active_project(self):
        RagWorkbenchService.ingest_document(
            "project-a-report.md",
            "Alpha project export contract requires schema and scaler.",
            metadata={"project_id": "project_a"},
        )
        RagWorkbenchService.ingest_document(
            "project-b-report.md",
            "Beta project export contract requires a confusion matrix.",
            metadata={"project_id": "project_b"},
        )

        retrieval = RagWorkbenchService.retrieve(
            "export contract requires",
            top_k=5,
            filters={"project_id": "project_a"},
        )

        self.assertEqual(len(retrieval["results"]), 1)
        self.assertEqual(retrieval["results"][0]["source"], "project-a-report.md")

    def test_chat_uses_clean_conversation_state_and_saves_agent_run(self):
        RagWorkbenchService.ingest_document(
            "guide.txt",
            "Citation coverage means the answer links back to the source chunk.",
        )
        dirty_state = [
            {"role": "assistant", "content": "Valid prior answer", "meta": {"button_text": "Copy"}},
            {"role": "ui", "content": "Accept Reject Button"},
            {"role": "assistant", "html": "<button>Reject</button>"},
        ]

        run = RagWorkbenchService.chat("What is citation coverage?", dirty_state)

        self.assertTrue(run["sources"])
        self.assertEqual(run["metrics"]["citation_coverage"], 1.0)
        self.assertEqual([step["step"] for step in run["agent_trace"]], ["parse", "retrieve", "validate", "final"])
        roles = [item["role"] for item in run["conversation_state"]]
        self.assertNotIn("ui", roles)
        serialized = str(run["conversation_state"])
        self.assertNotIn("Accept Reject Button", serialized)
        self.assertNotIn("<button>", serialized)

        runs = RagWorkbenchService.list_agent_runs()["runs"]
        self.assertEqual(runs[0]["run_id"], run["run_id"])

    def test_sandbox_preview_composes_html_css_and_js_and_exports_artifact(self):
        RagWorkbenchService.update_sandbox_file("index.html", "<html><head></head><body><div id=\"app\">Hi</div></body></html>")
        RagWorkbenchService.update_sandbox_file("css/style.css", "#app { color: red; }")
        sandbox = RagWorkbenchService.update_sandbox_file("js/app.js", "window.__ragPreview = true;")

        preview = sandbox["preview_html"]
        self.assertIn("#app { color: red; }", preview)
        self.assertIn("window.__ragPreview = true;", preview)
        self.assertFalse(sandbox["policy"]["os_isolation"])

        artifact = RagWorkbenchService.export_sandbox()
        self.assertTrue(Path(artifact["path"]).exists())
        self.assertEqual(artifact["type"], "sandbox_project_zip")

    def test_evaluation_report_summarizes_rag_runs(self):
        RagWorkbenchService.ingest_document("eval.md", "RAG evaluation checks source hit rate and latency.")
        RagWorkbenchService.chat("How do we evaluate RAG?")
        RagWorkbenchService.chat("No matching phrase qwertyuiop")

        report = RagWorkbenchService.evaluation_report(golden_set=[
            {"query": "How do we evaluate RAG?", "expected_source": "eval.md", "expected_answer": "source hit rate"}
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
            files={"file": ("upload.md", b"Streamed RAG answers send sources events.", "text/markdown")},
        )
        self.assertEqual(upload.status_code, 200)
        self.assertGreaterEqual(upload.json()["document"]["chunk_count"], 1)

        stream = client.post(
            "/api/project-assistant/chat/stream?project_id=upload_project",
            json={"message": "What does streamed RAG send?", "conversation_state": []},
        )
        self.assertEqual(stream.status_code, 200)
        body = stream.text
        self.assertIn("event: sources", body)
        self.assertIn("event: final", body)

    def test_api_routes_expose_workbench_contract(self):
        client = TestClient(app)
        response = client.get("/api/project-assistant/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("knowledge_base", payload)
        self.assertIn("chat", payload["navigation"])


if __name__ == "__main__":
    unittest.main()
