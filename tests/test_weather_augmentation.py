import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from src.augmenter import ImageAugmenter
from src.api.routes.augmentation import (
    config_for_augmentation_sample,
    get_applied_augmentation_parameters,
    normalize_augmentation_config,
)


class WeatherAugmentationTests(unittest.TestCase):
    def test_route_normalization_and_sample_seed_are_stable(self):
        config = normalize_augmentation_config({
            "weather": {
                "overcast": 1.5,
                "rain": "0.55",
                "fog": -2,
                "sun_suppression": 0.8,
                "wet_surface": 0.7,
                "puddle": 0.4,
                "splash": 0.3,
                "visibility_protection": True,
                "max_occlusion": 0.9,
            },
            "camera": {"lens_droplets": 2},
        })
        self.assertEqual(config["weather"]["overcast"], 1.0)
        self.assertEqual(config["weather"]["rain"], 0.55)
        self.assertEqual(config["weather"]["fog"], 0.0)
        self.assertEqual(config["weather"]["max_occlusion"], 0.35)
        self.assertEqual(config["camera"]["lens_droplets"], 1.0)

        first = config_for_augmentation_sample(config, "frame.jpg", 0)
        repeated = config_for_augmentation_sample(config, "frame.jpg", 0)
        second_copy = config_for_augmentation_sample(config, "frame.jpg", 1)
        self.assertEqual(first["weather"]["seed"], repeated["weather"]["seed"])
        self.assertNotEqual(first["weather"]["seed"], second_copy["weather"]["seed"])
        self.assertNotIn("seed", config["weather"])
        params = get_applied_augmentation_parameters(config)
        self.assertIn("overcast_grade", params)
        self.assertIn("three_layer_rain", params)
        self.assertIn("annotation_visibility_protection", params)
        self.assertIn("sunny_cue_suppression", params)
        self.assertIn("wet_surface", params)
        self.assertIn("puddles", params)
        self.assertIn("ground_splashes", params)
        self.assertIn("lens_droplets", params)

    def test_overcast_grade_is_cooler_and_dimmer(self):
        image = np.zeros((96, 128, 3), dtype=np.uint8)
        image[:, :] = (90, 140, 210)

        result = ImageAugmenter.apply_overcast_grade(image, 0.8)

        self.assertEqual(result.shape, image.shape)
        self.assertLess(float(result.mean()), float(image.mean()))
        original_blue_red_gap = float(image[:, :, 0].mean() - image[:, :, 2].mean())
        result_blue_red_gap = float(result[:, :, 0].mean() - result[:, :, 2].mean())
        self.assertGreater(result_blue_red_gap, original_blue_red_gap)

    def test_depth_fog_affects_distant_top_more_than_near_bottom(self):
        image = np.full((240, 320, 3), 40, dtype=np.uint8)
        result = ImageAugmenter.add_fog(
            image,
            0.8,
            rng=np.random.default_rng(11),
        )

        top_change = np.abs(result[:60].astype(np.float32) - image[:60]).mean()
        bottom_change = np.abs(result[-60:].astype(np.float32) - image[-60:]).mean()
        self.assertGreater(top_change, bottom_change * 1.8)

    def test_visibility_protection_reduces_rain_inside_target(self):
        image = np.full((360, 480, 3), 32, dtype=np.uint8)
        annotations = [{"type": "bbox", "category": "target", "bbox": [0.5, 0.5, 0.5, 0.5]}]
        mask = ImageAugmenter.build_annotation_visibility_mask(image.shape, annotations)
        protected = ImageAugmenter.add_rain(
            image,
            1.0,
            visibility_mask=mask,
            max_occlusion=0.15,
            rng=np.random.default_rng(42),
        )
        unprotected = ImageAugmenter.add_rain(
            image,
            1.0,
            visibility_mask=None,
            max_occlusion=0.15,
            rng=np.random.default_rng(42),
        )

        target = mask > 0.9
        protected_change = np.abs(protected.astype(np.float32) - image)[target].mean()
        unprotected_change = np.abs(unprotected.astype(np.float32) - image)[target].mean()
        self.assertLess(protected_change, unprotected_change * 0.65)

    def test_task_aware_partition_does_not_protect_road_polygon(self):
        annotations = [
            {"type": "polygon", "category": "道路", "bbox": [0.5, 0.72, 0.8, 0.45],
             "points": [[20, 100], [180, 100], [195, 158], [5, 158]]},
            {"type": "bbox", "category": "person", "bbox": [0.5, 0.5, 0.08, 0.2]},
        ]
        protected, surfaces = ImageAugmenter.partition_weather_annotations((160, 200, 3), annotations)
        self.assertEqual([item["category"] for item in protected], ["person"])
        self.assertEqual([item["category"] for item in surfaces], ["道路"])

    def test_sunny_cue_suppression_compresses_top_highlight(self):
        image = np.full((160, 220, 3), 90, dtype=np.uint8)
        cv2.circle(image, (110, 35), 18, (245, 250, 255), -1)
        result = ImageAugmenter.suppress_sunny_cues(image, 0.9)
        self.assertLess(float(result[35, 110].mean()), float(image[35, 110].mean()) - 15)
        self.assertLess(
            float(np.abs(result[-30:].astype(np.float32) - image[-30:]).mean()),
            float(np.abs(result[:70].astype(np.float32) - image[:70]).mean()),
        )

    def test_rain_uses_bounded_airlight_blend_on_bright_background(self):
        image = np.full((240, 320, 3), 248, dtype=np.uint8)
        result = ImageAugmenter.add_rain(image, 1.0, rng=np.random.default_rng(7))
        self.assertTrue(np.any(result < image))
        self.assertLess(int(result.max()), 255)

    def test_wet_surface_and_splashes_are_confined_to_surface(self):
        image = np.full((180, 240, 3), (80, 130, 180), dtype=np.uint8)
        mask = np.zeros((180, 240), dtype=np.float32)
        mask[90:, :] = 1.0
        wet = ImageAugmenter.add_wet_surface(
            image, mask, 0.9, 0.6, np.random.default_rng(5)
        )
        splashed = ImageAugmenter.add_ground_splashes(
            wet, mask, 0.9, np.random.default_rng(5)
        )
        self.assertLess(float(wet[120:].mean()), float(image[120:].mean()))
        self.assertLess(float(np.abs(wet[:60].astype(np.float32) - image[:60]).mean()), 0.5)
        self.assertGreater(float(np.abs(splashed[90:].astype(np.float32) - wet[90:]).mean()), 0.0)
        self.assertEqual(float(np.abs(splashed[:60].astype(np.float32) - wet[:60]).mean()), 0.0)

    def test_lens_droplets_are_deterministic_and_separate(self):
        x = np.linspace(0, 255, 300, dtype=np.uint8)
        image = np.repeat(x[None, :, None], 180, axis=0)
        image = np.repeat(image, 3, axis=2)
        first = ImageAugmenter.add_lens_droplets(image, 0.8, rng=np.random.default_rng(22))
        repeated = ImageAugmenter.add_lens_droplets(image, 0.8, rng=np.random.default_rng(22))
        self.assertTrue(np.array_equal(first, repeated))
        self.assertGreater(float(np.abs(first.astype(np.float32) - image).mean()), 0.02)

    def test_preview_contract_uses_png_clean_and_annotated_variants(self):
        route_source = Path("src/api/routes/augmentation.py").read_text(encoding="utf-8")
        self.assertIn('cv2.imencode(".png", aug_img)', route_source)
        self.assertIn('"preview_annotated"', route_source)
        self.assertIn('"preview_mime": "image/png"', route_source)

    def test_weather_ui_keeps_world_surface_and_lens_controls_separate(self):
        html = Path("static/index.html").read_text(encoding="utf-8")
        page_js = Path("static/pages/augmentation.js").read_text(encoding="utf-8")
        self.assertIn('data-aug-preset="wet_reflection"', html)
        self.assertIn('data-aug-preset="lens_rain"', html)
        self.assertIn('id="aug-weather-wet-surface"', html)
        self.assertIn('id="aug-weather-puddle"', html)
        self.assertIn('id="aug-weather-splash"', html)
        self.assertIn('id="aug-camera-lens-droplets"', html)
        self.assertIn('camera: {', page_js)
        self.assertIn('lens_droplets: Number(qs("#aug-camera-lens-droplets")', page_js)

    def test_preview_selection_survives_page_rerender(self):
        page_js = Path("static/pages/augmentation.js").read_text(encoding="utf-8")
        self.assertIn('let selectedPreviewFilename = "";', page_js)
        self.assertIn('selectedPreviewFilename = filename;', page_js)
        self.assertIn('filenames.includes(currentSelection)', page_js)
        self.assertIn('select.value = currentSelection;', page_js)

    def test_approved_augmentation_workspace_uses_six_functional_groups(self):
        html = Path("static/index.html").read_text(encoding="utf-8")
        css = Path("static/styles/pages/augmentation.css").read_text(encoding="utf-8")
        page_start = html.index('<section class="page" id="page-augmentation">')
        page_end = html.index('<section class="page" id="page-training">')
        page = html[page_start:page_end]

        self.assertEqual(page.count('data-aug-preset='), 6)
        self.assertEqual(page.count('class="aug-parameter-card"'), 6)
        self.assertIn('class="aug-parameter-grid"', page)
        self.assertIn('class="aug-execution-grid"', page)
        self.assertIn('aug-live-preview-card', page)
        self.assertIn('id="aug-max-occlusion"', page)
        self.assertIn('grid-template-columns: repeat(6, minmax(0, 1fr));', css)

    def test_workspace_exposes_only_geometry_with_annotation_remap(self):
        html = Path("static/index.html").read_text(encoding="utf-8")
        page_js = Path("static/pages/augmentation.js").read_text(encoding="utf-8")
        self.assertIn('id="aug-camera-perspective"', html)
        self.assertIn('id="aug-rotation"', html)
        self.assertIn('id="aug-scale"', html)
        self.assertIn('id="aug-horizontal-flip"', html)
        self.assertIn('id="aug-vertical-flip"', html)
        self.assertIn('max_occlusion: Number(qs("#aug-max-occlusion")?.value || 0.15)', page_js)
        self.assertIn('random_crop: Number(qs("#aug-random-crop")?.value || 0)', page_js)

    def test_compare_preview_uses_a_draggable_split_slider(self):
        html = Path("static/index.html").read_text(encoding="utf-8")
        css = Path("static/styles/pages/augmentation.css").read_text(encoding="utf-8")
        page_js = Path("static/pages/augmentation.js").read_text(encoding="utf-8")
        self.assertIn('id="aug-compare-stage"', html)
        self.assertIn('id="aug-compare-slider"', html)
        self.assertIn('class="aug-compare-divider"', html)
        self.assertIn('clip-path: inset(0 0 0 var(--compare-position));', css)
        self.assertIn('function updateComparePosition()', page_js)

    def test_risky_geometry_controls_require_preview_review_without_being_blocked(self):
        page_js = Path("static/pages/augmentation.js").read_text(encoding="utf-8")
        zh_tw = Path("static/state/i18n/zh-TW.js").read_text(encoding="utf-8")
        en = Path("static/state/i18n/en.js").read_text(encoding="utf-8")
        self.assertIn('verticalFlipEnabled ? { kind: "warning"', page_js)
        self.assertIn('randomCrop > 0 ? { kind: "warning"', page_js)
        self.assertIn('augmentation.risk.geometryReview', page_js)
        self.assertIn('augmentation.risk.reviewRequired', page_js)
        self.assertIn('"augmentation.risk.verticalFlip"', zh_tw)
        self.assertIn('"augmentation.risk.randomCrop"', en)
        self.assertNotIn('el.id === "aug-camera-perspective"', page_js)

    def test_affine_geometry_keeps_polygon_and_bbox_annotations_aligned(self):
        image = np.full((120, 160, 3), 128, dtype=np.uint8)
        annotations = [
            {"category": "box", "type": "bbox", "bbox": [0.5, 0.5, 0.25, 0.25]},
            {"category": "poly", "type": "polygon", "bbox": [0.5, 0.5, 0.25, 0.25], "points": [[60, 45], [100, 45], [100, 75], [60, 75]]},
        ]
        transformed_image, transformed = ImageAugmenter.apply_geometry(
            image, annotations, 8, 0.08, True, False, 0.08, np.random.default_rng(7)
        )
        self.assertEqual(transformed_image.shape, image.shape)
        self.assertEqual(len(transformed), 2)
        for annotation in transformed:
            xc, yc, width, height = annotation["bbox"]
            self.assertTrue(0 <= xc <= 1 and 0 <= yc <= 1)
            self.assertTrue(0 < width <= 1 and 0 < height <= 1)
        polygon = next(item for item in transformed if item["type"] == "polygon")
        self.assertEqual(len(polygon["points"]), 4)

    def test_polygon_visibility_mask_and_metadata_are_preserved(self):
        image = np.full((160, 200, 3), (60, 120, 180), dtype=np.uint8)
        annotations = [{
            "type": "polygon",
            "category": "road-sign",
            "bbox": [0.5, 0.5, 0.4, 0.4],
            "points": [[60, 40], [140, 40], [140, 120], [60, 120]],
        }]
        mask = ImageAugmenter.build_annotation_visibility_mask(image.shape, annotations)
        self.assertGreater(float(mask[80, 100]), 0.95)
        self.assertEqual(float(mask[5, 5]), 0.0)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.png"
            self.assertTrue(cv2.imwrite(str(path), image))
            result, output_annotations, metadata = ImageAugmenter.augment_single_image(
                str(path),
                annotations,
                {
                    "weather": {
                        "overcast": 0.5,
                        "fog": 0.35,
                        "rain": 0.5,
                        "visibility_protection": True,
                        "max_occlusion": 0.15,
                        "seed": 9,
                    }
                },
                return_metadata=True,
            )

        self.assertEqual(result.shape, image.shape)
        self.assertEqual(output_annotations, annotations)
        self.assertEqual(metadata["weather_engine"], "scene-weather-v2")
        self.assertEqual(metadata["rain_layers"], 3)
        self.assertTrue(metadata["visibility_protection"])
        self.assertEqual(metadata["protected_annotations"], 1)


if __name__ == "__main__":
    unittest.main()
