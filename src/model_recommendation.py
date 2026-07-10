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

        if fit == "compatible" and minimum_vram:
            recommended_floor = 6144 if vram_mb >= 6144 else 2048
            if minimum_vram == recommended_floor:
                fit = "recommended"

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
    return annotated
