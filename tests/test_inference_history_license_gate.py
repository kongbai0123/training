import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from src.api.routes import inference


class InferenceHistoryLicenseGateTests(unittest.TestCase):
    def setUp(self):
        self.project = {"project_id": "proj_history_gate", "project_name": "history gate"}

    def test_list_inference_jobs_does_not_require_inference_license(self):
        with patch.object(inference.ProjectManager, "get_project", return_value=self.project), patch.object(
            inference.InferenceHistory, "list_jobs", return_value={"jobs": []}
        ), patch.object(inference, "require_feature", side_effect=AssertionError("history read should not require feature gate")):
            result = inference.list_inference_jobs("proj_history_gate")

        self.assertEqual(result, {"jobs": []})

    def test_get_inference_job_does_not_require_inference_license(self):
        payload = {"job_id": "job_1", "summary": {}}
        with patch.object(inference.ProjectManager, "get_project", return_value=self.project), patch.object(
            inference.InferenceHistory, "get_job", return_value=payload
        ), patch.object(inference, "require_feature", side_effect=AssertionError("history read should not require feature gate")):
            result = inference.get_inference_job("proj_history_gate", "job_1")

        self.assertEqual(result, payload)

    def test_run_image_inference_still_requires_inference_license(self):
        def blocked_feature(feature):
            def _raise():
                raise HTTPException(status_code=403, detail={"error": {"code": "FEATURE_DISABLED", "feature": feature}})

            return _raise

        with patch.object(inference, "require_feature", side_effect=blocked_feature):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(inference.run_image_inference("proj_history_gate"))

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail["error"]["feature"], "inference")


if __name__ == "__main__":
    unittest.main()
