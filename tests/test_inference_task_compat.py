import unittest

from src.inference_engine import InferenceEngine


class InferenceTaskCompatibilityTests(unittest.TestCase):
    def test_semantic_segmentation_project_matches_yolo_segment_task(self):
        self.assertEqual(InferenceEngine._normalize_task_family("semantic_segmentation"), "segmentation")
        self.assertEqual(InferenceEngine._normalize_task_family("segment"), "segmentation")

    def test_object_detection_project_matches_yolo_detect_task(self):
        self.assertEqual(InferenceEngine._normalize_task_family("object_detection"), "detection")
        self.assertEqual(InferenceEngine._normalize_task_family("detect"), "detection")


if __name__ == "__main__":
    unittest.main()
