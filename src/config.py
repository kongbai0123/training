import os
from pathlib import Path

# Base directories
# 優先使用環境變數 VTS_BASE_DIR，否則動態計算專案根目錄 (本檔案位於 src/ 下)
BASE_DIR = Path(os.environ.get("VTS_BASE_DIR", Path(__file__).resolve().parents[1])).resolve()
PROJECTS_DIR = BASE_DIR / "projects"
STATIC_DIR = BASE_DIR / "static"

# Ensure directories exist
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Device Configuration
# 延遲導入 torch，在無 PyTorch 環境下仍可正常啟動服務
try:
    import torch
    HAS_GPU = torch.cuda.is_available()
    DEVICE = "0" if HAS_GPU else "cpu"
    DEVICE_NAME = torch.cuda.get_device_name(0) if HAS_GPU else "CPU"
except ImportError:
    HAS_GPU = False
    DEVICE = "cpu"
    DEVICE_NAME = "CPU (PyTorch not installed)"

print(f"[Config] System initialized. BASE_DIR: {BASE_DIR}")
print(f"[Config] Device detected: {DEVICE_NAME} (Use GPU: {HAS_GPU})")
