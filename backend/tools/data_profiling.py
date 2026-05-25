"""ydata-profiling integration as an MCP tool."""
from __future__ import annotations

import time
from typing import Any

import pandas as pd

from core.config import settings
from core.paths import resolve_upload_file


def _top_correlations(df: pd.DataFrame, k: int = 10) -> list[dict[str, Any]]:
    numeric = df.select_dtypes(include="number")
    if numeric.shape[1] < 2:
        return []
    corr = numeric.corr(numeric_only=True).abs()
    pairs = []
    cols = corr.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            pairs.append((cols[i], cols[j], float(corr.iloc[i, j])))
    pairs.sort(key=lambda x: x[2], reverse=True)
    return [
        {"feature_a": a, "feature_b": b, "abs_correlation": round(c, 4)}
        for a, b, c in pairs[:k]
    ]


def run_data_profiling_sync(file_path: str) -> dict[str, Any]:
    """Synchronous core. Called by the async MCP tool wrapper (which reports progress)."""
    from ydata_profiling import ProfileReport  # heavy import, defer

    path = resolve_upload_file(file_path)
    df = pd.read_csv(path)

    profile = ProfileReport(
        df,
        title=f"Data Profile — {path.name}",
        minimal=True,
        explorative=False,
        progress_bar=False,
        correlations={"auto": {"calculate": True}},
    )

    ts = int(time.time())
    stem = path.stem.replace(" ", "_")
    report_name = f"profile_{stem}_{ts}.html"
    report_path = settings.reports_path / report_name
    profile.to_file(report_path)

    missing_per_col = {col: int(v) for col, v in df.isna().sum().items() if v > 0}
    return {
        "file": path.name,
        "shape": {"rows": int(df.shape[0]), "columns": int(df.shape[1])},
        "duplicate_rows": int(df.duplicated().sum()),
        "missing_total": int(df.isna().sum().sum()),
        "missing_per_column": missing_per_col,
        "numeric_columns": df.select_dtypes(include="number").columns.tolist(),
        "categorical_columns": df.select_dtypes(
            include=["object", "category", "bool"]
        ).columns.tolist(),
        "top_correlations": _top_correlations(df),
        "report_file": report_name,
        "report_url": f"/static/reports/{report_name}",
    }