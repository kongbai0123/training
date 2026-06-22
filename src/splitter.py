import random
import numpy as np
from collections import defaultdict
from typing import Dict, Any, List, Tuple

class DataSplitter:
    @staticmethod
    def calculate_split_quality(images: List[Dict[str, Any]], splits: Dict[str, List[str]], class_names: List[str], expected_ratio: Dict[str, float]) -> Dict[str, Any]:
        """
        計算資料切分品質分數與相關指標
        """
        # 1. 統計各 split 的圖片數量
        split_counts = {k: len(v) for k, v in splits.items()}
        total_imgs = sum(split_counts.values())
        if total_imgs == 0:
            return {"score": 0, "class_distribution": {}, "warnings": ["沒有切分任何圖片"]}

        # 2. 統計各 split 中各類別的數量
        class_distribution = {k: {cls: 0 for cls in class_names} for k in splits.keys()}
        total_class_counts = {cls: 0 for cls in class_names}
        
        # 建立 filename 對應 metadata
        img_map = {img["filename"]: img for img in images}
        
        for split_name, filenames in splits.items():
            for fname in filenames:
                img = img_map.get(fname)
                if not img:
                    continue
                for ann in img.get("annotations", []):
                    cat = ann.get("category")
                    if cat in class_distribution[split_name]:
                        class_distribution[split_name][cat] += 1
                        total_class_counts[cat] += 1

        # 3. 計算品質分數 (扣分法)
        # 對比每個類別的 Train/Val/Test 實際比例與預期比例的 RMSE
        rmse_sum = 0
        active_classes = 0
        
        warnings = []
        for cls in class_names:
            total_cls = total_class_counts[cls]
            if total_cls == 0:
                warnings.append(f"類別 '{cls}' 在整個資料集中數量為 0")
                continue
                
            active_classes += 1
            cls_rmse = 0
            for split_name, expected in expected_ratio.items():
                actual = class_distribution[split_name][cls] / total_cls
                cls_rmse += (actual - expected) ** 2
                
                # 若 Validation 或 Test 完全沒有該類別
                if actual == 0 and expected > 0:
                    warnings.append(f"類別 '{cls}' 在 '{split_name}' 集完全缺失")
                    
            rmse_sum += np.sqrt(cls_rmse / len(expected_ratio))

        # RMSE 平均值映射到分數 (RMSE 越大分數越低)
        avg_rmse = rmse_sum / max(1, active_classes)
        score = int(max(0, 100 - (avg_rmse * 150))) # 誤差 15% 以上即扣分
        
        # 額外扣分：若某些 Split 完全無資料
        for k, v in split_counts.items():
            if v == 0 and expected_ratio[k] > 0:
                score = max(0, score - 30)
                warnings.append(f"分組 '{k}' 中無任何圖片")

        return {
            "score": score,
            "split_counts": split_counts,
            "class_distribution": class_distribution,
            "warnings": warnings[:5] # 只回傳前 5 個重要警告
        }

    @staticmethod
    def split_dataset(
        images: List[Dict[str, Any]],
        class_names: List[str],
        method: str = "stratified",
        ratio: Dict[str, float] = None
    ) -> Tuple[Dict[str, List[str]], Dict[str, Any]]:
        """
        核心切分函式：支援 basic, stratified, scene, group (source-aware)
        """
        if ratio is None:
            ratio = {"train": 0.7, "val": 0.2, "test": 0.1}
            
        # 確保比例總和為 1.0
        r_sum = sum(ratio.values())
        norm_ratio = {k: v / r_sum for k, v in ratio.items()}
        
        filenames = [img["filename"] for img in images]
        random.seed(42) # 固定種子以保證可複現
        
        splits = {"train": [], "val": [], "test": []}
        
        if len(filenames) == 0:
            return splits, {"score": 0, "warnings": ["沒有圖片可切分"]}

        # 1. 來源/影片分組切分 (Group Split)
        if method == "group":
            # 依影片來源分組
            groups = defaultdict(list)
            for img in images:
                src = img.get("source_video", "")
                if not src:
                    # 沒有影片來源的當作獨立的組
                    src = f"solo_{img['filename']}"
                groups[src].append(img["filename"])
                
            # 將組 (影片檔) 隨機洗牌並按比例分配
            group_keys = list(groups.keys())
            random.shuffle(group_keys)
            
            acc = 0.0
            for k in group_keys:
                r = random.random()
                # 依累積機率分配組
                if r < norm_ratio["train"]:
                    splits["train"].extend(groups[k])
                elif r < norm_ratio["train"] + norm_ratio["val"]:
                    splits["val"].extend(groups[k])
                else:
                    splits["test"].extend(groups[k])

        # 2. 場景分組切分 (Scene-aware Split)
        elif method == "scene":
            # 依場景分組，並在各場景組內進行比例隨機切分
            scene_groups = defaultdict(list)
            for img in images:
                scene = img.get("scene", "unknown")
                scene_groups[scene].append(img["filename"])
                
            for scene, fnames in scene_groups.items():
                random.shuffle(fnames)
                n = len(fnames)
                n_train = int(n * norm_ratio["train"])
                n_val = int(n * norm_ratio["val"])
                
                splits["train"].extend(fnames[:n_train])
                splits["val"].extend(fnames[n_train:n_train+n_val])
                splits["test"].extend(fnames[n_train+n_val:])

        # 3. 分層隨機切分 (Stratified Split)
        elif method == "stratified":
            # 統計每張圖片含有的最稀有類別
            # 首先計算整體類別總數
            class_counts = defaultdict(int)
            for img in images:
                for ann in img.get("annotations", []):
                    class_counts[ann.get("category")] += 1
            
            # 將類別以稀有度排序 (次數越少越稀有)
            sorted_classes = sorted(class_names, key=lambda c: class_counts[c])
            
            # 依圖片包含的最稀有類別對圖片進行歸類
            bucket = defaultdict(list)
            unlabelled = []
            
            for img in images:
                anns = img.get("annotations", [])
                if not anns:
                    unlabelled.append(img["filename"])
                    continue
                
                # 尋找該圖片包含的最稀有類別
                found = False
                for c in sorted_classes:
                    if any(ann.get("category") == c for ann in anns):
                        bucket[c].append(img["filename"])
                        found = True
                        break
                if not found:
                    unlabelled.append(img["filename"])
            
            # 對每個 bucket 分別依比例分配
            for c, fnames in bucket.items():
                random.shuffle(fnames)
                n = len(fnames)
                n_train = int(n * norm_ratio["train"])
                n_val = int(n * norm_ratio["val"])
                splits["train"].extend(fnames[:n_train])
                splits["val"].extend(fnames[n_train:n_train+n_val])
                splits["test"].extend(fnames[n_train+n_val:])
                
            # 對未標註的圖片也依比例分配
            random.shuffle(unlabelled)
            n = len(unlabelled)
            n_train = int(n * norm_ratio["train"])
            n_val = int(n * norm_ratio["val"])
            splits["train"].extend(unlabelled[:n_train])
            splits["val"].extend(unlabelled[n_train:n_train+n_val])
            splits["test"].extend(unlabelled[n_train+n_val:])

        # 4. 基本隨機切分 (Basic Random Split)
        else:
            fnames = filenames.copy()
            random.shuffle(fnames)
            n = len(fnames)
            n_train = int(n * norm_ratio["train"])
            n_val = int(n * norm_ratio["val"])
            
            splits["train"] = fnames[:n_train]
            splits["val"] = fnames[n_train:n_train+n_val]
            splits["test"] = fnames[n_train+n_val:]

        # 計算切分品質報告
        quality_report = DataSplitter.calculate_split_quality(images, splits, class_names, norm_ratio)
        return splits, quality_report
