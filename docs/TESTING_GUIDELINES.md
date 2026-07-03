# Testing Guidelines

## API route patch targets

Tests may import the FastAPI application from `app.py` for `TestClient` setup:

```python
from app import app
```

Tests must not patch internal symbols through `app.py`, for example:

```python
patch("app.ProjectManager.get_project")
patch.object(app, "require_feature")
```

Patch the module that owns the route or service dependency instead:

```python
patch("src.api.routes.training_orchestration.ProjectManager.get_project")
patch("src.api.routes.inference.require_feature")
```

This keeps `app.py` as the application composition entrypoint and prevents route
tests from depending on compatibility imports.
