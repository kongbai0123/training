import unittest
from pathlib import Path

from scripts.check_opencv_compatibility import run_checks


class OpenCvCompatibilityTests(unittest.TestCase):
    def test_required_opencv_surface_and_application_integrations(self):
        result = run_checks(minimum_major=4)

        self.assertEqual(result["status"], "pass")
        self.assertGreaterEqual(result["required_symbols"], 20)
        self.assertGreaterEqual(result["polygon_points"], 3)

    def test_release_requirements_pin_validated_opencv_five_wheel(self):
        requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8").splitlines()

        self.assertIn("opencv-python==5.0.0.93", requirements)
        self.assertIn("torch==2.5.1+cu121", requirements)
        self.assertIn("torchvision==0.20.1+cu121", requirements)
        self.assertIn("onnx==1.21.0", requirements)


if __name__ == "__main__":
    unittest.main()
