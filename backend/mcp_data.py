"""Unisole Empower — Data Ingestion & Schema Microservice (Port 8001)

Responsibilities:
  - Ingest CSV/TSV/Parquet datasets into the shared workspace.
  - Validate dataframes against a pandera schema spec.
  - Expose a native MCP **Resource** at `dataset://{dataset_name}/schema`
    that the LLM can read without invoking a tool call.

Transport: streamable-http on http://127.0.0.1:8001/mcp
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import pandera.pandas as pa
from fastmcp import FastMCP

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
SERVICE_NAME = "mcp-data"
SERVICE_PORT = 8001
BACKEND_ROOT = Path(__file__).resolve().parent
UPLOAD_DIR = (BACKEND_ROOT / "uploads").resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | mcp_data | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(SERVICE_NAME)

mcp = FastMCP(name=SERVICE_NAME)


# ----------------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------------
def _resolve(file_path: str) -> Path:
    """Strict path resolver — refuses anything outside upload dir."""
    if not file_path:
        raise ValueError("file_path must be a non-empty string")
    raw = Path(file_path)
    candidate = (raw if raw.is_absolute() else (UPLOAD_DIR / raw.name)).resolve()
    try:
        candidate.relative_to(UPLOAD_DIR)
    except ValueError as exc:
        raise ValueError(f"Refusing path outside upload dir: {candidate}") from exc
    if not candidate.exists():
        raise FileNotFoundError(f"Not found: {candidate}")
    return candidate


def _load_df(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        sep = "\t" if suffix == ".tsv" else ","
        return pd.read_csv(path, sep=sep)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".json", ".jsonl"}:
        return pd.read_json(path, lines=suffix == ".jsonl")
    raise ValueError(f"Unsupported file format: {suffix}")


def _infer_pandera_rules(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Build a per-column pandera-style rule descriptor."""
    rules: dict[str, dict[str, Any]] = {}
    for col in df.columns:
        s = df[col]
        rule: dict[str, Any] = {
            "dtype": str(s.dtype),
            "nullable": bool(s.isna().any()),
            "unique_count": int(s.nunique(dropna=True)),
        }
        if pd.api.types.is_numeric_dtype(s):
            non_null = s.dropna()
            if len(non_null):
                rule["min"] = float(non_null.min())
                rule["max"] = float(non_null.max())
                rule["mean"] = float(non_null.mean())
                rule["check"] = "in_range(min, max)"
        elif pd.api.types.is_string_dtype(s) or s.dtype == object:
            sample = s.dropna().astype(str).head(50).tolist()
            rule["sample_values"] = sample[:5]
            if rule["unique_count"] <= 20:
                rule["check"] = "isin(allowed_categories)"
                rule["allowed_categories"] = sorted({str(v) for v in non_unique_values(s)})
        rules[str(col)] = rule
    return rules


def non_unique_values(s: pd.Series) -> list[Any]:
    """Return up to 20 distinct values for a categorical-like column."""
    return s.dropna().unique().tolist()[:20]


def _build_pandera_schema(rules: dict[str, dict[str, Any]]) -> pa.DataFrameSchema:
    """Convert the inferred rules into a real pandera DataFrameSchema."""
    columns: dict[str, pa.Column] = {}
    for col, rule in rules.items():
        dtype = rule.get("dtype", "object")
        nullable = bool(rule.get("nullable", True))
        checks: list[pa.Check] = []
        if "min" in rule and "max" in rule:
            checks.append(pa.Check.in_range(rule["min"], rule["max"]))
        if "allowed_categories" in rule and rule["allowed_categories"]:
            checks.append(pa.Check.isin(rule["allowed_categories"]))
        pandera_dtype: Any = object
        try:
            if "int" in dtype:
                pandera_dtype = int
            elif "float" in dtype:
                pandera_dtype = float
            elif "bool" in dtype:
                pandera_dtype = bool
            elif "datetime" in dtype:
                pandera_dtype = "datetime64[ns]"
        except Exception:
            pandera_dtype = object
        columns[col] = pa.Column(
            pandera_dtype, checks=checks, nullable=nullable, coerce=True
        )
    return pa.DataFrameSchema(columns=columns, strict=False, coerce=True)


# ----------------------------------------------------------------------------
# MCP Tools
# ----------------------------------------------------------------------------
@mcp.tool
def list_uploaded_files() -> dict[str, Any]:
    """Return all datasets currently available in the shared upload folder."""
    items = []
    for entry in sorted(UPLOAD_DIR.iterdir()):
        if entry.is_file() and entry.suffix.lower() in {".csv", ".tsv", ".parquet", ".json", ".jsonl"}:
            st = entry.stat()
            items.append(
                {
                    "filename": entry.name,
                    "size_kb": round(st.st_size / 1024, 2),
                    "modified_unix": int(st.st_mtime),
                }
            )
    return {"upload_dir": str(UPLOAD_DIR), "count": len(items), "files": items}


@mcp.tool
def ingest_dataset(file_path: str, n_preview_rows: int = 5) -> dict[str, Any]:
    """Load a dataset from disk, return shape, dtypes, and head preview.

    Args:
        file_path: Name (or absolute path) of an uploaded file.
        n_preview_rows: Number of head rows to return (capped at 100).
    """
    path = _resolve(file_path)
    df = _load_df(path)
    n = max(1, min(int(n_preview_rows), 100))
    head_df = df.head(n)
    head_records = head_df.where(pd.notna(head_df), None).to_dict(orient="records")
    return {
        "file": path.name,
        "format": path.suffix.lower().lstrip("."),
        "shape": {"rows": int(df.shape[0]), "columns": int(df.shape[1])},
        "memory_kb": round(df.memory_usage(deep=True).sum() / 1024, 2),
        "columns": list(df.columns),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "head_rows": head_records,
        "missing_total": int(df.isna().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
    }


@mcp.tool
def validate_schema_with_pandera(
    file_path: str,
    expected_columns: list[str] | None = None,
    strict_dtypes: bool = False,
) -> dict[str, Any]:
    """Validate a dataset against an auto-inferred pandera DataFrameSchema.

    Performs a `lazy=True` validation so all violations are returned at once.

    Args:
        file_path: Filename of an uploaded dataset.
        expected_columns: Optional whitelist — fail if missing.
        strict_dtypes: When true, fail on any dtype coercion.
    """
    path = _resolve(file_path)
    df = _load_df(path)

    if expected_columns:
        missing = [c for c in expected_columns if c not in df.columns]
        if missing:
            return {
                "file": path.name,
                "valid": False,
                "fatal": True,
                "error": f"Required columns missing: {missing}",
                "available_columns": list(df.columns),
            }

    rules = _infer_pandera_rules(df)
    schema = _build_pandera_schema(rules)

    failure_cases: list[dict[str, Any]] = []
    valid = True
    try:
        schema.validate(df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        valid = False
        # Pandera returns a failure_cases dataframe
        try:
            for _, row in exc.failure_cases.head(50).iterrows():
                failure_cases.append(
                    {
                        "column": str(row.get("column")) if row.get("column") is not None else None,
                        "check": str(row.get("check")),
                        "failure_case": str(row.get("failure_case")),
                        "index": int(row["index"]) if pd.notna(row.get("index")) else None,
                    }
                )
        except Exception as inner:
            log.warning("Could not enumerate pandera failures: %s", inner)

    return {
        "file": path.name,
        "valid": valid,
        "row_count": int(df.shape[0]),
        "column_count": int(df.shape[1]),
        "rules": rules,
        "failure_cases": failure_cases,
        "strict_dtypes": strict_dtypes,
    }


# ----------------------------------------------------------------------------
# MCP Resource — `dataset://{dataset_name}/schema`
# ----------------------------------------------------------------------------
@mcp.resource("dataset://{dataset_name}/schema")
def dataset_schema_resource(dataset_name: str) -> str:
    """Return a structured Markdown+JSON schema breakdown for the given dataset.

    The LLM can subscribe to this URI without making a tool call — useful
    for richly-grounded reasoning during system-prompt context loading.
    """
    try:
        path = _resolve(dataset_name)
    except (FileNotFoundError, ValueError) as exc:
        return json.dumps({"error": str(exc), "dataset_name": dataset_name})

    df = _load_df(path)
    rules = _infer_pandera_rules(df)
    null_counts = {col: int(df[col].isna().sum()) for col in df.columns}

    payload = {
        "dataset": path.name,
        "generated_at": int(time.time()),
        "shape": {"rows": int(df.shape[0]), "columns": int(df.shape[1])},
        "schema": [
            {
                "column": col,
                "dtype": rules[col]["dtype"],
                "nullable": rules[col]["nullable"],
                "unique_count": rules[col]["unique_count"],
                "null_count": null_counts[col],
                "pandera_check": rules[col].get("check"),
                "min": rules[col].get("min"),
                "max": rules[col].get("max"),
                "mean": rules[col].get("mean"),
                "sample_values": rules[col].get("sample_values"),
            }
            for col in df.columns
        ],
    }

    md_lines: list[str] = [
        f"# Schema — `{path.name}`",
        "",
        f"- **Rows:** {payload['shape']['rows']:,}",
        f"- **Columns:** {payload['shape']['columns']}",
        "",
        "## Columns",
        "",
        "| Column | Dtype | Nullable | Unique | Nulls | Pandera Rule |",
        "|---|---|---|---|---|---|",
    ]
    for entry in payload["schema"]:
        md_lines.append(
            f"| `{entry['column']}` | {entry['dtype']} | {entry['nullable']} | "
            f"{entry['unique_count']} | {entry['null_count']} | "
            f"{entry.get('pandera_check') or '—'} |"
        )

    return json.dumps(
        {
            "markdown": "\n".join(md_lines),
            "json": payload,
        },
        default=str,
    )


# ----------------------------------------------------------------------------
# Entrypoint
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    log.info("Starting %s on http://127.0.0.1:%d/mcp", SERVICE_NAME, SERVICE_PORT)
    mcp.run(transport="streamable-http", host="127.0.0.1", port=SERVICE_PORT)