from __future__ import annotations

from src.project_assistant_service import ASSISTANT_MODES, ProjectAssistantService

# Backward-compatible import alias only. Product-facing code should import
# ProjectAssistantService from src.project_assistant or src.project_assistant_service.
RagWorkbenchService = ProjectAssistantService

__all__ = ["ASSISTANT_MODES", "ProjectAssistantService", "RagWorkbenchService"]
