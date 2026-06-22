import os
import json
import base64
import shutil
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from PIL import Image
from src.config import BASE_DIR, PROJECTS_DIR, STATIC_DIR, HAS_GPU, DEVICE_NAME
from src.project_manager import ProjectManager
from src.dataset_utils import DatasetUtils
from src.splitter import DataSplitter
from src.augmenter import ImageAugmenter
from src.trainer import YOLOTrainer
from src.labelme_adapter import LabelMeAdapter

app = FastAPI(title="Vision Training Studio API")

# 1. 載入靜態網頁資源
# 如果 static/ 不存在，建立它
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR.resolve())), name="static")

# 根目錄直接重定向到 index.html
@app.get("/")
def get_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        # 若 index.html 還沒建立，回傳簡單歡迎語
        return {"message": "Vision Training Studio backend is running. static/index.html not found."}
    return FileResponse(str(index_path))

# --- Pydantic Models ---
class ProjectCreate(BaseModel):
    project_name: str
    task_type: str
    class_names: List[str]

class AnnotationSave(BaseModel):
    filename: str
    status: str # annotated, flagged, skipped
    scene: Optional[str] = "unknown"
    source_video: Optional[str] = ""
    annotations: List[Dict[str, Any]]

class SplitRequest(BaseModel):
    method: str # basic, stratified, scene, group
    ratio: Dict[str, float] # e.g. {"train": 0.7, "val": 0.2, "test": 0.1}

class AugmentPreviewRequest(BaseModel):
    filename: str
    config: Dict[str, Any]

class TrainConfigRequest(BaseModel):
    model: str
    epochs: int
    batch_size: int
    imgsz: int
    lr0: float
    device: str

# --- API Endpoints ---

# 1. 專案管理 API
@app.get("/api/projects")
def list_projects():
    return ProjectManager.get_all_projects()

@app.post("/api/projects")
def create_project(data: ProjectCreate):
    try:
        project = ProjectManager.create_project(data.project_name, data.task_type, data.class_names)
        return project
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    success = ProjectManager.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found or unable to delete")
    return {"message": "Project deleted successfully"}

# 2. 資料集與圖片存取 API
@app.get("/api/projects/{project_id}/images/{filename}")
def get_project_image(project_id: str, filename: str):
    """取得專案中的原始圖片"""
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    img_path = Path(project["dataset_path"]) / "raw" / "images" / filename
    # 若在 raw 找不到，去 augmented_images 找 (物理擴充產生的圖)
    if not img_path.exists():
        img_path = Path(project["dataset_path"]) / "augmentations" / "augmented_images" / filename
        
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
        
    return FileResponse(str(img_path))

@app.post("/api/projects/{project_id}/import-local")
def import_local_folder(project_id: str, path: str = Form(...)):
    """匯入本機資料夾中的圖片"""
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    import_path = Path(path)
    if not import_path.exists() or not import_path.is_dir():
        raise HTTPException(status_code=400, detail="指定的路徑不存在或不是資料夾")
        
    dest_dir = Path(project["dataset_path"]) / "raw" / "images"
    imported = []
    
    # 支援副檔名
    valid_exts = {".jpg", ".jpeg", ".png", ".bmp"}
    
    for f in import_path.iterdir():
        if f.is_file() and f.suffix.lower() in valid_exts:
            shutil.copy(str(f), str(dest_dir / f.name))
            imported.append(f.name)
            
    # 更新 project.json 結構
    for fname in imported:
        # 避免重複加入
        if any(img["filename"] == fname for img in project["images"]):
            continue
            
        project["images"].append({
            "filename": fname,
            "status": "unannotated",
            "scene": "unknown",
            "source_video": "",
            "annotations": [],
            "split": None,
            "quality": {}
        })
        
    project["annotation_progress"]["total"] = len(project["images"])
    ProjectManager.save_project(project_id, project)
    
    return {"message": f"成功匯入 {len(imported)} 張圖片", "imported": imported}

@app.post("/api/projects/{project_id}/import-video")
def import_video(project_id: str, video_path: str = Form(...), fps: int = Form(1)):
    """匯入本機影片並自動抽幀"""
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    v_path = Path(video_path)
    if not v_path.exists() or not v_path.is_file():
        raise HTTPException(status_code=400, detail="影片檔案不存在")
        
    dest_dir = Path(project["dataset_path"]) / "raw" / "images"
    
    try:
        filenames = DatasetUtils.extract_frames(str(v_path), str(dest_dir), fps)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"抽幀失敗: {str(e)}")
        
    # 將抽出的幀加入 project.json 并記錄 source_video
    for fname in filenames:
        if any(img["filename"] == fname for img in project["images"]):
            continue
        project["images"].append({
            "filename": fname,
            "status": "unannotated",
            "scene": "unknown",
            "source_video": v_path.name, # 用作後續 Group Split
            "annotations": [],
            "split": None,
            "quality": {}
        })
        
    project["annotation_progress"]["total"] = len(project["images"])
    ProjectManager.save_project(project_id, project)
    
    return {"message": f"成功從影片抽幀並匯入 {len(filenames)} 張圖片", "imported_count": len(filenames)}

@app.post("/api/projects/{project_id}/quality-check")
def trigger_quality_check(project_id: str):
    """觸發資料品質檢查並計算重複雜湊"""
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    dataset_path = Path(project["dataset_path"])
    images_list = project.get("images", [])
    
    # 1. 進行個別圖片的品質掃描
    hashes = {}
    for img in images_list:
        fname = img["filename"]
        img_path = dataset_path / "raw" / "images" / fname
        if not img_path.exists():
            continue
            
        quality = DatasetUtils.analyze_image_quality(str(img_path))
        img["quality"] = quality
        
        # 計算 dHash
        h = DatasetUtils.dhash(str(img_path))
        hashes[fname] = h
        
    # 2. 重複圖片檢查 (比對雜湊值)
    for fname, h in hashes.items():
        is_duplicate = False
        for other_fname, other_h in hashes.items():
            if fname == other_fname:
                continue
            if DatasetUtils.hamming_distance(h, other_h) <= 5:
                is_duplicate = True
                break
                
        # 尋找對應的 metadata 並標記
        for img in images_list:
            if img["filename"] == fname:
                img["quality"]["is_duplicate"] = is_duplicate
                if is_duplicate:
                    img["quality"]["status"] = "yellow"
                    if "可能為重複/極相似影像" not in img["quality"]["warnings"]:
                        img["quality"]["warnings"].append("可能為重複/極相似影像")
                break
                
    # 3. 計算整個資料集的健康度健康評估報告
    health_report = DatasetUtils.get_dataset_health(images_list)
    project["dataset_health"] = health_report
    
    ProjectManager.save_project(project_id, project)
    return health_report

# 3. 標註 API
@app.post("/api/projects/{project_id}/annotations")
def save_annotations(project_id: str, data: AnnotationSave):
    """保存單張圖片的標註，並同步寫入 LabelMe JSON 標註檔案"""
    import numpy as np
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    dataset_path = Path(project["dataset_path"])
    
    # 讀取圖片高寬
    img_path = dataset_path / "raw" / "images" / data.filename
    w, h = 640, 640
    if img_path.exists():
        try:
            with Image.open(img_path) as pil_img:
                w, h = pil_img.size
        except Exception:
            pass
            
    # 建立 LabelMe JSON 檔
    labelme_shapes = []
    for ann in data.annotations:
        label = ann.get("category")
        pts = ann.get("points")
        shape_type = ann.get("type", "bbox")
        
        if not pts:
            # bbox: [xc, yc, bw, bh] (normalized) -> points: [[x1,y1], [x2,y2]] (pixels)
            bbox = ann.get("bbox")
            if bbox and len(bbox) == 4:
                x1 = (bbox[0] - bbox[2]/2) * w
                y1 = (bbox[1] - bbox[3]/2) * h
                x2 = (bbox[0] + bbox[2]/2) * w
                y2 = (bbox[1] + bbox[3]/2) * h
                pts = [[float(x1), float(y1)], [float(x2), float(y2)]]
                shape_type = "rectangle"
                
        if pts:
            labelme_shapes.append({
                "label": label,
                "points": pts,
                "group_id": None,
                "shape_type": "rectangle" if shape_type == "bbox" or shape_type == "rectangle" else "polygon",
                "flags": {}
            })
            
    labelme_json = {
        "version": "5.0.1",
        "flags": {},
        "shapes": labelme_shapes,
        "imagePath": data.filename,
        "imageData": None,
        "imageHeight": h,
        "imageWidth": w
    }
    
    # 寫入 json
    labelme_dir = dataset_path / "raw" / "annotations" / "labelme"
    labelme_dir.mkdir(parents=True, exist_ok=True)
    json_path = labelme_dir / Path(data.filename).with_suffix(".json")
    
    try:
        with open(json_path, "w", encoding="utf-8") as json_f:
            json.dump(labelme_json, json_f, indent=2, ensure_ascii=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LabelMe JSON 寫入失敗: {e}")
        
    # 尋找並更新對應圖片的元數據
    found = False
    for img in project["images"]:
        if img["filename"] == data.filename:
            img["status"] = data.status
            img["scene"] = data.scene
            img["source_video"] = data.source_video
            img["width"] = w
            img["height"] = h
            # 對於原始圖像，annotations 會由後續 sync 從 json 載入
            # 但為了前端能立即渲染，這裡也直接更新它
            temp_anns = []
            for shape in labelme_shapes:
                # 重新歸一化 bbox
                pts_arr = np.array(shape["points"])
                x_min, y_min = np.min(pts_arr, axis=0)
                x_max, y_max = np.max(pts_arr, axis=0)
                bw = x_max - x_min
                bh = y_max - y_min
                xc = x_min + bw/2
                yc = y_min + bh/2
                temp_anns.append({
                    "category": shape["label"],
                    "type": "bbox" if shape["shape_type"] == "rectangle" else "polygon",
                    "bbox": [xc/w, yc/h, bw/w, bh/h],
                    "points": shape["points"]
                })
            img["annotations"] = temp_anns
            found = True
            break
            
    if not found:
        raise HTTPException(status_code=404, detail="Image metadata not found in project")
        
    # 重新計算標註進度
    total = len(project["images"])
    annotated = sum(1 for img in project["images"] if img["status"] == "annotated")
    flagged = sum(1 for img in project["images"] if img["status"] == "flagged")
    skipped = sum(1 for img in project["images"] if img["status"] == "skipped")
    
    project["annotation_progress"] = {
        "total": total,
        "annotated": annotated,
        "flagged": flagged,
        "skipped": skipped
    }
    
    ProjectManager.save_project(project_id, project)
    return {"message": "標註儲存成功", "progress": project["annotation_progress"]}


# --- 全新 LabelMe 與 縮圖 / ZIP API ---

@app.post("/api/projects/{project_id}/labelme/sync")
def sync_labelme(project_id: str):
    """觸發 LabelMe JSON 掃描與 project.json 同步"""
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    try:
        report = LabelMeAdapter.sync_labelme_annotations(project)
        ProjectManager.save_project(project_id, project)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步失敗: {e}")

@app.get("/api/projects/{project_id}/labelme/preview/{filename}")
def get_labelme_preview(project_id: str, filename: str):
    """取得特定圖片的原始 LabelMe shapes"""
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    shapes_data = LabelMeAdapter.get_labelme_shapes(project, filename)
    if not shapes_data:
        return {"shapes": [], "imageHeight": 640, "imageWidth": 640}
    return shapes_data

class ConvertRequest(BaseModel):
    export_type: str # yolo_detection, yolo_segmentation, coco, semantic_mask

@app.post("/api/projects/{project_id}/labelme/convert")
def convert_labelme_labels(project_id: str, req: ConvertRequest):
    """執行標註檔案轉換 (如 YOLO, COCO 或 Mask)"""
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    try:
        res = LabelMeAdapter.convert_labelme(project, req.export_type)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"轉換失敗: {e}")

@app.get("/api/projects/{project_id}/thumbnails/{filename}")
def get_image_thumbnail(project_id: str, filename: str):
    """獲取快取縮圖 API"""
    try:
        thumb_path = DatasetUtils.get_thumbnail(project_id, filename)
        return FileResponse(thumb_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Image not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/projects/{project_id}/import-zip")
def import_zip_dataset(project_id: str, file: UploadFile = File(...)):
    """上傳與解壓縮 ZIP 格式資料集 (包含 images & json)"""
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    # 保存上傳的 zip 檔
    temp_zip_dir = Path(project["dataset_path"]) / ".tmp_zip_upload"
    temp_zip_dir.mkdir(parents=True, exist_ok=True)
    temp_zip_path = temp_zip_dir / "upload.zip"
    
    try:
        with open(temp_zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 執行解壓縮與分類導入
        import_res = DatasetUtils.import_zip_package(project_id, str(temp_zip_path))
        
        # 同步元數據
        sync_res = LabelMeAdapter.sync_labelme_annotations(project)
        ProjectManager.save_project(project_id, project)
        
        return {
            "message": "ZIP 資料包導入完成",
            "imported_images": import_res["imported_images_count"],
            "imported_jsons": import_res["imported_jsons_count"],
            "sync_status": sync_res
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ZIP 匯入失敗: {e}")
    finally:
        # 清理暫存 zip
        if temp_zip_path.exists():
            os.remove(temp_zip_path)
        if temp_zip_dir.exists():
            shutil.rmtree(temp_zip_dir)

@app.post("/api/projects/{project_id}/import-annotations")
def import_annotations(project_id: str, files: List[UploadFile] = File(...)):
    """上傳多個已標註之標註檔 (.json 或 .txt) 至專案對應目錄中"""
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    dataset_path = Path(project["dataset_path"])
    labelme_dir = dataset_path / "raw" / "annotations" / "labelme"
    labels_dir = dataset_path / "raw" / "labels"
    
    labelme_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)
    
    imported_jsons = 0
    imported_txts = 0
    
    try:
        for file in files:
            fname = file.filename
            if fname.endswith(".json"):
                target_path = labelme_dir / fname
                with open(target_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                imported_jsons += 1
            elif fname.endswith(".txt"):
                target_path = labels_dir / fname
                with open(target_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                imported_txts += 1
                
        # 同步標註進度
        sync_res = LabelMeAdapter.sync_labelme_annotations(project)
        ProjectManager.save_project(project_id, project)
        
        return {
            "message": f"成功匯入 {imported_jsons} 個 JSON 檔案與 {imported_txts} 個 TXT 檔案",
            "imported_jsons": imported_jsons,
            "imported_txts": imported_txts,
            "sync_status": sync_res
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"標註檔案匯入失敗: {e}")


class UpdateClassesRequest(BaseModel):
    class_names: List[str]

@app.post("/api/projects/{project_id}/classes")
def update_project_classes(project_id: str, req: UpdateClassesRequest):
    """更新專案類別 (class_names)"""
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    project["class_names"] = req.class_names
    ProjectManager.save_project(project_id, project)
    
    # 執行一次標註同步更新以對齊最新類別
    sync_res = LabelMeAdapter.sync_labelme_annotations(project)
    ProjectManager.save_project(project_id, project)
    
    return {
        "message": "專案類別更新成功",
        "class_names": project["class_names"],
        "sync_status": sync_res
    }


# 4. 資料切分 API
@app.post("/api/projects/{project_id}/split")
def split_dataset(project_id: str, req: SplitRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    # 執行切分
    splits, quality_report = DataSplitter.split_dataset(
        images=project["images"],
        class_names=project["class_names"],
        method=req.method,
        ratio=req.ratio
    )
    
    # 將切分結果寫入 project.json 中每張圖片的 split 屬性
    for img in project["images"]:
        fname = img["filename"]
        if fname in splits["train"]:
            img["split"] = "train"
        elif fname in splits["val"]:
            img["split"] = "val"
        elif fname in splits["test"]:
            img["split"] = "test"
        else:
            img["split"] = None
            
    project["split_config"] = {
        "method": req.method,
        "ratio": req.ratio,
        "split_quality_score": quality_report["score"]
    }
    project["split_report"] = quality_report
    
    ProjectManager.save_project(project_id, project)
    return {"message": "資料切分成功", "report": quality_report}

# 5. 物理擴充 API
@app.post("/api/projects/{project_id}/augment-preview")
def preview_augmentation(project_id: str, req: AugmentPreviewRequest):
    """針對單張影像套用擴充設定並回傳 Base64 預覽圖"""
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    img_metadata = next((img for img in project["images"] if img["filename"] == req.filename), None)
    if not img_metadata:
        raise HTTPException(status_code=404, detail="Image metadata not found")
        
    dataset_path = Path(project["dataset_path"])
    raw_img_path = dataset_path / "raw" / "images" / req.filename
    if not raw_img_path.exists():
        raise HTTPException(status_code=404, detail="Image file not found")
        
    try:
        # 套用擴充
        aug_img, aug_bboxes = ImageAugmenter.augment_single_image(
            str(raw_img_path),
            img_metadata.get("annotations", []),
            req.config
        )
        
        # 將擴充後的圖片畫上變換後的 BBox 以供視覺化預覽
        preview_img = aug_img.copy()
        h, w, _ = preview_img.shape
        for ann in aug_bboxes:
            bbox = ann["bbox"] # [xc, yc, bw, bh]
            xc, yc, bw, bh = bbox[0]*w, bbox[1]*h, bbox[2]*w, bbox[3]*h
            x1 = int(xc - bw/2)
            y1 = int(yc - bh/2)
            x2 = int(xc + bw/2)
            y2 = int(yc + bh/2)
            cv2.rectangle(preview_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(preview_img, ann["category"], (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            
        # 轉換為 Base64
        _, encoded_img = cv2.imencode(".jpg", preview_img)
        base64_str = base64.b64encode(encoded_img).decode("utf-8")
        
        return {"preview": f"data:image/jpeg;base64,{base64_str}", "bboxes": aug_bboxes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"擴充預覽生成失敗: {str(e)}")

@app.post("/api/projects/{project_id}/apply-augmentation")
def apply_augmentation(project_id: str, req: Dict[str, Any]):
    """套用物理擴充，將擴充影像實體寫入 augmented_images 目錄，並在 metadata 中註冊"""
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    dataset_path = Path(project["dataset_path"])
    aug_dir = dataset_path / "augmentations" / "augmented_images"
    # 清空先前的擴充結果
    if aug_dir.exists():
        shutil.rmtree(aug_dir)
    aug_dir.mkdir(parents=True, exist_ok=True)
    
    # 過濾出原本已經被劃分在 "train" 或是 val 的圖片
    # 或者是使用者指定要套用的 split (通常為 train 集)
    target_split = req.get("target_split", "train")
    multiplier = int(req.get("multiplier", 1)) # 每張圖片生成多少張擴充副本
    config = req.get("config", {})
    
    train_images = [img for img in project["images"] if img.get("split") == target_split and img.get("status") == "annotated"]
    
    if len(train_images) == 0:
        raise HTTPException(status_code=400, detail="沒有已標註的訓練集圖片，無法進行擴充。")
        
    augmented_list = []
    # 保留非擴充圖片的 metadata
    original_images = [img for img in project["images"] if not img.get("is_augmented", False)]
    
    for img in train_images:
        fname = img["filename"]
        raw_img_path = dataset_path / "raw" / "images" / fname
        if not raw_img_path.exists():
            continue
            
        for i in range(multiplier):
            try:
                aug_img, aug_bboxes = ImageAugmenter.augment_single_image(
                    str(raw_img_path),
                    img.get("annotations", []),
                    config
                )
                
                # 生成新檔名
                new_fname = f"aug_{i}_{fname}"
                dest_path = aug_dir / new_fname
                cv2.imwrite(str(dest_path.resolve()), aug_img)
                
                # 建立擴充圖片的元數據，並歸類在對應的 split
                augmented_list.append({
                    "filename": new_fname,
                    "status": "annotated",
                    "scene": img.get("scene", "unknown"),
                    "source_video": img.get("source_video", ""),
                    "annotations": aug_bboxes,
                    "split": target_split,
                    "is_augmented": True,
                    "quality": {"status": "green", "warnings": []}
                })
            except Exception as e:
                print(f"Failed to augment {fname}: {e}")
                
    # 將擴充圖片註冊回 project.json
    project["images"] = original_images + augmented_list
    project["annotation_progress"]["total"] = len(project["images"])
    project["augmentation_config"] = config
    
    ProjectManager.save_project(project_id, project)
    return {"message": f"成功生成 {len(augmented_list)} 張物理擴充影像"}

# 6. 訓練 API
@app.post("/api/projects/{project_id}/train/start")
def start_training(project_id: str, config: TrainConfigRequest):
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    # 檢查防呆
    # 沒有完成 split 不能訓練
    has_split = any(img.get("split") is not None for img in project["images"])
    if not has_split:
        raise HTTPException(status_code=400, detail="請先在 [3. 分散] 階段完成資料集切分")
        
    # 類別數為 0 不能訓練
    if len(project["class_names"]) == 0:
        raise HTTPException(status_code=400, detail="類別數量不能為 0")
        
    # 更新訓練設定
    project["training_config"] = {
        "model": config.model,
        "epochs": config.epochs,
        "batch_size": config.batch_size,
        "imgsz": config.imgsz,
        "lr0": config.lr0,
        "device": config.device
    }
    ProjectManager.save_project(project_id, project)
    
    # 啟動背景訓練
    YOLOTrainer.start_training(project)
    return {"status": "started", "message": "訓練已成功啟動"}

@app.post("/api/projects/{project_id}/train/stop")
def stop_training(project_id: str):
    YOLOTrainer.stop_training(project_id)
    return {"status": "stopped", "message": "訓練中止中，正在釋放記憶體..."}

@app.get("/api/projects/{project_id}/train/status")
def get_train_status(project_id: str):
    return YOLOTrainer.get_status(project_id)

# --- WebSocket 監控連線 ---
@app.websocket("/api/projects/{project_id}/monitor")
async def monitor_training(websocket: WebSocket, project_id: str):
    await websocket.accept()
    print(f"[WS] Client connected to monitor project {project_id}")
    try:
        while True:
            # 每秒讀取一次最新的訓練進度與 GPU/CPU telemetry
            status = YOLOTrainer.get_status(project_id)
            await websocket.send_json(status)
            
            # 若訓練已結束、中止或出錯，可以稍微減緩推送，但持續保持連線或等待客戶端關閉
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        print(f"[WS] Client disconnected from {project_id}")
    except Exception as e:
        print(f"[WS] Error in monitor loop: {e}")
        try:
            await websocket.close()
        except:
            pass

# 7. 模型與報告匯出 API
@app.get("/api/projects/{project_id}/export")
def export_model(project_id: str):
    """匯出 YOLO pt / ONNX 模型檔"""
    project = ProjectManager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    dataset_path = Path(project["dataset_path"])
    runs_dir = dataset_path.parent / "training" / "runs" / "train"
    best_pt = runs_dir / "weights" / "best.pt"
    
    if not best_pt.exists():
        raise HTTPException(status_code=400, detail="最佳模型檔案不存在，可能訓練尚未完成。")
        
    # 一併匯出為 ONNX 格式
    try:
        model = YOLO(str(best_pt.resolve()))
        # export 會產生 best.onnx
        model.export(format="onnx")
        best_onnx = runs_dir / "weights" / "best.onnx"
        
        # 複製到專案 export 目錄下
        export_pt = dataset_path.parent / "exports" / "onnx" / "best.pt"
        export_onnx = dataset_path.parent / "exports" / "onnx" / "best.onnx"
        
        shutil.copy(str(best_pt), str(export_pt))
        if best_onnx.exists():
            shutil.copy(str(best_onnx), str(export_onnx))
            
        return {
            "success": True,
            "pt_path": str(export_pt.resolve().as_posix()),
            "onnx_path": str(export_onnx.resolve().as_posix() if best_onnx.exists() else "")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模型匯出失敗: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print(f"Starting Vision Training Studio Server...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
