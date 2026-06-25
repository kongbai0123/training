from __future__ import annotations

import csv
import json
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import Image

from src.project_layout import ProjectLayout
from src.security_utils import safe_filename


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")
MASK_EXTENSIONS = (".png", ".tif", ".tiff")


class AnnotationImporter:
    """Convert external annotation files into LabelMe-compatible JSON drafts."""

    @staticmethod
    def create_import_id() -> str:
        return f"imp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    @staticmethod
    def draft_root(layout: ProjectLayout, import_id: str) -> Path:
        return layout.project_dir / "annotations" / "drafts" / "import" / import_id

    @staticmethod
    def import_files(project: Dict[str, Any], source_files: List[Path], import_id: Optional[str] = None, csv_mapping: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        import_id = import_id or AnnotationImporter.create_import_id()
        root = AnnotationImporter.draft_root(layout, import_id)
        source_dir = root / "source"
        labelme_dir = root / "labelme"
        source_dir.mkdir(parents=True, exist_ok=True)
        labelme_dir.mkdir(parents=True, exist_ok=True)

        report: Dict[str, Any] = {
            "import_id": import_id,
            "created_at": datetime.now().isoformat(),
            "target_format": "labelme",
            "total_files": 0,
            "labelme_json": 0,
            "coco_json": 0,
            "yolo_txt": 0,
            "csv": 0,
            "voc_xml": 0,
            "mask_png": 0,
            "converted": 0,
            "failed": 0,
            "csv_mapping": csv_mapping or {},
            "warnings": [],
            "errors": [],
            "converted_files": [],
        }

        grouped_csv_rows: Dict[str, List[Dict[str, str]]] = {}
        csv_sources: List[str] = []

        for source in source_files:
            if not source.exists() or not source.is_file():
                continue
            report["total_files"] += 1
            cleaned_name = safe_filename(source.name)
            staged_path = source_dir / cleaned_name
            shutil.copy2(source, staged_path)
            suffix = staged_path.suffix.lower()

            try:
                if suffix == ".txt":
                    report["yolo_txt"] += 1
                    converted = AnnotationImporter._convert_yolo_txt(project, layout, staged_path, labelme_dir)
                    AnnotationImporter._record_converted(report, converted)
                elif suffix == ".json":
                    converted, source_format = AnnotationImporter._accept_json(project, layout, staged_path, labelme_dir)
                    if source_format == "coco_json":
                        report["coco_json"] += 1
                    else:
                        report["labelme_json"] += 1
                    AnnotationImporter._record_converted(report, converted)
                elif suffix == ".csv":
                    report["csv"] += 1
                    file_csv_mapping = AnnotationImporter._csv_mapping_for_file(csv_mapping or {}, staged_path.name)
                    rows = AnnotationImporter._read_csv_rows(staged_path)
                    for row in rows:
                        mapped = AnnotationImporter._apply_csv_mapping(row, file_csv_mapping)
                        filename = (mapped.get("filename") or row.get("filename") or row.get("image") or row.get("imagePath") or "").strip()
                        if filename:
                            row_with_source = dict(row)
                            row_with_source["_csv_source"] = staged_path.name
                            grouped_csv_rows.setdefault(filename, []).append(row_with_source)
                    csv_sources.append(staged_path.name)
                elif suffix == ".xml":
                    report["voc_xml"] += 1
                    converted = AnnotationImporter._convert_voc_xml(project, layout, staged_path, labelme_dir)
                    AnnotationImporter._record_converted(report, converted)
                elif suffix in MASK_EXTENSIONS:
                    report["mask_png"] += 1
                    converted = AnnotationImporter._convert_mask_image(project, layout, staged_path, labelme_dir)
                    AnnotationImporter._record_converted(report, converted)
                else:
                    report["failed"] += 1
                    report["errors"].append({"file": staged_path.name, "message": "Unsupported annotation file extension."})
            except Exception as exc:
                report["failed"] += 1
                report["errors"].append({"file": staged_path.name, "message": str(exc)})

        if grouped_csv_rows:
            for filename, rows in grouped_csv_rows.items():
                try:
                    source_name = rows[0].get("_csv_source", "") if rows else ""
                    file_csv_mapping = AnnotationImporter._csv_mapping_for_file(csv_mapping or {}, source_name)
                    converted = AnnotationImporter._convert_csv_rows(project, layout, filename, rows, labelme_dir, csv_sources, file_csv_mapping)
                    AnnotationImporter._record_converted(report, converted)
                except Exception as exc:
                    report["failed"] += len(rows)
                    report["errors"].append({"file": filename, "message": str(exc)})

        report_path = root / "import_report.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return report

    @staticmethod
    def latest_report(project: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        layout = ProjectLayout.from_project(project)
        imports_dir = layout.project_dir / "annotations" / "drafts" / "import"
        if not imports_dir.exists():
            return None
        reports = sorted(imports_dir.glob("*/import_report.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not reports:
            return None
        return json.loads(reports[0].read_text(encoding="utf-8"))

    @staticmethod
    def apply_import(project: Dict[str, Any], import_id: str) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        root = AnnotationImporter.draft_root(layout, import_id)
        report_path = root / "import_report.json"
        draft_labelme = root / "labelme"
        if not report_path.exists() or not draft_labelme.exists():
            raise ValueError(f"Import draft not found: {import_id}")

        current_labelme = layout.resolve_current_labelme_dir().path
        current_labelme.mkdir(parents=True, exist_ok=True)

        applied = 0
        merged_files = 0
        skipped_duplicates = 0
        for json_file in draft_labelme.glob("*.json"):
            result = AnnotationImporter._merge_labelme_json(json_file, current_labelme / json_file.name)
            applied += result["added"]
            merged_files += 1
            skipped_duplicates += result["duplicates"]

        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["applied_at"] = datetime.now().isoformat()
        report["applied_count"] = applied
        report["applied_files"] = merged_files
        report["skipped_duplicates"] = skipped_duplicates
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "import_id": import_id,
            "applied_count": applied,
            "applied_files": merged_files,
            "skipped_duplicates": skipped_duplicates,
            "report": report,
        }

    @staticmethod
    def preview_apply_import(project: Dict[str, Any], import_id: str) -> Dict[str, Any]:
        layout = ProjectLayout.from_project(project)
        root = AnnotationImporter.draft_root(layout, import_id)
        report_path = root / "import_report.json"
        draft_labelme = root / "labelme"
        if not report_path.exists() or not draft_labelme.exists():
            raise ValueError(f"Import draft not found: {import_id}")

        current_labelme = layout.resolve_current_labelme_dir().path
        files: List[Dict[str, Any]] = []
        total_add = 0
        total_duplicates = 0
        for json_file in draft_labelme.glob("*.json"):
            result = AnnotationImporter._merge_labelme_json(json_file, current_labelme / json_file.name, dry_run=True)
            file_summary = {
                "file": json_file.name,
                "will_add": result["added"],
                "duplicates": result["duplicates"],
            }
            files.append(file_summary)
            total_add += result["added"]
            total_duplicates += result["duplicates"]

        return {
            "import_id": import_id,
            "will_add": total_add,
            "duplicates": total_duplicates,
            "files": files,
        }

    @staticmethod
    def _merge_labelme_json(source_path: Path, target_path: Path, dry_run: bool = False) -> Dict[str, int]:
        source = json.loads(source_path.read_text(encoding="utf-8"))
        source_shapes = source.get("shapes", [])
        if not isinstance(source_shapes, list):
            source_shapes = []

        if target_path.exists():
            target = json.loads(target_path.read_text(encoding="utf-8"))
            target_shapes = target.get("shapes", [])
            if not isinstance(target_shapes, list):
                target_shapes = []
        else:
            target = dict(source)
            target_shapes = []

        existing_keys = {AnnotationImporter._shape_key(shape) for shape in target_shapes}
        added = 0
        duplicates = 0
        for shape in source_shapes:
            key = AnnotationImporter._shape_key(shape)
            if key in existing_keys or any(AnnotationImporter._is_duplicate_shape(shape, existing) for existing in target_shapes):
                duplicates += 1
                continue
            target_shapes.append(shape)
            existing_keys.add(key)
            added += 1

        if dry_run:
            return {"added": added, "duplicates": duplicates}

        target["version"] = target.get("version") or source.get("version") or "5.0.1"
        target["flags"] = target.get("flags") if isinstance(target.get("flags"), dict) else {}
        target["imagePath"] = target.get("imagePath") or source.get("imagePath") or source_path.with_suffix("").name
        target["imageHeight"] = target.get("imageHeight") or source.get("imageHeight")
        target["imageWidth"] = target.get("imageWidth") or source.get("imageWidth")
        target["imageData"] = None
        target["shapes"] = target_shapes
        target_path.write_text(json.dumps(target, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"added": added, "duplicates": duplicates}

    @staticmethod
    def _shape_key(shape: Dict[str, Any]) -> Tuple[Any, ...]:
        points = shape.get("points", [])
        normalized_points = []
        if isinstance(points, list):
            for point in points:
                if isinstance(point, list) and len(point) >= 2:
                    normalized_points.append((round(float(point[0]), 3), round(float(point[1]), 3)))
        return (
            str(shape.get("label", "")),
            str(shape.get("shape_type", "")),
            tuple(normalized_points),
        )

    @staticmethod
    def _is_duplicate_shape(candidate: Dict[str, Any], existing: Dict[str, Any]) -> bool:
        if str(candidate.get("label", "")) != str(existing.get("label", "")):
            return False

        candidate_type = str(candidate.get("shape_type", ""))
        existing_type = str(existing.get("shape_type", ""))
        candidate_bbox = AnnotationImporter._shape_bbox(candidate)
        existing_bbox = AnnotationImporter._shape_bbox(existing)
        bbox_iou = AnnotationImporter._bbox_iou(candidate_bbox, existing_bbox)

        if candidate_type == "rectangle" or existing_type == "rectangle":
            return bbox_iou >= 0.95

        candidate_area = AnnotationImporter._polygon_area(candidate)
        existing_area = AnnotationImporter._polygon_area(existing)
        area_similarity = AnnotationImporter._area_similarity(candidate_area, existing_area)
        return bbox_iou >= 0.95 and area_similarity >= 0.97

    @staticmethod
    def _shape_bbox(shape: Dict[str, Any]) -> Tuple[float, float, float, float]:
        points = shape.get("points", [])
        coords = []
        if isinstance(points, list):
            for point in points:
                if isinstance(point, list) and len(point) >= 2:
                    coords.append((float(point[0]), float(point[1])))
        if not coords:
            return (0.0, 0.0, 0.0, 0.0)
        xs = [point[0] for point in coords]
        ys = [point[1] for point in coords]
        return (min(xs), min(ys), max(xs), max(ys))

    @staticmethod
    def _bbox_iou(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
        inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
        inter = inter_w * inter_h
        area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
        area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    @staticmethod
    def _polygon_area(shape: Dict[str, Any]) -> float:
        points = shape.get("points", [])
        coords: List[Tuple[float, float]] = []
        if isinstance(points, list):
            for point in points:
                if isinstance(point, list) and len(point) >= 2:
                    coords.append((float(point[0]), float(point[1])))
        if len(coords) < 3:
            x1, y1, x2, y2 = AnnotationImporter._shape_bbox(shape)
            return max(0.0, x2 - x1) * max(0.0, y2 - y1)
        area = 0.0
        for idx, (x1, y1) in enumerate(coords):
            x2, y2 = coords[(idx + 1) % len(coords)]
            area += x1 * y2 - x2 * y1
        return abs(area) / 2.0

    @staticmethod
    def _area_similarity(area_a: float, area_b: float) -> float:
        larger = max(area_a, area_b)
        smaller = min(area_a, area_b)
        return smaller / larger if larger > 0 else 0.0

    @staticmethod
    def _record_converted(report: Dict[str, Any], converted: Union[Dict[str, Any], List[Dict[str, Any]]]) -> None:
        converted_items = converted if isinstance(converted, list) else [converted]
        for item in converted_items:
            report["converted"] += 1
            report["converted_files"].append(item)
            report["warnings"].extend(item.get("warnings", []))

    @staticmethod
    def _image_path(layout: ProjectLayout, filename: str) -> Path:
        image_dir = layout.resolve_raw_images_dir().path
        direct = image_dir / filename
        if direct.exists():
            return direct
        stem = Path(filename).stem
        for ext in IMAGE_EXTENSIONS:
            candidate = image_dir / f"{stem}{ext}"
            if candidate.exists():
                return candidate
        raise ValueError(f"Image file not found for {filename}.")

    @staticmethod
    def _image_size(layout: ProjectLayout, filename: str) -> Tuple[str, int, int]:
        path = AnnotationImporter._image_path(layout, filename)
        with Image.open(path) as img:
            width, height = img.size
        return path.name, int(width), int(height)

    @staticmethod
    def _label_from_class_id(project: Dict[str, Any], class_id: int, file_name: str) -> Tuple[str, List[Dict[str, str]]]:
        class_names = project.get("class_names", [])
        warnings: List[Dict[str, str]] = []
        if 0 <= class_id < len(class_names):
            return str(class_names[class_id]), warnings
        label = f"class_{class_id}"
        warnings.append({"file": file_name, "message": f"Class id {class_id} is outside project class list; using {label}."})
        return label, warnings

    @staticmethod
    def _convert_yolo_txt(project: Dict[str, Any], layout: ProjectLayout, txt_path: Path, out_dir: Path) -> Dict[str, Any]:
        image_name, width, height = AnnotationImporter._image_size(layout, txt_path.stem)
        shapes: List[Dict[str, Any]] = []
        warnings: List[Dict[str, str]] = []

        for line_number, line in enumerate(txt_path.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 5:
                warnings.append({"file": txt_path.name, "message": f"Line {line_number} has too few values."})
                continue
            class_id = int(float(parts[0]))
            coords = [float(value) for value in parts[1:]]
            label, label_warnings = AnnotationImporter._label_from_class_id(project, class_id, txt_path.name)
            warnings.extend(label_warnings)

            if len(coords) == 4:
                xc, yc, box_w, box_h = coords
                x1 = (xc - box_w / 2) * width
                y1 = (yc - box_h / 2) * height
                x2 = (xc + box_w / 2) * width
                y2 = (yc + box_h / 2) * height
                shape_type = "rectangle"
                points = [[x1, y1], [x2, y2]]
            elif len(coords) >= 6 and len(coords) % 2 == 0:
                shape_type = "polygon"
                points = [[coords[idx] * width, coords[idx + 1] * height] for idx in range(0, len(coords), 2)]
            else:
                warnings.append({"file": txt_path.name, "message": f"Line {line_number} coordinate count is not valid for bbox or polygon."})
                continue

            shapes.append(AnnotationImporter._shape(label, points, shape_type))

        if not shapes:
            raise ValueError("No valid YOLO annotations found.")
        return AnnotationImporter._write_labelme(out_dir, image_name, width, height, shapes, "yolo_txt", txt_path.name, warnings)

    @staticmethod
    def _read_csv_rows(csv_path: Path) -> List[Dict[str, str]]:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            return list(csv.DictReader(csv_file))

    @staticmethod
    def _convert_csv_rows(project: Dict[str, Any], layout: ProjectLayout, filename: str, rows: List[Dict[str, str]], out_dir: Path, sources: List[str], csv_mapping: Dict[str, str]) -> Dict[str, Any]:
        image_name, width, height = AnnotationImporter._image_size(layout, filename)
        shapes = []
        warnings: List[Dict[str, str]] = []
        class_names = set(project.get("class_names", []))

        for idx, row in enumerate(rows, start=1):
            mapped = AnnotationImporter._apply_csv_mapping(row, csv_mapping)
            label = (mapped.get("label") or row.get("label") or row.get("class") or row.get("category") or "").strip()
            if not label:
                warnings.append({"file": filename, "message": f"CSV row {idx} has no label."})
                continue
            if class_names and label not in class_names:
                warnings.append({"file": filename, "message": f"CSV row {idx} label '{label}' is not in project classes."})

            if all(key in mapped and mapped[key] not in (None, "") for key in ("xmin", "ymin", "xmax", "ymax")):
                points = [[float(mapped["xmin"]), float(mapped["ymin"])], [float(mapped["xmax"]), float(mapped["ymax"])]]
                shapes.append(AnnotationImporter._shape(label, points, "rectangle"))
                continue

            points_value = (mapped.get("points") or row.get("points") or "").strip()
            if points_value:
                points = []
                for pair in points_value.split(";"):
                    x_str, y_str = [item.strip() for item in pair.split(",", 1)]
                    points.append([float(x_str), float(y_str)])
                if len(points) >= 3:
                    shapes.append(AnnotationImporter._shape(label, points, "polygon"))
                else:
                    warnings.append({"file": filename, "message": f"CSV row {idx} polygon has fewer than 3 points."})
                continue

            xy_keys = [key for key in row.keys() if key and (key.startswith("x") or key.startswith("y"))]
            numbered = []
            point_idx = 1
            while f"x{point_idx}" in mapped and f"y{point_idx}" in mapped:
                numbered.append([float(mapped[f"x{point_idx}"]), float(mapped[f"y{point_idx}"])])
                point_idx += 1
            if len(numbered) >= 3:
                shapes.append(AnnotationImporter._shape(label, numbered, "polygon"))
            else:
                warnings.append({"file": filename, "message": f"CSV row {idx} has no supported bbox or polygon columns ({', '.join(xy_keys)})."})

        if not shapes:
            raise ValueError("No valid CSV annotations found.")
        return AnnotationImporter._write_labelme(out_dir, image_name, width, height, shapes, "csv", ", ".join(sources), warnings)

    @staticmethod
    def _apply_csv_mapping(row: Dict[str, str], csv_mapping: Dict[str, str]) -> Dict[str, str]:
        if not csv_mapping:
            return dict(row)
        mapped = dict(row)
        for canonical, source_column in csv_mapping.items():
            if source_column and source_column in row:
                mapped[canonical] = row[source_column]
        return mapped

    @staticmethod
    def _csv_mapping_for_file(csv_mapping: Dict[str, Any], file_name: str) -> Dict[str, str]:
        if not csv_mapping:
            return {}
        file_mappings = csv_mapping.get("files")
        if isinstance(file_mappings, dict):
            file_mapping = file_mappings.get(file_name)
            if isinstance(file_mapping, dict):
                return {str(key): str(value) for key, value in file_mapping.items() if value}
        return {str(key): str(value) for key, value in csv_mapping.items() if isinstance(value, str) and value}

    @staticmethod
    def _accept_json(project: Dict[str, Any], layout: ProjectLayout, json_path: Path, out_dir: Path) -> Tuple[Union[Dict[str, Any], List[Dict[str, Any]]], str]:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON root must be an object.")
        if "shapes" in data:
            return AnnotationImporter._accept_labelme_json(project, layout, json_path, out_dir, data), "labelme_json"
        if all(key in data for key in ("images", "annotations", "categories")):
            return AnnotationImporter._convert_coco_json(project, layout, json_path, out_dir, data), "coco_json"
        raise ValueError("JSON is not LabelMe or COCO format.")

    @staticmethod
    def _accept_labelme_json(project: Dict[str, Any], layout: ProjectLayout, json_path: Path, out_dir: Path, data: Dict[str, Any]) -> Dict[str, Any]:
        image_path = data.get("imagePath") or json_path.with_suffix(".jpg").name
        image_name, width, height = AnnotationImporter._image_size(layout, str(image_path))
        data["imagePath"] = image_name
        data["imageHeight"] = data.get("imageHeight") or height
        data["imageWidth"] = data.get("imageWidth") or width
        if not isinstance(data.get("shapes"), list):
            raise ValueError("LabelMe JSON shapes must be a list.")

        return AnnotationImporter._write_labelme(
            out_dir,
            image_name,
            int(data["imageWidth"]),
            int(data["imageHeight"]),
            data.get("shapes", []),
            "labelme_json",
            json_path.name,
            [],
        )

    @staticmethod
    def _convert_coco_json(project: Dict[str, Any], layout: ProjectLayout, json_path: Path, out_dir: Path, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        images = {item.get("id"): item for item in data.get("images", []) if isinstance(item, dict)}
        categories = {item.get("id"): item.get("name", f"class_{item.get('id')}") for item in data.get("categories", []) if isinstance(item, dict)}
        grouped: Dict[Any, List[Dict[str, Any]]] = {}
        for annotation in data.get("annotations", []):
            if isinstance(annotation, dict):
                grouped.setdefault(annotation.get("image_id"), []).append(annotation)

        converted: List[Dict[str, Any]] = []
        class_names = set(project.get("class_names", []))
        for image_id, image in images.items():
            file_name = image.get("file_name") or image.get("filename")
            if not file_name:
                continue
            image_name, width, height = AnnotationImporter._image_size(layout, str(file_name))
            shapes: List[Dict[str, Any]] = []
            warnings: List[Dict[str, str]] = []
            for annotation in grouped.get(image_id, []):
                label = str(categories.get(annotation.get("category_id"), f"class_{annotation.get('category_id')}"))
                if class_names and label not in class_names:
                    warnings.append({"file": json_path.name, "message": f"COCO label '{label}' is not in project classes."})

                segmentation = annotation.get("segmentation")
                if isinstance(segmentation, list) and segmentation:
                    polygon = segmentation[0] if isinstance(segmentation[0], list) else segmentation
                    if len(polygon) >= 6 and len(polygon) % 2 == 0:
                        points = [[polygon[idx], polygon[idx + 1]] for idx in range(0, len(polygon), 2)]
                        shapes.append(AnnotationImporter._shape(label, points, "polygon"))
                        continue
                elif isinstance(segmentation, dict):
                    mask_shapes = AnnotationImporter._coco_rle_to_shapes(segmentation, label, json_path.name)
                    if mask_shapes:
                        shapes.extend(mask_shapes)
                        continue

                bbox = annotation.get("bbox")
                if isinstance(bbox, list) and len(bbox) >= 4:
                    x, y, box_w, box_h = [float(value) for value in bbox[:4]]
                    shapes.append(AnnotationImporter._shape(label, [[x, y], [x + box_w, y + box_h]], "rectangle"))

            if shapes:
                converted.append(AnnotationImporter._write_labelme(out_dir, image_name, width, height, shapes, "coco_json", json_path.name, warnings))

        if not converted:
            raise ValueError("No supported COCO bbox or polygon annotations found.")
        return converted

    @staticmethod
    def _coco_rle_to_shapes(segmentation: Dict[str, Any], label: str, source_file: str) -> List[Dict[str, Any]]:
        mask = AnnotationImporter._decode_coco_rle(segmentation, source_file)
        return AnnotationImporter._mask_to_shapes(mask, {1: label})

    @staticmethod
    def _decode_coco_rle(segmentation: Dict[str, Any], source_file: str) -> List[List[int]]:
        size = segmentation.get("size")
        counts = segmentation.get("counts")
        if not isinstance(size, list) or len(size) != 2:
            raise ValueError(f"COCO RLE in {source_file} is missing size.")
        height, width = int(size[0]), int(size[1])

        if isinstance(counts, list):
            flat = []
            value = 0
            for run_length in counts:
                flat.extend([value] * int(run_length))
                value = 1 - value
            expected = height * width
            if len(flat) < expected:
                flat.extend([0] * (expected - len(flat)))
            flat = flat[:expected]
            return [[flat[x * height + y] for x in range(width)] for y in range(height)]

        if isinstance(counts, str):
            try:
                from pycocotools import mask as mask_utils  # type: ignore
            except Exception as exc:
                raise ValueError(f"Compressed COCO RLE in {source_file} requires pycocotools or polygon export.") from exc
            decoded = mask_utils.decode({"size": [height, width], "counts": counts.encode("utf-8")})
            return [[int(decoded[y][x]) for x in range(width)] for y in range(height)]

        raise ValueError(f"COCO RLE in {source_file} has unsupported counts.")

    @staticmethod
    def _convert_mask_image(project: Dict[str, Any], layout: ProjectLayout, mask_path: Path, out_dir: Path) -> Dict[str, Any]:
        image_name, width, height = AnnotationImporter._image_size(layout, mask_path.stem)
        class_names = project.get("class_names", [])
        with Image.open(mask_path) as mask_img:
            mask = mask_img.convert("L").resize((width, height))
            pixels = [[int(mask.getpixel((x, y))) for x in range(width)] for y in range(height)]

        label_map = {}
        for value in sorted({pixel for row in pixels for pixel in row if pixel != 0}):
            idx = int(value)
            label_map[idx] = str(class_names[idx]) if 0 <= idx < len(class_names) else f"class_{idx}"
        shapes = AnnotationImporter._mask_to_shapes(pixels, label_map)
        if not shapes:
            raise ValueError("Mask image has no non-background pixels.")
        return AnnotationImporter._write_labelme(out_dir, image_name, width, height, shapes, "mask_png", mask_path.name, [])

    @staticmethod
    def _mask_to_shapes(mask: List[List[int]], label_map: Dict[int, str]) -> List[Dict[str, Any]]:
        try:
            import cv2  # type: ignore
            import numpy as np
        except Exception:
            return AnnotationImporter._mask_to_bbox_shapes(mask, label_map)

        arr = np.array(mask, dtype=np.uint8)
        shapes: List[Dict[str, Any]] = []
        for value, label in label_map.items():
            binary = (arr == int(value)).astype(np.uint8) * 255
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                epsilon = max(1.0, 0.002 * cv2.arcLength(contour, True))
                approx = cv2.approxPolyDP(contour, epsilon, True)
                points = [[float(point[0][0]), float(point[0][1])] for point in approx]
                if len(points) >= 3:
                    shapes.append(AnnotationImporter._shape(label, points, "polygon"))
        return shapes or AnnotationImporter._mask_to_bbox_shapes(mask, label_map)

    @staticmethod
    def _mask_to_bbox_shapes(mask: List[List[int]], label_map: Dict[int, str]) -> List[Dict[str, Any]]:
        shapes: List[Dict[str, Any]] = []
        for value, label in label_map.items():
            coords = [(x, y) for y, row in enumerate(mask) for x, pixel in enumerate(row) if int(pixel) == int(value)]
            if not coords:
                continue
            xs = [coord[0] for coord in coords]
            ys = [coord[1] for coord in coords]
            shapes.append(AnnotationImporter._shape(label, [[min(xs), min(ys)], [max(xs), max(ys)]], "rectangle"))
        return shapes

    @staticmethod
    def _convert_voc_xml(project: Dict[str, Any], layout: ProjectLayout, xml_path: Path, out_dir: Path) -> Dict[str, Any]:
        root = ET.parse(xml_path).getroot()
        filename = root.findtext("filename") or xml_path.with_suffix(".jpg").name
        image_name, width, height = AnnotationImporter._image_size(layout, filename)
        class_names = set(project.get("class_names", []))
        shapes: List[Dict[str, Any]] = []
        warnings: List[Dict[str, str]] = []

        for obj in root.findall("object"):
            label = (obj.findtext("name") or "").strip()
            if not label:
                warnings.append({"file": xml_path.name, "message": "VOC object has no class name."})
                continue
            if class_names and label not in class_names:
                warnings.append({"file": xml_path.name, "message": f"VOC label '{label}' is not in project classes."})
            box = obj.find("bndbox")
            if box is None:
                warnings.append({"file": xml_path.name, "message": f"VOC object '{label}' has no bndbox."})
                continue
            xmin = float(box.findtext("xmin", "0"))
            ymin = float(box.findtext("ymin", "0"))
            xmax = float(box.findtext("xmax", "0"))
            ymax = float(box.findtext("ymax", "0"))
            shapes.append(AnnotationImporter._shape(label, [[xmin, ymin], [xmax, ymax]], "rectangle"))

        if not shapes:
            raise ValueError("No valid VOC objects found.")
        return AnnotationImporter._write_labelme(out_dir, image_name, width, height, shapes, "voc_xml", xml_path.name, warnings)

    @staticmethod
    def _shape(label: str, points: List[List[float]], shape_type: str) -> Dict[str, Any]:
        return {
            "label": label,
            "points": [[round(float(x), 3), round(float(y), 3)] for x, y in points],
            "group_id": None,
            "description": "",
            "shape_type": shape_type,
            "flags": {},
        }

    @staticmethod
    def _write_labelme(out_dir: Path, image_name: str, width: int, height: int, shapes: List[Dict[str, Any]], source_format: str, source_file: str, warnings: List[Dict[str, str]]) -> Dict[str, Any]:
        data = {
            "version": "5.0.1",
            "flags": {},
            "shapes": shapes,
            "imagePath": image_name,
            "imageData": None,
            "imageHeight": height,
            "imageWidth": width,
        }
        out_path = out_dir / Path(image_name).with_suffix(".json").name
        if out_path.exists():
            temp_path = out_path.with_suffix(".incoming.json")
            temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            merge_result = AnnotationImporter._merge_labelme_json(temp_path, out_path)
            temp_path.unlink(missing_ok=True)
            shape_count = len(json.loads(out_path.read_text(encoding="utf-8")).get("shapes", []))
            added_count = merge_result["added"]
            duplicate_count = merge_result["duplicates"]
        else:
            out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            shape_count = len(shapes)
            added_count = len(shapes)
            duplicate_count = 0
        return {
            "file": out_path.name,
            "source_file": source_file,
            "source_format": source_format,
            "shape_count": shape_count,
            "added_shapes": added_count,
            "duplicate_shapes": duplicate_count,
            "warnings": warnings,
        }
