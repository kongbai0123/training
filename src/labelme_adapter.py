import os
import json
import numpy as np
import cv2
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

class LabelMeAdapter:
    @staticmethod
    def sync_labelme_annotations(project_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        掃描並同步 LabelMe 的 JSON 標註。
        更新 project.json 中的 images 列表及其狀態。
        """
        dataset_path = Path(project_data["dataset_path"])
        labelme_dir = dataset_path / "raw" / "annotations" / "labelme"
        labelme_dir.mkdir(parents=True, exist_ok=True)
        
        class_names = project_data.get("class_names", [])
        class_to_idx = {name: i for i, name in enumerate(class_names)}
        
        images_list = project_data.get("images", [])
        image_map = {img["filename"]: img for img in images_list}
        
        # 統計
        stats = {
            "annotated": 0,
            "missing_json": 0,
            "corrupted_json": 0,
            "unknown_classes": set(),
            "total_images": 0
        }
        
        # 掃描實際的圖片
        img_dir = dataset_path / "raw" / "images"
        valid_exts = {".jpg", ".jpeg", ".png", ".bmp"}
        
        scanned_images = []
        if img_dir.exists():
            for f in img_dir.iterdir():
                if f.is_file() and f.suffix.lower() in valid_exts:
                    scanned_images.append(f.name)
                    
        stats["total_images"] = len(scanned_images)
        
        updated_images = []
        
        for filename in scanned_images:
            # 取得現有的 metadata
            img_meta = image_map.get(filename, {
                "filename": filename,
                "status": "unannotated",
                "scene": "unknown",
                "source_video": "",
                "annotations": [],
                "split": None,
                "quality": {}
            })
            
            # 若為擴充影像，跳過 LabelMe 同步 (擴充影像在 augmenter 處理)
            if img_meta.get("is_augmented", False):
                updated_images.append(img_meta)
                continue
                
            json_filename = Path(filename).with_suffix(".json")
            json_path = labelme_dir / json_filename
            
            if not json_path.exists():
                img_meta["status"] = "unannotated"
                img_meta["annotations"] = []
                stats["missing_json"] += 1
            else:
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        label_data = json.load(f)
                    
                    shapes = label_data.get("shapes", [])
                    img_w = label_data.get("imageWidth", img_meta.get("width", 100))
                    img_h = label_data.get("imageHeight", img_meta.get("height", 100))
                    
                    img_meta["width"] = img_w
                    img_meta["height"] = img_h
                    
                    temp_annotations = []
                    for shape in shapes:
                        label = shape.get("label")
                        points = shape.get("points", [])
                        shape_type = shape.get("shape_type", "polygon")
                        
                        if label not in class_to_idx:
                            stats["unknown_classes"].add(label)
                            
                        # 計算 BBox (供 Web UI 畫框顯示使用)
                        if len(points) >= 2:
                            pts = np.array(points)
                            x_min, y_min = np.min(pts, axis=0)
                            x_max, y_max = np.max(pts, axis=0)
                            
                            w = x_max - x_min
                            h = y_max - y_min
                            xc = x_min + w/2
                            yc = y_min + h/2
                            
                            # 歸一化
                            norm_bbox = [xc / img_w, yc / img_h, w / img_w, h / img_h]
                            
                            temp_annotations.append({
                                "category": label,
                                "type": "bbox" if shape_type == "rectangle" else "polygon",
                                "bbox": norm_bbox,
                                "points": points # 保留 polygon 的原始點
                            })
                            
                    if temp_annotations:
                        img_meta["status"] = "annotated"
                        img_meta["annotations"] = temp_annotations
                        stats["annotated"] += 1
                    else:
                        img_meta["status"] = "unannotated"
                        img_meta["annotations"] = []
                        stats["missing_json"] += 1
                        
                except Exception as e:
                    print(f"Error reading JSON {json_filename}: {e}")
                    img_meta["status"] = "unannotated"
                    img_meta["annotations"] = []
                    stats["corrupted_json"] += 1
                    
            updated_images.append(img_meta)
            
        project_data["images"] = updated_images
        
        # 更新 project.json 中的 progress
        annotated_count = sum(1 for img in updated_images if img.get("status") == "annotated")
        flagged_count = sum(1 for img in updated_images if img.get("status") == "flagged")
        skipped_count = sum(1 for img in updated_images if img.get("status") == "skipped")
        
        project_data["annotation_progress"] = {
            "total": len(updated_images),
            "annotated": annotated_count,
            "flagged": flagged_count,
            "skipped": skipped_count
        }
        
        return {
            "annotated": annotated_count,
            "missing_json": stats["missing_json"],
            "corrupted_json": stats["corrupted_json"],
            "unknown_classes": list(stats["unknown_classes"]),
            "total_images": stats["total_images"]
        }

    @staticmethod
    def get_labelme_shapes(project_data: Dict[str, Any], filename: str) -> Optional[Dict[str, Any]]:
        """讀取並回傳特定的 LabelMe JSON shape 數據"""
        dataset_path = Path(project_data["dataset_path"])
        json_filename = Path(filename).with_suffix(".json")
        json_path = dataset_path / "raw" / "annotations" / "labelme" / json_filename
        
        if not json_path.exists():
            return None
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    @staticmethod
    def convert_labelme(project_data: Dict[str, Any], export_type: str) -> Dict[str, Any]:
        """
        執行 LabelMe 標註轉換管線。
        支援 YOLO Detection, YOLO Segmentation, COCO JSON, 與 Semantic Mask
        """
        dataset_path = Path(project_data["dataset_path"])
        labelme_dir = dataset_path / "raw" / "annotations" / "labelme"
        
        class_names = project_data.get("class_names", [])
        class_to_idx = {name: i for i, name in enumerate(class_names)}
        
        # 篩選已標註影像
        images = [img for img in project_data.get("images", []) if img.get("status") == "annotated"]
        
        converted_count = 0
        errors = []
        
        if export_type == "yolo_detection":
            # 建立 YOLO labels 目錄
            labels_dir = dataset_path / "raw" / "labels"
            labels_dir.mkdir(parents=True, exist_ok=True)
            
            for img in images:
                fname = img["filename"]
                json_path = labelme_dir / Path(fname).with_suffix(".json")
                if not json_path.exists():
                    continue
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    img_w = data.get("imageWidth", 100)
                    img_h = data.get("imageHeight", 100)
                    
                    txt_path = labels_dir / Path(fname).with_suffix(".txt")
                    with open(txt_path, "w", encoding="utf-8") as txt_f:
                        for shape in data.get("shapes", []):
                            label = shape.get("label")
                            if label not in class_to_idx:
                                continue
                            cls_idx = class_to_idx[label]
                            
                            points = np.array(shape.get("points", []))
                            if len(points) < 2:
                                continue
                            
                            x_min, y_min = np.min(points, axis=0)
                            x_max, y_max = np.max(points, axis=0)
                            
                            w = x_max - x_min
                            h = y_max - y_min
                            xc = x_min + w/2
                            yc = y_min + h/2
                            
                            # 寫入 YOLO Detection 格式: class x_center y_center width height (normalized)
                            txt_f.write(f"{cls_idx} {xc/img_w:.6f} {yc/img_h:.6f} {w/img_w:.6f} {h/img_h:.6f}\n")
                    
                    converted_count += 1
                except Exception as e:
                    errors.append(f"{fname} 轉換失敗: {e}")

        elif export_type == "yolo_segmentation":
            labels_dir = dataset_path / "raw" / "labels"
            labels_dir.mkdir(parents=True, exist_ok=True)
            
            for img in images:
                fname = img["filename"]
                json_path = labelme_dir / Path(fname).with_suffix(".json")
                if not json_path.exists():
                    continue
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    img_w = data.get("imageWidth", 100)
                    img_h = data.get("imageHeight", 100)
                    
                    txt_path = labels_dir / Path(fname).with_suffix(".txt")
                    with open(txt_path, "w", encoding="utf-8") as txt_f:
                        for shape in data.get("shapes", []):
                            label = shape.get("label")
                            if label not in class_to_idx:
                                continue
                            cls_idx = class_to_idx[label]
                            
                            points = shape.get("points", [])
                            if len(points) < 3: # 多邊形至少需要 3 個點
                                continue
                            
                            # 歸一化並展平為 YOLO Segmentation 格式: class x1 y1 x2 y2 ... xn yn
                            pts_str = " ".join(f"{pt[0]/img_w:.6f} {pt[1]/img_h:.6f}" for pt in points)
                            txt_f.write(f"{cls_idx} {pts_str}\n")
                            
                    converted_count += 1
                except Exception as e:
                    errors.append(f"{fname} 轉換失敗: {e}")

        elif export_type == "coco":
            coco_data = {
                "info": {"description": "Vision Training Studio Export"},
                "images": [],
                "annotations": [],
                "categories": [{"id": i, "name": name, "supercategory": "none"} for i, name in enumerate(class_names)]
            }
            
            ann_id = 1
            for img_idx, img in enumerate(images):
                fname = img["filename"]
                json_path = labelme_dir / Path(fname).with_suffix(".json")
                if not json_path.exists():
                    continue
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    img_w = data.get("imageWidth", 100)
                    img_h = data.get("imageHeight", 100)
                    
                    coco_data["images"].append({
                        "id": img_idx + 1,
                        "width": img_w,
                        "height": img_h,
                        "file_name": fname
                    })
                    
                    for shape in data.get("shapes", []):
                        label = shape.get("label")
                        if label not in class_to_idx:
                            continue
                        cls_idx = class_to_idx[label]
                        
                        points = shape.get("points", [])
                        if len(points) < 2:
                            continue
                            
                        pts = np.array(points)
                        x_min, y_min = np.min(pts, axis=0)
                        x_max, y_max = np.max(pts, axis=0)
                        w = x_max - x_min
                        h = y_max - y_min
                        
                        # 展平 polygon 坐標
                        poly_flat = [float(coord) for pt in points for coord in pt]
                        
                        coco_data["annotations"].append({
                            "id": ann_id,
                            "image_id": img_idx + 1,
                            "category_id": cls_idx,
                            "segmentation": [poly_flat] if len(points) >= 3 else [],
                            "bbox": [float(x_min), float(y_min), float(w), float(h)],
                            "area": float(w * h),
                            "iscrowd": 0
                        })
                        ann_id += 1
                        
                    converted_count += 1
                except Exception as e:
                    errors.append(f"{fname} 轉換失敗: {e}")
                    
            # 寫入 coco.json
            coco_path = dataset_path / "coco.json"
            with open(coco_path, "w", encoding="utf-8") as f:
                json.dump(coco_data, f, indent=2, ensure_ascii=False)

        elif export_type == "semantic_mask":
            masks_dir = dataset_path / "raw" / "masks"
            masks_dir.mkdir(parents=True, exist_ok=True)
            
            for img in images:
                fname = img["filename"]
                json_path = labelme_dir / Path(fname).with_suffix(".json")
                if not json_path.exists():
                    continue
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    img_w = data.get("imageWidth", 100)
                    img_h = data.get("imageHeight", 100)
                    
                    # 建立單通道 Mask，0 代表背景
                    mask = np.zeros((img_h, img_w), dtype=np.uint8)
                    
                    for shape in data.get("shapes", []):
                        label = shape.get("label")
                        if label not in class_to_idx:
                            continue
                        # Class index 從 1 開始 (0 為背景)
                        cls_val = class_to_idx[label] + 1
                        
                        points = np.array(shape.get("points", []), dtype=np.int32)
                        if len(points) < 3:
                            continue
                        
                        cv2.fillPoly(mask, [points], int(cls_val))
                        
                    # 儲存為 PNG
                    mask_path = masks_dir / Path(fname).with_suffix(".png")
                    cv2.imwrite(str(mask_path.resolve()), mask)
                    converted_count += 1
                except Exception as e:
                    errors.append(f"{fname} 轉換失敗: {e}")
                    
        return {
            "success": True,
            "export_type": export_type,
            "converted_count": converted_count,
            "errors": errors
        }

    @staticmethod
    def convert_yolo_to_labelme(project_data: Dict[str, Any]) -> None:
        """
        將 raw/labels 下的所有 .txt 轉換為對應的 LabelMe .json (若該 .json 還不存在)。
        """
        dataset_path = Path(project_data["dataset_path"])
        labels_dir = dataset_path / "raw" / "labels"
        labelme_dir = dataset_path / "raw" / "annotations" / "labelme"
        img_dir = dataset_path / "raw" / "images"
        
        if not labels_dir.exists():
            return
            
        labelme_dir.mkdir(parents=True, exist_ok=True)
        class_names = project_data.get("class_names", [])
        
        # 建立圖片 filename 對應 width/height 的 map
        images_list = project_data.get("images", [])
        image_meta_map = {img["filename"]: img for img in images_list}
        
        valid_img_exts = {".jpg", ".jpeg", ".png", ".bmp"}
        
        for txt_file in labels_dir.glob("*.txt"):
            json_filename = txt_file.with_suffix(".json").name
            json_path = labelme_dir / json_filename
            
            # 若已存在 JSON，跳過轉換以避免覆蓋使用者的精確標註
            if json_path.exists():
                continue
                
            # 尋找對應的圖片檔
            base_name = txt_file.stem
            img_filename = None
            for ext in valid_img_exts:
                test_name = f"{base_name}{ext}"
                if (img_dir / test_name).exists():
                    img_filename = test_name
                    break
                    
            if not img_filename:
                continue
                
            # 取得圖片高寬
            img_meta = image_meta_map.get(img_filename, {})
            img_w = img_meta.get("width")
            img_h = img_meta.get("height")
            
            if not img_w or not img_h:
                # 實體讀取圖片以獲取寬高
                try:
                    img_path = img_dir / img_filename
                    if img_path.exists():
                        from PIL import Image
                        with Image.open(img_path) as pil_img:
                            img_w, img_h = pil_img.size
                        # 回寫到 meta 裡
                        img_meta["width"] = img_w
                        img_meta["height"] = img_h
                    else:
                        print(f"[YOLO to LabelMe] Image file does not exist: {img_path}")
                        continue
                except Exception as e:
                    print(f"[YOLO to LabelMe] Error reading image size for {img_filename}: {e}")
                    continue
            
            if not img_w or not img_h:
                continue
                
            # 解析 YOLO .txt 檔案
            shapes = []
            try:
                with open(txt_file, "r") as f:
                    lines = f.readlines()
                
                for line in lines:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        try:
                            class_idx = int(parts[0])
                            xc = float(parts[1])
                            yc = float(parts[2])
                            w = float(parts[3])
                            h = float(parts[4])
                        except ValueError:
                            continue
                            
                        if class_idx < 0 or class_idx >= len(class_names):
                            label = f"class_{class_idx}"
                        else:
                            label = class_names[class_idx]
                            
                        # 計算像素 bbox 座標
                        x1 = (xc - w/2) * img_w
                        y1 = (yc - h/2) * img_h
                        x2 = (xc + w/2) * img_w
                        y2 = (yc + h/2) * img_h
                        
                        shapes.append({
                            "label": label,
                            "points": [[x1, y1], [x2, y2]],
                            "group_id": None,
                            "description": "",
                            "shape_type": "rectangle",
                            "flags": {}
                        })
            except Exception as e:
                print(f"Error parsing yolo txt {txt_file.name}: {e}")
                continue
                
            # 建立 LabelMe JSON
            labelme_data = {
                "version": "5.0.1",
                "flags": {},
                "shapes": shapes,
                "imagePath": img_filename,
                "imageData": None,
                "imageHeight": img_h,
                "imageWidth": img_w
            }
            
            try:
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(labelme_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"Error writing JSON {json_filename}: {e}")
