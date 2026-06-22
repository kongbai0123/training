import cv2
import numpy as np
import random
from PIL import Image
from typing import Dict, Any, List, Tuple

class ImageAugmenter:
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
        
        return np.clip(img_hsv, 0, 255).astype(np.uint8)

    @staticmethod
    def add_rain(image: np.ndarray, density: float) -> np.ndarray:
        """
        模擬雨天效果 (畫上隨機半透明斜向白線)
        density: 0.0 to 1.0
        """
        if density <= 0.0:
            return image
            
        h, w, c = image.shape
        rain_layer = np.zeros_like(image, dtype=np.uint8)
        
        # 線的數量取決於 density
        num_lines = int(density * 150)
        for _ in range(num_lines):
            x1 = random.randint(0, w)
            y1 = random.randint(0, h - 50)
            length = random.randint(15, 35)
            angle = random.randint(-15, -5) # 斜向
            
            x2 = int(x1 + length * np.sin(np.radians(angle)))
            y2 = int(y1 + length * np.cos(np.radians(angle)))
            
            thickness = random.randint(1, 2)
            color = random.randint(200, 255)
            
            cv2.line(rain_layer, (x1, y1), (x2, y2), (color, color, color), thickness)
            
        # 模糊雨線
        rain_layer = cv2.GaussianBlur(rain_layer, (3, 3), 0)
        
        # 與原圖混色
        alpha = 0.85
        return cv2.addWeighted(image, alpha, rain_layer, 1 - alpha, 0)

    @staticmethod
    def add_fog(image: np.ndarray, intensity: float) -> np.ndarray:
        """
        模擬霧氣 (疊加白色半透明層)
        intensity: 0.0 to 1.0
        """
        if intensity <= 0.0:
            return image
            
        h, w, c = image.shape
        # 霧氣是不均勻的，用高斯模糊生成不規則的霧分布
        fog_mask = np.ones((h, w), dtype=np.float32) * intensity * 0.7
        # 加入點雜訊或隨機變化
        noise = np.random.normal(0, 0.1, (h, w)).astype(np.float32)
        fog_mask = np.clip(fog_mask + noise, 0, 1.0)
        fog_mask = cv2.GaussianBlur(fog_mask, (101, 101), 0)
        
        # 霧氣顏色
        fog_color = np.array([230, 230, 230], dtype=np.uint8)
        
        # 混合
        fog_mask = np.expand_dims(fog_mask, axis=2)
        fogged = image.astype(np.float32) * (1.0 - fog_mask) + fog_color * fog_mask
        return np.clip(fogged, 0, 255).astype(np.uint8)

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
        config: Dict[str, Any]
    ) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
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
            
        # 2. 局部陰影
        if light_cfg.get("shadow", False):
            augmented_img = cls.add_shadow(augmented_img)
            
        # 3. 雨天
        weather_cfg = config.get("weather", {})
        rain = float(weather_cfg.get("rain", 0.0))
        if rain > 0.0:
            augmented_img = cls.add_rain(augmented_img, rain)
            
        # 4. 霧氣
        fog = float(weather_cfg.get("fog", 0.0))
        if fog > 0.0:
            augmented_img = cls.add_fog(augmented_img, fog)
            
        # 5. 運動模糊
        motion_cfg = config.get("motion", {})
        blur = float(motion_cfg.get("motion_blur", 0.0))
        if blur > 0.0:
            augmented_img = cls.add_motion_blur(augmented_img, blur)
            
        # 6. 相機雜訊
        camera_cfg = config.get("camera", {})
        noise = float(camera_cfg.get("noise", 0.0))
        if noise > 0.0:
            augmented_img = cls.add_noise(augmented_img, noise)
            
        # 7. 透視變換 (幾何)
        perspective = float(camera_cfg.get("perspective", 0.0))
        if perspective > 0.0:
            augmented_img, augmented_bboxes = cls.apply_perspective(augmented_img, augmented_bboxes, perspective)
            
        return augmented_img, augmented_bboxes
