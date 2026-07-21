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


def _find_portable_root(start: Path) -> Path | None:
    # Portable storage must be explicitly enabled beside the executable.
    # Scanning parent folders can accidentally adopt a source checkout and leak
    # its projects or logs into a packaged release.
    if (start / "portable.mode").is_file():
        return start.resolve()
    return None


def _resolve_user_data_root() -> Path:
    explicit = os.environ.get("VTS_USER_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        portable_root = _find_portable_root(exe_dir)
        if portable_root:
            return portable_root
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return (Path(local_app_data).expanduser() / "VisionTrainingStudio").resolve()
        return (Path.home() / "AppData" / "Local" / "VisionTrainingStudio").resolve()
    return APP_HOME


def _resolve_projects_dir(user_data_dir: Path) -> Path:
    explicit = os.environ.get("VTS_PROJECTS_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        portable_root = _find_portable_root(exe_dir)
        if portable_root:
            candidate = portable_root / "projects"
            if candidate.exists():
                return candidate.resolve()
    return user_data_dir / "projects"


def _resolve_models_dir(user_data_dir: Path) -> Path:
    explicit = os.environ.get("VTS_MODELS_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()

    # Explicit/portable user-data roots remain self-contained. During source
    # development, only projects stay in the checkout; downloaded models share
    # the same per-user store as the installed application.
    if os.environ.get("VTS_USER_DATA_DIR") or getattr(sys, "frozen", False):
        return (user_data_dir / "models").resolve()

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return (Path(local_app_data).expanduser() / "VisionTrainingStudio" / "models").resolve()
    return (user_data_dir / "models").resolve()


APP_HOME = _resolve_app_home()
USER_DATA_DIR = _resolve_user_data_root()

PROJECTS_DIR = _resolve_projects_dir(USER_DATA_DIR)
MODELS_DIR = _resolve_models_dir(USER_DATA_DIR)
LOGS_DIR = USER_DATA_DIR / "logs"
CONFIG_DIR = USER_DATA_DIR / "config"
LICENSES_DIR = USER_DATA_DIR / "licenses"
CACHE_DIR = USER_DATA_DIR / "cache"
TMP_DIR = USER_DATA_DIR / "tmp"
COMPONENTS_DIR = USER_DATA_DIR / "components"

def _ensure_dirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


_ensure_dirs(PROJECTS_DIR, MODELS_DIR, LOGS_DIR, CONFIG_DIR, LICENSES_DIR, CACHE_DIR, TMP_DIR, COMPONENTS_DIR)

# Backward compatible legacy directory for UI assets.
STATIC_DIR = APP_HOME / "static"
BASE_DIR = APP_HOME

APP_DATA_CONFIG = {
    "mode": os.environ.get("VTS_ENV", os.environ.get("VTS_MODE", "development")),
    "app_home": str(APP_HOME),
    "user_data_dir": str(USER_DATA_DIR),
    "projects_dir": str(PROJECTS_DIR),
}
