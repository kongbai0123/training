from typing import Dict, Any

class ConfigRecommender:
    @staticmethod
    def recommend(task_type: str, vram_mb: float, dataset_size: int) -> Dict[str, Any]:
        """
        根據 task_type、GPU VRAM 與資料集大小推薦訓練超參數
        """
        is_seg = "segmentation" in task_type or "seg" in task_type
        
        # 1. 推薦模型
        if is_seg:
            if vram_mb < 6000: # < 6GB
                model = "yolov8n-seg.pt"
                batch = 4
                imgsz = 640
                workers = 2
            elif vram_mb < 12000: # 6~12GB
                model = "yolov8s-seg.pt"
                batch = 8
                imgsz = 640
                workers = 4
            else: # >= 12GB
                model = "yolov8s-seg.pt" # 或者是 yolov8m-seg.pt
                batch = 16
                imgsz = 768
                workers = 4
        else:
            if vram_mb < 6000:
                model = "yolov8n.pt"
                batch = 8
                imgsz = 640
                workers = 2
            elif vram_mb < 12000:
                model = "yolov8s.pt"
                batch = 16
                imgsz = 640
                workers = 4
            else:
                model = "yolov8m.pt"
                batch = 32
                imgsz = 640
                workers = 4

        # 2. 推薦 Epoch 與 Patience
        if dataset_size < 500:
            epochs = 80
            patience = 20
        elif dataset_size <= 3000:
            epochs = 100
            patience = 25
        else:
            epochs = 120
            patience = 30

        return {
            "model": model,
            "epochs": epochs,
            "batch_size": batch,
            "imgsz": imgsz,
            "lr0": 0.01,
            "patience": patience,
            "workers": workers,
            "cache": False,
            "amp": True,
            "seed": 42,
            "save_period": 5,
            "close_mosaic": 10
        }
