import unittest
from types import SimpleNamespace

import numpy as np

from src.inference_engine import InferenceEngine


class _TensorLike:
    def __init__(self, value):
        self.value = np.array(value)

    def item(self):
        return self.value.item()

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.value


class _SequenceLike:
    def __init__(self, values):
        self.values = values

    def __len__(self):
        return len(self.values)

    def __getitem__(self, index):
        return _TensorLike(self.values[index])


class InferenceMaskPolygonTests(unittest.TestCase):
    def test_render_predictions_exports_polygon_points_from_segmentation_mask(self):
        original = np.zeros((80, 100, 3), dtype=np.uint8)
        mask = np.zeros((80, 100), dtype=np.float32)
        mask[20:60, 15:70] = 1.0
        class Boxes:
            cls = _SequenceLike([0])
            conf = _SequenceLike([0.95])
            xyxy = _SequenceLike([[15, 20, 70, 60]])

            def __len__(self):
                return 1

        result = SimpleNamespace(boxes=Boxes(), masks=SimpleNamespace(data=_SequenceLike([mask])))

        predictions, _, mask_area_ratio = InferenceEngine._render_predictions(
            original=original,
            result=result,
            class_names={0: "road"},
            mask_opacity=0.45,
            show_mask=True,
            show_bbox=True,
            class_filter=None,
        )

        self.assertEqual(len(predictions), 1)
        self.assertEqual(predictions[0]["class_name"], "road")
        self.assertGreater(mask_area_ratio, 0)
        self.assertGreaterEqual(len(predictions[0]["polygon_points"]), 4)
        self.assertEqual(predictions[0]["bbox_xyxy"], [15, 20, 70, 60])


if __name__ == "__main__":
    unittest.main()
