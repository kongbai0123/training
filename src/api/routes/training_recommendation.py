from fastapi import APIRouter, HTTPException

import src.trainer as trainer_module
from src.project_manager import ProjectManager

router = APIRouter()


@router.get("/api/projects/{project_id}/train/recommend")
def recommend_config(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    vram_mb = 0
    try:
        if trainer_module.HAS_NVML:
            handle = trainer_module.nvmlDeviceGetHandleByIndex(0)
            mem_info = trainer_module.nvmlDeviceGetMemoryInfo(handle)
            vram_mb = int(mem_info.total / (1024 ** 2))
    except Exception:
        pass

    if vram_mb == 0:
        import torch

        if torch.cuda.is_available():
            try:
                vram_mb = int(torch.cuda.get_device_properties(0).total_memory / (1024 ** 2))
            except Exception:
                vram_mb = 8000
        else:
            vram_mb = 2000

    dataset_size = len([img for img in project.get("images", []) if not img.get("is_augmented", False)])
    task_type = project.get("task_type", "detection")

    from src.training.config_recommender import ConfigRecommender

    return ConfigRecommender.recommend(task_type, vram_mb, dataset_size)
