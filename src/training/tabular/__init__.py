"""Row-level tabular training data contracts.

This package is intentionally independent from ``src.training.rnn``.  Tabular
rows must never be converted into sequence windows as a side effect of loading
them.
"""

from src.training.tabular.dataset import (
    TABULAR_DATASET_SCHEMA_VERSION,
    TabularDatasetError,
    load_csv_tabular_dataset,
    write_preprocess_artifacts,
)

__all__ = [
    "TABULAR_DATASET_SCHEMA_VERSION",
    "TabularDatasetError",
    "load_csv_tabular_dataset",
    "write_preprocess_artifacts",
]
