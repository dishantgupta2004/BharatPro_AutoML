"""NSK AI Labs BharatPro AutoML — Exploratory Data Analysis (in-process MCP server)."""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from fastmcp import Context, FastMCP

from core.config import settings
from core.paths import resolve_dataset_for_user
from core.storage import upload_artifact

SERVICE_NAME = "mcp-eda"

logging.basicConfig(
    stream=sys.stderr, level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | mcp_eda | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(SERVICE_NAME)

mcp = FastMCP(name=SERVICE_NAME)


def _require_user(user_id: str) -> str:
    if not user_id:
        raise PermissionError("Missing _user_id in tool call context")
    return user_id


def _tmp_workspace(user_id: str) -> Path:
    p = settings.tmp_path / user_id / "eda"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_df(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        return pd.read_csv(path, sep=("\t" if suffix == ".tsv" else ","))
    if suffix == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported format: {suffix}")


def _numeric_stats(df: pd.DataFrame) -> list[dict[str, Any]]:
    num = df.select_dtypes(include="number")
    rows = []
    for col in num.columns:
        s = num[col].dropna()
        if len(s) == 0:
            continue
        q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
        iqr = q3 - q1
        rows.append({
            "column": col,
            "count": int(s.count()),
            "missing": int(df[col].isna().sum()),
            "mean": round(float(s.mean()), 4),
            "std": round(float(s.std()), 4),
            "min": float(s.min()),
            "q25": q1, "median": float(s.median()), "q75": q3,
            "max": float(s.max()),
            "iqr": round(iqr, 4),
            "skewness": round(float(s.skew()), 4),
            "outliers_iqr": int(((s < (q1 - 1.5 * iqr)) | (s > (q3 + 1.5 * iqr))).sum()),
        })
    return rows


def _categorical_stats(df: pd.DataFrame) -> list[dict[str, Any]]:
    cat = df.select_dtypes(include=["object", "category", "bool"])
    rows = []
    for col in cat.columns:
        s = df[col]
        vc = s.value_counts(dropna=True)
        rows.append({
            "column": col,
            "count": int(s.count()),
            "missing": int(s.isna().sum()),
            "unique": int(s.nunique(dropna=True)),
            "top_value": str(vc.index[0]) if len(vc) else None,
            "top_freq": int(vc.iloc[0]) if len(vc) else None,
            "top_5": [str(v) for v in vc.index[:5].tolist()],
        })
    return rows


def _save_correlation_png(df: pd.DataFrame, workspace: Path, ts: int) -> Path | None:
    num = df.select_dtypes(include="number")
    if num.shape[1] < 2:
        return None
    fig, ax = plt.subplots(figsize=(max(6, num.shape[1] * 0.6), max(5, num.shape[1] * 0.55)))
    corr = num.corr()
    im = ax.imshow(corr.values, cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr.columns)))
    ax.set_yticks(range(len(corr.columns)))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(corr.columns, fontsize=8)
    for i in range(len(corr)):
        for j in range(len(corr.columns)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=6)
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    ax.set_title("Correlation Matrix", fontsize=12, fontweight="bold")
    fig.tight_layout()
    path = workspace / f"correlation_{ts}.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


def _save_distributions_png(df: pd.DataFrame, workspace: Path, ts: int) -> Path | None:
    num = df.select_dtypes(include="number")
    cols = num.columns.tolist()[:12]
    if not cols:
        return None
    ncols = min(3, len(cols))
    nrows = (len(cols) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 4, nrows * 3))
    axes_flat = np.array(axes).flatten() if nrows * ncols > 1 else [axes]
    for i, col in enumerate(cols):
        ax = axes_flat[i]
        s = num[col].dropna()
        ax.hist(s, bins=min(30, max(5, len(s) // 20)), color="#6366f1", edgecolor="none", alpha=0.8)
        ax.set_title(col, fontsize=9, fontweight="bold")
        ax.tick_params(labelsize=7)
    for j in range(len(cols), len(axes_flat)):
        axes_flat[j].set_visible(False)
    fig.suptitle("Feature Distributions", fontsize=12, fontweight="bold")
    fig.tight_layout()
    path = workspace / f"distributions_{ts}.png"
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return path


def _save_missing_png(df: pd.DataFrame, workspace: Path, ts: int) -> Path | None:
    missing = df.isna().mean().sort_values(ascending=False)
    missing = missing[missing > 0]
    if missing.empty:
        return None
    fig, ax = plt.subplots(figsize=(8, max(3, len(missing) * 0.35)))
    ax.barh(missing.index.tolist(), missing.values * 100, color="#f59e0b", edgecolor="none")
    ax.set_xlabel("% Missing")
    ax.set_title("Missing Values by Column", fontsize=11, fontweight="bold")
    ax.tick_params(axis="y", labelsize=8)
    fig.tight_layout()
    path = workspace / f"missing_{ts}.png"
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return path


# ── MCP tools ────────────────────────────────────────────────────
@mcp.tool
async def run_full_eda(
    file_path: str,
    _user_id: str = "",
    _conversation_id: str | None = None,
    target_column: str | None = None,
) -> dict[str, Any]:
    """Run a comprehensive EDA: statistics, missing values, correlations, and distribution charts.
    Uploads all chart artifacts and returns signed URLs.

    Args:
        file_path: Filename or UUID of an uploaded dataset.
        target_column: Optional target column name for extra target analysis.
    """
    user_id = _require_user(_user_id)
    path = resolve_dataset_for_user(user_id, file_path)
    df = _load_df(path)
    workspace = _tmp_workspace(user_id)
    ts = int(time.time())

    num_stats = _numeric_stats(df)
    cat_stats = _categorical_stats(df)

    missing_counts = df.isna().sum()
    missing_pct = (df.isna().mean() * 100).round(2)
    missing_summary = {
        col: {"count": int(missing_counts[col]), "pct": float(missing_pct[col])}
        for col in df.columns if missing_counts[col] > 0
    }
    total_missing_pct = round(float(df.isna().mean().mean() * 100), 2)

    artifacts: list[dict[str, Any]] = []

    corr_path = _save_correlation_png(df, workspace, ts)
    if corr_path:
        corr_artifact = upload_artifact(
            user_id=user_id, bucket=settings.BUCKET_PLOTS,
            local_path=corr_path, kind="plot",
            conversation_id=_conversation_id,
            metadata={"chart_type": "correlation_matrix", "dataset": path.name},
        )
        corr_path.unlink(missing_ok=True)
        artifacts.append({
            "type": "correlation_matrix",
            "artifact_id": corr_artifact.id,
            "plot_url": corr_artifact.signed_url,
            "markdown_embed": f"![Correlation Matrix]({corr_artifact.signed_url})",
        })

    dist_path = _save_distributions_png(df, workspace, ts)
    if dist_path:
        dist_artifact = upload_artifact(
            user_id=user_id, bucket=settings.BUCKET_PLOTS,
            local_path=dist_path, kind="plot",
            conversation_id=_conversation_id,
            metadata={"chart_type": "distributions", "dataset": path.name},
        )
        dist_path.unlink(missing_ok=True)
        artifacts.append({
            "type": "distributions",
            "artifact_id": dist_artifact.id,
            "plot_url": dist_artifact.signed_url,
            "markdown_embed": f"![Distributions]({dist_artifact.signed_url})",
        })

    missing_path = _save_missing_png(df, workspace, ts)
    if missing_path:
        miss_artifact = upload_artifact(
            user_id=user_id, bucket=settings.BUCKET_PLOTS,
            local_path=missing_path, kind="plot",
            conversation_id=_conversation_id,
            metadata={"chart_type": "missing_values", "dataset": path.name},
        )
        missing_path.unlink(missing_ok=True)
        artifacts.append({
            "type": "missing_values",
            "artifact_id": miss_artifact.id,
            "plot_url": miss_artifact.signed_url,
            "markdown_embed": f"![Missing Values]({miss_artifact.signed_url})",
        })

    target_info: dict[str, Any] | None = None
    if target_column and target_column in df.columns:
        s = df[target_column]
        vc = s.value_counts(dropna=True)
        target_info = {
            "column": target_column,
            "dtype": str(s.dtype),
            "unique": int(s.nunique(dropna=True)),
            "missing": int(s.isna().sum()),
            "value_counts": {str(k): int(v) for k, v in vc.head(20).items()},
            "problem_hint": (
                "classification" if (not pd.api.types.is_numeric_dtype(s) or s.nunique() <= 20)
                else "regression"
            ),
        }

    return {
        "file": path.name,
        "shape": {"rows": int(df.shape[0]), "columns": int(df.shape[1])},
        "total_missing_pct": total_missing_pct,
        "duplicate_rows": int(df.duplicated().sum()),
        "numeric_columns": len(df.select_dtypes(include="number").columns),
        "categorical_columns": len(df.select_dtypes(include=["object", "category", "bool"]).columns),
        "numeric_stats": num_stats,
        "categorical_stats": cat_stats,
        "missing_summary": missing_summary,
        "target_analysis": target_info,
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
    }


@mcp.tool
async def render_correlation_matrix(
    file_path: str,
    _user_id: str = "",
    _conversation_id: str | None = None,
    method: str = "pearson",
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Render a standalone correlation matrix heatmap for numeric columns.

    Args:
        file_path: Filename or UUID of an uploaded dataset.
        method: Correlation method — 'pearson', 'spearman', or 'kendall'.
    """
    user_id = _require_user(_user_id)
    if method not in {"pearson", "spearman", "kendall"}:
        return {"error": f"Invalid method '{method}'. Use pearson, spearman, or kendall."}

    path = resolve_dataset_for_user(user_id, file_path)
    df = _load_df(path)
    num = df.select_dtypes(include="number")
    if num.shape[1] < 2:
        return {"error": "Need at least 2 numeric columns to compute a correlation matrix."}

    corr = num.corr(method=method)
    ts = int(time.time())
    workspace = _tmp_workspace(user_id)

    n = len(corr.columns)
    fig, ax = plt.subplots(figsize=(max(6, n * 0.65), max(5, n * 0.6)))
    im = ax.imshow(corr.values, cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(corr.columns, fontsize=8)
    for i in range(n):
        for j in range(n):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=6)
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    ax.set_title(f"Correlation Matrix ({method.capitalize()})", fontsize=12, fontweight="bold")
    fig.tight_layout()

    png_path = workspace / f"corr_{method}_{ts}.png"
    fig.savefig(png_path, dpi=130, bbox_inches="tight")
    plt.close(fig)

    artifact = upload_artifact(
        user_id=user_id, bucket=settings.BUCKET_PLOTS,
        local_path=png_path, kind="plot",
        conversation_id=_conversation_id,
        metadata={"chart_type": "correlation_matrix", "method": method, "dataset": path.name},
    )
    png_path.unlink(missing_ok=True)

    pairs = []
    for i, c1 in enumerate(corr.columns):
        for j, c2 in enumerate(corr.columns):
            if i < j:
                v = float(corr.iloc[i, j])
                if abs(v) >= 0.6:
                    pairs.append({"col1": c1, "col2": c2, "correlation": round(v, 4)})
    pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)

    return {
        "file": path.name,
        "method": method,
        "columns": corr.columns.tolist(),
        "artifact_id": artifact.id,
        "plot_url": artifact.signed_url,
        "markdown_embed": f"![Correlation Matrix ({method})]({artifact.signed_url})",
        "strong_correlations": pairs[:10],
    }


# ── MCP prompt ────────────────────────────────────────────────────
@mcp.prompt
def eda_deep_dive(file_path: str, target_column: str = "") -> str:
    """Multi-step EDA prompt: profile, visualise, and recommend next steps."""
    target_part = (
        f"The target column is `{target_column}`. Include target distribution analysis. "
        if target_column else "No target column specified — skip target analysis. "
    )
    return (
        f"Run a full exploratory data analysis on `{file_path}`. "
        f"{target_part}"
        "Steps: 1) call run_full_eda to get statistics and upload charts, "
        "2) call render_correlation_matrix for a standalone heatmap, "
        "3) summarise key findings: missing values, skewed features, strong correlations, "
        "outlier columns, and recommend feature-engineering actions before training."
    )
