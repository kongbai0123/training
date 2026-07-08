import unittest

from fastapi.testclient import TestClient

from app import app
from src.api.error_response import build_error, normalize_error_response


class ApiStructuredErrorTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_http_exception_returns_normalized_error_contract(self):
        response = self.client.get("/api/not-found-for-structured-error-test")
        self.assertEqual(404, response.status_code)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertEqual("API_ERROR", body["error"]["code"])
        self.assertEqual("Not Found", body["error"]["message"])
        self.assertEqual(404, body["error"]["status"])
        self.assertIn("suggestion", body["error"])
        self.assertIn("retryable", body["error"])
        self.assertIn("field_errors", body["error"])

    def test_nested_http_exception_detail_is_not_wrapped_as_message_dict(self):
        nested = {"detail": build_error("AUTH_REQUIRED", "Missing token", 401)}
        body = normalize_error_response(nested, status_code=401)
        self.assertFalse(body["success"])
        self.assertEqual("AUTH_REQUIRED", body["error"]["code"])
        self.assertEqual("Missing token", body["error"]["message"])
        self.assertEqual(401, body["error"]["status"])
        self.assertIsInstance(body["error"]["details"], dict)


if __name__ == "__main__":
    unittest.main()
