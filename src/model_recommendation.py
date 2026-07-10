from __future__ import annotations

from typing import Any, Dict, Iterable, List


def annotate_hardware_fit(models: Iterable[Dict[str, Any]], capabilities: Dict[str, Any]) -> List[Dict[str, Any]]:
    gpu = capabilities.get("gpu") or {}
    memory = capabilities.get("memory") or {}
    disk = capabilities.get("disk") or {}
    devices = gpu.get("devices") or []
    vram_mb = max((int(device.get("vram_total_mb") or 0) for device in devices), default=0)
    ram_gb = float(memory.get("total_gb") or 0)
    disk_gb = float(disk.get("available_gb") or 0)
    cuda_available = bool(gpu.get("cuda_available"))

    annotated: List[Dict[str, Any]] = []
    for source in models:
        model = dict(source)
        if not model.get("installation_required"):
            model["hardware_fit"] = "ready" if model.get("usable") else "unavailable"
            model["hardware_reasons"] = []
            annotated.append(model)
            continue

        minimum_vram = int(model.get("min_vram_mb") or 0)
        minimum_ram = float(model.get("min_ram_gb") or 4)
        download_size = int(model.get("download_size") or 0)
        required_disk_gb = max(download_size * 2 / (1024**3), 0.1)
        reasons: List[str] = []

        if ram_gb and ram_gb < minimum_ram:
            reasons.append("insufficient_ram")
        if disk_gb and disk_gb < required_disk_gb:
            reasons.append("insufficient_disk")
        if not cuda_available and minimum_vram > 0:
            fit = "not_recommended"
            reasons.append("cuda_unavailable")
        elif minimum_vram and vram_mb < minimum_vram:
            fit = "not_recommended"
            reasons.append("insufficient_vram")
        elif minimum_vram and vram_mb >= minimum_vram:
            fit = "compatible"
        else:
            fit = "compatible"

        if any(reason in reasons for reason in ("insufficient_ram", "insufficient_disk")):
            fit = "incompatible"

        model.update({
            "hardware_fit": fit,
            "hardware_reasons": reasons,
            "hardware_snapshot": {
                "cuda_available": cuda_available,
                "vram_total_mb": vram_mb,
                "ram_total_gb": ram_gb,
                "disk_available_gb": disk_gb,
            },
        })
        annotated.append(model)

    recommendation_limit = int(vram_mb * 0.75) if vram_mb else 0
    task_families = {str(model.get("task_family") or "") for model in annotated}
    for task_family in task_families:
        candidates = [
            model for model in annotated
            if model.get("task_family") == task_family
            and model.get("installation_required")
            and not model.get("installed")
            and model.get("hardware_fit") == "compatible"
            and (not recommendation_limit or int(model.get("min_vram_mb") or 0) <= recommendation_limit)
        ]
        if not candidates:
            continue
        candidates.sort(
            key=lambda model: (int(model.get("generation_rank") or 0), int(model.get("min_vram_mb") or 0)),
            reverse=True,
        )
        candidates[0]["hardware_fit"] = "recommended"
    return annotated


def rank_models_for_project(
    models: Iterable[Dict[str, Any]],
    capabilities: Dict[str, Any],
    project: Dict[str, Any],
    objective: str = "balanced",
) -> List[Dict[str, Any]]:
    """Rank task-compatible models with deterministic, inspectable criteria."""
    normalized_objective = objective if objective in {"balanced", "speed", "accuracy"} else "balanced"
    sample_count = _project_sample_count(project)
    ranked: List[Dict[str, Any]] = []

    for source in models:
        model = dict(source)
        profile = model.get("decision_profile") or {}
        benchmark = model.get("benchmark") or {}
        fit = str(model.get("hardware_fit") or "unavailable")
        status = str(model.get("status") or "")
        scale = str(profile.get("scale") or "")
        score = {
            "ready": 34,
            "recommended": 34,
            "compatible": 27,
            "not_recommended": 4,
            "unavailable": -70,
            "incompatible": -100,
        }.get(fit, 0)
        reasons: List[str] = []

        if model.get("usable"):
            score += 14
            reasons.append("available_now")
        elif model.get("installation_required") and fit not in {"incompatible", "unavailable"}:
            score += 5
            reasons.append("install_required")

        if status == "planned" or not model.get("trainable"):
            score -= 100
            reasons.append("training_unavailable")

        if sample_count:
            if sample_count <= 500 and scale in {"nano", "standard"}:
                score += 12
                reasons.append("fits_small_dataset")
            elif 500 < sample_count <= 5000 and scale in {"small", "standard"}:
                score += 10
                reasons.append("fits_medium_dataset")
            elif sample_count > 5000 and scale in {"small", "medium", "standard"}:
                score += 8
                reasons.append("fits_large_dataset")

        primary_value = float((benchmark.get("primary_metric") or {}).get("value") or 0)
        latency_value = float((benchmark.get("latency") or {}).get("cpu_onnx_ms") or 0)
        params_m = float(benchmark.get("parameters_m") or 0)
        generation_rank = int(model.get("generation_rank") or 0)

        if normalized_objective == "accuracy":
            score += primary_value * 0.9
            reasons.append("quality_priority")
        elif normalized_objective == "speed":
            if latency_value:
                score += max(0, 32 - min(latency_value / 5, 32))
            if params_m:
                score += max(0, 16 - min(params_m, 16))
            reasons.append("speed_priority")
        else:
            score += primary_value * 0.55
            if latency_value:
                score += max(0, 18 - min(latency_value / 10, 18))
            score += min(generation_rank / 3, 9)
            reasons.append("balanced_priority")

        model["decision_score"] = round(score, 2)
        model["decision_reasons"] = reasons
        model["decision_context"] = {
            "objective": normalized_objective,
            "sample_count": sample_count,
            "task_type": project.get("task_type"),
        }
        ranked.append(model)

    ranked.sort(key=lambda item: (float(item.get("decision_score") or -999), bool(item.get("usable"))), reverse=True)
    for index, model in enumerate(ranked, start=1):
        model["recommendation_rank"] = index
        model["recommended_for_project"] = index <= 3 and float(model.get("decision_score") or -999) > -50
    return ranked


def _project_sample_count(project: Dict[str, Any]) -> int:
    images = project.get("images") or []
    if images:
        return len([
            item for item in images
            if not isinstance(item, dict) or not item.get("is_augmented")
        ])
    for container_key in ("rnn_dataset", "sequence_dataset", "dataset_summary"):
        container = project.get(container_key) or {}
        for key in ("sequence_count", "sample_count", "row_count", "total_rows"):
            value = container.get(key)
            if value is not None:
                try:
                    return max(0, int(value))
                except (TypeError, ValueError):
                    continue
    return 0
