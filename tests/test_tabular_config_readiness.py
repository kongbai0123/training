import tempfile
import unittest
from pathlib import Path

from src.tabular_config import inspect_tabular_csv, validate_tabular_config


class TabularConfigReadinessTests(unittest.TestCase):
    def inspect(self, rows: list[str]):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "business.csv"
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")
            return inspect_tabular_csv(path)

    @staticmethod
    def config(**overrides):
        return {
            "feature_columns": ["revenue"],
            "target_column": "outcome",
            "id_column": "account_id",
            "split_column": "split",
            "task_head": "classification",
            "missing_strategy": "median",
            "train_ratio": 0.7,
            "val_ratio": 0.15,
            "test_ratio": 0.15,
            **overrides,
        }

    def test_valid_business_classification_accepts_string_labels_and_split_aliases(self):
        inspection = self.inspect([
            "account_id,revenue,outcome,split",
            "A-01,1200,retain,training",
            "A-02,900,churn,train",
            "A-03,1300,retain,validation",
            "A-04,850,churn,dev",
            "A-05,1400,retain,testing",
            "A-06,800,churn,test",
        ])

        validation = validate_tabular_config(self.config(), inspection)

        self.assertTrue(validation["valid"], validation["errors"])
        self.assertEqual(
            inspection["column_profiles"]["split"]["split_counts"],
            {"train": 2, "val": 2, "test": 2},
        )

    def test_invalid_or_incomplete_provided_split_is_blocked_before_training(self):
        invalid = self.inspect([
            "account_id,revenue,outcome,split",
            "A-01,1200,retain,train",
            "A-02,900,churn,holdout",
            "A-03,1300,retain,train",
            "A-04,850,churn,train",
            "A-05,1400,retain,train",
            "A-06,800,churn,train",
        ])

        errors = validate_tabular_config(self.config(), invalid)["errors"]

        self.assertTrue(any("values must be train" in message for message in errors))
        self.assertTrue(any("validation row" in message for message in errors))

    def test_valid_business_regression_accepts_finite_numeric_targets(self):
        inspection = self.inspect([
            "account_id,revenue,outcome",
            "A-01,1200,18.5",
            "A-02,900,12.0",
            "A-03,1300,20.1",
            "A-04,850,10.2",
            "A-05,1400,22.4",
            "A-06,800,9.8",
        ])

        validation = validate_tabular_config(
            self.config(split_column="", task_head="regression"), inspection
        )

        self.assertTrue(validation["valid"], validation["errors"])

    def test_target_contract_errors_are_reported_during_configuration(self):
        missing_target = self.inspect([
            "account_id,revenue,outcome",
            "A-01,1200,retain",
            "A-02,900,churn",
            "A-03,1300,retain",
            "A-04,850,",
            "A-05,1400,retain",
            "A-06,800,churn",
        ])
        missing_errors = validate_tabular_config(
            self.config(split_column=""), missing_target
        )["errors"]
        self.assertTrue(any("missing values" in message for message in missing_errors))

        text_regression = self.inspect([
            "account_id,revenue,outcome",
            "A-01,1200,high",
            "A-02,900,low",
            "A-03,1300,high",
            "A-04,850,low",
            "A-05,1400,high",
            "A-06,800,low",
        ])
        regression_errors = validate_tabular_config(
            self.config(split_column="", task_head="regression"), text_regression
        )["errors"]
        self.assertTrue(any("finite numeric" in message for message in regression_errors))

        single_label = self.inspect([
            "account_id,revenue,outcome",
            "A-01,1200,retain",
            "A-02,900,retain",
            "A-03,1300,retain",
            "A-04,850,retain",
            "A-05,1400,retain",
            "A-06,800,retain",
        ])
        classification_errors = validate_tabular_config(
            self.config(split_column=""), single_label
        )["errors"]
        self.assertTrue(any("two distinct labels" in message for message in classification_errors))


if __name__ == "__main__":
    unittest.main()
