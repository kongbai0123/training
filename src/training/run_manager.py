import os
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from src.training.metrics_collector import MetricsCollector
from src.training.trend_analyzer import TrendAnalyzer

class RunManager:
    @staticmethod
    def generate_run_id() -> str:
        """生成格式如 run_YYYYMMDD_HHMMSS 的 run_id"""
        return f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    @staticmethod
    def create_run_directory(runs_dir: Path, run_id: str) -> Path:
        """建立獨立的 run 目錄"""
        run_dir = runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    @staticmethod
    def save_run_metadata(
        run_dir: Path,
        config: Dict[str, Any],
        images_metadata: List[Dict[str, Any]]
    ):
        """儲存訓練設定快照與 dataset 劃分快照"""
        try:
            # 儲存 config.json
            with open(run_dir / "train_config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            # 儲存 dataset_snapshot.json (只保存 filename 與 split 以防檔案過大)
            snapshot = []
            for img in images_metadata:
                snapshot.append({
                    "filename": img.get("filename"),
                    "split": img.get("split"),
                    "is_augmented": img.get("is_augmented", False),
                    "status": img.get("status")
                })
            with open(run_dir / "dataset_snapshot.json", "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[RunManager] Error saving run metadata: {e}")

    @classmethod
    def finalize_run(
        cls,
        run_dir: Path,
        task_type: str,
        status: str,
        error_msg: str = "",
        data_yaml_path: Optional[Path] = None
    ) -> Optional[Dict[str, Any]]:
        """
        當訓練完成/中止/出錯時：
        1. 確保 run_dir 目錄一定存在 (避免 failed run 無法寫入紀錄)
        2. 解析 results.csv 並生成 metrics.json
        3. 計算 Best Epoch & Platform Score & Health 分析
        4. 保存 run_summary.json
        5. 保存 / 備份必要的 YAML 與錯誤日誌
        6. 回傳摘要資訊以寫入 project.json
        """
        # 1. 確保 run_dir 存在
        run_dir.mkdir(parents=True, exist_ok=True)

        # 2. 確保基本快照檔案存在
        config_file = run_dir / "train_config.json"
        if not config_file.exists():
            try:
                with open(config_file, "w", encoding="utf-8") as f:
                    json.dump({}, f, indent=2)
            except Exception:
                pass

        snapshot_file = run_dir / "dataset_snapshot.json"
        if not snapshot_file.exists():
            try:
                with open(snapshot_file, "w", encoding="utf-8") as f:
                    json.dump([], f, indent=2)
            except Exception:
                pass

        # 3. 記錄錯誤日誌 (若出錯)
        if status == "failed" and error_msg:
            try:
                with open(run_dir / "error.log", "w", encoding="utf-8") as f:
                    f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                    f.write(f"Status: {status}\n")
                    f.write(f"Error Message:\n{error_msg}\n")
            except Exception:
                pass

        # 4. 轉化為 metrics.json
        metrics_data = MetricsCollector.parse_results_csv(run_dir)
        
        best_epoch = 0
        best_metrics = {}
        platform_score = 0.0
        health_analysis = {
            "health_status": "Danger" if status == "failed" else "Good",
            "convergence_status": "Unknown",
            "overfitting_warning": False,
            "plateau_warning": False,
            "unstable_warning": False,
            "suggestions": ["訓練出錯中止。"] if status == "failed" else ["無 metrics 數據。"]
        }

        if metrics_data:
            try:
                with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
                    json.dump(metrics_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[RunManager] Failed to write metrics.json: {e}")

            best_epoch, best_metrics = TrendAnalyzer.find_best_epoch(metrics_data, task_type)
            platform_score = TrendAnalyzer.calculate_platform_score(best_metrics, task_type)
            health_analysis = TrendAnalyzer.analyze_health(metrics_data, task_type)

        # 5. 儲存 run_summary.json
        summary = {
            "run_id": run_dir.name,
            "status": status,
            "task_type": task_type,
            "best_epoch": best_epoch,
            "best_metrics": best_metrics,
            "platform_score": platform_score,
            "health": health_analysis,
            "error": error_msg,
            "completed_at": datetime.now().isoformat()
        }

        try:
            with open(run_dir / "run_summary.json", "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[RunManager] Failed to write run_summary.json: {e}")

        # 6. 生成寫入 project.json 的摘要
        is_seg = "segmentation" in task_type or "seg" in task_type
        mAP50_key = "metrics/mAP50(M)" if is_seg else "metrics/mAP50(B)"
        mAP50_95_key = "metrics/mAP50-95(M)" if is_seg else "metrics/mAP50-95(B)"

        best_mAP50 = best_metrics.get(mAP50_key)
        if best_mAP50 is None:
            fallback = "metrics/mAP50(B)" if is_seg else "metrics/mAP50(M)"
            best_mAP50 = best_metrics.get(fallback, 0.0)
            best_mAP50_95 = best_metrics.get("metrics/mAP50-95(B)" if is_seg else "metrics/mAP50-95(M)", 0.0)
        else:
            best_mAP50_95 = best_metrics.get(mAP50_95_key, 0.0)

        # 7. 備份 data.yaml
        target_data_yaml = run_dir / "data.yaml"
        if data_yaml_path and data_yaml_path.exists():
            try:
                import shutil
                shutil.copy(data_yaml_path, target_data_yaml)
            except Exception:
                pass
        elif not target_data_yaml.exists():
            # Fallback 舊邏輯，以防 path 為空時向後相容
            legacy_yaml = run_dir.parent / "data.yaml"
            if legacy_yaml.exists():
                try:
                    import shutil
                    shutil.copy(legacy_yaml, target_data_yaml)
                except Exception:
                    pass

        return {
            "run_id": run_dir.name,
            "status": status,
            "best_epoch": best_epoch,
            "best_mAP50": round(best_mAP50, 5),
            "best_mAP50_95": round(best_mAP50_95, 5),
            "platform_score": platform_score,
            "metrics_path": f"training/runs/{run_dir.name}/metrics.json",
            "summary_path": f"training/runs/{run_dir.name}/run_summary.json",
            "completed_at": summary["completed_at"]
        }

    @staticmethod
    def list_project_runs(runs_dir: Path) -> List[Dict[str, Any]]:
        """
        遍歷 runs 目錄，載入所有歷史 run_summary.json 檔案
        """
        runs = []
        if not runs_dir.exists():
            return runs

        for d in runs_dir.iterdir():
            if d.is_dir() and d.name.startswith("run_"):
                summary_file = d / "run_summary.json"
                if summary_file.exists():
                    try:
                        with open(summary_file, "r", encoding="utf-8") as f:
                            runs.append(json.load(f))
                    except Exception:
                        pass
                else:
                    # 尚未結束或出錯的舊 run，回傳基本資訊
                    runs.append({
                        "run_id": d.name,
                        "status": "unknown",
                        "completed_at": None
                    })
        # 降序排序
        runs.sort(key=lambda x: x.get("run_id", ""), reverse=True)
        return runs
