import unittest

from src.training.rnn.trainer import _diagnostics as rnn_diagnostics
from src.training.rnn.xgboost_trainer import _diagnostics as xgb_diagnostics


class RNNTrainingDiagnosticsTests(unittest.TestCase):
    def test_classification_diagnostics_write_confusion_matrix(self):
        payload = rnn_diagnostics(predictions=[0, 1, 1, 0], targets=[0, 1, 0, 1], is_regression=False)

        self.assertEqual(payload["confusion_labels"], ["0", "1"])
        self.assertEqual(payload["confusion_matrix"], [[1, 1], [1, 1]])

    def test_regression_diagnostics_write_residual_and_prediction_actual_samples(self):
        payload = rnn_diagnostics(predictions=[1.5, 2.0], targets=[1.0, 2.25], is_regression=True)

        self.assertEqual(payload["residuals"], [0.5, -0.25])
        self.assertEqual(
            payload["prediction_actual_samples"],
            [
                {"prediction": 1.5, "actual": 1.0, "residual": 0.5},
                {"prediction": 2.0, "actual": 2.25, "residual": -0.25},
            ],
        )

    def test_xgboost_diagnostics_share_same_payload_contract(self):
        payload = xgb_diagnostics(predictions=[1, 0], targets=[1, 1], is_regression=False)

        self.assertEqual(payload["confusion_labels"], ["0", "1"])
        self.assertEqual(payload["confusion_matrix"], [[0, 0], [1, 1]])


if __name__ == "__main__":
    unittest.main()
