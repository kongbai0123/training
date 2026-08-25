import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.training.artifact_manifest import build_artifact_manifest, write_artifact_manifest


class ArtifactManifestV2Tests(unittest.TestCase):
    def test_legacy_call_builds_v2_integrity_and_producer_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run_legacy_call"
            run_dir.joinpath("weights").mkdir(parents=True)
            payload = b"portable-model-payload"
            run_dir.joinpath("weights", "best.pt").write_bytes(payload)
            run_dir.joinpath("metrics.json").write_text('{"accuracy": 0.9}', encoding="utf-8")

            # This is the original public call shape and must remain valid.
            manifest = build_artifact_manifest(run_dir, run_dir.name)
            artifacts = {entry["path"]: entry for entry in manifest["artifacts"]}

            self.assertEqual(manifest["contract_version"], "2.0")
            self.assertEqual(manifest["producer"]["contract_version"], "2.0")
            self.assertTrue(manifest["producer"]["product"])
            self.assertTrue(manifest["producer"]["app_version"])
            self.assertTrue(manifest["producer"]["runtime_version"])
            self.assertNotIn("lineage", manifest)
            self.assertEqual(artifacts["weights/best.pt"]["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(artifacts["weights/best.pt"]["content_type"], "application/octet-stream")
            self.assertEqual(artifacts["metrics.json"]["content_type"], "application/json")
            for artifact in manifest["artifacts"]:
                self.assertEqual(len(artifact["sha256"]), 64)
                self.assertTrue(artifact["content_type"])

    def test_optional_lineage_and_producer_overrides_are_serialized(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run_with_lineage"
            run_dir.joinpath("weights").mkdir(parents=True)
            run_dir.joinpath("weights", "best.json").write_text("{}", encoding="utf-8")
            dataset_lineage = {
                "dataset_id": "quality-inspection",
                "version": "dataset-v3",
                "snapshot_sha256": "a" * 64,
            }
            model_lineage = {
                "parent_model_id": "baseline-xgb",
                "parent_run_id": "run_001",
            }

            manifest = write_artifact_manifest(
                run_dir,
                run_dir.name,
                producer={"app_version": "9.9.9", "runtime_version": "r9"},
                dataset_lineage=dataset_lineage,
                model_lineage=model_lineage,
            )

            # Caller-owned dictionaries must not become mutable manifest state.
            dataset_lineage["version"] = "changed-after-build"
            stored = json.loads(run_dir.joinpath("artifact_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["producer"]["app_version"], "9.9.9")
            self.assertEqual(manifest["producer"]["runtime_version"], "r9")
            self.assertEqual(manifest["producer"]["contract_version"], "2.0")
            self.assertEqual(stored["lineage"]["dataset"]["version"], "dataset-v3")
            self.assertEqual(stored["lineage"]["model"]["parent_run_id"], "run_001")
            artifact = stored["artifacts"][0]
            self.assertEqual(artifact["content_type"], "application/json")
            self.assertEqual(artifact["sha256"], hashlib.sha256(b"{}").hexdigest())

    def test_invalid_optional_metadata_is_rejected_without_affecting_legacy_calls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run_invalid_lineage"
            run_dir.mkdir()

            with self.assertRaisesRegex(TypeError, "dataset lineage must be a mapping"):
                build_artifact_manifest(run_dir, run_dir.name, dataset_lineage="dataset-v1")
            with self.assertRaisesRegex(TypeError, "producer overrides must be a mapping"):
                build_artifact_manifest(run_dir, run_dir.name, producer="runtime-r1")


if __name__ == "__main__":
    unittest.main()
