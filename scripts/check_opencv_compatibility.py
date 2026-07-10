from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REQUIRED_SYMBOLS = (
    "VideoCapture",
    "addWeighted",
    "approxPolyDP",
    "arcLength",
    "contourArea",
    "cvtColor",
    "fillPoly",
    "filter2D",
    "findContours",
    "GaussianBlur",
    "getPerspectiveTransform",
    "getRotationMatrix2D",
    "imencode",
    "imread",
    "imwrite",
    "Laplacian",
    "line",
    "perspectiveTransform",
    "polylines",
    "putText",
    "rectangle",
    "resize",
    "warpAffine",
    "warpPerspective",
)


def _major_version(version: str) -> int:
    return int(str(version or "0").split(".", 1)[0])


def run_checks(minimum_major: int = 4) -> Dict[str, Any]:
    missing = [name for name in REQUIRED_SYMBOLS if not hasattr(cv2, name)]
    if missing:
        raise RuntimeError(f"Missing required OpenCV symbols: {', '.join(missing)}")
    if _major_version(cv2.__version__) < minimum_major:
        raise RuntimeError(f"OpenCV {minimum_major}+ is required; found {cv2.__version__}.")

    image = np.zeros((128, 160, 3), dtype=np.uint8)
    cv2.rectangle(image, (12, 14), (92, 104), (20, 180, 240), 2)
    cv2.line(image, (0, 0), (159, 127), (255, 255, 255), 1)
    cv2.putText(image, "VTS", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)
    polygon = np.array([[20, 20], [110, 24], [92, 96], [28, 100]], dtype=np.int32)
    cv2.polylines(image, [polygon], True, (255, 80, 20), 2)

    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [polygon], 255)
    blurred = cv2.GaussianBlur(mask, (5, 5), 0)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise RuntimeError("Contour extraction returned no contours.")
    contour = max(contours, key=cv2.contourArea)
    perimeter = cv2.arcLength(contour, True)
    approximation = cv2.approxPolyDP(contour, max(1.0, perimeter * 0.002), True)

    src = np.float32([[0, 0], [159, 0], [0, 127], [159, 127]])
    dst = np.float32([[3, 2], [155, 4], [5, 123], [157, 125]])
    perspective = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(image, perspective, (160, 128))
    transformed = cv2.perspectiveTransform(polygon.astype(np.float32).reshape(-1, 1, 2), perspective)
    rotation = cv2.getRotationMatrix2D((80, 64), 5, 1.0)
    rotated = cv2.warpAffine(image, rotation, (160, 128))
    filtered = cv2.filter2D(image, -1, np.ones((3, 3), dtype=np.float32) / 9.0)
    resized = cv2.resize(mask, (80, 64), interpolation=cv2.INTER_NEAREST)
    blended = cv2.addWeighted(image, 0.75, warped, 0.25, 0)

    ok_png, encoded_png = cv2.imencode(".png", blended)
    ok_jpg, encoded_jpg = cv2.imencode(".jpg", filtered)
    if not ok_png or not ok_jpg or not encoded_png.size or not encoded_jpg.size:
        raise RuntimeError("OpenCV image encoding failed.")

    with tempfile.TemporaryDirectory(prefix="vts-opencv-") as temp_dir:
        output = Path(temp_dir) / "compatibility.png"
        if not cv2.imwrite(str(output), rotated):
            raise RuntimeError("OpenCV image write failed.")
        decoded = cv2.imread(str(output))
        if decoded is None or decoded.shape != image.shape:
            raise RuntimeError("OpenCV image round trip failed.")

    capture = cv2.VideoCapture()
    capture.release()
    if hsv.shape != image.shape or laplacian.shape != gray.shape or blurred.shape != mask.shape:
        raise RuntimeError("OpenCV color or filtering output shape mismatch.")
    if transformed.shape != (4, 1, 2) or resized.shape != (64, 80):
        raise RuntimeError("OpenCV geometry output shape mismatch.")
    if len(approximation) < 3:
        raise RuntimeError("OpenCV polygon approximation is invalid.")

    from src.augmenter import ImageAugmenter
    from src.dataset_utils import DatasetUtils
    from src.inference_engine import InferenceEngine

    adjusted = ImageAugmenter.adjust_light(image, 0.1, 0.1)
    polygon_points = InferenceEngine._mask_to_polygon_points(mask)
    if adjusted.shape != image.shape or len(polygon_points) < 3:
        raise RuntimeError("Application OpenCV integration check failed.")
    if DatasetUtils.hamming_distance("00", "01") != 1:
        raise RuntimeError("Dataset utility sanity check failed.")

    return {
        "status": "pass",
        "opencv_version": cv2.__version__,
        "numpy_version": np.__version__,
        "required_symbols": len(REQUIRED_SYMBOLS),
        "contours": len(contours),
        "polygon_points": len(polygon_points),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the OpenCV APIs used by Vision Training Studio.")
    parser.add_argument("--minimum-major", type=int, default=4)
    args = parser.parse_args()
    print(json.dumps(run_checks(args.minimum_major), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
