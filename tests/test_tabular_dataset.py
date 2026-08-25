import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.training.tabular.dataset import (
    TabularDatasetError,
    load_csv_tabular_dataset,
    write_preprocess_artifacts,
)


class TabularDatasetTests(unittest.TestCase):
    def _write(self, root: Path, rows: list[str], name: str = "table.csv") -> Path:
        path = root / name
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return path

    def test_classification_is_row_level_stratified_and_deterministic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rows = ["temperature,pressure,target"]
            rows.extend(f"{index},{100 + index},normal" for index in range(20))
            rows.extend(f"{index},{200 + index},alarm" for index in range(20))
            path = self._write(root, rows)

            first = load_csv_tabular_dataset(path, target_column="target", seed=17)
            second = load_csv_tabular_dataset(path, target_column="target", seed=17)

            self.assertEqual(first["task_head"], "classification")
            self.assertEqual(first["num_outputs"], 2)
            self.assertEqual(first["label_encoder"], {"alarm": 0, "normal": 1})
            self.assertEqual(first["summary"]["split_method"], "stratified")
            self.assertEqual(first["summary"]["split_counts"], {"train": 28, "val": 6, "test": 6})
            self.assertEqual(first["tensors"]["train"]["x"].shape, (28, 2))
            self.assertEqual(first["tensors"]["train"]["x"].ndim, 2)
            for split in ("train", "val", "test"):
                self.assertEqual(
                    first["tensors"][split]["row_indices"].tolist(),
                    second["tensors"][split]["row_indices"].tolist(),
                )
                self.assertEqual(set(first["tensors"][split]["y"].tolist()), {0, 1})

            all_indices = np.concatenate(
                [first["tensors"][name]["row_indices"] for name in ("train", "val", "test")]
            )
            self.assertEqual(sorted(all_indices.tolist()), list(range(40)))
            self.assertEqual(len(set(all_indices.tolist())), 40)

    def test_provided_split_uses_training_medians_and_writes_portable_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = self._write(
                root,
                [
                    "feature_a,feature_b,target,split",
                    "1,10,A,training",
                    ",20,B,train",
                    "100,,A,validation",
                    ",40,B,testing",
                ],
            )

            dataset = load_csv_tabular_dataset(path, target_column="target")

            self.assertEqual(dataset["split_column"], "split")
            self.assertEqual(dataset["summary"]["split_method"], "provided")
            self.assertEqual(dataset["summary"]["split_counts"], {"train": 2, "val": 1, "test": 1})
            self.assertEqual(
                dataset["imputation"]["statistics"],
                {"feature_a": 1.0, "feature_b": 15.0},
            )
            np.testing.assert_allclose(dataset["tensors"]["val"]["x"], [[100.0, 15.0]])
            np.testing.assert_allclose(dataset["tensors"]["test"]["x"], [[1.0, 40.0]])

            run_dir = root / "run"
            write_preprocess_artifacts(run_dir, dataset)
            feature_schema = json.loads(
                (run_dir / "preprocess" / "feature_schema.json").read_text(encoding="utf-8")
            )
            imputation = json.loads(
                (run_dir / "preprocess" / "imputation.json").read_text(encoding="utf-8")
            )
            label_encoder = json.loads(
                (run_dir / "preprocess" / "label_encoder.json").read_text(encoding="utf-8")
            )
            self.assertEqual(feature_schema["architecture"], "tabular")
            self.assertEqual(feature_schema["feature_columns"], ["feature_a", "feature_b"])
            self.assertEqual(feature_schema["input_dim"], 2)
            self.assertEqual(
                feature_schema["feature_config_hash"], dataset["feature_config_hash"]
            )
            self.assertEqual(imputation["strategy"], "median")
            self.assertEqual(imputation["fit_split"], "train")
            self.assertEqual(label_encoder["mapping"], {"A": 0, "B": 1})
            self.assertEqual(label_encoder["classes"], ["A", "B"])

    def test_provided_classification_split_rejects_labels_missing_from_training(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = self._write(
                root,
                [
                    "feature,target,partition",
                    "1,A,train",
                    "2,A,training",
                    "3,B,val",
                    "4,B,validation",
                    "5,C,test",
                    "6,C,testing",
                ],
            )

            with self.assertRaisesRegex(
                TabularDatasetError,
                "training split is missing target labels",
            ) as captured:
                load_csv_tabular_dataset(
                    path,
                    target_column="target",
                    split_column="partition",
                )

            message = str(captured.exception)
            self.assertIn("'B'", message)
            self.assertIn("'C'", message)
            self.assertIn("Move at least one row", message)

    def test_regression_random_split_is_reproducible_and_seeded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rows = ["x1,x2,y"]
            rows.extend(f"{index},{index * 2},{index / 10}" for index in range(20))
            path = self._write(root, rows)

            first = load_csv_tabular_dataset(
                path, target_column="y", task_head="regression", seed=7
            )
            repeated = load_csv_tabular_dataset(
                path, target_column="y", task_head="regression", seed=7
            )
            different = load_csv_tabular_dataset(
                path, target_column="y", task_head="regression", seed=8
            )

            self.assertEqual(first["summary"]["split_method"], "random")
            self.assertEqual(first["summary"]["split_counts"], {"train": 14, "val": 3, "test": 3})
            self.assertEqual(first["num_outputs"], 1)
            self.assertIsNone(first["label_encoder"])
            self.assertEqual(first["tensors"]["train"]["y"].dtype, np.float32)
            self.assertEqual(
                first["tensors"]["train"]["row_indices"].tolist(),
                repeated["tensors"]["train"]["row_indices"].tolist(),
            )
            self.assertNotEqual(
                first["tensors"]["train"]["row_indices"].tolist(),
                different["tensors"]["train"]["row_indices"].tolist(),
            )
            self.assertEqual(first["feature_config_hash"], repeated["feature_config_hash"])
            self.assertNotEqual(first["feature_config_hash"], different["feature_config_hash"])

            run_dir = root / "regression_run"
            write_preprocess_artifacts(run_dir, first)
            self.assertFalse((run_dir / "preprocess" / "label_encoder.json").exists())

    def test_small_classification_split_degrades_without_duplicates_or_losing_train_labels(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = self._write(
                root,
                [
                    "x,target",
                    "1,A",
                    "2,A",
                    "3,B",
                ],
            )

            dataset = load_csv_tabular_dataset(path, target_column="target", seed=3)

            train_targets = set(dataset["tensors"]["train"]["y"].tolist())
            self.assertEqual(train_targets, {0, 1})
            all_indices = []
            for split in ("train", "val", "test"):
                all_indices.extend(dataset["tensors"][split]["row_indices"].tolist())
            self.assertEqual(sorted(all_indices), [0, 1, 2])
            self.assertEqual(len(set(all_indices)), 3)

    def test_hash_is_stable_but_changes_with_feature_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = self._write(
                root,
                [
                    "first,second,target,split",
                    "1,2,A,train",
                    "3,4,B,train",
                    "5,6,A,val",
                    "7,8,B,test",
                ],
            )

            original = load_csv_tabular_dataset(
                path,
                target_column="target",
                feature_columns=["first", "second"],
            )
            repeated = load_csv_tabular_dataset(
                path,
                target_column="target",
                feature_columns=["first", "second"],
            )
            reordered = load_csv_tabular_dataset(
                path,
                target_column="target",
                feature_columns=["second", "first"],
            )

            self.assertEqual(original["feature_config_hash"], repeated["feature_config_hash"])
            self.assertNotEqual(original["feature_config_hash"], reordered["feature_config_hash"])
            self.assertEqual(original["summary"]["dataset_hash"], original["dataset_hash"])
            self.assertNotIn(str(root), json.dumps(original["summary"]))

    def test_invalid_numeric_target_split_and_training_median_are_actionable(self):
        cases = [
            (
                ["x,target", "not-a-number,A", "2,B"],
                {},
                "non-numeric value",
            ),
            (
                ["x,target", "1,", "2,B"],
                {},
                "targets are not imputed",
            ),
            (
                ["x,target,split", "1,A,train", "2,B,holdout"],
                {},
                "invalid value",
            ),
            (
                ["x,target,split", ",A,train", ",B,train", "2,A,val"],
                {},
                "median cannot be fitted",
            ),
        ]
        for rows, kwargs, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as temp_dir:
                path = self._write(Path(temp_dir), rows)
                with self.assertRaisesRegex(TabularDatasetError, message):
                    load_csv_tabular_dataset(path, target_column="target", **kwargs)

    def test_ratio_validation_and_utf8_bom_headers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "bom.csv"
            path.write_text("x,target\n1,A\n2,A\n3,B\n4,B\n", encoding="utf-8-sig")

            dataset = load_csv_tabular_dataset(path, target_column="target")
            self.assertEqual(dataset["feature_columns"], ["x"])

            with self.assertRaisesRegex(TabularDatasetError, "add up to 1.0"):
                load_csv_tabular_dataset(
                    path,
                    target_column="target",
                    train_ratio=0.8,
                    val_ratio=0.2,
                    test_ratio=0.2,
                )


if __name__ == "__main__":
    unittest.main()
