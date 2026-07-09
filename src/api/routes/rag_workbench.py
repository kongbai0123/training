from __future__ import annotations

# Backward-compatible route module only. Primary routes live in
# src.api.routes.project_assistant and expose /api/project-assistant/*.
from src.api.routes.project_assistant import router

__all__ = ["router"]
