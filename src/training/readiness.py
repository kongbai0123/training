import json
from pathlib import Path
from typing import Dict, Any, List
from src.model_store import ModelStore

def validate_training_readiness(project: Dict[str, Any], config_data: Dict[str, Any]) -> List[str]:
    """
    驗證專案與訓練設定的就緒性，回傳錯誤訊息清單。若清單為空，表示通過驗證。
    """
    errors = []
    
    # 1. 專案基本資料檢查
    class_names = project.get("class_names", [])
    if not class_names:
        errors.append("類別清單 (class_names) 不能為空。")
        
    images = project.get("images", [])
    if not images:
        errors.append("專案中沒有任何影像數據。")
        return errors # 沒有影像後面很多檢查無法繼續，直接回傳
        
    # 2. 劃分集檢查
    train_count = sum(1 for img in images if img.get("split") == "train")
    val_count = sum(1 for img in images if img.get("split") == "val")
    if train_count == 0:
        errors.append("訓練集 (train split) 影像數量不能為 0。請在 [3. 分散] 階段完成切分。")
    if val_count == 0:
        errors.append("驗證集 (val split) 影像數量不能為 0。請在 [3. 分散] 階段完成切分。")

    # 3. 任務類型檢查與正規化
    project_task = str(project.get("task_type", "detection")).lower()
    if project_task in {"instance_segmentation", "semantic_segmentation", "seg", "segmentation"}:
        project_task = "segmentation"
    elif project_task in {"det", "detection", "object_detection"}:
        project_task = "detection"
    elif project_task in {"cls", "classification"}:
        project_task = "classification"
    elif project_task in {"pose", "keypoints"}:
        project_task = "pose"
    elif project_task in {"obb", "oriented_bounding_box"}:
        project_task = "obb"

    valid_tasks = {"detection", "segmentation", "classification", "pose", "obb"}
    if project_task not in valid_tasks:
        errors.append(f"不支援的專案任務類型: {project_task}。")

    # 4. 模型任務類型與專案任務類型匹配檢查
    try:
        resolved_model = ModelStore.resolve_training_model(config_data.get("model") or "yolov8n.pt")
    except ValueError as exc:
        errors.append(str(exc))
        resolved_model = config_data.get("model") or "yolov8n.pt"
    model_path = Path(str(resolved_model))
    manifest_task = None
    manifest_path = model_path.parent / "model_manifest.json"
    if model_path.is_absolute() and manifest_path.exists():
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_task = str(manifest_data.get("task_family") or "").lower()
        except Exception:
            manifest_task = None
    model_name = model_path.name.lower()
    
    # 從模型檔名猜測其任務類型
    if manifest_task in {"segmentation", "detection", "classification", "pose", "obb"}:
        model_task = manifest_task
    elif "-seg" in model_name or "seg" in model_name:
        model_task = "segmentation"
    elif "-cls" in model_name or "cls" in model_name:
        model_task = "classification"
    elif "-pose" in model_name or "pose" in model_name:
        model_task = "pose"
    elif "-obb" in model_name or "obb" in model_name:
        model_task = "obb"
    else:
        model_task = "detection"

    if model_task != project_task:
        errors.append(f"模型任務類型 ({model_task}) 與專案任務類型 ({project_task}) 不匹配，請選擇相符的 YOLO 權重模型。")

    # 5. 標註內容一致性與格式檢查
    has_any_labels = False
    train_labeled = False
    val_labeled = False
    train_polygon_ok = False
    val_polygon_ok = False

    for img in images:
        split = img.get("split")
        annotations = img.get("annotations", [])
        if annotations:
            has_any_labels = True
            if split == "train":
                train_labeled = True
            elif split == "val":
                val_labeled = True

            # 針對 segmentation 多邊形檢查
            for ann in annotations:
                points = ann.get("points")
                if isinstance(points, list) and len(points) >= 3:
                    if split == "train":
                        train_polygon_ok = True
                    elif split == "val":
                        val_polygon_ok = True

    if not has_any_labels:
        errors.append("沒有偵測到任何標註數據。請至 [2. 標註] 進行標註。")
    else:
        if not train_labeled:
            errors.append("訓練集 (train split) 的影像全部沒有標註！請先在 [2. 標註] 階段完成標註。")
        if not val_labeled:
            errors.append("驗證集 (val split) 的影像全部沒有標註！請先在 [2. 標註] 階段完成標註。")

        if project_task == "segmentation":
            if not train_polygon_ok:
                errors.append("分割任務的訓練集 (train) 中沒有任何有效多邊形 (polygon) 標註！請確認已在 LabelMe 中完成多邊形繪製。")
            if not val_polygon_ok:
                errors.append("分割任務的驗證集 (val) 中沒有 any 有效多邊形 (polygon) 標註！請確認已在 LabelMe 中完成多邊形繪製。")

        # 針對標註資料的細部格式驗證
        for img in images:
            filename = img.get("filename", "unknown")
            annotations = img.get("annotations", [])
            for ann in annotations:
                cat = ann.get("category")
                if cat not in class_names:
                    errors.append(f"影像 '{filename}' 的標註類別 '{cat}' 不存在於專案類別清單中。")
                
                # Segmentation 任務檢查
                if project_task == "segmentation":
                    points = ann.get("points")
                    if not points:
                        errors.append(f"分割任務出錯！影像 '{filename}' 的標註資料不包含多邊形頂點點位。")
                        continue
                    
                    # 檢查多邊形點的格式
                    if isinstance(points, list):
                        if len(points) == 0:
                            errors.append(f"影像 '{filename}' 包含空的多邊形標註。")
                        elif isinstance(points[0], (int, float)):
                            # 平坦的 list [x1, y1, x2, y2, ...]
                            if len(points) < 6 or len(points) % 2 != 0:
                                errors.append(f"影像 '{filename}' 的平坦多邊形點位數不足 3 個點 (至少 6 個坐標值) 或長度不為偶數。")
                        elif isinstance(points[0], list) or isinstance(points[0], tuple):
                            # [[x1, y1], [x2, y2], ...]
                            if len(points) < 3:
                                errors.append(f"影像 '{filename}' 的多邊形點數不足 3 個點。")
                            for pt in points:
                                if len(pt) < 2:
                                    errors.append(f"影像 '{filename}' 的多邊形標註點 {pt} 格式錯誤。")
                        else:
                            errors.append(f"影像 '{filename}' 的多邊形點位格式無效。")
                    else:
                        errors.append(f"影像 '{filename}' 的標註 points 欄位必須為列表格式。")
                        
                # Detection 任務檢查
                elif project_task == "detection":
                    bbox = ann.get("bbox")
                    points = ann.get("points")
                    if (not bbox or len(bbox) != 4) and not points:
                        errors.append(f"影像 '{filename}' 沒有有效的 bbox 或 points，無法自動生成 YOLO 偵測標註。")

    # 6. 訓練超參數有效性檢查
    batch_size = config_data.get("batch_size")
    imgsz = config_data.get("imgsz")
    device = config_data.get("device")
    
    if batch_size is not None:
        try:
            b_val = int(batch_size)
            if b_val <= 0:
                errors.append("Batch Size 必須大於 0。")
        except ValueError:
            errors.append("Batch Size 必須是有效的整數。")
            
    if imgsz is not None:
        try:
            i_val = int(imgsz)
            if i_val <= 0:
                errors.append("Image Size 必須大於 0。")
            elif i_val % 32 != 0:
                errors.append("Image Size 必須是 32 的倍數 (例如 320, 640)。")
        except ValueError:
            errors.append("Image Size 必須是有效的整數。")
            
    if device not in {"cpu", "gpu"}:
        errors.append("Device 設定值無效，僅支援 'cpu' 或 'gpu'。")
        
    return errors
