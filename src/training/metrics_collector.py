import csv
from pathlib import Path
from typing import Dict, List, Any, Optional

class MetricsCollector:
    @staticmethod
    def calculate_ema(data: List[float], alpha: float = 0.25) -> List[float]:
        """計算 EMA (Exponential Moving Average) 平滑資料"""
        if not data:
            return []
        ema = []
        current = data[0]
        for val in data:
            current = alpha * val + (1 - alpha) * current
            ema.append(round(current, 5))
        return ema

    @classmethod
    def parse_results_csv(cls, run_dir: Path, alpha: float = 0.25) -> Optional[Dict[str, Any]]:
        """
        解析 YOLO 產生的 results.csv 並轉換為包含 raw 與 smooth 的指標字典
        """
        csv_path = run_dir / "results.csv"
        if not csv_path.exists():
            return None

        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                # 讀取 CSV
                reader = csv.reader(f)
                headers = [h.strip() for h in next(reader)]
                rows = []
                for row in reader:
                    if not row:
                        continue
                    rows.append([val.strip() for val in row])

            if not rows:
                return None

            epochs = []
            raw_metrics: Dict[str, List[float]] = {h: [] for h in headers if h != "epoch"}
            
            # 部分 YOLO 版本 header 可能含有空白，清理之
            # 建立映射以防 header 名稱不同
            header_map = {}
            for h in headers:
                cleaned = h.replace(" ", "")
                header_map[cleaned] = h

            for row in rows:
                if len(row) < len(headers):
                    continue
                # 找出 epoch
                try:
                    epoch_idx = headers.index("epoch")
                    epoch_val = int(row[epoch_idx])
                except ValueError:
                    epoch_val = len(epochs) + 1
                
                epochs.append(epoch_val)

                for idx, val in enumerate(row):
                    if idx == headers.index("epoch"):
                        continue
                    header_name = headers[idx]
                    try:
                        f_val = float(val)
                    except ValueError:
                        f_val = 0.0
                    raw_metrics[header_name].append(f_val)

            # 計算 EMA 平滑
            smooth_metrics: Dict[str, List[float]] = {}
            for k, vals in raw_metrics.items():
                smooth_metrics[k] = cls.calculate_ema(vals, alpha)

            return {
                "epochs": epochs,
                "raw": raw_metrics,
                "smooth": smooth_metrics
            }
        except Exception as e:
            print(f"[MetricsCollector] Error parsing results.csv: {e}")
            return None
