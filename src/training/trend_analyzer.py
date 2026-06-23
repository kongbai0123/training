from typing import Dict, List, Any, Tuple

class TrendAnalyzer:
    @staticmethod
    def find_best_epoch(metrics_data: Dict[str, Any], task_type: str) -> Tuple[int, Dict[str, float]]:
        """
        找出最佳 Epoch。對於 Segmentation 任務優先看 metrics/mAP50-95(M)；若無則看 metrics/mAP50-95(B)。
        """
        epochs = metrics_data.get("epochs", [])
        raw = metrics_data.get("raw", {})
        if not epochs or not raw:
            return 0, {}

        # 優先指標
        is_seg = "segmentation" in task_type or "seg" in task_type
        primary_key = "metrics/mAP50-95(M)" if is_seg else "metrics/mAP50-95(B)"
        
        # Fallbacks
        keys_to_try = [
            primary_key,
            "metrics/mAP50-95(M)",
            "metrics/mAP50-95(B)",
            "metrics/mAP50(M)",
            "metrics/mAP50(B)"
        ]

        metric_key = None
        for k in keys_to_try:
            if k in raw and len(raw[k]) > 0:
                metric_key = k
                break

        if not metric_key:
            # 隨便選一個長度對得上的指標
            for k, v in raw.items():
                if len(v) == len(epochs):
                    metric_key = k
                    break

        if not metric_key:
            return 0, {}

        values = raw[metric_key]
        best_val = -1.0
        best_idx = 0

        for idx, val in enumerate(values):
            if val >= best_val:
                best_val = val
                best_idx = idx

        best_epoch = epochs[best_idx]
        best_epoch_metrics = {k: vals[best_idx] for k, vals in raw.items() if len(vals) > best_idx}
        
        return best_epoch, best_epoch_metrics

    @staticmethod
    def calculate_platform_score(best_epoch_metrics: Dict[str, float], task_type: str) -> float:
        """
        計算平台主要成績 (platform_score)
        segmentation: 0.60 * mAP50-95(M) + 0.20 * mAP50(M) + 0.10 * precision(M) + 0.10 * recall(M)
        detection: 0.60 * mAP50-95(B) + 0.20 * mAP50(B) + 0.10 * precision(B) + 0.10 * recall(B)
        """
        is_seg = "segmentation" in task_type or "seg" in task_type
        
        # 決定讀取 M (Mask) 還是 B (Box) 欄位
        suffix = "(M)" if is_seg else "(B)"
        
        # 檢查欄位是否存在，不存在則 fallback 互換
        map50_95 = best_epoch_metrics.get(f"metrics/mAP50-95{suffix}")
        if map50_95 is None:
            fallback_suffix = "(B)" if is_seg else "(M)"
            map50_95 = best_epoch_metrics.get(f"metrics/mAP50-95{fallback_suffix}", 0.0)
            map50 = best_epoch_metrics.get(f"metrics/mAP50{fallback_suffix}", 0.0)
            precision = best_epoch_metrics.get(f"metrics/precision{fallback_suffix}", 0.0)
            recall = best_epoch_metrics.get(f"metrics/recall{fallback_suffix}", 0.0)
        else:
            map50 = best_epoch_metrics.get(f"metrics/mAP50{suffix}", 0.0)
            precision = best_epoch_metrics.get(f"metrics/precision{suffix}", 0.0)
            recall = best_epoch_metrics.get(f"metrics/recall{suffix}", 0.0)

        score = 0.60 * map50_95 + 0.20 * map50 + 0.10 * precision + 0.10 * recall
        return round(score, 5)

    @classmethod
    def analyze_health(cls, metrics_data: Dict[str, Any], task_type: str) -> Dict[str, Any]:
        """
        分析訓練收斂性、過擬合與 Plateau
        """
        epochs = metrics_data.get("epochs", [])
        raw = metrics_data.get("raw", {})
        if not epochs or len(epochs) < 5:
            return {
                "health_status": "Good",
                "convergence_status": "Analyzing",
                "overfitting_warning": False,
                "plateau_warning": False,
                "unstable_warning": False,
                "suggestions": ["訓練 Epoch 數量太少，還在積累數據。"]
            }

        # 找對應的 loss 鍵與 metrics 鍵
        is_seg = "segmentation" in task_type or "seg" in task_type
        
        # Loss 評估
        val_loss_keys = [k for k in raw.keys() if "val/" in k and "loss" in k]
        train_loss_keys = [k for k in raw.keys() if "train/" in k and "loss" in k]
        
        mAP_key = "metrics/mAP50-95(M)" if is_seg else "metrics/mAP50-95(B)"
        if mAP_key not in raw:
            mAP_key = "metrics/mAP50-95(B)" if mAP_key == "metrics/mAP50-95(M)" else "metrics/mAP50-95(M)"
        if mAP_key not in raw:
            # 隨便選一個
            mAP_key = next((k for k in raw.keys() if "mAP" in k), None)

        val_losses = []
        if val_loss_keys:
            # 加總所有 val loss 作為整體 loss
            length = len(raw[val_loss_keys[0]])
            for i in range(length):
                val_losses.append(sum(raw[k][i] for k in val_loss_keys))
        
        train_losses = []
        if train_loss_keys:
            length = len(raw[train_loss_keys[0]])
            for i in range(length):
                train_losses.append(sum(raw[k][i] for k in train_loss_keys))

        mAPs = raw.get(mAP_key, [])

        overfitting = False
        plateau = False
        unstable = False
        suggestions = []

        # 1. Overfitting 檢查: train loss 持續下降，但 val loss 上升，且 validation mAP 下降或停滯
        if len(val_losses) >= 10 and len(train_losses) >= 10:
            # 檢查最近 8 個 epoch 的 val loss 趨勢
            recent_val = val_losses[-8:]
            recent_train = train_losses[-8:]
            
            # 如果 train loss 整體呈下降，而 val loss 大致呈上升
            train_descending = recent_train[-1] < recent_train[0]
            
            # 計算 val loss 上升次數
            val_up_count = sum(1 for i in range(1, len(recent_val)) if recent_val[i] > recent_val[i-1])
            
            if train_descending and val_up_count >= 5:
                # 檢查 mAP 是否停滯或下降
                if mAPs and len(mAPs) >= 8:
                    recent_map = mAPs[-8:]
                    map_improving = recent_map[-1] > (max(recent_map[:-3]) if len(recent_map) > 3 else recent_map[0])
                    if not map_improving:
                        overfitting = True
                        suggestions.append("偵測到疑似過擬合 (Overfitting)！建議調大 Augmentation 幅度或啟用 Early Stopping。")

        # 2. Plateau 檢查: 最近 N 個 epoch 的 metrics 改善小於 threshold
        if mAPs and len(mAPs) >= 12:
            recent_maps = mAPs[-10:]
            best_in_recent = max(recent_maps)
            old_best = max(mAPs[:-10]) if len(mAPs) > 10 else mAPs[0]
            improvement = best_in_recent - old_best
            if improvement < 0.005:
                plateau = True
                suggestions.append("訓練已進入高原期 (Plateau)。建議降低學習率 (Learning Rate Decay) 或微調模型架構。")

        # 3. Unstable 檢查: metrics 劇烈晃動
        if mAPs and len(mAPs) >= 6:
            recent_maps = mAPs[-6:]
            diffs = [abs(recent_maps[i] - recent_maps[i-1]) for i in range(1, len(recent_maps))]
            mean_diff = sum(diffs) / len(diffs)
            if mean_diff > 0.08:
                unstable = True
                suggestions.append("訓練表現波動劇烈 (Unstable)。建議檢查 Learning Rate 是否設得太高，或增大學習 Batch Size。")

        # 4. Convergence 狀態研判
        if overfitting:
            convergence_status = "Overfitting"
            status = "Danger"
        elif unstable:
            convergence_status = "Unstable"
            status = "Warning"
        elif plateau:
            convergence_status = "Plateau"
            status = "Warning"
        else:
            convergence_status = "Converging"
            status = "Good"

        if not suggestions:
            suggestions.append("訓練狀態良好，收斂趨勢正常。")

        return {
            "health_status": status,
            "convergence_status": convergence_status,
            "overfitting_warning": overfitting,
            "plateau_warning": plateau,
            "unstable_warning": unstable,
            "suggestions": suggestions
        }
