from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import platform
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import UploadFile

from src.model_lifecycle_registry import ModelLifecycleRegistry
from src.model_registry import ModelRegistry
from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.tabular_config import import_tabular_csv, resolve_tabular_source, update_project_tabular_config
from src.tabular_xgboost_inference import TabularXGBoostInferenceService
from src.training.compare_service import CompareService
from src.training.dispatcher import TrainerDispatcher
from src.training.export_service import ExportService
from src.training.start_service import TrainingStartService
from src.training.tabular.dataset import load_csv_tabular_dataset


REPORT_SCHEMA_VERSION = "1.0"
TERMINAL_TRAINING_STATUSES = {"completed", "failed", "stopped"}


@dataclass(frozen=True)
class UciSource:
    key: str
    name: str
    dataset_id: int
    task_head: str
    landing_url: str
    download_url: str
    archive_sha256: str
    archive_member: str
    doi: str
    citation: str
    license_name: str = "CC BY 4.0"
    license_url: str = "https://creativecommons.org/licenses/by/4.0/"


@dataclass(frozen=True)
class ProjectionSpec:
    source: UciSource
    output_name: str
    feature_columns: tuple[str, ...]
    target_column: str
    excluded_columns: tuple[str, ...]
    projector: Callable[[bytes, Path], Dict[str, Any]]


ONLINE_SHOPPERS = UciSource(
    key="online_shoppers",
    name="Online Shoppers Purchasing Intention",
    dataset_id=468,
    task_head="classification",
    landing_url="https://archive.ics.uci.edu/dataset/468/online+shoppers+purchasing+intention+dataset",
    download_url="https://archive.ics.uci.edu/static/public/468/online+shoppers+purchasing+intention+dataset.zip",
    archive_sha256="2972e6184d3ad7beaaa831d9fc2b059dc3ee29df69d1ec593c466a5cd8485d14",
    archive_member="online_shoppers_intention.csv",
    doi="10.24432/C5F88Q",
    citation=(
        "Sakar, C. & Kastro, Y. (2018). Online Shoppers Purchasing Intention "
        "Dataset. UCI Machine Learning Repository."
    ),
)


SEOUL_BIKE = UciSource(
    key="seoul_bike",
    name="Seoul Bike Sharing Demand",
    dataset_id=560,
    task_head="regression",
    landing_url="https://archive.ics.uci.edu/dataset/560/seoul+bike+sharing+demand",
    download_url="https://archive.ics.uci.edu/static/public/560/seoul+bike+sharing+demand.zip",
    archive_sha256="139e9908f0a3544bb222386855c9ce107e96467306bb8e4ce936aab59e7baac4",
    archive_member="SeoulBikeData.csv",
    doi="10.24432/C5F62R",
    citation="Seoul Bike Sharing Demand (2020). UCI Machine Learning Repository.",
)


ONLINE_SHOPPERS_FEATURES = (
    "administrative",
    "administrative_duration",
    "informational",
    "informational_duration",
    "product_related",
    "product_related_duration",
    "bounce_rates",
    "exit_rates",
    "page_values",
    "special_day",
)


SEOUL_BIKE_FEATURES = (
    "hour",
    "temperature_c",
    "humidity_pct",
    "wind_speed_m_s",
    "visibility_10m",
    "dew_point_c",
    "solar_radiation_mj_m2",
    "rainfall_mm",
    "snowfall_cm",
)


PROJECTIONS: Dict[str, ProjectionSpec] = {
    "classification": ProjectionSpec(
        source=ONLINE_SHOPPERS,
        output_name="online_shoppers_numeric_acceptance.csv",
        feature_columns=ONLINE_SHOPPERS_FEATURES,
        target_column="purchase_completed",
        excluded_columns=(
            "Month",
            "OperatingSystems",
            "Browser",
            "Region",
            "TrafficType",
            "VisitorType",
            "Weekend",
        ),
        projector=lambda payload, path: project_online_shoppers(payload, path),
    ),
    "regression": ProjectionSpec(
        source=SEOUL_BIKE,
        output_name="seoul_bike_numeric_acceptance.csv",
        feature_columns=SEOUL_BIKE_FEATURES,
        target_column="rented_bike_count",
        excluded_columns=("Date", "Seasons", "Holiday", "Functioning Day"),
        projector=lambda payload, path: project_seoul_bike(payload, path),
    ),
}


class AcceptanceFailure(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_uci_source(source: UciSource, cache_dir: Path, *, offline: bool = False) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive_path = cache_dir / f"uci_{source.dataset_id}_{source.key}.zip"
    if archive_path.is_file():
        actual = sha256_file(archive_path)
        if actual != source.archive_sha256:
            raise AcceptanceFailure(
                f"Cached UCI archive checksum mismatch for {source.name}: "
                f"expected {source.archive_sha256}, got {actual}. Remove the cache file and retry."
            )
        return archive_path
    if offline:
        raise AcceptanceFailure(
            f"Offline acceptance requires cached source archive: {archive_path}"
        )

    temporary = archive_path.with_suffix(".zip.part")
    request = urllib.request.Request(
        source.download_url,
        headers={"User-Agent": "VisionTrainingStudio-TabularAcceptance/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        actual = sha256_file(temporary)
        if actual != source.archive_sha256:
            raise AcceptanceFailure(
                f"Downloaded UCI archive checksum mismatch for {source.name}: "
                f"expected {source.archive_sha256}, got {actual}."
            )
        os.replace(temporary, archive_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return archive_path


def read_archive_member(archive_path: Path, source: UciSource) -> bytes:
    with zipfile.ZipFile(archive_path) as archive:
        corrupt = archive.testzip()
        if corrupt:
            raise AcceptanceFailure(f"UCI archive CRC validation failed: {corrupt}")
        names = {name.replace("\\", "/"): name for name in archive.namelist()}
        requested = source.archive_member.replace("\\", "/")
        member = names.get(requested)
        if not member:
            matches = [original for normalized, original in names.items() if normalized.endswith(f"/{requested}")]
            member = matches[0] if len(matches) == 1 else None
        if not member:
            raise AcceptanceFailure(
                f"UCI archive does not contain expected member {source.archive_member}."
            )
        return archive.read(member)


def decode_csv(payload: bytes, encodings: Sequence[str]) -> str:
    for encoding in encodings:
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise AcceptanceFailure(f"CSV could not be decoded with: {', '.join(encodings)}")


def project_online_shoppers(payload: bytes, output_path: Path) -> Dict[str, Any]:
    text = decode_csv(payload, ("utf-8-sig", "cp1252"))
    reader = csv.DictReader(io.StringIO(text))
    required = (
        "Administrative",
        "Administrative_Duration",
        "Informational",
        "Informational_Duration",
        "ProductRelated",
        "ProductRelated_Duration",
        "BounceRates",
        "ExitRates",
        "PageValues",
        "SpecialDay",
        "Revenue",
    )
    _require_headers(reader.fieldnames or [], required, ONLINE_SHOPPERS.name)
    mappings = {
        "administrative": "Administrative",
        "administrative_duration": "Administrative_Duration",
        "informational": "Informational",
        "informational_duration": "Informational_Duration",
        "product_related": "ProductRelated",
        "product_related_duration": "ProductRelated_Duration",
        "bounce_rates": "BounceRates",
        "exit_rates": "ExitRates",
        "page_values": "PageValues",
        "special_day": "SpecialDay",
    }
    rows: List[Dict[str, str]] = []
    injected = {"administrative_duration": 0, "bounce_rates": 0}
    for index, raw in enumerate(reader, start=1):
        row = {output: str(raw[source]).strip() for output, source in mappings.items()}
        if index % 211 == 0:
            row["administrative_duration"] = ""
            injected["administrative_duration"] += 1
        if index % 307 == 0:
            row["bounce_rates"] = ""
            injected["bounce_rates"] += 1
        revenue = str(raw["Revenue"]).strip().lower()
        if revenue not in {"true", "false"}:
            raise AcceptanceFailure(f"Unexpected Online Shoppers Revenue value: {raw['Revenue']}")
        row["purchase_completed"] = "purchase" if revenue == "true" else "no_purchase"
        rows.append(row)
    fieldnames = [*ONLINE_SHOPPERS_FEATURES, "purchase_completed"]
    _write_projection(output_path, fieldnames, rows)
    return _projection_summary(output_path, rows, fieldnames, injected)


def project_seoul_bike(payload: bytes, output_path: Path) -> Dict[str, Any]:
    text = decode_csv(payload, ("utf-8-sig", "cp1252", "latin-1"))
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    by_prefix = {
        "rented_bike_count": _header_starting(headers, "Rented Bike Count"),
        "hour": _header_starting(headers, "Hour"),
        "temperature_c": _header_starting(headers, "Temperature("),
        "humidity_pct": _header_starting(headers, "Humidity("),
        "wind_speed_m_s": _header_starting(headers, "Wind speed"),
        "visibility_10m": _header_starting(headers, "Visibility"),
        "dew_point_c": _header_starting(headers, "Dew point temperature"),
        "solar_radiation_mj_m2": _header_starting(headers, "Solar Radiation"),
        "rainfall_mm": _header_starting(headers, "Rainfall"),
        "snowfall_cm": _header_starting(headers, "Snowfall"),
    }
    rows: List[Dict[str, str]] = []
    injected = {"temperature_c": 0, "solar_radiation_mj_m2": 0}
    for index, raw in enumerate(reader, start=1):
        row = {
            output: str(raw[source]).strip()
            for output, source in by_prefix.items()
            if output != "rented_bike_count"
        }
        if index % 173 == 0:
            row["temperature_c"] = ""
            injected["temperature_c"] += 1
        if index % 257 == 0:
            row["solar_radiation_mj_m2"] = ""
            injected["solar_radiation_mj_m2"] += 1
        row["rented_bike_count"] = str(raw[by_prefix["rented_bike_count"]]).strip()
        rows.append(row)
    fieldnames = [*SEOUL_BIKE_FEATURES, "rented_bike_count"]
    _write_projection(output_path, fieldnames, rows)
    return _projection_summary(output_path, rows, fieldnames, injected)


def _require_headers(actual: Sequence[str], required: Sequence[str], name: str) -> None:
    missing = [header for header in required if header not in actual]
    if missing:
        raise AcceptanceFailure(f"{name} source schema changed; missing: {', '.join(missing)}")


def _header_starting(headers: Sequence[str], prefix: str) -> str:
    matches = [header for header in headers if str(header).strip().lower().startswith(prefix.lower())]
    if len(matches) != 1:
        raise AcceptanceFailure(
            f"Seoul Bike source schema changed; expected one header starting with {prefix!r}, got {matches}."
        )
    return matches[0]


def _write_projection(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _projection_summary(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fieldnames: Sequence[str],
    injected: Mapping[str, int],
) -> Dict[str, Any]:
    return {
        "path": path,
        "row_count": len(rows),
        "column_count": len(fieldnames),
        "columns": list(fieldnames),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "controlled_missing_values": dict(injected),
        "controlled_missing_value_count": sum(injected.values()),
    }


def prepare_projection(
    spec: ProjectionSpec,
    cache_dir: Path,
    projection_dir: Path,
    *,
    offline: bool,
) -> Dict[str, Any]:
    archive_path = download_uci_source(spec.source, cache_dir, offline=offline)
    member = read_archive_member(archive_path, spec.source)
    output_path = projection_dir / spec.output_name
    first = spec.projector(member, output_path)
    repeat_path = projection_dir / f"repeat_{spec.output_name}"
    repeated = spec.projector(member, repeat_path)
    if first["sha256"] != repeated["sha256"]:
        raise AcceptanceFailure(f"Numeric projection is not reproducible: {spec.output_name}")
    repeat_path.unlink()
    return {
        **first,
        "path": output_path,
        "source": {
            "key": spec.source.key,
            "name": spec.source.name,
            "dataset_id": spec.source.dataset_id,
            "landing_url": spec.source.landing_url,
            "download_url": spec.source.download_url,
            "archive_sha256": spec.source.archive_sha256,
            "archive_member": spec.source.archive_member,
            "doi": spec.source.doi,
            "citation": spec.source.citation,
            "license": spec.source.license_name,
            "license_url": spec.source.license_url,
        },
        "feature_columns": list(spec.feature_columns),
        "target_column": spec.target_column,
        "excluded_columns": list(spec.excluded_columns),
        "repeated_projection_sha256": repeated["sha256"],
    }


def run_acceptance(
    *,
    work_root: Path,
    source_cache: Path,
    output_dir: Path,
    offline: bool = False,
    timeout_seconds: float = 180.0,
) -> Dict[str, Any]:
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    work_root = work_root.resolve()
    source_cache = source_cache.resolve()
    output_dir = output_dir.resolve()
    projects_root = work_root / "projects"
    projections_root = work_root / "projections"
    projects_root.mkdir(parents=True, exist_ok=True)
    projections_root.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    report: Dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": "running",
        "generated_at": generated_at,
        "environment": _environment_summary(),
        "sources": [],
        "scenarios": [],
        "summary": {},
    }

    with ExitStack() as stack:
        stack.enter_context(patch("src.project_manager.PROJECTS_DIR", projects_root))
        stack.enter_context(patch("src.project_layout.PROJECTS_DIR", projects_root))
        stack.enter_context(patch("src.model_registry.PROJECTS_DIR", projects_root))
        stack.enter_context(patch("src.config.PROJECTS_DIR", projects_root))

        for task_head in ("classification", "regression"):
            spec = PROJECTIONS[task_head]
            scenario: Dict[str, Any]
            try:
                projection = prepare_projection(
                    spec,
                    source_cache,
                    projections_root,
                    offline=offline,
                )
                report["sources"].append(_public_projection_summary(projection))
                scenario = execute_scenario(
                    spec,
                    projection,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:  # acceptance boundary records a complete report
                scenario = {
                    "task_head": task_head,
                    "status": "failed",
                    "error": str(exc),
                    "checks": [{"name": "scenario_exception", "status": "failed", "evidence": str(exc)}],
                }
            report["scenarios"].append(scenario)

    passed = all(item.get("status") == "passed" for item in report["scenarios"])
    checks = [check for scenario in report["scenarios"] for check in scenario.get("checks", [])]
    report["status"] = "passed" if passed else "failed"
    report["summary"] = {
        "scenario_count": len(report["scenarios"]),
        "passed_scenarios": sum(1 for item in report["scenarios"] if item.get("status") == "passed"),
        "check_count": len(checks),
        "passed_checks": sum(1 for item in checks if item.get("status") == "passed"),
        "duration_seconds": round(time.perf_counter() - started, 3),
    }
    write_report(report, output_dir)
    return report


def execute_scenario(
    spec: ProjectionSpec,
    projection: Mapping[str, Any],
    *,
    timeout_seconds: float,
) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    task_head = spec.source.task_head
    task_type = f"tabular_{task_head}"
    project = ProjectManager.create_project(
        f"UCI {spec.source.name} acceptance",
        task_type,
        [],
    )
    project_id = str(project["project_id"])

    with Path(projection["path"]).open("rb") as stream:
        uploaded = UploadFile(file=stream, filename=Path(projection["path"]).name)
        imported = import_tabular_csv(project, uploaded)
    _accept(
        checks,
        imported["inspection"]["row_count"] == projection["row_count"],
        "import_row_count",
        {"rows": imported["inspection"]["row_count"]},
    )

    configured = update_project_tabular_config(
        project_id,
        project,
        {
            "source_file": imported["source_file"],
            "feature_columns": list(spec.feature_columns),
            "target_column": spec.target_column,
            "id_column": "",
            "split_column": "",
            "task_head": task_head,
            "seed": 20260825,
            "train_ratio": 0.70,
            "val_ratio": 0.15,
            "test_ratio": 0.15,
            "missing_strategy": "median",
        },
    )
    _accept(
        checks,
        bool(configured["validation"]["valid"]),
        "config_numeric_projection",
        configured["validation"],
    )
    project = _require_project(project_id)
    imported_source = resolve_tabular_source(project)
    if not imported_source:
        raise AcceptanceFailure("Imported project source could not be resolved.")

    first_dataset = load_csv_tabular_dataset(
        imported_source,
        target_column=spec.target_column,
        feature_columns=spec.feature_columns,
        task_head=task_head,
        seed=20260825,
        train_ratio=0.70,
        val_ratio=0.15,
        test_ratio=0.15,
    )
    second_dataset = load_csv_tabular_dataset(
        imported_source,
        target_column=spec.target_column,
        feature_columns=spec.feature_columns,
        task_head=task_head,
        seed=20260825,
        train_ratio=0.70,
        val_ratio=0.15,
        test_ratio=0.15,
    )
    reproducible = (
        first_dataset["feature_config_hash"] == second_dataset["feature_config_hash"]
        and first_dataset["imputation"] == second_dataset["imputation"]
        and all(
            first_dataset["tensors"][split]["row_indices"].tolist()
            == second_dataset["tensors"][split]["row_indices"].tolist()
            for split in ("train", "val", "test")
        )
    )
    _accept(
        checks,
        reproducible,
        "deterministic_split_and_imputation",
        {
            "feature_config_hash": first_dataset["feature_config_hash"],
            "split_counts": first_dataset["summary"]["split_counts"],
            "seed": first_dataset["summary"]["seed"],
        },
    )
    _accept(
        checks,
        first_dataset["summary"]["imputed_value_count"] > 0,
        "controlled_missing_values",
        {
            "missing_feature_values": first_dataset["summary"]["missing_feature_values"],
            "imputed_value_count": first_dataset["summary"]["imputed_value_count"],
            "strategy": first_dataset["imputation"]["strategy"],
            "fit_split": first_dataset["imputation"]["fit_split"],
        },
    )

    run_configs = _run_configs(task_head)
    run_summaries: List[Dict[str, Any]] = []
    for config in run_configs:
        project = _require_project(project_id)
        launch = TrainingStartService.start(project_id, project, config)
        state = wait_for_training(
            project_id,
            timeout_seconds=timeout_seconds,
            expected_run_id=str(launch["run_id"]),
        )
        _accept(
            checks,
            state.get("status") == "completed",
            f"training_{config['run_id']}",
            {"status": state.get("status"), "error": state.get("error", "")},
        )
        project = _require_project(project_id)
        run_dir = ProjectLayout.from_project(project).training_run_dir(str(config["run_id"]))
        summary = _read_json(run_dir / "run_summary.json")
        metrics = _read_json(run_dir / "metrics.json")
        run_summaries.append(summary)
        required_artifacts = (
            "weights/best.json",
            "preprocess/feature_schema.json",
            "preprocess/imputation.json",
            "feature_importance.json",
            "artifact_manifest.json",
            "metric_schema.json",
        )
        if task_head == "classification":
            required_artifacts += ("preprocess/label_encoder.json",)
        _accept(
            checks,
            all((run_dir / relative).is_file() for relative in required_artifacts),
            f"artifacts_{config['run_id']}",
            {"required": list(required_artifacts)},
        )
        manifest = _read_json(run_dir / "artifact_manifest.json")
        _accept(
            checks,
            manifest.get("contract_version") == "2.0"
            and len(str(manifest.get("lineage", {}).get("dataset", {}).get("dataset_sha256", ""))) == 64,
            f"metadata_v2_{config['run_id']}",
            {"contract_version": manifest.get("contract_version"), "lineage": manifest.get("lineage")},
        )
        _accept(
            checks,
            bool(metrics.get("feature_importance"))
            and all(item.get("feature") in spec.feature_columns for item in metrics.get("feature_importance", [])),
            f"feature_importance_{config['run_id']}",
            {"top_features": metrics.get("feature_importance", [])[:5]},
        )

    project = _require_project(project_id)
    baseline_id = str(run_configs[0]["run_id"])
    candidate_id = str(run_configs[1]["run_id"])
    comparison = CompareService.compare_runs(
        project,
        "tabular",
        [baseline_id, candidate_id],
        baseline_id,
    )
    _accept(
        checks,
        comparison.get("architecture") == "tabular"
        and comparison.get("task_family") == task_head
        and len(comparison.get("selected_runs", [])) == 2,
        "model_comparison",
        {
            "recommendation": comparison.get("recommendation"),
            "config_diff_keys": sorted((comparison.get("summary", {}).get("config_diff") or {}).keys()),
        },
    )
    compare_report = CompareService.export_report(
        project,
        "tabular",
        [baseline_id, candidate_id],
        baseline_id,
    )
    _accept(
        checks,
        {item.get("filename") for item in compare_report.get("files", [])}
        == {"report.json", "report.md", "summary.csv", "report.pdf"},
        "comparison_report",
        {"files": compare_report.get("files", [])},
    )

    candidate_run_dir = ProjectLayout.from_project(project).training_run_dir(candidate_id)
    inference = TabularXGBoostInferenceService.load_from_run(
        candidate_run_dir,
        trusted_root=ProjectLayout.from_project(project).project_dir,
    )
    single_row, batch_rows = _inference_rows(imported_source, spec, limit=32)
    single = inference.predict_one(single_row)
    if task_head == "classification":
        single_valid = single.get("predicted_label") in {"purchase", "no_purchase"}
    else:
        single_valid = math.isfinite(float(single.get("prediction")))
    _accept(
        checks,
        single_valid and float(single.get("latency_ms", -1)) >= 0,
        "single_row_inference",
        single,
    )

    batch_dir = ProjectLayout.from_project(project).inference_job_dir(f"uci_{task_head}_batch")
    batch_dir.mkdir(parents=True, exist_ok=True)
    batch_input = batch_dir / "input.csv"
    batch_output = batch_dir / "predictions.csv"
    _write_projection(batch_input, spec.feature_columns, batch_rows)
    batch = inference.predict_csv(
        batch_input,
        batch_output,
        trusted_root=ProjectLayout.from_project(project).project_dir,
    )
    _accept(
        checks,
        batch.get("row_count") == len(batch_rows) and batch_output.is_file(),
        "batch_csv_inference",
        {
            "row_count": batch.get("row_count"),
            "average_latency_ms": batch.get("average_latency_ms"),
            "output_sha256": sha256_file(batch_output),
        },
    )

    project = _require_project(project_id)
    models = ModelRegistry.list_models(project)
    best_models = [model for model in models if model.get("weight_type") == "best"]
    candidate_model = next(model for model in best_models if model.get("run_id") == candidate_id)
    versions = ModelLifecycleRegistry.list_versions(project)
    _accept(
        checks,
        len(versions.get("versions", [])) == 2
        and all(version.get("dataset_lineage") for version in versions.get("versions", [])),
        "model_registry_metadata",
        {"versions": versions.get("versions", [])},
    )
    ModelLifecycleRegistry.transition(
        project_id,
        project,
        str(candidate_model["model_id"]),
        "validated",
        limitations=["Numeric-feature projection only"],
    )
    ModelLifecycleRegistry.transition(
        project_id,
        project,
        str(candidate_model["model_id"]),
        "production",
        limitations=["Numeric-feature projection only"],
    )
    project = _require_project(project_id)
    promoted = ModelLifecycleRegistry.list_versions(project)
    production = next(
        (item for item in promoted.get("versions", []) if item.get("status") == "production"),
        None,
    )
    _accept(
        checks,
        bool(production)
        and production.get("model_id") == candidate_model.get("model_id")
        and project.get("current", {}).get("best_model_id") == candidate_model.get("model_id"),
        "lifecycle_to_production",
        {"production_model_id": production.get("model_id") if production else None},
    )

    exported = ExportService.export_project_model(
        project_id,
        project,
        run_id=candidate_id,
        export_format="tabular_package",
    )
    package = Path(str(exported["package_path"]))
    with zipfile.ZipFile(package) as archive:
        corrupt = archive.testzip()
        names = set(archive.namelist())
    required_package_files = {
        "weights/best.json",
        "preprocess/feature_schema.json",
        "preprocess/imputation.json",
        "inference_contract.json",
        "artifact_manifest.json",
    }
    if task_head == "classification":
        required_package_files.add("preprocess/label_encoder.json")
    _accept(
        checks,
        corrupt is None and required_package_files.issubset(names),
        "export_package",
        {
            "export_type": exported.get("export_type"),
            "package_sha256": sha256_file(package),
            "required_files": sorted(required_package_files),
        },
    )

    candidate_summary = run_summaries[-1]
    quality = _quality_gate(task_head, candidate_summary)
    _accept(checks, quality["passed"], "business_quality_gate", quality)

    return {
        "task_head": task_head,
        "status": "passed",
        "dataset": {
            "source_name": spec.source.name,
            "rows": projection["row_count"],
            "features": list(spec.feature_columns),
            "target": spec.target_column,
            "projection_sha256": projection["sha256"],
            "split_counts": first_dataset["summary"]["split_counts"],
            "missing_value_count": first_dataset["summary"]["imputed_value_count"],
        },
        "runs": [
            {
                "run_id": summary.get("run_id"),
                "primary_metric_name": summary.get("primary_metric_name"),
                "primary_metric_value": summary.get("primary_metric_value"),
                "best_metrics": summary.get("best_metrics"),
            }
            for summary in run_summaries
        ],
        "production_model": {
            "version": production.get("version") if production else None,
            "run_id": production.get("run_id") if production else None,
            "primary_metric_name": production.get("primary_metric_name") if production else None,
            "primary_metric_value": production.get("primary_metric_value") if production else None,
        },
        "single_inference": single,
        "batch_inference": {
            "row_count": batch.get("row_count"),
            "latency_ms": batch.get("latency_ms"),
            "average_latency_ms": batch.get("average_latency_ms"),
        },
        "checks": checks,
    }


def _run_configs(task_head: str) -> List[Dict[str, Any]]:
    prefix = "uci_class" if task_head == "classification" else "uci_reg"
    model = "xgboost_classifier" if task_head == "classification" else "xgboost_regressor"
    common = {
        "model": model,
        "batch_size": 0,
        "imgsz": 0,
        "lr0_mode": "custom",
        "device": "cpu",
        "patience": 0,
        "workers": 1,
        "workers_mode": "custom",
        "cache": False,
        "amp": False,
        "seed": 20260825,
        "save_period": 0,
        "close_mosaic": 0,
        "optimizer": "xgboost",
        "backend": "xgboost_tabular",
        "task_head": task_head,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
    }
    return [
        {
            **common,
            "run_id": f"{prefix}_baseline",
            "epochs": 32,
            "lr0": 0.05,
            "learning_rate": 0.05,
            "max_depth": 4,
        },
        {
            **common,
            "run_id": f"{prefix}_candidate",
            "epochs": 48,
            "lr0": 0.08,
            "learning_rate": 0.08,
            "max_depth": 6,
        },
    ]


def wait_for_training(
    project_id: str,
    *,
    timeout_seconds: float,
    expected_run_id: str,
) -> Dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    state: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        project = _require_project(project_id)
        state = TrainerDispatcher.get_status(project_id, project)
        if state.get("run_id") == expected_run_id and state.get("status") in TERMINAL_TRAINING_STATUSES:
            return state
        time.sleep(0.2)
    raise AcceptanceFailure(
        f"Training {expected_run_id} did not finish within {timeout_seconds:g} seconds; last state: {state}"
    )


def _inference_rows(
    csv_path: Path,
    spec: ProjectionSpec,
    *,
    limit: int,
) -> tuple[Dict[str, str], List[Dict[str, str]]]:
    rows: List[Dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        for source in reader:
            row = {column: str(source.get(column) or "") for column in spec.feature_columns}
            rows.append(row)
            if len(rows) >= limit:
                break
    if not rows:
        raise AcceptanceFailure("Projected dataset contains no inference rows.")
    single = next(
        (row for row in rows if all(str(value).strip() for value in row.values())),
        rows[0],
    )
    return single, rows


def _quality_gate(task_head: str, summary: Mapping[str, Any]) -> Dict[str, Any]:
    metrics = summary.get("best_metrics") or {}
    if task_head == "classification":
        value = _finite_float(metrics.get("val/macro_f1"))
        threshold = 0.55
        return {
            "passed": value is not None and value >= threshold,
            "metric": "val/macro_f1",
            "value": value,
            "threshold": threshold,
            "rationale": "Exceeds a weak imbalanced-class baseline using numeric session behavior only.",
        }
    value = _finite_float(metrics.get("val/r2"))
    threshold = 0.40
    return {
        "passed": value is not None and value >= threshold,
        "metric": "val/r2",
        "value": value,
        "threshold": threshold,
        "rationale": "Demonstrates useful demand signal without date or categorical features.",
    }


def _finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _accept(
    checks: List[Dict[str, Any]],
    condition: bool,
    name: str,
    evidence: Any,
) -> None:
    check = {
        "name": name,
        "status": "passed" if condition else "failed",
        "evidence": _json_safe(evidence),
    }
    checks.append(check)
    if not condition:
        raise AcceptanceFailure(f"Acceptance check failed: {name}: {evidence}")


def _require_project(project_id: str) -> Dict[str, Any]:
    project = ProjectManager.get_project(project_id)
    if not project:
        raise AcceptanceFailure(f"Acceptance project disappeared: {project_id}")
    return project


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _public_projection_summary(projection: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "source": projection["source"],
        "projection": {
            "row_count": projection["row_count"],
            "column_count": projection["column_count"],
            "feature_columns": projection["feature_columns"],
            "target_column": projection["target_column"],
            "excluded_columns": projection["excluded_columns"],
            "sha256": projection["sha256"],
            "repeated_projection_sha256": projection["repeated_projection_sha256"],
            "controlled_missing_values": projection["controlled_missing_values"],
            "controlled_missing_value_count": projection["controlled_missing_value_count"],
            "size_bytes": projection["size_bytes"],
        },
    }


def _environment_summary() -> Dict[str, Any]:
    try:
        import numpy
        import xgboost

        numpy_version = numpy.__version__
        xgboost_version = xgboost.__version__
    except Exception:
        numpy_version = "unavailable"
        xgboost_version = "unavailable"
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "numpy": numpy_version,
        "xgboost": xgboost_version,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def write_report(report: Mapping[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "acceptance_report.json"
    markdown_path = output_dir / "acceptance_report.md"
    json_path.write_text(
        json.dumps(_json_safe(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")


def render_markdown_report(report: Mapping[str, Any]) -> str:
    status = str(report.get("status") or "unknown").upper()
    summary = report.get("summary") or {}
    lines = [
        "# Tabular Commercial CSV Product Acceptance",
        "",
        f"- Status: **{status}**",
        f"- Generated: `{report.get('generated_at', '--')}`",
        f"- Scenarios: `{summary.get('passed_scenarios', 0)}/{summary.get('scenario_count', 0)}` passed",
        f"- Checks: `{summary.get('passed_checks', 0)}/{summary.get('check_count', 0)}` passed",
        f"- Duration: `{summary.get('duration_seconds', '--')} s`",
        "",
        "## Environment",
        "",
    ]
    environment = report.get("environment") or {}
    for key in ("platform", "machine", "python", "numpy", "xgboost"):
        lines.append(f"- {key}: `{environment.get(key, '--')}`")

    lines.extend(["", "## Official UCI Sources", ""])
    for source_entry in report.get("sources") or []:
        source = source_entry.get("source") or {}
        projection = source_entry.get("projection") or {}
        lines.extend(
            [
                f"### {source.get('name', '--')}",
                "",
                f"- UCI dataset: [{source.get('dataset_id', '--')}]({source.get('landing_url', '')})",
                f"- DOI: [{source.get('doi', '--')}](https://doi.org/{source.get('doi', '')})",
                f"- License: [{source.get('license', '--')}]({source.get('license_url', '')})",
                f"- Citation: {source.get('citation', '--')}",
                f"- Pinned archive SHA-256: `{source.get('archive_sha256', '--')}`",
                f"- Numeric projection SHA-256: `{projection.get('sha256', '--')}`",
                f"- Rows / features: `{projection.get('row_count', 0)} / {len(projection.get('feature_columns') or [])}`",
                f"- Numeric features: `{', '.join(projection.get('feature_columns') or [])}`",
                f"- Target: `{projection.get('target_column', '--')}`",
                f"- Excluded categorical/date/leakage fields: `{', '.join(projection.get('excluded_columns') or [])}`",
                f"- Controlled missing values: `{projection.get('controlled_missing_value_count', 0)}`",
                "",
            ]
        )

    lines.extend(["## Scenario Results", ""])
    for scenario in report.get("scenarios") or []:
        lines.extend(
            [
                f"### {str(scenario.get('task_head') or '--').title()}: {str(scenario.get('status') or '--').upper()}",
                "",
            ]
        )
        if scenario.get("error"):
            lines.append(f"Error: `{scenario['error']}`")
            lines.append("")
        if scenario.get("dataset"):
            dataset = scenario["dataset"]
            lines.append(
                f"Dataset: `{dataset.get('rows')} rows`, `{len(dataset.get('features') or [])} features`, "
                f"split `{dataset.get('split_counts')}`, imputed `{dataset.get('missing_value_count')}` values."
            )
            lines.append("")
        for run in scenario.get("runs") or []:
            lines.append(
                f"- `{run.get('run_id')}`: {run.get('primary_metric_name')} = "
                f"`{run.get('primary_metric_value')}`"
            )
        if scenario.get("runs"):
            lines.append("")
        lines.extend(["| Check | Status |", "|---|---|"])
        for check in scenario.get("checks") or []:
            lines.append(f"| `{check.get('name')}` | {str(check.get('status') or '--').upper()} |")
        lines.append("")

    lines.extend(
        [
            "## Scope and Limitations",
            "",
            "- Raw UCI archives are downloaded into the ignored acceptance cache and are not committed.",
            "- The current first-party Tabular contract accepts numeric features only. Categorical and date fields are deliberately excluded and documented above.",
            "- Controlled missing values are added only to feature columns so train-only median imputation is exercised; targets are unchanged.",
            "- Quality thresholds are product smoke gates, not claims of state-of-the-art performance.",
            "- The harness uses real project, import, configuration, training, inference, comparison, lifecycle and export services in an isolated temporary project root.",
            "",
            "## Reproduce",
            "",
            "```powershell",
            "python scripts/run_tabular_commercial_acceptance.py",
            "python scripts/run_tabular_commercial_acceptance.py --offline",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the isolated, reproducible UCI commercial-CSV acceptance chain for "
            "Vision Training Studio Tabular XGBoost."
        )
    )
    parser.add_argument(
        "--source-cache",
        type=Path,
        default=PROJECT_ROOT / "cache" / "acceptance" / "uci",
        help="Ignored cache for checksum-pinned UCI source archives.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "build" / "reports" / "tabular_commercial_acceptance",
        help="Directory for acceptance_report.json and acceptance_report.md.",
    )
    parser.add_argument("--work-dir", type=Path, help="Optional isolated working directory.")
    parser.add_argument("--keep-work-dir", action="store_true", help="Keep generated projects and projections.")
    parser.add_argument("--offline", action="store_true", help="Use checksum-verified cached UCI archives only.")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cleanup = args.work_dir is None and not args.keep_work_dir
    work_root = args.work_dir or Path(tempfile.mkdtemp(prefix="vts-tabular-acceptance-"))
    try:
        report = run_acceptance(
            work_root=work_root,
            source_cache=args.source_cache,
            output_dir=args.output_dir,
            offline=args.offline,
            timeout_seconds=max(10.0, float(args.timeout_seconds)),
        )
        print(json.dumps(_json_safe(report["summary"] | {"status": report["status"]}), ensure_ascii=False, indent=2))
        print(f"JSON report: {(args.output_dir / 'acceptance_report.json').resolve()}")
        print(f"Markdown report: {(args.output_dir / 'acceptance_report.md').resolve()}")
        return 0 if report["status"] == "passed" else 1
    finally:
        if cleanup and work_root.exists():
            shutil.rmtree(work_root)


if __name__ == "__main__":
    raise SystemExit(main())
