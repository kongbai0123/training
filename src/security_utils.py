import re
from pathlib import Path
from typing import Set

def safe_filename(name: str) -> str:
    """
    清洗並返回安全的檔名，去除路徑穿越符與非法字元。
    """
    if not name:
        return "unnamed_file"
    # 只取檔名部分，防止路徑穿越
    filename = Path(name).name
    # 將所有非英數、底線、減號、點號的字元替換為底線
    sanitized = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', filename)
    # 避免開頭為點點等造成隱藏檔或路徑混淆
    if sanitized.startswith("..") or not sanitized:
        sanitized = "safe_" + sanitized
    return sanitized

def safe_resolve_under(base_dir: Path, target_path: Path) -> Path:
    """
    嚴格解析目標路徑，並確保其位於 base_dir 之下。若發生路徑穿越，拋出 ValueError。
    """
    resolved_base = base_dir.resolve()
    resolved_target = target_path.resolve()
    try:
        resolved_target.relative_to(resolved_base)
    except ValueError:
        raise ValueError(f"路徑越界存取被拒絕：{resolved_target} 不在 {resolved_base} 之下。")
    return resolved_target

def validate_extension(filename: str, allowed_extensions: Set[str]) -> str:
    """
    驗證檔案的副檔名是否包含在白名單中。
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_extensions:
        raise ValueError(f"不支援的檔案格式：'{suffix}'，僅支援 {allowed_extensions}。")
    return suffix

def sanitize_run_id(run_id: str) -> str:
    """
    驗證 run_id 格式是否安全。
    """
    if not run_id:
        raise ValueError("Run ID 不能為空。")
    if not re.fullmatch(r"[A-Za-z0-9_\-\.]+", run_id):
        raise ValueError(f"無效的 Run ID 格式：'{run_id}'。僅允許英數字、減號、底線與小數點。")
    return run_id
