import cv2
import numpy as np
import random
from PIL import Image
from typing import Dict, Any, List, Tuple

class ImageAugmenter:
    WEATHER_ENGINE_VERSION = "scene-weather-v2"
    _SURFACE_LABELS = {
        "road", "street", "ground", "pavement", "sidewalk", "floor",
        "drivablearea", "roadsurface", "路面", "道路", "地面", "人行道", "可行駛區",
    }

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @classmethod
    def build_annotation_visibility_mask(
        cls,
        image_shape: Tuple[int, ...],
        annotations: List[Dict[str, Any]],
    ) -> np.ndarray:
        """Build a feathered target mask for bbox and polygon visibility protection."""
        h, w = image_shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        for ann in annotations or []:
            points = ann.get("points")
            if ann.get("type") == "polygon" and points:
                pts = np.asarray(points, dtype=np.float32).reshape(-1, 2)
                if pts.size and float(np.max(np.abs(pts))) <= 1.0:
                    pts[:, 0] *= w
                    pts[:, 1] *= h
                pts[:, 0] = np.clip(pts[:, 0], 0, w - 1)
                pts[:, 1] = np.clip(pts[:, 1], 0, h - 1)
                if len(pts) >= 3:
                    cv2.fillPoly(mask, [pts.astype(np.int32)], 255)
                    continue

            bbox = ann.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            xc, yc, bw, bh = [float(value) for value in bbox]
            if max(abs(xc), abs(yc), abs(bw), abs(bh)) <= 1.0:
                xc, bw = xc * w, bw * w
                yc, bh = yc * h, bh * h
            x1 = max(0, int(round(xc - bw / 2)))
            y1 = max(0, int(round(yc - bh / 2)))
            x2 = min(w - 1, int(round(xc + bw / 2)))
            y2 = min(h - 1, int(round(yc + bh / 2)))
            if x2 > x1 and y2 > y1:
                cv2.rectangle(mask, (x1, y1), (x2, y2), 255, thickness=-1)

        if np.any(mask):
            feather = max(3, int(round(min(h, w) * 0.012)) | 1)
            mask = cv2.GaussianBlur(mask, (feather, feather), 0)
        return mask.astype(np.float32) / 255.0

    @staticmethod
    def _normalized_category(annotation: Dict[str, Any]) -> str:
        value = str(annotation.get("category") or annotation.get("label") or "").lower()
        return "".join(ch for ch in value if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")

    @classmethod
    def partition_weather_annotations(
        cls,
        image_shape: Tuple[int, ...],
        annotations: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Separate small/object targets from ground-like semantic surfaces."""
        h, w = image_shape[:2]
        protected: List[Dict[str, Any]] = []
        surfaces: List[Dict[str, Any]] = []
        for ann in annotations or []:
            category = cls._normalized_category(ann)
            area_fraction = 0.0
            center_y = 0.0
            bbox = ann.get("bbox")
            if bbox and len(bbox) == 4:
                center_y = float(bbox[1])
                bw, bh = abs(float(bbox[2])), abs(float(bbox[3]))
                if max(bw, bh) > 1.0:
                    bw, bh = bw / max(w, 1), bh / max(h, 1)
                if abs(center_y) > 1.0:
                    center_y /= max(h, 1)
                area_fraction = bw * bh

            is_lower_semantic_surface = (
                ann.get("type") == "polygon"
                and area_fraction >= 0.18
                and center_y >= 0.58
            )
            if category in cls._SURFACE_LABELS or is_lower_semantic_surface:
                surfaces.append(ann)
                continue

            # Boxes and compact instance polygons represent objects whose visual
            # identity must remain readable. Large unknown semantic regions are
            # deliberately not isolated from the weather.
            if ann.get("type") != "polygon" or area_fraction <= 0.18:
                protected.append(ann)
        return protected, surfaces

    @classmethod
    def build_surface_mask(
        cls,
        image_shape: Tuple[int, ...],
        surface_annotations: List[Dict[str, Any]],
    ) -> Tuple[np.ndarray, str]:
        """Return an annotated road mask or a conservative perspective ground prior."""
        h, w = image_shape[:2]
        if surface_annotations:
            return cls.build_annotation_visibility_mask(image_shape, surface_annotations), "annotation"

        y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
        x = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
        vertical = np.clip((y - 0.52) / 0.38, 0.0, 1.0)
        perspective = np.clip(1.18 - 0.28 * np.abs(x), 0.0, 1.0)
        return (vertical * perspective).astype(np.float32), "estimated"

    @classmethod
    def suppress_sunny_cues(cls, image: np.ndarray, intensity: float) -> np.ndarray:
        """Compress bright sky/sun cues without inpainting unrelated highlights."""
        strength = cls._clamp01(intensity)
        if strength <= 0.0:
            return image
        img = image.astype(np.float32) / 255.0
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        top_prior = np.clip((0.72 - np.linspace(0.0, 1.0, h, dtype=np.float32)) / 0.42, 0.0, 1.0)[:, None]
        threshold = max(0.68, float(np.percentile(gray, 88)))
        highlight = np.clip((gray - threshold) / max(1e-4, 1.0 - threshold), 0.0, 1.0)
        highlight = cv2.GaussianBlur(highlight * top_prior, (0, 0), max(2.0, min(h, w) / 90.0))
        highlight = np.clip(highlight * (0.65 + 0.55 * strength), 0.0, 1.0)

        local = cv2.GaussianBlur(img, (0, 0), max(5.0, min(h, w) / 24.0))
        neutral = cv2.cvtColor(local, cv2.COLOR_BGR2GRAY)[:, :, None]
        diffuse = neutral + (local - neutral) * 0.32
        diffuse = np.minimum(diffuse, local * 0.92 + 0.04)
        alpha = (highlight * strength * 0.94)[:, :, None]
        output = img * (1.0 - alpha) + diffuse * alpha
        output *= 1.0 - 0.09 * strength * top_prior[:, :, None]
        return np.clip(output * 255.0, 0, 255).astype(np.uint8)

    @classmethod
    def apply_overcast_grade(cls, image: np.ndarray, intensity: float) -> np.ndarray:
        """Apply a cool, diffuse overcast grade without forcing rain."""
        strength = cls._clamp01(intensity)
        if strength <= 0.0:
            return image

        srgb = image.astype(np.float32) / 255.0
        linear = np.where(
            srgb <= 0.04045,
            srgb / 12.92,
            ((srgb + 0.055) / 1.055) ** 2.4,
        )
        luminance = (
            linear[:, :, 0] * 0.0722
            + linear[:, :, 1] * 0.7152
            + linear[:, :, 2] * 0.2126
        )[:, :, None]
        saturation = 1.0 - 0.42 * strength
        graded = luminance + (linear - luminance) * saturation
        gains = np.array(
            [1.0 + 0.08 * strength, 1.0 - 0.01 * strength, 1.0 - 0.09 * strength],
            dtype=np.float32,
        )
        graded *= gains
        graded *= 2.0 ** (-0.45 * strength)
        scene_mean = np.mean(graded, axis=(0, 1), keepdims=True)
        graded = scene_mean + (graded - scene_mean) * (1.0 - 0.18 * strength)
        graded = graded / (1.0 + 0.12 * strength * graded)
        graded = np.clip(graded, 0.0, 1.0)
        srgb_out = np.where(
            graded <= 0.0031308,
            graded * 12.92,
            1.055 * np.power(graded, 1.0 / 2.4) - 0.055,
        )
        return np.clip(srgb_out * 255.0, 0, 255).astype(np.uint8)

    @staticmethod
    def adjust_light(image: np.ndarray, brightness: float, contrast: float) -> np.ndarray:
        """
        亮度與對比調整。
        brightness: -1.0 to 1.0
        contrast: -1.0 to 1.0
        """
        # 轉換為 float 進行安全計算
        img = image.astype(np.float32)
        
        # 調整對比度: contrast_factor
        if contrast > 0:
            factor = 1.0 + contrast
        else:
            factor = 1.0 / (1.0 - contrast)
        img = (img - 128.0) * factor + 128.0
        
        # 調整亮度
        img = img + brightness * 255.0
        
        return np.clip(img, 0, 255).astype(np.uint8)

    @staticmethod
    def add_shadow(image: np.ndarray) -> np.ndarray:
        """
        加入樹影斑駁 / 局部陰影效果 (疊加半透明隨機多邊形)
        """
        h, w, _ = image.shape
        shadow_mask = np.zeros((h, w), dtype=np.uint8)
        
        # 產生 2-5 個隨機多邊形陰影區
        num_shadows = random.randint(2, 5)
        for _ in range(num_shadows):
            num_pts = random.randint(3, 6)
            pts = []
            for _ in range(num_pts):
                pts.append([random.randint(0, w), random.randint(0, h)])
            pts = np.array(pts, dtype=np.int32)
            cv2.fillPoly(shadow_mask, [pts], 255)
            
        # 對 shadow mask 進行高斯模糊，使陰影邊緣柔和
        shadow_mask = cv2.GaussianBlur(shadow_mask, (49, 49), 0)
        
        # 疊加陰影 (降低陰影區域的亮度 30%-50%)
        shadow_factor = random.uniform(0.5, 0.7)
        img_hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
        img_hsv[:, :, 2] = np.where(shadow_mask > 0, 
                                    img_hsv[:, :, 2] * (1.0 - (shadow_mask / 255.0) * (1.0 - shadow_factor)), 
                                    img_hsv[:, :, 2])
        
        img_hsv = np.clip(img_hsv, 0, 255).astype(np.uint8)
        return cv2.cvtColor(img_hsv, cv2.COLOR_HSV2BGR)

    @staticmethod
    def add_rain(
        image: np.ndarray,
        density: float,
        visibility_mask: np.ndarray | None = None,
        max_occlusion: float = 0.15,
        wind_angle: float = -12.0,
        rng: np.random.Generator | None = None,
    ) -> np.ndarray:
        """Render far, middle and near rain layers with target protection."""
        density = ImageAugmenter._clamp01(density)
        if density <= 0.0:
            return image

        rng = rng or np.random.default_rng()
        h, w = image.shape[:2]
        area = h * w
        result = image.astype(np.float32)
        protection = np.ones((h, w), dtype=np.float32)
        if visibility_mask is not None and np.any(visibility_mask):
            protected_alpha = ImageAugmenter._clamp01(max_occlusion) / 0.35
            protection = 1.0 - visibility_mask * (1.0 - protected_alpha)

        layer_specs = (
            (950, (5, 13), (1, 1), (135, 190), 3, 0.30, "far"),
            (1750, (14, 34), (1, 2), (155, 215), 3, 0.34, "middle"),
            (5800, (34, 78), (1, 3), (175, 230), 5, 0.38, "near"),
        )
        y_norm = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
        for divisor, lengths, thicknesses, colors, blur, opacity, band in layer_specs:
            layer = np.zeros_like(image, dtype=np.uint8)
            count = max(1, int(density * area / divisor))
            for _ in range(count):
                x1 = int(rng.integers(0, max(1, w)))
                y1 = int(rng.integers(0, max(1, h)))
                length = int(rng.integers(lengths[0], lengths[1] + 1))
                angle = float(wind_angle + rng.uniform(-6.0, 6.0))
                x2 = int(round(x1 + length * np.sin(np.radians(angle))))
                y2 = int(round(y1 + length * np.cos(np.radians(angle))))
                thickness = int(rng.integers(thicknesses[0], thicknesses[1] + 1))
                value = int(rng.integers(colors[0], colors[1] + 1))
                cv2.line(layer, (x1, y1), (x2, y2), (value, value, value), thickness)

            layer = cv2.GaussianBlur(layer, (blur, blur), 0).astype(np.float32)
            if band == "far":
                depth_weight = 1.0 - 0.45 * y_norm
            elif band == "near":
                depth_weight = 0.55 + 0.45 * y_norm
            else:
                depth_weight = np.ones_like(y_norm)
            stroke_alpha = cv2.cvtColor(layer.astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
            alpha_map = np.clip(stroke_alpha * density * opacity * depth_weight * protection, 0.0, 0.48)
            airlight = np.array([205.0, 212.0, 216.0], dtype=np.float32)
            result = result * (1.0 - alpha_map[:, :, None]) + airlight * alpha_map[:, :, None]

        return np.clip(result, 0, 255).astype(np.uint8)

    @staticmethod
    def add_fog(
        image: np.ndarray,
        intensity: float,
        visibility_mask: np.ndarray | None = None,
        max_occlusion: float = 0.15,
        rng: np.random.Generator | None = None,
    ) -> np.ndarray:
        """Apply pseudo-depth atmospheric fog: distant regions lose contrast first."""
        intensity = ImageAugmenter._clamp01(intensity)
        if intensity <= 0.0:
            return image

        rng = rng or np.random.default_rng()
        h, w = image.shape[:2]
        y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
        pseudo_depth = np.clip((0.78 - y) / 0.78, 0.0, 1.0)
        noise_h = max(2, h // 64)
        noise_w = max(2, w // 64)
        low_noise = rng.normal(0.0, 1.0, (noise_h, noise_w)).astype(np.float32)
        low_noise = cv2.resize(low_noise, (w, h), interpolation=cv2.INTER_CUBIC)
        low_noise = cv2.GaussianBlur(low_noise, (0, 0), sigmaX=max(4.0, min(h, w) / 35.0))
        low_noise /= max(1e-6, float(np.max(np.abs(low_noise))))
        transmission_loss = intensity * np.clip(
            0.10 + 0.58 * pseudo_depth + 0.08 * low_noise,
            0.0,
            0.72,
        )

        if visibility_mask is not None and np.any(visibility_mask):
            protected_alpha = ImageAugmenter._clamp01(max_occlusion)
            transmission_loss *= 1.0 - visibility_mask * (1.0 - protected_alpha / 0.72)

        airlight = np.array([218.0, 216.0, 208.0], dtype=np.float32)
        alpha = transmission_loss[:, :, None]
        fogged = image.astype(np.float32) * (1.0 - alpha) + airlight * alpha
        return np.clip(fogged, 0, 255).astype(np.uint8)

    @classmethod
    def add_wet_surface(
        cls,
        image: np.ndarray,
        surface_mask: np.ndarray,
        intensity: float,
        puddle_intensity: float = 0.0,
        rng: np.random.Generator | None = None,
    ) -> np.ndarray:
        """Apply a bounded 2.5D wet-material and puddle response."""
        strength = cls._clamp01(intensity)
        puddle_strength = cls._clamp01(puddle_intensity)
        if strength <= 0.0 or surface_mask is None or not np.any(surface_mask):
            return image
        rng = rng or np.random.default_rng()
        h, w = image.shape[:2]
        mask = cv2.GaussianBlur(np.clip(surface_mask.astype(np.float32), 0.0, 1.0), (0, 0), 1.6)
        mask *= strength

        noise = rng.random((max(2, h // 42), max(2, w // 42)), dtype=np.float32)
        noise = cv2.resize(noise, (w, h), interpolation=cv2.INTER_CUBIC)
        noise = cv2.GaussianBlur(noise, (0, 0), max(3.0, min(h, w) / 58.0))
        noise = (noise - float(noise.min())) / max(1e-6, float(noise.max() - noise.min()))
        puddles = np.clip((noise - 0.56) / 0.22, 0.0, 1.0) * mask * puddle_strength

        img = image.astype(np.float32) / 255.0
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)[:, :, None]
        wet3 = mask[:, :, None]
        output = gray + (img - gray) * (1.0 - 0.18 * wet3)
        output *= 1.0 - 0.16 * wet3

        # A low-energy, vertically blurred environment response avoids the hard
        # mirror artifacts of a literal image flip.
        environment = cv2.GaussianBlur(img, (0, 0), max(2.0, min(h, w) / 110.0))
        environment = cv2.blur(environment, (3, max(5, int(h * 0.035) | 1)))
        reflection_alpha = np.clip((0.035 * mask + 0.16 * puddles), 0.0, 0.20)[:, :, None]
        output = output * (1.0 - reflection_alpha) + environment * reflection_alpha

        # Compact specular response follows existing bright detail rather than
        # inventing new scene geometry.
        detail = np.maximum(cv2.Laplacian(gray[:, :, 0], cv2.CV_32F), 0.0)
        detail /= max(1e-6, float(np.percentile(detail, 99)))
        specular = np.clip(detail, 0.0, 1.0) * (0.07 * mask + 0.14 * puddles)
        output += specular[:, :, None]
        return np.clip(output * 255.0, 0, 255).astype(np.uint8)

    @classmethod
    def add_ground_splashes(
        cls,
        image: np.ndarray,
        surface_mask: np.ndarray,
        intensity: float,
        rng: np.random.Generator | None = None,
    ) -> np.ndarray:
        """Render sparse ground impacts and ripples only on wettable surfaces."""
        strength = cls._clamp01(intensity)
        if strength <= 0.0 or surface_mask is None or not np.any(surface_mask):
            return image
        rng = rng or np.random.default_rng()
        h, w = image.shape[:2]
        layer = np.zeros_like(image, dtype=np.uint8)
        valid = np.argwhere(surface_mask > 0.35)
        if not len(valid):
            return image
        count = max(1, int(strength * h * w / 6500))
        for _ in range(count):
            y, x = valid[int(rng.integers(0, len(valid)))]
            scale = 0.45 + 0.9 * (float(y) / max(1, h - 1))
            radius = max(1, int(round(scale * rng.uniform(2.0, 5.0))))
            color = int(rng.integers(175, 225))
            cv2.ellipse(layer, (int(x), int(y)), (radius * 2, radius), 0, 0, 360, (color,) * 3, 1)
            if rng.random() < 0.65:
                cv2.line(layer, (int(x), int(y)), (int(x), max(0, int(y - radius * 2))), (color,) * 3, 1)
        layer = cv2.GaussianBlur(layer, (3, 3), 0).astype(np.float32)
        alpha = cv2.cvtColor(layer.astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        alpha *= surface_mask * (0.18 + 0.34 * strength)
        target = np.array([210.0, 216.0, 218.0], dtype=np.float32)
        result = image.astype(np.float32) * (1.0 - alpha[:, :, None]) + target * alpha[:, :, None]
        return np.clip(result, 0, 255).astype(np.uint8)

    @classmethod
    def add_lens_droplets(
        cls,
        image: np.ndarray,
        intensity: float,
        visibility_mask: np.ndarray | None = None,
        max_occlusion: float = 0.15,
        rng: np.random.Generator | None = None,
    ) -> np.ndarray:
        """Screen-space refractive droplets, kept separate from world weather."""
        strength = cls._clamp01(intensity)
        if strength <= 0.0:
            return image
        rng = rng or np.random.default_rng()
        h, w = image.shape[:2]
        height_map = np.zeros((h, w), dtype=np.float32)
        count = max(1, int(strength * h * w / 3200))
        min_dim = min(h, w)
        for _ in range(count):
            cx, cy = int(rng.integers(0, w)), int(rng.integers(0, h))
            radius = int(rng.integers(max(2, int(min_dim * 0.008)), max(3, int(min_dim * 0.052))))
            rx, ry = radius, max(radius, int(radius * rng.uniform(1.0, 1.7)))
            x1, x2 = max(0, cx - rx), min(w, cx + rx + 1)
            y1, y2 = max(0, cy - ry), min(h, cy + ry + 1)
            yy, xx = np.ogrid[y1:y2, x1:x2]
            dome = np.clip(1.0 - ((xx - cx) / max(rx, 1)) ** 2 - ((yy - cy) / max(ry, 1)) ** 2, 0.0, 1.0) ** 0.65
            np.maximum(height_map[y1:y2, x1:x2], dome.astype(np.float32), out=height_map[y1:y2, x1:x2])

        if visibility_mask is not None and np.any(visibility_mask):
            allowed = 1.0 - visibility_mask * (1.0 - cls._clamp01(max_occlusion) / 0.35)
            height_map *= allowed
        height_map = cv2.GaussianBlur(height_map, (0, 0), 0.9)
        gx = cv2.Sobel(height_map, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(height_map, cv2.CV_32F, 0, 1, ksize=3)
        scale = max(1e-6, float(np.percentile(np.sqrt(gx * gx + gy * gy), 99)))
        gx, gy = np.clip(gx / scale, -1.0, 1.0), np.clip(gy / scale, -1.0, 1.0)
        grid_x, grid_y = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        displacement = 2.0 + 7.0 * strength
        refracted = cv2.remap(image, grid_x + gx * displacement, grid_y + gy * displacement, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT101)
        refracted = cv2.GaussianBlur(refracted, (0, 0), 0.45 + 0.65 * strength)
        alpha = np.clip(height_map * (0.36 + 0.48 * strength), 0.0, 0.76)
        result = image.astype(np.float32) * (1.0 - alpha[:, :, None]) + refracted.astype(np.float32) * alpha[:, :, None]
        edge = np.clip(np.sqrt(gx * gx + gy * gy), 0.0, 1.0) * alpha
        result += edge[:, :, None] * (16.0 + 30.0 * strength)
        return np.clip(result, 0, 255).astype(np.uint8)

    @staticmethod
    def add_motion_blur(image: np.ndarray, intensity: float) -> np.ndarray:
        """
        運動模糊
        intensity: 0.0 to 1.0
        """
        if intensity <= 0.0:
            return image
            
        size = int(intensity * 25)
        if size % 2 == 0:
            size += 1
        size = max(3, size)
        
        # 建立運動模糊 Kernel (水平或斜向)
        kernel = np.zeros((size, size))
        kernel[int((size - 1)/2), :] = np.ones(size)
        kernel = kernel / size
        
        # 旋轉 Kernel 得到隨機方向
        angle = random.randint(-45, 45)
        M = cv2.getRotationMatrix2D((size/2, size/2), angle, 1)
        kernel = cv2.warpAffine(kernel, M, (size, size))
        
        return cv2.filter2D(image, -1, kernel)

    @staticmethod
    def add_noise(image: np.ndarray, intensity: float) -> np.ndarray:
        """
        加入高斯噪聲
        intensity: 0.0 to 1.0
        """
        if intensity <= 0.0:
            return image
        
        h, w, c = image.shape
        mean = 0
        sigma = intensity * 40
        gauss = np.random.normal(mean, sigma, (h, w, c))
        noisy = image.astype(np.float32) + gauss
        return np.clip(noisy, 0, 255).astype(np.uint8)

    @classmethod
    def adjust_color(
        cls,
        image: np.ndarray,
        temperature: float = 0.0,
        saturation: float = 0.0,
        hue: float = 0.0,
        sharpness: float = 0.0,
    ) -> np.ndarray:
        """Apply bounded color-temperature, HSV, and unsharp-mask adjustments."""
        output = image.astype(np.float32)
        temp = max(-1.0, min(1.0, float(temperature)))
        if temp != 0.0:
            # BGR gains: positive values warm the image, negative values cool it.
            output[:, :, 2] *= 1.0 + 0.18 * temp
            output[:, :, 0] *= 1.0 - 0.18 * temp
        output = np.clip(output, 0, 255).astype(np.uint8)

        sat = max(-1.0, min(1.0, float(saturation)))
        hue_shift = max(-0.5, min(0.5, float(hue)))
        if sat != 0.0 or hue_shift != 0.0:
            hsv = cv2.cvtColor(output, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[:, :, 1] *= max(0.0, 1.0 + sat)
            hsv[:, :, 0] = np.mod(hsv[:, :, 0] + hue_shift * 90.0, 180.0)
            output = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)

        amount = cls._clamp01(sharpness)
        if amount > 0.0:
            blurred = cv2.GaussianBlur(output, (0, 0), 1.0)
            output = cv2.addWeighted(output, 1.0 + 1.4 * amount, blurred, -1.4 * amount, 0)
        return output

    @classmethod
    def add_gaussian_blur(cls, image: np.ndarray, intensity: float) -> np.ndarray:
        strength = cls._clamp01(intensity)
        if strength <= 0.0:
            return image
        sigma = 0.35 + 3.2 * strength
        return cv2.GaussianBlur(image, (0, 0), sigma)

    @classmethod
    def add_compression_artifacts(cls, image: np.ndarray, intensity: float) -> np.ndarray:
        strength = cls._clamp01(intensity)
        if strength <= 0.0:
            return image
        quality = int(round(96 - 66 * strength))
        ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            return image
        decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        return decoded if decoded is not None else image

    @staticmethod
    def _transform_annotations(
        annotations: List[Dict[str, Any]],
        matrix: np.ndarray,
        width: int,
        height: int,
    ) -> List[Dict[str, Any]]:
        """Transform polygon and bbox coordinates with a 2x3 affine matrix."""
        transformed: List[Dict[str, Any]] = []
        for ann in annotations or []:
            points = ann.get("points") if ann.get("type") == "polygon" else None
            if points:
                pts = np.asarray(points, dtype=np.float32).reshape(-1, 2)
                if pts.size and float(np.max(np.abs(pts))) <= 1.0:
                    pts[:, 0] *= width
                    pts[:, 1] *= height
            else:
                bbox = ann.get("bbox")
                if not bbox or len(bbox) != 4:
                    continue
                xc, yc, bw, bh = [float(value) for value in bbox]
                if max(abs(xc), abs(yc), abs(bw), abs(bh)) <= 1.0:
                    xc, bw = xc * width, bw * width
                    yc, bh = yc * height, bh * height
                pts = np.asarray([
                    [xc - bw / 2, yc - bh / 2],
                    [xc + bw / 2, yc - bh / 2],
                    [xc + bw / 2, yc + bh / 2],
                    [xc - bw / 2, yc + bh / 2],
                ], dtype=np.float32)

            warped = cv2.transform(pts.reshape(-1, 1, 2), matrix).reshape(-1, 2)
            warped[:, 0] = np.clip(warped[:, 0], 0, width - 1)
            warped[:, 1] = np.clip(warped[:, 1], 0, height - 1)
            x1, y1 = np.min(warped, axis=0)
            x2, y2 = np.max(warped, axis=0)
            if x2 - x1 <= 2 or y2 - y1 <= 2:
                continue
            updated = dict(ann)
            updated["bbox"] = [
                float((x1 + x2) / 2 / width),
                float((y1 + y2) / 2 / height),
                float((x2 - x1) / width),
                float((y2 - y1) / height),
            ]
            if points:
                updated["points"] = warped.tolist()
            transformed.append(updated)
        return transformed

    @classmethod
    def apply_geometry(
        cls,
        image: np.ndarray,
        annotations: List[Dict[str, Any]],
        rotation: float,
        scale_variance: float,
        horizontal_flip: bool,
        vertical_flip: bool,
        random_crop: float,
        rng: np.random.Generator,
    ) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        """Apply deterministic affine/crop transforms and keep annotations aligned."""
        h, w = image.shape[:2]
        output = image
        updated = annotations
        rotation = max(0.0, min(20.0, float(rotation)))
        scale_variance = max(0.0, min(0.2, float(scale_variance)))
        if rotation > 0.0 or scale_variance > 0.0:
            angle = float(rng.uniform(-rotation, rotation))
            scale = float(rng.uniform(1.0 - scale_variance, 1.0 + scale_variance))
            matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, scale).astype(np.float32)
            output = cv2.warpAffine(output, matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT101)
            updated = cls._transform_annotations(updated, matrix, w, h)

        if horizontal_flip:
            matrix = np.asarray([[-1.0, 0.0, w - 1.0], [0.0, 1.0, 0.0]], dtype=np.float32)
            output = cv2.flip(output, 1)
            updated = cls._transform_annotations(updated, matrix, w, h)
        if vertical_flip:
            matrix = np.asarray([[1.0, 0.0, 0.0], [0.0, -1.0, h - 1.0]], dtype=np.float32)
            output = cv2.flip(output, 0)
            updated = cls._transform_annotations(updated, matrix, w, h)

        crop = max(0.0, min(0.2, float(random_crop)))
        if crop > 0.0:
            fraction = float(rng.uniform(crop * 0.45, crop))
            crop_w = max(8, int(round(w * (1.0 - fraction))))
            crop_h = max(8, int(round(h * (1.0 - fraction))))
            x0 = int(rng.integers(0, max(1, w - crop_w + 1)))
            y0 = int(rng.integers(0, max(1, h - crop_h + 1)))
            matrix = np.asarray([
                [w / crop_w, 0.0, -x0 * w / crop_w],
                [0.0, h / crop_h, -y0 * h / crop_h],
            ], dtype=np.float32)
            output = cv2.warpAffine(output, matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT101)
            updated = cls._transform_annotations(updated, matrix, w, h)
        return output, updated

    @classmethod
    def add_random_occlusion(
        cls,
        image: np.ndarray,
        intensity: float,
        visibility_mask: np.ndarray | None,
        max_occlusion: float,
        rng: np.random.Generator,
    ) -> np.ndarray:
        strength = max(0.0, min(0.5, float(intensity)))
        if strength <= 0.0:
            return image
        h, w = image.shape[:2]
        mask = np.zeros((h, w), dtype=np.float32)
        for _ in range(1 + int(round(strength * 5))):
            rw = int(rng.uniform(0.05, 0.10 + 0.22 * strength) * w)
            rh = int(rng.uniform(0.05, 0.10 + 0.22 * strength) * h)
            x = int(rng.integers(0, max(1, w - rw + 1)))
            y = int(rng.integers(0, max(1, h - rh + 1)))
            cv2.rectangle(mask, (x, y), (min(w - 1, x + rw), min(h - 1, y + rh)), 1.0, -1)
        mask = cv2.GaussianBlur(mask, (0, 0), max(1.0, min(h, w) / 260.0))
        if visibility_mask is not None:
            allowed = 1.0 - visibility_mask * (1.0 - cls._clamp01(max_occlusion))
            mask *= allowed
        fill = cv2.GaussianBlur(image, (0, 0), 8.0 + 8.0 * strength).astype(np.float32)
        alpha = np.clip(mask * (0.45 + 0.45 * strength), 0.0, 0.9)[:, :, None]
        result = image.astype(np.float32) * (1.0 - alpha) + fill * alpha
        return np.clip(result, 0, 255).astype(np.uint8)
    @staticmethod
    def apply_perspective(image: np.ndarray, bboxes: List[Dict[str, Any]], intensity: float) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        """Apply perspective transform to the image and preserve bbox or polygon annotations."""
        if intensity <= 0.0:
            return image, bboxes

        h, w, _ = image.shape
        src_pts = np.float32([[0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1]])
        max_offset = int(min(h, w) * intensity)
        dst_pts = np.float32([
            [random.randint(0, max_offset), random.randint(0, max_offset)],
            [w - 1 - random.randint(0, max_offset), random.randint(0, max_offset)],
            [random.randint(0, max_offset), h - 1 - random.randint(0, max_offset)],
            [w - 1 - random.randint(0, max_offset), h - 1 - random.randint(0, max_offset)]
        ])

        H = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped_img = cv2.warpPerspective(image, H, (w, h))
        warped_annotations = []

        for ann in bboxes:
            category = ann["category"]
            ann_type = ann.get("type", "bbox")

            if ann_type == "polygon" and ann.get("points"):
                pts = np.array(ann["points"], dtype=np.float32).reshape(-1, 1, 2)
                warped_pts = cv2.perspectiveTransform(pts, H).reshape(-1, 2)
                warped_pts[:, 0] = np.clip(warped_pts[:, 0], 0, w - 1)
                warped_pts[:, 1] = np.clip(warped_pts[:, 1], 0, h - 1)
                if len(warped_pts) < 3:
                    continue

                wx = warped_pts[:, 0]
                wy = warped_pts[:, 1]
                new_x1 = max(0.0, float(np.min(wx)))
                new_y1 = max(0.0, float(np.min(wy)))
                new_x2 = min(float(w), float(np.max(wx)))
                new_y2 = min(float(h), float(np.max(wy)))
                new_w = new_x2 - new_x1
                new_h = new_y2 - new_y1
                if new_w > 2 and new_h > 2:
                    warped_annotations.append({
                        "category": category,
                        "type": "polygon",
                        "bbox": [(new_x1 + new_w / 2) / w, (new_y1 + new_h / 2) / h, new_w / w, new_h / h],
                        "points": warped_pts.tolist()
                    })
                continue

            bbox = ann.get("bbox")
            if not bbox or len(bbox) != 4:
                continue

            xc, yc, bw, bh = bbox[0] * w, bbox[1] * h, bbox[2] * w, bbox[3] * h
            x1, y1 = xc - bw / 2, yc - bh / 2
            x2, y2 = xc + bw / 2, yc - bh / 2
            x3, y3 = xc - bw / 2, yc + bh / 2
            x4, y4 = xc + bw / 2, yc + bh / 2

            pts = np.array([[x1, y1], [x2, y2], [x3, y3], [x4, y4]], dtype=np.float32).reshape(-1, 1, 2)
            warped_pts = cv2.perspectiveTransform(pts, H).reshape(-1, 2)
            wx = warped_pts[:, 0]
            wy = warped_pts[:, 1]
            new_x1 = max(0.0, float(np.min(wx)))
            new_y1 = max(0.0, float(np.min(wy)))
            new_x2 = min(float(w), float(np.max(wx)))
            new_y2 = min(float(h), float(np.max(wy)))
            new_w = new_x2 - new_x1
            new_h = new_y2 - new_y1

            if new_w > 2 and new_h > 2:
                warped_annotations.append({
                    "category": category,
                    "type": ann_type,
                    "bbox": [(new_x1 + new_w / 2) / w, (new_y1 + new_h / 2) / h, new_w / w, new_h / h]
                })

        return warped_img, warped_annotations

    @classmethod
    def augment_single_image(
        cls, 
        image_path: str, 
        bboxes: List[Dict[str, Any]], 
        config: Dict[str, Any],
        return_metadata: bool = False,
    ) -> Tuple[np.ndarray, List[Dict[str, Any]]] | Tuple[np.ndarray, List[Dict[str, Any]], Dict[str, Any]]:
        """
        對單張影像套用一整組擴充設定，並回傳擴充後的 image ndarray 與對應的 bboxes。
        """
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"無法讀取圖片: {image_path}")
            
        augmented_img = img.copy()
        augmented_bboxes = [b.copy() for b in bboxes]
        
        # 1. 調整光照與對比
        light_cfg = config.get("light", {})
        br = float(light_cfg.get("brightness", 0.0))
        co = float(light_cfg.get("contrast", 0.0))
        if br != 0.0 or co != 0.0:
            # 加入一點隨機微調
            r_br = br + random.uniform(-0.05, 0.05) if br != 0.0 else 0.0
            r_co = co + random.uniform(-0.05, 0.05) if co != 0.0 else 0.0
            augmented_img = cls.adjust_light(augmented_img, r_br, r_co)
        temperature = max(-1.0, min(1.0, float(light_cfg.get("temperature", 0.0))))
        if temperature != 0.0:
            augmented_img = cls.adjust_color(augmented_img, temperature=temperature)
            
        # 2. 局部陰影
        if light_cfg.get("shadow", False):
            augmented_img = cls.add_shadow(augmented_img)

        weather_cfg = config.get("weather", {})
        seed = weather_cfg.get("seed")
        rng = np.random.default_rng(int(seed)) if seed is not None else np.random.default_rng()
        geometry_cfg = config.get("geometry", {}) or {}
        augmented_img, augmented_bboxes = cls.apply_geometry(
            augmented_img,
            augmented_bboxes,
            geometry_cfg.get("rotation", 0.0),
            geometry_cfg.get("scale", 0.0),
            bool(geometry_cfg.get("horizontal_flip", False)),
            bool(geometry_cfg.get("vertical_flip", False)),
            geometry_cfg.get("random_crop", 0.0),
            rng,
        )
        camera_cfg = config.get("camera", {}) or {}
        perspective = max(0.0, min(0.08, float(camera_cfg.get("perspective", 0.0))))
        if perspective > 0.0:
            augmented_img, augmented_bboxes = cls.apply_perspective(
                augmented_img, augmented_bboxes, perspective
            )

        # 3. 雨天
        overcast = cls._clamp01(weather_cfg.get("overcast", 0.0))
        rain = cls._clamp01(weather_cfg.get("rain", 0.0))
        fog = cls._clamp01(weather_cfg.get("fog", 0.0))
        sun_suppression = cls._clamp01(weather_cfg.get("sun_suppression", overcast))
        wet_surface = cls._clamp01(weather_cfg.get("wet_surface", 0.0))
        puddle = cls._clamp01(weather_cfg.get("puddle", 0.0))
        splash = cls._clamp01(weather_cfg.get("splash", 0.0))
        wind_angle = max(-45.0, min(45.0, float(weather_cfg.get("wind_angle", -12.0))))
        protect_visibility = bool(weather_cfg.get("visibility_protection", True))
        max_occlusion = max(0.05, min(0.35, float(weather_cfg.get("max_occlusion", 0.15))))
        protected_annotations, surface_annotations = cls.partition_weather_annotations(
            augmented_img.shape, augmented_bboxes
        )
        visibility_mask = (
            cls.build_annotation_visibility_mask(augmented_img.shape, protected_annotations)
            if protect_visibility else None
        )
        surface_mask, surface_mask_source = cls.build_surface_mask(
            augmented_img.shape, surface_annotations
        )
        if sun_suppression > 0.0:
            augmented_img = cls.suppress_sunny_cues(augmented_img, sun_suppression)
        if overcast > 0.0:
            augmented_img = cls.apply_overcast_grade(augmented_img, overcast)

        if wet_surface > 0.0:
            augmented_img = cls.add_wet_surface(
                augmented_img, surface_mask, wet_surface, puddle, rng
            )
            
        # 4. 霧氣
        if fog > 0.0:
            augmented_img = cls.add_fog(augmented_img, fog, visibility_mask, max_occlusion, rng)
        if rain > 0.0:
            augmented_img = cls.add_rain(
                augmented_img, rain, visibility_mask, max_occlusion,
                wind_angle=wind_angle, rng=rng,
            )
        if splash > 0.0:
            augmented_img = cls.add_ground_splashes(
                augmented_img, surface_mask, splash, rng
            )
            
        # 5. 運動模糊
        motion_cfg = config.get("motion", {})
        blur = float(motion_cfg.get("motion_blur", 0.0))
        if blur > 0.0:
            augmented_img = cls.add_motion_blur(augmented_img, blur)
        gaussian_blur = cls._clamp01(motion_cfg.get("gaussian_blur", 0.0))
        if gaussian_blur > 0.0:
            augmented_img = cls.add_gaussian_blur(augmented_img, gaussian_blur)
            
        # 6. 相機雜訊
        lens_droplets = cls._clamp01(camera_cfg.get("lens_droplets", 0.0))
        if lens_droplets > 0.0:
            augmented_img = cls.add_lens_droplets(
                augmented_img, lens_droplets, visibility_mask, max_occlusion, rng
            )
        noise = float(camera_cfg.get("noise", 0.0))
        if noise > 0.0:
            augmented_img = cls.add_noise(augmented_img, noise)
        compression = cls._clamp01(camera_cfg.get("compression", 0.0))
        if compression > 0.0:
            augmented_img = cls.add_compression_artifacts(augmented_img, compression)

        occlusion_cfg = config.get("occlusion", {}) or {}
        random_occlusion = max(0.0, min(0.5, float(occlusion_cfg.get("intensity", 0.0))))
        if random_occlusion > 0.0:
            augmented_img = cls.add_random_occlusion(
                augmented_img, random_occlusion, visibility_mask, max_occlusion, rng
            )

        color_cfg = config.get("color", {}) or {}
        saturation = max(-1.0, min(1.0, float(color_cfg.get("saturation", 0.0))))
        hue = max(-0.5, min(0.5, float(color_cfg.get("hue", 0.0))))
        sharpness = cls._clamp01(color_cfg.get("sharpness", 0.0))
        if saturation != 0.0 or hue != 0.0 or sharpness > 0.0:
            augmented_img = cls.adjust_color(
                augmented_img, saturation=saturation, hue=hue, sharpness=sharpness
            )
            
        metadata = {
            "weather_engine": cls.WEATHER_ENGINE_VERSION,
            "overcast_strength": overcast,
            "sun_suppression_strength": sun_suppression,
            "depth_fog_strength": fog,
            "rain_strength": rain,
            "rain_layers": 3 if rain > 0 else 0,
            "wet_surface_strength": wet_surface,
            "puddle_strength": puddle,
            "splash_strength": splash,
            "lens_droplets_strength": lens_droplets,
            "temperature": temperature,
            "gaussian_blur": gaussian_blur,
            "compression": compression,
            "perspective": perspective,
            "rotation": float(geometry_cfg.get("rotation", 0.0) or 0.0),
            "scale": float(geometry_cfg.get("scale", 0.0) or 0.0),
            "horizontal_flip": bool(geometry_cfg.get("horizontal_flip", False)),
            "vertical_flip": bool(geometry_cfg.get("vertical_flip", False)),
            "random_crop": float(geometry_cfg.get("random_crop", 0.0) or 0.0),
            "random_occlusion": random_occlusion,
            "saturation": saturation,
            "hue": hue,
            "sharpness": sharpness,
            "surface_mask_source": surface_mask_source,
            "visibility_protection": protect_visibility,
            "max_occlusion": max_occlusion,
            "protected_annotations": len(protected_annotations) if protect_visibility else 0,
            "surface_annotations": len(surface_annotations),
            "seed": int(seed) if seed is not None else None,
        }
        if return_metadata:
            return augmented_img, augmented_bboxes, metadata
        return augmented_img, augmented_bboxes
