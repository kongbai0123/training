import tempfile
import unittest
from pathlib import Path

from src.api.routes.annotation_labelme import build_labelme_open_command


class LabelMeOpenCommandTests(unittest.TestCase):
    def test_labelme_open_command_uses_project_labels_file_not_comma_string(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images_dir = root / "images"
            labelme_dir = root / "labelme"
            images_dir.mkdir()

            command = build_labelme_open_command(
                "labelme.exe",
                images_dir,
                labelme_dir,
                ["asphalt", "Belgian", "cement", "asphalt", " "],
            )

            self.assertIn("--labels", command)
            labels_path = Path(command[command.index("--labels") + 1])
            self.assertEqual(labels_path.name, "_project_labels.txt")
            self.assertEqual(labels_path.read_text(encoding="utf-8").splitlines(), ["asphalt", "Belgian", "cement"])
            self.assertIn("--validatelabel", command)
            self.assertIn("exact", command)
            self.assertNotIn("asphalt,Belgian,cement", command)


if __name__ == "__main__":
    unittest.main()
