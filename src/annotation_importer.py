from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    def import_files(project: Dict[str, Any], source_files: List[Path], import_id: Optional[str] = None) -> Dict[str, Any]:
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
            "yolo_txt": 0,
            "csv": 0,
            "converted": 0,
            "failed": 0,
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
                    report["labelme_json"] += 1
                    converted = AnnotationImporter._accept_labelme_json(project, layout, staged_path, labelme_dir)
                    AnnotationImporter._record_converted(report, converted)
                elif suffix == ".csv":
                    report["csv"] += 1
                    rows = AnnotationImporter._read_csv_rows(staged_path)
                    for row in rows:
                        filename = (row.get("filename") or row.get("image") or row.get("imagePath") or "").strip()
                        if filename:
                            grouped_csv_rows.setdefault(filename, []).append(row)
                    csv_sources.append(staged_path.name)
                else:
                    report["failed"] += 1
                    report["errors"].append({"file": staged_path.name, "message": "Unsupported annotation file extension."})
            except Exception as exc:
                report["failed"] += 1
                report["errors"].append({"file": staged_path.name, "message": str(exc)})

        if grouped_csv_rows:
            for filename, rows in grouped_csv_rows.items():
                try:
                    converted = AnnotationImporter._convert_csv_rows(project, layout, filename, rows, labelme_dir, csv_sources)
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
    def _record_converted(report: Dict[str, Any], converted: Dict[str, Any]) -> None:
        report["converted"] += 1
        report["converted_files"].append(converted)
        report["warnings"].extend(converted.get("warnings", []))

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
    def _convert_csv_rows(project: Dict[str, Any], layout: ProjectLayout, filename: str, rows: List[Dict[str, str]], out_dir: Path, sources: List[str]) -> Dict[str, Any]:
        image_name, width, height = AnnotationImporter._image_size(layout, filename)
        shapes = []
        warnings: List[Dict[str, str]] = []
        class_names = set(project.get("class_names", []))

        for idx, row in enumerate(rows, start=1):
            label = (row.get("label") or row.get("class") or row.get("category") or "").strip()
            if not label:
                warnings.append({"file": filename, "message": f"CSV row {idx} has no label."})
                continue
            if class_names and label not in class_names:
                warnings.append({"file": filename, "message": f"CSV row {idx} label '{label}' is not in project classes."})

            if all(key in row and row[key] not in (None, "") for key in ("xmin", "ymin", "xmax", "ymax")):
                points = [[float(row["xmin"]), float(row["ymin"])], [float(row["xmax"]), float(row["ymax"])]]
                shapes.append(AnnotationImporter._shape(label, points, "rectangle"))
                continue

            points_value = (row.get("points") or "").strip()
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
            while f"x{point_idx}" in row and f"y{point_idx}" in row:
                numbered.append([float(row[f"x{point_idx}"]), float(row[f"y{point_idx}"])])
                point_idx += 1
            if len(numbered) >= 3:
                shapes.append(AnnotationImporter._shape(label, numbered, "polygon"))
            else:
                warnings.append({"file": filename, "message": f"CSV row {idx} has no supported bbox or polygon columns ({', '.join(xy_keys)})."})

        if not shapes:
            raise ValueError("No valid CSV annotations found.")
        return AnnotationImporter._write_labelme(out_dir, image_name, width, height, shapes, "csv", ", ".join(sources), warnings)

    @staticmethod
    def _accept_labelme_json(project: Dict[str, Any], layout: ProjectLayout, json_path: Path, out_dir: Path) -> Dict[str, Any]:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "shapes" not in data:
            raise ValueError("JSON is not LabelMe format. COCO/custom JSON import is planned for P1.")

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
