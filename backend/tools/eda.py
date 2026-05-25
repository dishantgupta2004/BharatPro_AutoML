from __future__ import annotations

import time
from typing import Any

import pandas as pd

from core.paths import output_file_path, resolve_upload_file


def _safe_describe(df: pd.DataFrame) -> dict[str, Any]:
    desc = df.describe(include="all").transpose()
    desc = desc.where(pd.notna(desc), None)
    out: dict[str, Any] = {}
    for col, row in desc.iterrows():
        out[str(col)] = {k: (v if not isinstance(v, float) or v == v else None) for k, v in row.to_dict().items()}
    return out


def _correlations(df: pd.DataFrame, top_k: int = 10) -> list[dict[str, Any]]:
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
    return [{"feature_a": a, "feature_b": b, "abs_correlation": round(c, 4)} for a, b, c in pairs[:top_k]]


def _top_value_counts(df: pd.DataFrame, max_cols: int = 8, top_n: int = 5) -> dict[str, list[dict[str, Any]]]:
    cat_cols = df.select_dtypes(include=["object", "category", "bool"]).columns.tolist()[:max_cols]
    out: dict[str, list[dict[str, Any]]] = {}
    for col in cat_cols:
        vc = df[col].value_counts(dropna=False).head(top_n)
        out[col] = [{"value": str(idx), "count": int(val)} for idx, val in vc.items()]
    return out


def _render_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Exploratory Data Analysis Report")
    lines.append("")
    lines.append(f"**File:** `{summary['file']}`  ")
    lines.append(f"**Rows:** {summary['shape']['rows']:,}  ")
    lines.append(f"**Columns:** {summary['shape']['columns']}  ")
    lines.append(f"**Duplicates:** {summary['duplicate_rows']}  ")
    lines.append("")

    lines.append("## Column Types")
    lines.append("")
    lines.append("| Column | Dtype | Missing |")
    lines.append("|---|---|---|")
    for col, dtype in summary["dtypes"].items():
        miss = summary["missing_values"].get(col, 0)
        lines.append(f"| `{col}` | {dtype} | {miss} |")
    lines.append("")

    if summary["numeric_summary"]:
        lines.append("## Numeric Summary")
        lines.append("")
        lines.append("| Column | mean | std | min | max |")
        lines.append("|---|---|---|---|---|")
        for col, stats in summary["numeric_summary"].items():
            mean = stats.get("mean")
            std = stats.get("std")
            mn = stats.get("min")
            mx = stats.get("max")
            if mean is None:
                continue
            lines.append(
                f"| `{col}` | {mean:.4g} | {std:.4g} | {mn:.4g} | {mx:.4g} |"
                if all(v is not None for v in [mean, std, mn, mx])
                else f"| `{col}` | - | - | - | - |"
            )
        lines.append("")

    if summary["top_correlations"]:
        lines.append("## Top Correlated Feature Pairs")
        lines.append("")
        lines.append("| Feature A | Feature B | |corr| |")
        lines.append("|---|---|---|")
        for pair in summary["top_correlations"]:
            lines.append(f"| `{pair['feature_a']}` | `{pair['feature_b']}` | {pair['abs_correlation']:.4f} |")
        lines.append("")

    if summary["categorical_top_values"]:
        lines.append("## Categorical Value Counts (top 5 per column)")
        lines.append("")
        for col, values in summary["categorical_top_values"].items():
            lines.append(f"### `{col}`")
            lines.append("")
            for v in values:
                lines.append(f"- `{v['value']}` — {v['count']}")
            lines.append("")

    return "\n".join(lines)


def generate_eda_report(file_path: str) -> dict[str, Any]:
    path = resolve_upload_file(file_path)
    df = pd.read_csv(path)

    numeric = df.select_dtypes(include="number")
    numeric_summary: dict[str, Any] = {}
    if numeric.shape[1] > 0:
        for col in numeric.columns:
            s = numeric[col].dropna()
            if len(s) == 0:
                numeric_summary[col] = {"mean": None, "std": None, "min": None, "max": None}
                continue
            numeric_summary[col] = {
                "count": int(s.count()),
                "mean": float(s.mean()),
                "std": float(s.std()) if s.std() == s.std() else 0.0,
                "min": float(s.min()),
                "p25": float(s.quantile(0.25)),
                "p50": float(s.quantile(0.50)),
                "p75": float(s.quantile(0.75)),
                "max": float(s.max()),
            }

    summary = {
        "file": path.name,
        "shape": {"rows": int(df.shape[0]), "columns": int(df.shape[1])},
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "missing_values": {col: int(v) for col, v in df.isna().sum().items() if v > 0},
        "duplicate_rows": int(df.duplicated().sum()),
        "numeric_summary": numeric_summary,
        "top_correlations": _correlations(df),
        "categorical_top_values": _top_value_counts(df),
    }

    stem = path.stem.replace(" ", "_")
    ts = int(time.time())
    report_name = f"eda_{stem}_{ts}.md"
    report_path = output_file_path(report_name)
    report_path.write_text(_render_markdown(summary), encoding="utf-8")

    summary["report_file"] = report_name
    summary["report_path"] = str(report_path)
    return summary
