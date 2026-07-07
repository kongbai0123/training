import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InferencePageStaticTests(unittest.TestCase):
    def test_inference_output_uses_token_authenticated_blob_url(self):
        api_js = (ROOT / "static" / "api.js").read_text(encoding="utf-8")
        inference_js = (ROOT / "static" / "pages" / "inference.js").read_text(encoding="utf-8")

        self.assertIn("export async function apiFetchBlob", api_js)
        self.assertIn('extraHeaders["X-VTS-Token"] = token;', api_js)
        self.assertIn("return res.blob();", api_js)
        self.assertIn("import { apiFetch, apiFetchBlob }", inference_js)
        self.assertIn("const blob = await apiFetchBlob(imageUrl", inference_js)
        self.assertIn("URL.createObjectURL(blob)", inference_js)
        self.assertIn("window.open(resultImageObjectUrl", inference_js)
        self.assertNotIn("outputImg.src = `${result.urls.annotated_image}?t=${Date.now()}`;", inference_js)


if __name__ == "__main__":
    unittest.main()
