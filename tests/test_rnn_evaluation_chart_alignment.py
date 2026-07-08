import json
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RnnEvaluationChartAlignmentTests(unittest.TestCase):
    def test_sparse_final_metrics_keep_epoch_axis_alignment(self):
        script = textwrap.dedent(
            """
            globalThis.localStorage = {
              getItem() { return ""; },
              setItem() {},
              removeItem() {}
            };
            globalThis.document = {
              documentElement: { setAttribute() {} },
              body: { dataset: {}, classList: { toggle() {}, add() {}, remove() {} } },
              querySelectorAll() { return []; }
            };
            const mod = await import("./static/pages/rnn_evaluation_helpers.js");
            const dashboard = mod.buildRnnTaskAwareDashboard({
              metrics: { task_type: "sequence_regression" },
              history: [
                { epoch: 1, "train/loss": 8.4, "val/loss": 8.1 },
                { epoch: 2, "train/loss": 8.3, "val/loss": 8.0 },
                { epoch: 3, "train/loss": 8.2, "val/loss": 7.9, "val/mae": 6.6, "val/rmse": 8.0 }
              ]
            });
            const mae = dashboard.scoreChart.series.find((item) => item.key === "val/mae");
            const loss = dashboard.lossChart.series.find((item) => item.key === "train/loss");
            console.log(JSON.stringify({
              labels: dashboard.scoreChart.labels,
              maeValues: mae.values,
              maePointCount: mae.pointCount,
              lossValues: loss.values
            }));
            """
        )
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)

        self.assertEqual(payload["labels"], [1, 2, 3])
        self.assertEqual(payload["maeValues"], [None, None, 6.6])
        self.assertEqual(payload["maePointCount"], 1)
        self.assertEqual(payload["lossValues"], [8.4, 8.3, 8.2])


if __name__ == "__main__":
    unittest.main()
