import unittest

from fastapi.testclient import TestClient

from app import app


class FrontendCacheHeaderTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def assert_no_store_cache_header(self, path):
        response = self.client.get(path)
        self.assertEqual(200, response.status_code)
        cache_control = response.headers.get("cache-control", "")
        self.assertIn("no-store", cache_control)
        self.assertIn("no-cache", cache_control)
        self.assertIn("max-age=0", cache_control)
        self.assertEqual("no-cache", response.headers.get("pragma"))
        self.assertEqual("0", response.headers.get("expires"))

    def test_index_is_not_cached(self):
        self.assert_no_store_cache_header("/")

    def test_app_js_is_not_cached(self):
        self.assert_no_store_cache_header("/static/app.js")

    def test_auto_labeling_module_is_not_cached_even_with_version_query(self):
        self.assert_no_store_cache_header(
            "/static/pages/auto_labeling.js?v=20260703-auto-workbench-rules"
        )


if __name__ == "__main__":
    unittest.main()
