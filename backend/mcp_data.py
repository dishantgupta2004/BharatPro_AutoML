"""Unisole Empower — Data Ingestion & Schema (in-process MCP server)."""
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

from core.paths import resolve_dataset_for_user
from core.storage import list_datasets

SERVICE_NAME = "mcp-data"

logging.basicConfig(
    stream=sys.stderr, level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | mcp_data | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(SERVICE_NAME)

mcp = FastMCP(name=SERVICE_NAME)


def _pop_user(user_id: str | None) -> str:
    if not user_id:
        raise PermissionError("Missing _user_id in tool call context")
    return user_id


def _load_df(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        return pd.read_csv(path, sep=("\t" if suffix == ".tsv" else ","))
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".json", ".jsonl"}:
        return pd.read_json(path, lines=suffix == ".jsonl")
    raise ValueError(f"Unsupported file format: {suffix}")


def _infer_rules(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
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
                rule["allowed_categories"] = sorted(
                    {str(v) for v in s.dropna().unique().tolist()[:20]}
                )
        rules[str(col)] = rule
    return rules


def _build_schema(rules: dict[str, dict[str, Any]]) -> pa.DataFrameSchema:
    columns: dict[str, pa.Column] = {}
    for col, rule in rules.items():
        dtype = rule.get("dtype", "object")
        checks: list[pa.Check] = []
        if "min" in rule and "max" in rule:
            checks.append(pa.Check.in_range(rule["min"], rule["max"]))
        if "allowed_categories" in rule and rule["allowed_categories"]:
            checks.append(pa.Check.isin(rule["allowed_categories"]))
        pandera_dtype: Any = object
        try:
            if "int" in dtype: pandera_dtype = int
            elif "float" in dtype: pandera_dtype = float
            elif "bool" in dtype: pandera_dtype = bool
            elif "datetime" in dtype: pandera_dtype = "datetime64[ns]"
        except Exception:
            pandera_dtype = object
        columns[col] = pa.Column(
            pandera_dtype, checks=checks,
            nullable=bool(rule.get("nullable", True)), coerce=True,
        )
    return pa.DataFrameSchema(columns=columns, strict=False, coerce=True)


# ── MCP tools ────────────────────────────────────────────────────
@mcp.tool
def list_uploaded_files(user_id: str):
    """List all datasets the user has uploaded."""
    rows = list_datasets(user_id)
    items = [
        {
            "filename": r["filename"],
            "dataset_id": r["id"],
            "size_kb": round((r.get("size_bytes") or 0) / 1024, 2),
            "rows": r.get("row_count"),
            "columns": r.get("column_count"),
            "created_at": r.get("created_at"),
        }
        for r in rows
    ]
    return {"count": len(items), "files": items}


@mcp.tool
def ingest_dataset(file_path: str, user_id: str, n_preview_rows: int = 5) -> dict[str, Any]:
    """Load a dataset, return shape, dtypes, and head preview.

    Args:
        file_path: Filename or UUID of an uploaded dataset.
        user_id: The ID of the user uploading the dataset.
        n_preview_rows: Head rows to return (capped at 100).
    """
    path = resolve_dataset_for_user(user_id, file_path)
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
    user_id: str,
    expected_columns: list[str] | None = None,
    strict_dtypes: bool = False
) -> dict[str, Any]:
    """Validate a dataset against an auto-inferred pandera DataFrameSchema."""
    path = resolve_dataset_for_user(user_id, file_path)
    df = _load_df(path)

    if expected_columns:
        missing = [c for c in expected_columns if c not in df.columns]
        if missing:
            return {
                "file": path.name, "valid": False, "fatal": True,
                "error": f"Required columns missing: {missing}",
                "available_columns": list(df.columns),
            }

    rules = _infer_rules(df)
    schema = _build_schema(rules)

    failure_cases: list[dict[str, Any]] = []
    valid = True
    try:
        schema.validate(df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        valid = False
        try:
            for _, row in exc.failure_cases.head(50).iterrows():
                failure_cases.append({
                    "column": str(row.get("column")) if row.get("column") is not None else None,
                    "check": str(row.get("check")),
                    "failure_case": str(row.get("failure_case")),
                    "index": int(row["index"]) if pd.notna(row.get("index")) else None,
                })
        except Exception as inner:
            log.warning("Could not enumerate pandera failures: %s", inner)

    return {
        "file": path.name, "valid": valid,
        "row_count": int(df.shape[0]), "column_count": int(df.shape[1]),
        "rules": rules, "failure_cases": failure_cases,
        "strict_dtypes": strict_dtypes,
    }


# ── MCP resource ─────────────────────────────────────────────────
# NOTE: Resources don't receive per-request kwargs in fastmcp the same way tools
# do. To keep this Phase C, we look up by filename in a *global* context — and
# in main.py we expose a parallel REST endpoint `/api/datasets/{id}/schema`
# that uses the authenticated user. The MCP resource here remains for
# anonymous/admin introspection only; the schema is also available via the
# `validate_schema_with_pandera` tool which IS per-user.
@mcp.resource("dataset://{dataset_name}/schema")
def dataset_schema_resource(dataset_name: str) -> str:
    """DEPRECATED for v1 (no user context in MCP resources). Use the
    `validate_schema_with_pandera` tool instead — it is per-user."""
    return json.dumps({
        "warning": (
            "MCP resources don't carry user context in this version. "
            "Call validate_schema_with_pandera(file_path='...') instead."
        ),
        "dataset_name": dataset_name,
        "generated_at": int(time.time()),
    })