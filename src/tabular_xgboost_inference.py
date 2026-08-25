from __future__ import annotations

import csv
import json
import math
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

import numpy as np


_CSV_NUMERIC_LITERAL = re.compile(
    r"^[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?$"
)
_CSV_FORMULA_PREFIXES = frozenset({"=", "+", "-", "@"})


class TabularXGBoostInferenceError(RuntimeError):
    """A safe, user-presentable error raised by the tabular inference core."""


@dataclass(frozen=True)
class TabularPreprocessContract:
    schema_version: str
    feature_columns: tuple[str, ...]
    feature_dtypes: Dict[str, str]
    task_head: str
    target_column: str
    imputation_strategy: str
    imputation_statistics: Dict[str, float]
    missing_tokens: frozenset[str]
    class_labels: tuple[Any, ...]


class TabularXGBoostInferenceService:
    """Safe row-level and CSV inference for platform-produced Tabular XGBoost runs.

    Loading is deliberately run based.  Callers provide a project-owned trusted
    root and a run directory under it; the model path cannot be redirected by
    request data or metadata and is always ``weights/best.json``.
    """

    MODEL_RELATIVE_PATH = Path("weights") / "best.json"
    FEATURE_SCHEMA_RELATIVE_PATH = Path("preprocess") / "feature_schema.json"
    IMPUTATION_RELATIVE_PATH = Path("preprocess") / "imputation.json"
    LABEL_ENCODER_RELATIVE_PATH = Path("preprocess") / "label_encoder.json"
    BACKEND_RELATIVE_PATH = Path("backend.json")

    MAX_MODEL_BYTES = 512 * 1024 * 1024
    MAX_METADATA_BYTES = 4 * 1024 * 1024
    MAX_CSV_BYTES = 256 * 1024 * 1024
    MAX_CSV_ROWS = 250_000
    MAX_FEATURES = 10_000

    _SUPPORTED_SCHEMA_MAJORS = {"1", "2"}
    _SUPPORTED_DTYPES = {
        "float",
        "float16",
        "float32",
        "float64",
        "double",
        "int",
        "int8",
        "int16",
        "int32",
        "int64",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
        "number",
        "numeric",
    }
    _CLASSIFICATION_OBJECTIVES = {"binary:logistic", "multi:softprob"}
    _REGRESSION_OBJECTIVES = {"reg:squarederror"}

    def __init__(
        self,
        *,
        trusted_root: Path,
        run_dir: Path,
        model_path: Path,
        booster: Any,
        contract: TabularPreprocessContract,
        objective: str,
        model_load_latency_ms: float,
    ) -> None:
        self.trusted_root = trusted_root
        self.run_dir = run_dir
        self.model_path = model_path
        self.contract = contract
        self.objective = objective
        self.model_load_latency_ms = model_load_latency_ms
        self._booster = booster
        self._predict_lock = threading.RLock()

    @classmethod
    def load_from_run(
        cls,
        run_dir: str | os.PathLike[str],
        *,
        trusted_root: str | os.PathLike[str],
    ) -> "TabularXGBoostInferenceService":
        """Load one platform-produced run from an explicitly trusted root."""

        root = _secure_root(Path(trusted_root))
        secure_run_dir = _secure_existing_dir(root, Path(run_dir), "Run directory")
        model_path = _secure_existing_file(
            root,
            secure_run_dir / cls.MODEL_RELATIVE_PATH,
            label="XGBoost model",
            allowed_suffixes={".json"},
            max_bytes=cls.MAX_MODEL_BYTES,
        )
        schema_path = _secure_existing_file(
            root,
            secure_run_dir / cls.FEATURE_SCHEMA_RELATIVE_PATH,
            label="Feature schema",
            allowed_suffixes={".json"},
            max_bytes=cls.MAX_METADATA_BYTES,
        )

        schema = _load_json_object(schema_path, "Feature schema")
        imputation = cls._load_imputation(root, secure_run_dir, schema)
        label_encoder = cls._load_label_encoder(root, secure_run_dir, schema)
        contract = cls._build_contract(schema, imputation, label_encoder)
        cls._validate_optional_backend_contract(root, secure_run_dir, contract)

        # Parse the model as plain JSON before handing it to the native runtime.
        # This excludes pickle-like payloads, malformed JSON and non-XGBoost files.
        model_stat_before = _file_signature(model_path)
        model_payload = _load_json_object(model_path, "XGBoost model")
        if not isinstance(model_payload.get("learner"), dict):
            raise TabularXGBoostInferenceError("XGBoost model JSON is missing the learner contract.")

        started = time.perf_counter()
        try:
            import xgboost as xgb
        except Exception as exc:  # pragma: no cover - depends on packaged runtime
            raise TabularXGBoostInferenceError("XGBoost runtime is not available for tabular inference.") from exc

        try:
            booster = xgb.Booster()
            booster.load_model(str(model_path))
        except Exception as exc:
            raise TabularXGBoostInferenceError("The XGBoost model could not be loaded safely.") from exc
        if _file_signature(model_path) != model_stat_before:
            raise TabularXGBoostInferenceError("The XGBoost model changed while it was being loaded.")

        load_latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
        cls._validate_loaded_booster(booster, contract)
        objective = cls._objective_name(booster)
        cls._validate_objective(objective, contract)
        return cls(
            trusted_root=root,
            run_dir=secure_run_dir,
            model_path=model_path,
            booster=booster,
            contract=contract,
            objective=objective,
            model_load_latency_ms=load_latency_ms,
        )

    def describe(self) -> Dict[str, Any]:
        """Return non-sensitive model and input-contract information for an API."""

        return {
            "architecture": "tabular",
            "backend": "xgboost_tabular",
            "task_head": self.contract.task_head,
            "schema_version": self.contract.schema_version,
            "feature_columns": list(self.contract.feature_columns),
            "target_column": self.contract.target_column,
            "objective": self.objective,
            "class_labels": list(self.contract.class_labels),
            "model_load_latency_ms": self.model_load_latency_ms,
        }

    def predict_one(self, row: Mapping[str, Any]) -> Dict[str, Any]:
        """Predict one row and include end-to-end preprocessing/prediction latency."""

        result = self.predict_rows([row])
        prediction = dict(result["predictions"][0])
        prediction["latency_ms"] = result["latency_ms"]
        return prediction

    def predict_rows(self, rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        """Predict a non-empty bounded row collection in one native batch."""

        if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
            raise TabularXGBoostInferenceError("Tabular rows must be supplied as a sequence of objects.")
        if not rows:
            raise TabularXGBoostInferenceError("At least one tabular row is required for inference.")
        if len(rows) > self.MAX_CSV_ROWS:
            raise TabularXGBoostInferenceError(f"Tabular inference is limited to {self.MAX_CSV_ROWS} rows per request.")

        started = time.perf_counter()
        matrix = self._preprocess_rows(rows)
        raw_predictions = self._predict_matrix(matrix)
        predictions = self._format_predictions(raw_predictions, len(rows))
        latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
        return {
            "task_head": self.contract.task_head,
            "row_count": len(rows),
            "predictions": predictions,
            "latency_ms": latency_ms,
            "average_latency_ms": round(latency_ms / len(rows), 6),
        }

    def predict_csv(
        self,
        input_path: str | os.PathLike[str],
        output_path: str | os.PathLike[str],
        *,
        overwrite: bool = False,
        trusted_root: str | os.PathLike[str] | None = None,
    ) -> Dict[str, Any]:
        """Predict an UTF-8 CSV and atomically write a CSV below ``trusted_root``."""

        total_started = time.perf_counter()
        if trusted_root is not None and _secure_root(Path(trusted_root)) != self.trusted_root:
            raise TabularXGBoostInferenceError(
                "CSV trusted root must match the root used to load the tabular model."
            )
        secure_input = _secure_existing_file(
            self.trusted_root,
            Path(input_path),
            label="Input CSV",
            allowed_suffixes={".csv"},
            max_bytes=self.MAX_CSV_BYTES,
        )
        secure_output = _secure_output_file(
            self.trusted_root,
            Path(output_path),
            allowed_suffixes={".csv"},
            overwrite=overwrite,
        )
        if secure_input == secure_output:
            raise TabularXGBoostInferenceError("Input and output CSV paths must be different.")

        fieldnames, rows = self._read_csv(secure_input)
        reserved = self._csv_prediction_fields()
        collisions = [name for name in reserved if name in fieldnames]
        if collisions:
            raise TabularXGBoostInferenceError(
                f"Input CSV uses reserved prediction columns: {', '.join(collisions)}."
            )

        result = self.predict_rows(rows)
        self._write_csv_atomic(
            secure_output,
            fieldnames,
            rows,
            result["predictions"],
            overwrite=overwrite,
        )
        total_latency_ms = round((time.perf_counter() - total_started) * 1000.0, 3)
        return {
            **result,
            "input_path": secure_input.as_posix(),
            "output_path": secure_output.as_posix(),
            "total_latency_ms": total_latency_ms,
        }

    @classmethod
    def _load_imputation(
        cls,
        root: Path,
        run_dir: Path,
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        path = run_dir / cls.IMPUTATION_RELATIVE_PATH
        if path.exists():
            secure_path = _secure_existing_file(
                root,
                path,
                label="Imputation contract",
                allowed_suffixes={".json"},
                max_bytes=cls.MAX_METADATA_BYTES,
            )
            return _load_json_object(secure_path, "Imputation contract")

        embedded = schema.get("imputation") or schema.get("imputation_values")
        if not isinstance(embedded, dict):
            raise TabularXGBoostInferenceError(
                "Tabular preprocessing requires preprocess/imputation.json or schema-embedded imputation."
            )
        return dict(embedded)

    @classmethod
    def _load_label_encoder(
        cls,
        root: Path,
        run_dir: Path,
        schema: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        path = run_dir / cls.LABEL_ENCODER_RELATIVE_PATH
        if path.exists():
            secure_path = _secure_existing_file(
                root,
                path,
                label="Label encoder",
                allowed_suffixes={".json"},
                max_bytes=cls.MAX_METADATA_BYTES,
            )
            return _load_json_object(secure_path, "Label encoder")
        embedded = schema.get("label_encoder") or schema.get("label_mapping")
        return dict(embedded) if isinstance(embedded, dict) else None

    @classmethod
    def _build_contract(
        cls,
        schema: Dict[str, Any],
        imputation: Dict[str, Any],
        label_encoder: Dict[str, Any] | None,
    ) -> TabularPreprocessContract:
        schema_version = str(schema.get("schema_version") or schema.get("contract_version") or "").strip()
        if not schema_version or schema_version.split(".", 1)[0] not in cls._SUPPORTED_SCHEMA_MAJORS:
            raise TabularXGBoostInferenceError("Unsupported or missing tabular feature schema version.")
        if str(schema.get("architecture") or "").strip().lower() != "tabular":
            raise TabularXGBoostInferenceError("Feature schema architecture must be tabular.")

        raw_columns = schema.get("feature_columns")
        if not isinstance(raw_columns, list) or not raw_columns or len(raw_columns) > cls.MAX_FEATURES:
            raise TabularXGBoostInferenceError("Feature schema must contain a bounded, non-empty feature_columns list.")
        feature_columns: List[str] = []
        for value in raw_columns:
            if not isinstance(value, str):
                raise TabularXGBoostInferenceError("Every feature column name must be a string.")
            name = value.strip()
            if not name or len(name) > 256 or any(ord(char) < 32 for char in name):
                raise TabularXGBoostInferenceError("Feature schema contains an invalid column name.")
            feature_columns.append(name)
        if len(set(feature_columns)) != len(feature_columns):
            raise TabularXGBoostInferenceError("Feature schema contains duplicate feature columns.")
        try:
            input_dim = int(schema.get("input_dim"))
        except (TypeError, ValueError) as exc:
            raise TabularXGBoostInferenceError("Feature schema input_dim is required.") from exc
        if input_dim != len(feature_columns):
            raise TabularXGBoostInferenceError("Feature schema input_dim does not match feature_columns.")

        task_head = str(schema.get("task_head") or "").strip().lower()
        if task_head not in {"classification", "regression"}:
            raise TabularXGBoostInferenceError("Feature schema task_head must be classification or regression.")

        raw_dtypes = schema.get("feature_dtypes") or {}
        if not isinstance(raw_dtypes, dict):
            raise TabularXGBoostInferenceError("Feature schema feature_dtypes must be an object.")
        feature_dtypes: Dict[str, str] = {}
        for feature in feature_columns:
            dtype = str(raw_dtypes.get(feature) or "float32").strip().lower()
            if dtype not in cls._SUPPORTED_DTYPES:
                raise TabularXGBoostInferenceError(
                    f"Feature {feature} uses unsupported non-numeric dtype {dtype or '<empty>'}."
                )
            feature_dtypes[feature] = dtype

        strategy = str(imputation.get("strategy") or "median").strip().lower()
        if strategy != "median":
            raise TabularXGBoostInferenceError("Only median imputation is supported by this inference contract.")
        raw_statistics = (
            imputation.get("statistics")
            or imputation.get("values")
            or imputation.get("fill_values")
            or imputation
        )
        if not isinstance(raw_statistics, dict):
            raise TabularXGBoostInferenceError("Imputation statistics must be an object.")
        statistics: Dict[str, float] = {}
        for feature in feature_columns:
            if feature not in raw_statistics:
                raise TabularXGBoostInferenceError(f"Imputation statistic is missing for feature {feature}.")
            statistics[feature] = _finite_number(raw_statistics[feature], f"Imputation statistic for {feature}")

        raw_missing_tokens = imputation.get("missing_tokens") or ["", "na", "n/a", "nan", "null", "none"]
        if not isinstance(raw_missing_tokens, list) or len(raw_missing_tokens) > 100:
            raise TabularXGBoostInferenceError("Imputation missing_tokens must be a bounded list.")
        missing_tokens = set()
        for token in raw_missing_tokens:
            if not isinstance(token, str) or len(token) > 128:
                raise TabularXGBoostInferenceError("Each missing-value token must be a short string.")
            missing_tokens.add(token.strip().casefold())
        missing_tokens.add("")

        class_labels: tuple[Any, ...] = ()
        if task_head == "classification":
            class_labels = cls._class_labels(label_encoder)

        return TabularPreprocessContract(
            schema_version=schema_version,
            feature_columns=tuple(feature_columns),
            feature_dtypes=feature_dtypes,
            task_head=task_head,
            target_column=str(schema.get("target_column") or "").strip(),
            imputation_strategy=strategy,
            imputation_statistics=statistics,
            missing_tokens=frozenset(missing_tokens),
            class_labels=class_labels,
        )

    @staticmethod
    def _class_labels(label_encoder: Dict[str, Any] | None) -> tuple[Any, ...]:
        if not isinstance(label_encoder, dict):
            raise TabularXGBoostInferenceError("Classification inference requires a label encoder contract.")
        raw_mapping = label_encoder.get("mapping") if isinstance(label_encoder.get("mapping"), dict) else label_encoder
        raw_classes = label_encoder.get("classes")
        if not isinstance(raw_mapping, dict) or len(raw_mapping) < 2:
            raise TabularXGBoostInferenceError("Label encoder must map at least two labels to class indexes.")

        inverse: Dict[int, Any] = {}
        for label, raw_index in raw_mapping.items():
            if label in {"schema_version", "classes"} and raw_mapping is label_encoder:
                continue
            if isinstance(raw_index, bool):
                raise TabularXGBoostInferenceError("Label encoder class indexes must be integers.")
            try:
                index = int(raw_index)
            except (TypeError, ValueError) as exc:
                raise TabularXGBoostInferenceError("Label encoder class indexes must be integers.") from exc
            if index < 0 or index in inverse:
                raise TabularXGBoostInferenceError("Label encoder contains duplicate or negative class indexes.")
            inverse[index] = label
        expected = list(range(len(inverse)))
        if sorted(inverse) != expected or len(expected) < 2:
            raise TabularXGBoostInferenceError("Label encoder class indexes must be contiguous from zero.")

        if raw_classes is not None:
            if not isinstance(raw_classes, list) or len(raw_classes) != len(inverse):
                raise TabularXGBoostInferenceError("Label encoder classes do not match its mapping.")
            for label in raw_classes:
                key = str(label)
                if key not in raw_mapping:
                    raise TabularXGBoostInferenceError("Label encoder classes do not match its mapping.")
                inverse[int(raw_mapping[key])] = label
        return tuple(inverse[index] for index in expected)

    @classmethod
    def _validate_optional_backend_contract(
        cls,
        root: Path,
        run_dir: Path,
        contract: TabularPreprocessContract,
    ) -> None:
        path = run_dir / cls.BACKEND_RELATIVE_PATH
        if not path.exists():
            return
        secure_path = _secure_existing_file(
            root,
            path,
            label="Backend contract",
            allowed_suffixes={".json"},
            max_bytes=cls.MAX_METADATA_BYTES,
        )
        payload = _load_json_object(secure_path, "Backend contract")
        architecture = str(payload.get("architecture") or "").lower()
        backend = str(payload.get("backend") or "").lower()
        task_type = str(payload.get("task_type") or "").lower()
        if architecture and architecture != "tabular":
            raise TabularXGBoostInferenceError("Backend contract architecture does not match tabular inference.")
        if backend and backend not in {
            "sklearn_xgboost",
            "tabular_xgboost",
            "xgboost_tabular",
            "xgboost",
        }:
            raise TabularXGBoostInferenceError("Backend contract is not an approved XGBoost backend.")
        if task_type:
            expected_suffix = "classification" if contract.task_head == "classification" else "regression"
            if not task_type.endswith(expected_suffix):
                raise TabularXGBoostInferenceError("Backend contract task type does not match preprocessing.")

    @classmethod
    def _validate_loaded_booster(cls, booster: Any, contract: TabularPreprocessContract) -> None:
        try:
            feature_count = int(booster.num_features())
        except Exception as exc:
            raise TabularXGBoostInferenceError("XGBoost model does not expose a valid feature contract.") from exc
        if feature_count != len(contract.feature_columns):
            raise TabularXGBoostInferenceError("XGBoost model feature count does not match feature schema.")
        model_feature_names = booster.feature_names
        if model_feature_names and list(model_feature_names) != list(contract.feature_columns):
            raise TabularXGBoostInferenceError("XGBoost model feature names do not match feature schema order.")

    @staticmethod
    def _objective_name(booster: Any) -> str:
        try:
            config = json.loads(booster.save_config())
            return str(config["learner"]["objective"]["name"]).strip().lower()
        except Exception as exc:
            raise TabularXGBoostInferenceError("XGBoost objective metadata is invalid.") from exc

    @classmethod
    def _validate_objective(cls, objective: str, contract: TabularPreprocessContract) -> None:
        if contract.task_head == "classification":
            if objective not in cls._CLASSIFICATION_OBJECTIVES:
                raise TabularXGBoostInferenceError("XGBoost objective does not provide classification probabilities.")
            expected = "binary:logistic" if len(contract.class_labels) == 2 else "multi:softprob"
            if objective != expected:
                raise TabularXGBoostInferenceError("XGBoost objective does not match the label encoder class count.")
        elif objective not in cls._REGRESSION_OBJECTIVES:
            raise TabularXGBoostInferenceError("XGBoost objective is not an approved tabular regression objective.")

    def _preprocess_rows(self, rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
        matrix: List[List[float]] = []
        for row_index, row in enumerate(rows, start=1):
            if not isinstance(row, Mapping):
                raise TabularXGBoostInferenceError(f"Row {row_index} must be an object keyed by feature name.")
            missing_columns = [feature for feature in self.contract.feature_columns if feature not in row]
            if missing_columns:
                raise TabularXGBoostInferenceError(
                    f"Row {row_index} is missing required feature columns: {', '.join(missing_columns)}."
                )
            values = [self._feature_value(row[feature], feature, row_index) for feature in self.contract.feature_columns]
            matrix.append(values)
        return np.asarray(matrix, dtype=np.float32)

    def _feature_value(self, value: Any, feature: str, row_index: int) -> float:
        is_missing = value is None
        if isinstance(value, str):
            stripped = value.strip()
            is_missing = stripped.casefold() in self.contract.missing_tokens
            value = stripped
        elif isinstance(value, (float, np.floating)):
            is_missing = math.isnan(float(value))
        if is_missing:
            return self.contract.imputation_statistics[feature]
        try:
            return _finite_number(value, f"Feature {feature} at row {row_index}")
        except TabularXGBoostInferenceError as exc:
            raise TabularXGBoostInferenceError(
                f"Feature {feature} at row {row_index} must be numeric or a configured missing value."
            ) from exc

    def _predict_matrix(self, matrix: np.ndarray) -> np.ndarray:
        try:
            import xgboost as xgb

            dmatrix = xgb.DMatrix(matrix, feature_names=list(self.contract.feature_columns))
            with self._predict_lock:
                predictions = self._booster.predict(dmatrix, validate_features=True)
        except TabularXGBoostInferenceError:
            raise
        except Exception as exc:
            raise TabularXGBoostInferenceError("XGBoost inference failed for the supplied tabular rows.") from exc
        array = np.asarray(predictions, dtype=float)
        if not np.all(np.isfinite(array)):
            raise TabularXGBoostInferenceError("XGBoost inference returned non-finite values.")
        return array

    def _format_predictions(self, raw: np.ndarray, row_count: int) -> List[Dict[str, Any]]:
        if self.contract.task_head == "regression":
            values = raw.reshape(-1)
            if len(values) != row_count:
                raise TabularXGBoostInferenceError("XGBoost regression output shape is invalid.")
            return [{"prediction": float(value)} for value in values]

        labels = self.contract.class_labels
        class_count = len(labels)
        if class_count == 2:
            positive = raw.reshape(-1)
            if len(positive) != row_count:
                raise TabularXGBoostInferenceError("XGBoost binary classification output shape is invalid.")
            probability_rows = np.column_stack((1.0 - positive, positive))
        else:
            probability_rows = raw
            if probability_rows.ndim == 1 and row_count == 1 and probability_rows.size == class_count:
                probability_rows = probability_rows.reshape(1, -1)
            if probability_rows.shape != (row_count, class_count):
                raise TabularXGBoostInferenceError("XGBoost multiclass probability output shape is invalid.")

        if np.any(probability_rows < -1e-6) or np.any(probability_rows > 1.0 + 1e-6):
            raise TabularXGBoostInferenceError("XGBoost classification output contains invalid probabilities.")
        probability_rows = np.clip(probability_rows, 0.0, 1.0)
        totals = probability_rows.sum(axis=1)
        if np.any(np.abs(totals - 1.0) > 1e-4):
            raise TabularXGBoostInferenceError("XGBoost classification probabilities do not sum to one.")

        results: List[Dict[str, Any]] = []
        for probabilities in probability_rows:
            class_index = int(np.argmax(probabilities))
            probability_map = {
                str(label): round(float(probabilities[index]), 8)
                for index, label in enumerate(labels)
            }
            results.append(
                {
                    "predicted_class": class_index,
                    "predicted_label": labels[class_index],
                    "confidence": round(float(probabilities[class_index]), 8),
                    "probabilities": probability_map,
                }
            )
        return results

    def _read_csv(self, path: Path) -> tuple[List[str], List[Dict[str, str]]]:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                fieldnames = list(reader.fieldnames or [])
                if not fieldnames:
                    raise TabularXGBoostInferenceError("Input CSV must contain a header row.")
                if len(set(fieldnames)) != len(fieldnames):
                    raise TabularXGBoostInferenceError("Input CSV contains duplicate column names.")
                missing = [feature for feature in self.contract.feature_columns if feature not in fieldnames]
                if missing:
                    raise TabularXGBoostInferenceError(
                        f"Input CSV is missing required feature columns: {', '.join(missing)}."
                    )
                rows: List[Dict[str, str]] = []
                for row_number, row in enumerate(reader, start=2):
                    if None in row:
                        raise TabularXGBoostInferenceError(
                            f"Input CSV row {row_number} contains more values than its header."
                        )
                    rows.append(dict(row))
                    if len(rows) > self.MAX_CSV_ROWS:
                        raise TabularXGBoostInferenceError(
                            f"Input CSV exceeds the {self.MAX_CSV_ROWS}-row inference limit."
                        )
        except UnicodeDecodeError as exc:
            raise TabularXGBoostInferenceError("Input CSV must use UTF-8 encoding.") from exc
        except csv.Error as exc:
            raise TabularXGBoostInferenceError("Input CSV is malformed.") from exc
        if not rows:
            raise TabularXGBoostInferenceError("Input CSV contains no data rows.")
        return fieldnames, rows

    def _csv_prediction_fields(self) -> List[str]:
        if self.contract.task_head == "classification":
            return ["predicted_class", "predicted_label", "confidence", "probabilities"]
        return ["prediction"]

    def _write_csv_atomic(
        self,
        path: Path,
        input_fields: Sequence[str],
        rows: Sequence[Mapping[str, Any]],
        predictions: Sequence[Mapping[str, Any]],
        *,
        overwrite: bool,
    ) -> None:
        fields = [*input_fields, *self._csv_prediction_fields()]
        temp_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                prefix=f".{path.stem}_",
                suffix=".tmp",
                dir=path.parent,
                delete=False,
            ) as handle:
                temp_name = handle.name
                writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                for row, prediction in zip(rows, predictions):
                    output_row = dict(row)
                    output_row.update(prediction)
                    if "probabilities" in output_row:
                        output_row["probabilities"] = json.dumps(
                            output_row["probabilities"], ensure_ascii=False, separators=(",", ":")
                        )
                    # CSV quoting does not stop spreadsheet applications from
                    # evaluating formula-like cell contents.  Keep the API
                    # prediction objects untouched, but make every exported
                    # string cell safe at the spreadsheet boundary.  Genuine
                    # finite numeric literals (including signed/scientific
                    # notation) remain numeric-looking for downstream tools.
                    output_row = {
                        key: _spreadsheet_safe_csv_cell(
                            value,
                            # A class label is categorical even when its text
                            # happens to look like a signed number.
                            preserve_numeric=(key != "predicted_label"),
                        )
                        for key, value in output_row.items()
                    }
                    writer.writerow(output_row)
                handle.flush()
                os.fsync(handle.fileno())
            if path.exists() and not overwrite:
                raise TabularXGBoostInferenceError("Output CSV already exists; explicit overwrite is required.")
            os.replace(temp_name, path)
            temp_name = ""
        except TabularXGBoostInferenceError:
            raise
        except OSError as exc:
            raise TabularXGBoostInferenceError("Prediction CSV could not be written.") from exc
        finally:
            if temp_name:
                try:
                    Path(temp_name).unlink(missing_ok=True)
                except OSError:
                    pass


def _spreadsheet_safe_csv_cell(value: Any, *, preserve_numeric: bool = True) -> Any:
    """Neutralize formula-like text only in downloadable spreadsheet cells.

    The apostrophe is the conventional spreadsheet text marker.  It is kept
    out of row-level and JSON prediction responses, so callers that need the
    original label continue to receive it unchanged.  Valid finite decimal or
    scientific literals are intentionally preserved to avoid turning signed
    numeric feature values into text.
    """

    if not isinstance(value, str):
        return value
    candidate = value.lstrip()
    if not candidate or candidate[0] not in _CSV_FORMULA_PREFIXES:
        return value
    if preserve_numeric and _CSV_NUMERIC_LITERAL.fullmatch(candidate):
        try:
            if math.isfinite(float(candidate)):
                return value
        except (ValueError, OverflowError):
            pass
    return f"'{value}"


def _secure_root(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise TabularXGBoostInferenceError("Trusted root does not exist or cannot be resolved.") from exc
    if not resolved.is_dir():
        raise TabularXGBoostInferenceError("Trusted root must be a directory.")
    return resolved


def _lexical_under(root: Path, candidate: Path, label: str) -> Path:
    combined = candidate if candidate.is_absolute() else root / candidate
    lexical = Path(os.path.abspath(os.fspath(combined)))
    try:
        relative = lexical.relative_to(root)
    except ValueError as exc:
        raise TabularXGBoostInferenceError(f"{label} must remain inside the trusted root.") from exc

    current = root
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise TabularXGBoostInferenceError(f"{label} cannot traverse symbolic links.")
    return lexical


def _secure_existing_dir(root: Path, candidate: Path, label: str) -> Path:
    lexical = _lexical_under(root, candidate, label)
    try:
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise TabularXGBoostInferenceError(f"{label} does not exist inside the trusted root.") from exc
    if not resolved.is_dir():
        raise TabularXGBoostInferenceError(f"{label} must be a directory.")
    return resolved


def _secure_existing_file(
    root: Path,
    candidate: Path,
    *,
    label: str,
    allowed_suffixes: set[str],
    max_bytes: int,
) -> Path:
    lexical = _lexical_under(root, candidate, label)
    try:
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise TabularXGBoostInferenceError(f"{label} does not exist inside the trusted root.") from exc
    if not resolved.is_file():
        raise TabularXGBoostInferenceError(f"{label} must be a file.")
    if resolved.suffix.lower() not in allowed_suffixes:
        raise TabularXGBoostInferenceError(f"{label} has an unsupported file type.")
    try:
        size = resolved.stat().st_size
    except OSError as exc:
        raise TabularXGBoostInferenceError(f"{label} metadata cannot be read.") from exc
    if size <= 0 or size > max_bytes:
        raise TabularXGBoostInferenceError(f"{label} is empty or exceeds the safe size limit.")
    return resolved


def _secure_output_file(
    root: Path,
    candidate: Path,
    *,
    allowed_suffixes: set[str],
    overwrite: bool,
) -> Path:
    lexical = _lexical_under(root, candidate, "Output CSV")
    if lexical.suffix.lower() not in allowed_suffixes:
        raise TabularXGBoostInferenceError("Output CSV has an unsupported file type.")
    parent = _secure_existing_dir(root, lexical.parent, "Output directory")
    resolved = parent / lexical.name
    if resolved.exists():
        if resolved.is_symlink() or not resolved.is_file():
            raise TabularXGBoostInferenceError("Output CSV must be a regular file path.")
        if not overwrite:
            raise TabularXGBoostInferenceError("Output CSV already exists; explicit overwrite is required.")
    return resolved


def _load_json_object(path: Path, label: str) -> Dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"Invalid JSON number: {value}")

    def reject_duplicates(pairs: Iterable[tuple[str, Any]]) -> Dict[str, Any]:
        output: Dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError(f"Duplicate JSON key: {key}")
            output[key] = value
        return output

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8-sig"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise TabularXGBoostInferenceError(f"{label} is not valid, unambiguous UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise TabularXGBoostInferenceError(f"{label} JSON root must be an object.")
    return payload


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise TabularXGBoostInferenceError(f"{label} must be numeric.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TabularXGBoostInferenceError(f"{label} must be numeric.") from exc
    if not math.isfinite(number):
        raise TabularXGBoostInferenceError(f"{label} must be finite.")
    return number


def _file_signature(path: Path) -> tuple[int, int, int]:
    try:
        stat = path.stat()
    except OSError as exc:
        raise TabularXGBoostInferenceError("XGBoost model metadata cannot be read.") from exc
    return stat.st_size, stat.st_mtime_ns, getattr(stat, "st_ino", 0)
