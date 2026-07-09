import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class I18nCatalogIntegrityTests(unittest.TestCase):
    def test_zh_tw_catalog_is_clean_and_key_compatible_with_en(self):
        zh_tw_js = (ROOT / "static" / "state" / "i18n" / "zh-TW.js").read_text(encoding="utf-8")

        self.assertIn("export const zhTWOverrides = {", zh_tw_js)
        self.assertIn("export const zhTW = {", zh_tw_js)
        self.assertNotIn("Object.assign(zhTW", zh_tw_js)
        self.assertNotRegex(zh_tw_js, r"[\uFFFD\uE000-\uF8FF]|嚗|銝|撠|蝣|閮|隢||||||")

        check_script = """
            import { en } from './static/state/i18n/en.js';
            import { zhTW, zhTWOverrides } from './static/state/i18n/zh-TW.js';
            const enKeys = Object.keys(en).sort();
            const zhKeys = Object.keys(zhTW).sort();
            const overrideOnly = Object.keys(zhTWOverrides).filter((key) => !Object.prototype.hasOwnProperty.call(en, key));
            if (JSON.stringify(enKeys) !== JSON.stringify(zhKeys)) {
              console.error(JSON.stringify({ en: enKeys.length, zh: zhKeys.length }));
              process.exit(1);
            }
            if (overrideOnly.length) {
              console.error(JSON.stringify({ overrideOnly }));
              process.exit(2);
            }
        """
        subprocess.run(
            ["node", "--input-type=module", "-e", check_script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
