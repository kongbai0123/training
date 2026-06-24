from __future__ import annotations

from pathlib import Path
import os
import sys


def _resolve_app_home() -> Path:
    explicit = os.environ.get("VTS_APP_HOME")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if getattr(sys, "frozen", False):
        internal_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        return internal_dir.resolve()
    base = Path(__file__).resolve().parents[1]
    return base.resolve()


def _resolve_user_data_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data).expanduser().resolve() / "VisionTrainingStudio"
    return Path.home() / "AppData" / "Local" / "VisionTrainingStudio"


APP_HOME = _resolve_app_home()
USER_DATA_DIR = _resolve_user_data_root()

PROJECTS_DIR = USER_DATA_DIR / "projects"
MODELS_DIR = USER_DATA_DIR / "models"
LOGS_DIR = USER_DATA_DIR / "logs"
CONFIG_DIR = USER_DATA_DIR / "config"
LICENSES_DIR = USER_DATA_DIR / "licenses"
CACHE_DIR = USER_DATA_DIR / "cache"
TMP_DIR = USER_DATA_DIR / "tmp"

def _ensure_dirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


_ensure_dirs(PROJECTS_DIR, MODELS_DIR, LOGS_DIR, CONFIG_DIR, LICENSES_DIR, CACHE_DIR, TMP_DIR)

# Backward compatible legacy directory for UI assets.
STATIC_DIR = APP_HOME / "static"
BASE_DIR = APP_HOME

APP_DATA_CONFIG = {
    "mode": os.environ.get("VTS_ENV", os.environ.get("VTS_MODE", "development")),
    "app_home": str(APP_HOME),
    "user_data_dir": str(USER_DATA_DIR),
}
