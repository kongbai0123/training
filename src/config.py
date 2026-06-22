import os
from pathlib import Path
import torch

# Base directories
BASE_DIR = Path("d:/software/yolo").resolve()
PROJECTS_DIR = BASE_DIR / "projects"
STATIC_DIR = BASE_DIR / "static"

# Ensure directories exist
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Device Configuration
HAS_GPU = torch.cuda.is_available()
DEVICE = "0" if HAS_GPU else "cpu"
DEVICE_NAME = torch.cuda.get_device_name(0) if HAS_GPU else "CPU"

print(f"[Config] System initialized. BASE_DIR: {BASE_DIR}")
print(f"[Config] Device detected: {DEVICE_NAME} (Use GPU: {HAS_GPU})")
