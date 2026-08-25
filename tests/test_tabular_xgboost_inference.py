from __future__ import annotations

import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from src.tabular_xgboost_inference import (
    TabularXGBoostInferenceError,
    TabularXGBoostInferenceService,
    _lexical_under,
)


class TabularXGBoostInferenceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        self.run_dir = self.root / "projects" / "tabular" / "training" / "runs" / "run_001"
        (self.run_dir / "weights").mkdir(parents=True)
        (self.run_dir / "preprocess").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_contracts(self, *, task_head: str, embedded_imputation: bool = False) -> None:
        schema = {
            "schema_version": "1.0",
            "architecture": "tabular",
            "feature_columns": ["temperature", "pressure"],
            "target_column": "status" if task_head == "classification" else "quality",
            "split_column": "split",
            "input_dim": 2,
            "task_head": task_head,
            "feature_dtypes": {"temperature": "float32", "pressure": "float32"},
            "feature_config_hash": "unit-test",
        }
        imputation = {
            "schema_version": "1.0",
            "strategy": "median",
            "fit_split": "train",
            "statistics": {"temperature": 25.0, "pressure": 3.0},
            "missing_tokens": ["", "NA", "null"],
        }
        if embedded_imputation:
            schema["imputation"] = imputation
        else:
            (self.run_dir / "preprocess" / "imputation.json").write_text(
                json.dumps(imputation), encoding="utf-8"
            )
        (self.run_dir / "preprocess" / "feature_schema.json").write_text(
            json.dumps(schema), encoding="utf-8"
        )
        (self.run_dir / "backend.json").write_text(
            json.dumps(
                {
                    "architecture": "tabular",
                    "backend": "xgboost_tabular",
                    "task_type": f"tabular_{task_head}",
                }
            ),
            encoding="utf-8",
        )
        if task_head == "classification":
            (self.run_dir / "preprocess" / "label_encoder.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "classes": ["normal", "alarm"],
                        "mapping": {"normal": 0, "alarm": 1},
                    }
                ),
                encoding="utf-8",
            )

    def _train_model(self, *, task_head: str) -> None:
        import xgboost as xgb

        features = np.asarray(
            [
                [18.0, 1.0],
                [20.0, 1.5],
                [22.0, 2.0],
                [28.0, 4.0],
                [30.0, 5.0],
                [32.0, 6.0],
            ],
            dtype=np.float32,
        )
        if task_head == "classification":
            labels = np.asarray([0, 0, 0, 1, 1, 1], dtype=np.float32)
            params = {
                "objective": "binary:logistic",
                "eval_metric": "logloss",
                "max_depth": 2,
                "eta": 0.8,
                "seed": 7,
                "nthread": 1,
            }
        else:
            labels = np.asarray([10.0, 12.0, 14.0, 22.0, 26.0, 30.0], dtype=np.float32)
            params = {
                "objective": "reg:squarederror",
                "eval_metric": "rmse",
                "max_depth": 2,
                "eta": 0.8,
                "seed": 7,
                "nthread": 1,
            }
        matrix = xgb.DMatrix(features, label=labels, feature_names=["temperature", "pressure"])
        booster = xgb.train(params, matrix, num_boost_round=5)
        booster.save_model(self.run_dir / "weights" / "best.json")

    def _write_and_train_multiclass(self) -> None:
        import xgboost as xgb

        self._write_contracts(task_head="classification")
        label_path = self.run_dir / "preprocess" / "label_encoder.json"
        label_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "classes": ["cold", "normal", "hot"],
                    "mapping": {"cold": 0, "normal": 1, "hot": 2},
                }
            ),
            encoding="utf-8",
        )
        features = np.asarray(
            [
                [10.0, 1.0],
                [12.0, 1.2],
                [20.0, 2.0],
                [22.0, 2.2],
                [30.0, 3.0],
                [32.0, 3.2],
            ],
            dtype=np.float32,
        )
        labels = np.asarray([0, 0, 1, 1, 2, 2], dtype=np.float32)
        matrix = xgb.DMatrix(features, label=labels, feature_names=["temperature", "pressure"])
        booster = xgb.train(
            {
                "objective": "multi:softprob",
                "num_class": 3,
                "eval_metric": "mlogloss",
                "max_depth": 2,
                "eta": 0.8,
                "seed": 7,
                "nthread": 1,
            },
            matrix,
            num_boost_round=5,
        )
        booster.save_model(self.run_dir / "weights" / "best.json")

    def _service(
        self,
        *,
        task_head: str = "classification",
        embedded_imputation: bool = False,
    ) -> TabularXGBoostInferenceService:
        self._write_contracts(task_head=task_head, embedded_imputation=embedded_imputation)
        self._train_model(task_head=task_head)
        return TabularXGBoostInferenceService.load_from_run(self.run_dir, trusted_root=self.root)

    def test_classification_predict_one_returns_label_probabilities_and_latency(self) -> None:
        service = self._service()

        result = service.predict_one({"temperature": 31.0, "pressure": 5.5, "unused": "kept out"})

        self.assertIn(result["predicted_class"], {0, 1})
        self.assertIn(result["predicted_label"], {"normal", "alarm"})
        self.assertEqual(set(result["probabilities"]), {"normal", "alarm"})
        self.assertAlmostEqual(sum(result["probabilities"].values()), 1.0, places=5)
        self.assertGreaterEqual(result["confidence"], 0.5)
        self.assertGreaterEqual(result["latency_ms"], 0.0)
        description = service.describe()
        self.assertEqual(description["architecture"], "tabular")
        self.assertEqual(description["backend"], "xgboost_tabular")
        self.assertEqual(description["task_head"], "classification")

    def test_embedded_imputation_fallback_handles_configured_missing_tokens(self) -> None:
        service = self._service(embedded_imputation=True)

        result = service.predict_one({"temperature": "NA", "pressure": None})

        self.assertIn(result["predicted_label"], {"normal", "alarm"})
        self.assertEqual(set(result["probabilities"]), {"normal", "alarm"})

    def test_regression_predict_one_returns_finite_value(self) -> None:
        service = self._service(task_head="regression")

        result = service.predict_one({"temperature": "29.5", "pressure": 4.5})

        self.assertIn("prediction", result)
        self.assertTrue(np.isfinite(result["prediction"]))
        self.assertNotIn("predicted_label", result)
        self.assertGreaterEqual(result["latency_ms"], 0.0)

    def test_multiclass_predict_returns_complete_label_probability_mapping(self) -> None:
        self._write_and_train_multiclass()
        service = TabularXGBoostInferenceService.load_from_run(self.run_dir, trusted_root=self.root)

        result = service.predict_rows(
            [
                {"temperature": 11.0, "pressure": 1.1},
                {"temperature": 31.0, "pressure": 3.1},
            ]
        )

        self.assertEqual(result["row_count"], 2)
        for prediction in result["predictions"]:
            self.assertIn(prediction["predicted_class"], {0, 1, 2})
            self.assertIn(prediction["predicted_label"], {"cold", "normal", "hot"})
            self.assertEqual(set(prediction["probabilities"]), {"cold", "normal", "hot"})
            self.assertAlmostEqual(sum(prediction["probabilities"].values()), 1.0, places=5)

    def test_csv_batch_writes_predictions_and_preserves_input_columns(self) -> None:
        service = self._service()
        input_path = self.root / "input.csv"
        output_dir = self.root / "outputs"
        output_dir.mkdir()
        output_path = output_dir / "predictions.csv"
        input_path.write_text(
            "sample_id,temperature,pressure\nA,19,1.2\nB,,5.0\n",
            encoding="utf-8",
        )

        result = service.predict_csv(input_path, output_path, trusted_root=self.root)

        self.assertEqual(result["row_count"], 2)
        self.assertEqual(Path(result["output_path"]), output_path)
        self.assertGreaterEqual(result["latency_ms"], 0.0)
        self.assertGreaterEqual(result["total_latency_ms"], result["latency_ms"])
        with output_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([row["sample_id"] for row in rows], ["A", "B"])
        self.assertIn(rows[0]["predicted_label"], {"normal", "alarm"})
        self.assertEqual(set(json.loads(rows[0]["probabilities"])), {"normal", "alarm"})

    def test_csv_batch_neutralizes_formula_cells_but_preserves_numeric_literals_and_raw_predictions(self) -> None:
        self._write_contracts(task_head="classification")
        label_path = self.run_dir / "preprocess" / "label_encoder.json"
        label_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "classes": ["-1", "+2"],
                    "mapping": {"-1": 0, "+2": 1},
                }
            ),
            encoding="utf-8",
        )
        self._train_model(task_head="classification")
        service = TabularXGBoostInferenceService.load_from_run(self.run_dir, trusted_root=self.root)
        input_path = self.root / "formula_input.csv"
        output_path = self.root / "formula_predictions.csv"
        with input_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "sample_id",
                    "note",
                    "command",
                    "at_value",
                    "negative_number",
                    "positive_number",
                    "temperature",
                    "pressure",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "sample_id": "=HYPERLINK(\"https://invalid.example\")",
                    "note": "  +SUM(1,1)",
                    "command": "-cmd|' /C calc'!A0",
                    "at_value": "\t@malicious",
                    "negative_number": "-12.5",
                    "positive_number": "+7.25e1",
                    "temperature": "-19.0",
                    "pressure": "+1.2",
                }
            )

        result = service.predict_csv(input_path, output_path)

        raw_label = result["predictions"][0]["predicted_label"]
        self.assertIn(raw_label, {"-1", "+2"})
        self.assertFalse(str(raw_label).startswith("'"))
        with output_path.open("r", encoding="utf-8", newline="") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(row["sample_id"], "'=HYPERLINK(\"https://invalid.example\")")
        self.assertEqual(row["note"], "'  +SUM(1,1)")
        self.assertEqual(row["command"], "'-cmd|' /C calc'!A0")
        self.assertEqual(row["at_value"], "'\t@malicious")
        self.assertEqual(row["negative_number"], "-12.5")
        self.assertEqual(row["positive_number"], "+7.25e1")
        self.assertEqual(row["temperature"], "-19.0")
        self.assertEqual(row["pressure"], "+1.2")
        self.assertEqual(row["predicted_label"], f"'{raw_label}")
        self.assertFalse(row["predicted_class"].startswith("'"))
        self.assertFalse(row["confidence"].startswith("'"))
        self.assertEqual(set(json.loads(row["probabilities"])), {"-1", "+2"})

    def test_missing_feature_column_is_rejected_instead_of_silently_imputed(self) -> None:
        service = self._service()

        with self.assertRaisesRegex(TabularXGBoostInferenceError, "missing required feature"):
            service.predict_one({"temperature": 22.0})

    def test_non_numeric_non_missing_value_is_rejected(self) -> None:
        service = self._service()

        with self.assertRaisesRegex(TabularXGBoostInferenceError, "must be numeric"):
            service.predict_one({"temperature": "hot", "pressure": 2.0})

    def test_run_and_csv_paths_cannot_escape_trusted_root(self) -> None:
        self._write_contracts(task_head="classification")
        self._train_model(task_head="classification")
        outside = self.root.parent / f"outside_{self.root.name}"
        outside.mkdir(exist_ok=True)
        try:
            with self.assertRaisesRegex(TabularXGBoostInferenceError, "trusted root"):
                TabularXGBoostInferenceService.load_from_run(outside, trusted_root=self.root)

            service = TabularXGBoostInferenceService.load_from_run(self.run_dir, trusted_root=self.root)
            outside_input = outside / "input.csv"
            outside_input.write_text("temperature,pressure\n20,2\n", encoding="utf-8")
            with self.assertRaisesRegex(TabularXGBoostInferenceError, "trusted root"):
                service.predict_csv(outside_input, self.root / "result.csv")
            inside_input = self.root / "inside.csv"
            inside_input.write_text("temperature,pressure\n20,2\n", encoding="utf-8")
            with self.assertRaisesRegex(TabularXGBoostInferenceError, "trusted root"):
                service.predict_csv(inside_input, outside / "result.csv")
        finally:
            for child in outside.glob("*"):
                child.unlink(missing_ok=True)
            outside.rmdir()

    @unittest.skipUnless(os.name == "nt", "Windows 8.3 path alias behavior")
    def test_equivalent_windows_short_path_alias_remains_inside_trusted_root(self) -> None:
        canonical_root = self.root / "canonical-project"
        alias_root = self.root / "PROJECT~1"
        candidate = alias_root / "training" / "runs" / "run_001"

        def same_file(left, right):
            left_path = Path(left)
            right_path = Path(right)
            return left_path == alias_root and right_path == canonical_root

        with patch("src.tabular_xgboost_inference.os.path.samefile", side_effect=same_file):
            secured = _lexical_under(canonical_root, candidate, "Run directory")

        self.assertEqual(secured, candidate)

    @unittest.skipUnless(os.name == "nt", "Windows reparse-point containment")
    def test_equivalent_alias_cannot_enter_root_through_parent_reparse_point(self) -> None:
        canonical_root = self.root / "canonical-project"
        alias_parent = self.root / "outside-link"
        alias_root = alias_parent / "canonical-project"
        candidate = alias_root / "training" / "runs" / "run_001"

        def same_file(left, right):
            return Path(left) == alias_root and Path(right) == canonical_root

        def is_link_or_reparse(path):
            return Path(path) == alias_parent

        with (
            patch("src.tabular_xgboost_inference.os.path.samefile", side_effect=same_file),
            patch(
                "src.tabular_xgboost_inference._is_link_or_reparse",
                side_effect=is_link_or_reparse,
            ),
            self.assertRaisesRegex(TabularXGBoostInferenceError, "reparse points"),
        ):
            _lexical_under(canonical_root, candidate, "Run directory")

    def test_loader_rejects_wrong_architecture_and_non_xgboost_json(self) -> None:
        self._write_contracts(task_head="classification")
        schema_path = self.run_dir / "preprocess" / "feature_schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["architecture"] = "rnn"
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        (self.run_dir / "weights" / "best.json").write_text('{"not_learner": {}}', encoding="utf-8")

        with self.assertRaisesRegex(TabularXGBoostInferenceError, "architecture must be tabular"):
            TabularXGBoostInferenceService.load_from_run(self.run_dir, trusted_root=self.root)

        schema["architecture"] = "tabular"
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        with self.assertRaisesRegex(TabularXGBoostInferenceError, "missing the learner"):
            TabularXGBoostInferenceService.load_from_run(self.run_dir, trusted_root=self.root)

    def test_output_requires_explicit_overwrite(self) -> None:
        service = self._service()
        input_path = self.root / "input.csv"
        output_path = self.root / "predictions.csv"
        input_path.write_text("temperature,pressure\n20,2\n", encoding="utf-8")
        output_path.write_text("existing\n", encoding="utf-8")

        with self.assertRaisesRegex(TabularXGBoostInferenceError, "explicit overwrite"):
            service.predict_csv(input_path, output_path)
        result = service.predict_csv(input_path, output_path, overwrite=True)
        self.assertEqual(result["row_count"], 1)


if __name__ == "__main__":
    unittest.main()
