from __future__ import annotations

from typing import Any

import pandas as pd

from core.config import settings
from core.paths import resolve_upload_file


def _read_csv(path) -> pd.DataFrame:
    return pd.read_csv(path)


def analyze_csv_head(file_path: str, n_rows: int = 5) -> dict[str, Any]:
    path = resolve_upload_file(file_path)
    df = _read_csv(path)
    head_df = df.head(n_rows)
    head_records = head_df.where(pd.notna(head_df), None).to_dict(orient="records")
    return {
        "file": path.name,
        "shape": {"rows": int(df.shape[0]), "columns": int(df.shape[1])},
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "head_rows": head_records,
        "n_rows_returned": len(head_records),
    }


def get_dataset_info(file_path: str) -> dict[str, Any]:
    path = resolve_upload_file(file_path)
    df = _read_csv(path)
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = df.select_dtypes(include=["object", "category", "bool"]).columns.tolist()
    datetime_cols = df.select_dtypes(include="datetime").columns.tolist()
    missing_counts = df.isna().sum().to_dict()
    return {
        "file": path.name,
        "shape": {"rows": int(df.shape[0]), "columns": int(df.shape[1])},
        "memory_kb": round(df.memory_usage(deep=True).sum() / 1024, 2),
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "numeric_columns": numeric_cols,
        "categorical_columns": categorical_cols,
        "datetime_columns": datetime_cols,
        "missing_values": {col: int(val) for col, val in missing_counts.items() if val > 0},
        "missing_total": int(df.isna().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
    }


def list_uploaded_files() -> dict[str, Any]:
    upload_dir = settings.upload_path
    files = []
    for entry in sorted(upload_dir.iterdir()):
        if entry.is_file() and entry.suffix.lower() in {".csv", ".tsv"}:
            stat = entry.stat()
            files.append(
                {
                    "filename": entry.name,
                    "size_kb": round(stat.st_size / 1024, 2),
                    "modified_unix": int(stat.st_mtime),
                }
            )
    return {"upload_dir": str(upload_dir), "count": len(files), "files": files}


def detect_problem_type(file_path: str, target_column: str) -> dict[str, Any]:
    path = resolve_upload_file(file_path)
    df = _read_csv(path)
    if target_column not in df.columns:
        raise ValueError(
            f"Target column '{target_column}' not found. Available: {list(df.columns)}"
        )
    target = df[target_column].dropna()
    unique = target.nunique()
    is_numeric = pd.api.types.is_numeric_dtype(target)
    if not is_numeric:
        problem = "classification"
    elif unique <= max(20, int(len(target) * 0.05)):
        problem = "classification"
    else:
        problem = "regression"
    return {
        "target_column": target_column,
        "problem_type": problem,
        "unique_values": int(unique),
        "is_numeric": bool(is_numeric),
        "sample_values": [str(v) for v in target.head(5).tolist()],
    }
