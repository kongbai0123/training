import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from src.model_system.catalog import ModelCatalog
from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.training.dispatcher import TrainerDispatcher
from src.training.vision.torchvision_trainer import train_torchvision_model


class VisionModelExpansionTests(unittest.TestCase):
    def test_catalog_lists_recommended_trainable_models_by_task(self):
        classification = {item["model_id"] for item in ModelCatalog.list_trainable(task_family="image_classification", architecture="cnn")}
        detection = {item["model_id"] for item in ModelCatalog.list_trainable(task_family="object_detection", architecture="cnn")}
        instance = {item["model_id"] for item in ModelCatalog.list_trainable(task_family="instance_segmentation", architecture="cnn")}
        semantic = {item["model_id"] for item in ModelCatalog.list_trainable(task_family="semantic_segmentation", architecture="cnn")}

        self.assertTrue({
            "builtin.torchvision.resnet18",
            "builtin.torchvision.mobilenet-v3-large",
            "builtin.torchvision.efficientnet-b0",
        }.issubset(classification))
        self.assertTrue({
            "builtin.torchvision.fasterrcnn-mobilenet-v3",
            "builtin.torchvision.fcos-resnet50",
            "builtin.dfine.small",
        }.issubset(detection))
        self.assertIn("builtin.torchvision.maskrcnn-resnet50", instance)
        self.assertTrue({
            "builtin.torchvision.deeplabv3-mobilenet-v3",
            "template.vision.unet",
        }.issubset(semantic))
        self.assertNotIn("builtin.yolov8n-seg", semantic)

    def test_dispatcher_registers_new_backends(self):
        self.assertIn("pytorch_torchvision", TrainerDispatcher._backends)
        self.assertIn("transformers_dfine", TrainerDispatcher._backends)

    def test_project_defaults_match_visual_task(self):
        self.assertEqual(ProjectManager._default_training_config("image_classification")["backend"], "pytorch_torchvision")
        self.assertEqual(ProjectManager._default_training_config("semantic_segmentation")["model"], "unet")
        self.assertEqual(ProjectManager._default_training_config("instance_segmentation")["model"], "yolov8n-seg.pt")

    def test_training_selector_is_categorized_and_sends_backend(self):
        source = (Path(__file__).parents[1] / "static" / "pages" / "training.js").read_text(encoding="utf-8")
        self.assertIn("trainingCategoryLabel(category)", source)
        self.assertIn("option.dataset.trainingCategory", source)
        self.assertIn('backend: selectedOption?.dataset?.backend || "ultralytics_yolo"', source)
        self.assertIn("圖片分類（整張圖，不畫框）", source)
        self.assertIn("物件輪廓分割（可分別計數）", source)

    def test_builtin_unet_completes_one_epoch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            layout = ProjectLayout(root, {"layout": {"mode": "v3"}})
            layout.ensure_v3_tree()
            raw = layout.resolve_raw_images_dir().path
            images = []
            for index, split in enumerate(["train", "train", "val"]):
                filename = f"sample_{index}.png"
                Image.new("RGB", (32, 32), (40 + index * 20, 80, 120)).save(raw / filename)
                images.append({
                    "filename": filename,
                    "split": split,
                    "width": 32,
                    "height": 32,
                    "annotations": [{
                        "category": "part",
                        "type": "polygon",
                        "points": [[4, 4], [27, 4], [27, 27], [4, 27]],
                        "bbox": [0.484375, 0.484375, 0.71875, 0.71875],
                    }],
                })
            project = {
                "project_id": "vision_smoke",
                "dataset_path": (root / "dataset").as_posix(),
                "layout": {"mode": "v3"},
                "task_type": "semantic_segmentation",
                "class_names": ["part"],
                "images": images,
            }
            run_dir = root / "training" / "runs" / "smoke"
            result = train_torchvision_model(project, run_dir, {
                "model": "unet",
                "epochs": 1,
                "batch_size": 1,
                "imgsz": 64,
                "device": "cpu",
                "workers": 0,
                "lr0": 0.001,
            })
            self.assertEqual(result["best_epoch"], 1)
            self.assertTrue((run_dir / "weights" / "best.pt").exists())
            self.assertEqual(json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))["backend"], "pytorch_torchvision")


if __name__ == "__main__":
    unittest.main()
