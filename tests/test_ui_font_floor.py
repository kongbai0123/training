import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class UiFontFloorTests(unittest.TestCase):
    def test_first_party_styles_do_not_define_text_below_twelve_pixels(self):
        offenders = []
        for path in (STATIC / "styles").rglob("*.css"):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"font-size\s*:\s*(\d*\.?\d+)\s*(px|rem|em)", text, re.I):
                value = float(match.group(1))
                unit = match.group(2).lower()
                below_floor = value < 12 if unit == "px" else value < 0.75
                if below_floor:
                    line = text.count("\n", 0, match.start()) + 1
                    offenders.append(f"{path.relative_to(ROOT)}:{line} {match.group(0)}")
        self.assertEqual([], offenders, "\n".join(offenders))

    def test_first_party_chart_fonts_do_not_define_text_below_twelve_pixels(self):
        offenders = []
        pattern = re.compile(r"font\s*:\s*\{[^{}\r\n]*?\bsize\s*:\s*(\d*\.?\d+)")
        for path in STATIC.rglob("*.js"):
            if "vendor" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for match in pattern.finditer(text):
                if float(match.group(1)) < 12:
                    line = text.count("\n", 0, match.start()) + 1
                    offenders.append(f"{path.relative_to(ROOT)}:{line} {match.group(0)}")
        self.assertEqual([], offenders, "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
