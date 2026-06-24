import os
import json
import cv2
import numpy as np
from PIL import Image
import shutil
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Tuple

class DatasetUtils:
    @staticmethod
    def extract_frames(video_path: str, output_dir: str, fps: int = 1) -> List[str]:
        """讀取影片並自動抽幀"""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"無法開啟影片檔案: {video_path}")
            
        video_name = Path(video_path).stem
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        if video_fps <= 0:
            video_fps = 25.0
            
        # 決定抽幀間隔 (每隔多少幀抽一次)
        frame_interval = max(1, int(video_fps / fps))
        
        extracted_files = []
        frame_idx = 0
        saved_count = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            if frame_idx % frame_interval == 0:
                filename = f"frame_{video_name}_{saved_count:06d}.jpg"
                file_path = out_path / filename
                cv2.imwrite(str(file_path.resolve()), frame)
                extracted_files.append(filename)
                saved_count += 1
                
            frame_idx += 1
            
        cap.release()
        return extracted_files

    @staticmethod
    def dhash(image_path: str) -> str:
        """計算影像的 Difference Hash (dHash) 以進行重複檢查"""
        try:
            with Image.open(image_path) as img:
                # 縮放到 9x8 灰階
                img = img.convert('L').resize((9, 8), Image.Resampling.BILINEAR)
                pixels = np.array(img)
                # 計算左右相鄰像素之差
                diff = pixels[:, 1:] > pixels[:, :-1]
                # 轉成 16 進位字串
                return ''.join(f'{int("".join(map(str, row)), 2):02x}' for row in diff.astype(int))
        except Exception:
            return ""

    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        """計算兩 16 進位 Hash 字串的漢明距離"""
        if not hash1 or not hash2 or len(hash1) != len(hash2):
            return 999
        bin1 = bin(int(hash1, 16))[2:].zfill(64)
        bin2 = bin(int(hash2, 16))[2:].zfill(64)
        return sum(c1 != c2 for c1, c2 in zip(bin1, bin2))

    @staticmethod
    def analyze_image_quality(image_path: str) -> Dict[str, Any]:
        """
        利用 OpenCV/PIL 檢查影像品質
        包含：損毀、解析度過小、過暗、過曝、模糊、重複
        """
        result = {
            "corrupted": False,
            "width": 0,
            "height": 0,
            "blurriness": 0.0,
            "is_blurry": False,
            "brightness": 128.0,
            "is_dark": False,
            "is_overexposed": False,
            "status": "green", # green, yellow, red
            "warnings": []
        }
        
        # 1. 損毀與解析度檢查
        try:
            with Image.open(image_path) as img:
                w, h = img.size
                result["width"] = w
                result["height"] = h
                if w < 100 or h < 100:
                    result["warnings"].append("圖片解析度過小")
                    result["status"] = "yellow"
        except Exception:
            result["corrupted"] = True
            result["status"] = "red"
            result["warnings"].append("圖片損毀，無法載入")
            return result

        # 2. 亮度與模糊度檢查
        img_cv = cv2.imread(image_path)
        if img_cv is None:
            result["corrupted"] = True
            result["status"] = "red"
            result["warnings"].append("圖片格式損毀")
            return result
            
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        
        # 亮度平均值
        mean_brightness = float(np.mean(gray))
        result["brightness"] = mean_brightness
        if mean_brightness < 40:
            result["is_dark"] = True
            result["warnings"].append("影像亮度偏暗")
            result["status"] = "yellow" if result["status"] != "red" else "red"
        elif mean_brightness > 220:
            result["is_overexposed"] = True
            result["warnings"].append("影像亮度過曝")
            result["status"] = "yellow" if result["status"] != "red" else "red"

        # 模糊度 (Laplacian Variance)
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        result["blurriness"] = lap_var
        if lap_var < 80.0: # 模糊臨界點
            result["is_blurry"] = True
            result["warnings"].append("影像偏向模糊")
            result["status"] = "yellow" if result["status"] != "red" else "red"
            
        return result

    @staticmethod
    def get_dataset_health(images_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
        """計算資料集健康分數 (Dataset Health Score) 與分析摘要"""
        total = len(images_metadata)
        if total == 0:
            return {"score": 100, "warnings": ["無資料圖片"], "summary": {}}
            
        corrupted_cnt = sum(1 for img in images_metadata if img.get("quality", {}).get("corrupted", False))
        blurry_cnt = sum(1 for img in images_metadata if img.get("quality", {}).get("is_blurry", False))
        dark_cnt = sum(1 for img in images_metadata if img.get("quality", {}).get("is_dark", False))
        overexposed_cnt = sum(1 for img in images_metadata if img.get("quality", {}).get("is_overexposed", False))
        duplicate_cnt = sum(1 for img in images_metadata if img.get("quality", {}).get("is_duplicate", False))
        unannotated_cnt = sum(1 for img in images_metadata if img.get("status") == "unannotated")
        
        # 扣分法計算分數
        score = 100
        score -= (corrupted_cnt / total) * 100
        score -= (blurry_cnt / total) * 30
        score -= (dark_cnt / total) * 15
        score -= (overexposed_cnt / total) * 15
        score -= (duplicate_cnt / total) * 20
        score -= (unannotated_cnt / total) * 25
        
        score = max(0, min(100, int(score)))
        
        warnings = []
        if corrupted_cnt > 0:
            warnings.append(f"發現 {corrupted_cnt} 張損毀圖片 (必須修復)")
        if blurry_cnt / total > 0.2:
            warnings.append(f"模糊圖片比例過高 ({blurry_cnt}/{total})")
        if dark_cnt / total > 0.2:
            warnings.append("偏暗圖片比例過高，建議套用光照擴充")
        if duplicate_cnt / total > 0.1:
            warnings.append(f"發現重複影像達 {duplicate_cnt} 張，可能會影響評估指標真實性")
        if unannotated_cnt > 0:
            warnings.append(f"尚有 {unannotated_cnt} 張圖片未進行標註")
            
        return {
            "score": score,
            "warnings": warnings,
            "summary": {
                "total": total,
                "corrupted": corrupted_cnt,
                "blurry": blurry_cnt,
                "dark": dark_cnt,
                "overexposed": overexposed_cnt,
                "duplicate": duplicate_cnt,
                "unannotated": unannotated_cnt
            }
        }

    @staticmethod
    def get_thumbnail(project_id: str, filename: str) -> str:
        """
        獲取縮圖，若快取存在則直接讀取，否則生成 200x200 縮圖並儲存至 cache
        """
        from src.config import PROJECTS_DIR
        from src.project_layout import ProjectLayout
        from src.project_manager import ProjectManager
        proj_dir = PROJECTS_DIR / project_id
        project = ProjectManager.get_project(project_id)
        layout = ProjectLayout.from_project(project) if project else ProjectLayout(proj_dir)
        raw_img_path = layout.resolve_raw_images_dir().path / filename
        
        # 尋找原始影像或擴充影像路徑
        if not raw_img_path.exists():
            raw_img_path = proj_dir / "dataset" / "augmentations" / "augmented_images" / filename
            
        if not raw_img_path.exists():
            raise FileNotFoundError(f"找不到原始圖片: {filename}")
            
        cache_dir = proj_dir / "dataset" / ".cache" / "thumbnails"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        thumb_path = cache_dir / filename
        if thumb_path.exists():
            return str(thumb_path.resolve())
            
        # 生成縮圖
        try:
            with Image.open(raw_img_path) as img:
                img.thumbnail((200, 200))
                # 確保以原本的格式/RGB格式存檔
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(thumb_path, "JPEG", quality=85)
            return str(thumb_path.resolve())
        except Exception as e:
            print(f"Error generating thumbnail for {filename}: {e}")
            return str(raw_img_path.resolve())

    @staticmethod
    def import_zip_package(project_id: str, zip_file_path: str) -> Dict[str, Any]:
        """
        解壓縮 ZIP 檔案，掃描其中的圖片與 LabelMe JSON，將其歸類移入對應的資料夾
        """
        from src.config import PROJECTS_DIR
        from src.project_layout import ProjectLayout
        from src.project_manager import ProjectManager
        proj_dir = PROJECTS_DIR / project_id
        project = ProjectManager.get_project(project_id)
        layout = ProjectLayout.from_project(project) if project else ProjectLayout(proj_dir)
        
        temp_dir = proj_dir / "dataset" / ".tmp_zip"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 解壓縮
        try:
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
        except Exception as e:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            raise ValueError(f"ZIP 檔案解壓縮失敗: {e}")
            
        dest_img_dir = layout.resolve_raw_images_dir().path
        dest_labelme_dir = layout.resolve_current_labelme_dir().path
        dest_labels_dir = layout.resolve_current_yolo_labels_dir().path
        
        dest_img_dir.mkdir(parents=True, exist_ok=True)
        dest_labelme_dir.mkdir(parents=True, exist_ok=True)
        dest_labels_dir.mkdir(parents=True, exist_ok=True)
        
        valid_exts = {".jpg", ".jpeg", ".png", ".bmp"}
        imported_imgs = []
        imported_jsons = []
        imported_txts = []
        
        # 遞迴掃描解壓目錄
        for root, _, files in os.walk(temp_dir):
            for file in files:
                fpath = Path(root) / file
                ext = fpath.suffix.lower()
                
                if ext in valid_exts:
                    shutil.copy(str(fpath), str(dest_img_dir / file))
                    imported_imgs.append(file)
                elif ext == ".json":
                    # 簡易驗證是否為 LabelMe JSON (包含 shapes 欄位)
                    try:
                        with open(fpath, "r", encoding="utf-8") as json_f:
                            content = json.load(json_f)
                        if "shapes" in content:
                            shutil.copy(str(fpath), str(dest_labelme_dir / file))
                            imported_jsons.append(file)
                    except Exception:
                        pass
                elif ext == ".txt":
                    shutil.copy(str(fpath), str(dest_labels_dir / file))
                    imported_txts.append(file)
                        
        # 刪除暫存區
        shutil.rmtree(temp_dir)
        
        return {
            "imported_images_count": len(imported_imgs),
            "imported_jsons_count": len(imported_jsons),
            "imported_txts_count": len(imported_txts),
            "images": imported_imgs
        }
