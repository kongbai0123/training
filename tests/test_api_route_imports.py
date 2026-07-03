import importlib
from pathlib import Path
import unittest

import app


ROUTE_MODULES = [
    "src.api.routes.annotation_labelme",
    "src.api.routes.augmentation",
    "src.api.routes.auto_labeling",
    "src.api.routes.dataset_split",
    "src.api.routes.datasets",
    "src.api.routes.diagnostics",
    "src.api.routes.evaluation",
    "src.api.routes.inference",
    "src.api.routes.models",
    "src.api.routes.monitor",
    "src.api.routes.project_layout",
    "src.api.routes.projects",
    "src.api.routes.rnn_config",
    "src.api.routes.system",
    "src.api.routes.training_orchestration",
    "src.api.routes.training_recommendation",
    "src.api.routes.training_runs",
]


EXPECTED_ROUTE_PATHS = {
    "/api/bootstrap",
    "/api/diagnostics/report",
    "/api/projects",
    "/api/projects/{project_id}/models",
    "/api/projects/{project_id}/inference/image",
    "/api/projects/{project_id}/images/{filename}",
    "/api/projects/{project_id}/split",
    "/api/projects/{project_id}/annotations",
    "/api/projects/{project_id}/augment-preview",
    "/api/projects/{project_id}/auto-labeling/status",
    "/api/projects/{project_id}/evaluation",
    "/api/projects/{project_id}/rnn/config",
    "/api/projects/{project_id}/train/start",
    "/api/projects/{project_id}/train/recommend",
    "/api/projects/{project_id}/train/status",
    "/api/projects/{project_id}/monitor",
}


class ApiRouteImportSmokeTests(unittest.TestCase):
    def test_route_modules_import_and_expose_router(self):
        for module_name in ROUTE_MODULES:
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                router = getattr(module, "router", None)
                self.assertIsNotNone(router)
                self.assertGreater(len(router.routes), 0)

    def test_app_registers_expected_route_paths(self):
        registered_paths = {route.path for route in app.app.routes if hasattr(route, "path")}
        missing = EXPECTED_ROUTE_PATHS - registered_paths
        self.assertEqual(missing, set())

    def test_tests_do_not_patch_app_internal_symbols(self):
        tests_dir = Path(__file__).resolve().parent
        forbidden_patterns = [
            "patch(" + '"app.',
            "patch(" + "'app.",
            "patch.object(" + "app,",
        ]
        violations = []
        for test_file in tests_dir.glob("test_*.py"):
            text = test_file.read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                if pattern in text:
                    violations.append(f"{test_file.name}: {pattern}")

        self.assertEqual(
            violations,
            [],
            "Patch route or service modules directly instead of app.py compatibility symbols.",
        )


if __name__ == "__main__":
    unittest.main()
