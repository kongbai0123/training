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
                    rows = AnnotationImporter._read_csv_rows(staged_path)
                    for row in rows:
                        mapped = AnnotationImporter._apply_csv_mapping(row, csv_mapping or {})
                        filename = (mapped.get("filename") or row.get("filename") or row.get("image") or row.get("imagePath") or "").strip()
                        if filename:
                            grouped_csv_rows.setdefault(filename, []).append(row)
                    csv_sources.append(staged_path.name)
                elif suffix == ".xml":
                    report["voc_xml"] += 1
                    converted = AnnotationImporter._convert_voc_xml(project, layout, staged_path, labelme_dir)
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
                    converted = AnnotationImporter._convert_csv_rows(project, layout, filename, rows, labelme_dir, csv_sources, csv_mapping or {})
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

        copied = 0
        for json_file in draft_labelme.glob("*.json"):
            shutil.copy2(json_file, current_labelme / json_file.name)
            copied += 1

        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["applied_at"] = datetime.now().isoformat()
        report["applied_count"] = copied
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"import_id": import_id, "applied_count": copied, "report": report}

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

        out_path = out_dir / Path(image_name).with_suffix(".json").name
        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"file": out_path.name, "source_file": json_path.name, "source_format": "labelme_json", "warnings": []}

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
        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"file": out_path.name, "source_file": source_file, "source_format": source_format, "shape_count": len(shapes), "warnings": warnings}
