import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_supported_yolo_families_have_detection_and_segmentation_scales():
    catalog = json.loads((ROOT / "data" / "builtin_model_catalog.json").read_text(encoding="utf-8"))
    models = {item["model_id"]: item for item in catalog}
    for family in ("yolov8", "yolo11", "yolo26"):
        for scale in "nsm lx".replace(" ", ""):
            for task in ("det", "seg"):
                model = models[f"builtin.{family}{scale}-{task}"]
                assert model["download_url"].startswith("https://github.com/ultralytics/assets/releases/download/")
                assert len(model["sha256"]) == 64
                assert model["download_size"] > 0
                assert model["min_vram_mb"] > 0


def test_catalog_has_no_duplicate_model_ids_or_weights():
    catalog = json.loads((ROOT / "data" / "builtin_model_catalog.json").read_text(encoding="utf-8"))
    model_ids = [item["model_id"] for item in catalog]
    cnn_weights = [item["weight"] for item in catalog if item.get("architecture") == "cnn" and item.get("weight")]
    assert len(model_ids) == len(set(model_ids))
    assert len(cnn_weights) == len(set(cnn_weights))
