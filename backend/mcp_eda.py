"""Unisole Empower — EDA Profiling & Visualization Microservice (Port 8002)

Responsibilities:
  - Generate full ydata-profiling HTML reports.
  - Render correlation matrices, distribution plots, missing-value matrices.
  - Expose a native MCP **Prompt** template `eda-deep-dive` that injects
    a multi-step analytical instruction sequence into the LLM context.

Transport: streamable-http on http://127.0.0.1:8002/mcp
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from fastmcp import Context, FastMCP

SERVICE_NAME = "mcp-eda"
SERVICE_PORT = 8002
BACKEND_ROOT = Path(__file__).resolve().parent
UPLOAD_DIR = (BACKEND_ROOT / "uploads").resolve()
REPORTS_DIR = (BACKEND_ROOT / "outputs" / "reports").resolve()
PLOTS_DIR = (BACKEND_ROOT / "outputs" / "plots").resolve()
for d in (UPLOAD_DIR, REPORTS_DIR, PLOTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | mcp_eda | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(SERVICE_NAME)

mcp = FastMCP(name=SERVICE_NAME)


def _resolve(file_path: str) -> Path:
    raw = Path(file_path)
    candidate = (raw if raw.is_absolute() else (UPLOAD_DIR / raw.name)).resolve()
    candidate.relative_to(UPLOAD_DIR)
    if not candidate.exists():
        raise FileNotFoundError(f"Not found: {candidate}")
    return candidate


def _top_correlations(df: pd.DataFrame, k: int = 12) -> list[dict[str, Any]]:
    numeric = df.select_dtypes(include="number")
    if numeric.shape[1] < 2:
        return []
    corr = numeric.corr(numeric_only=True).abs()
    pairs: list[tuple[str, str, float]] = []
    cols = corr.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            pairs.append((cols[i], cols[j], float(corr.iloc[i, j])))
    pairs.sort(key=lambda x: x[2], reverse=True)
    return [
        {"feature_a": a, "feature_b": b, "abs_correlation": round(c, 4)}
        for a, b, c in pairs[:k]
    ]


# ----------------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------------
@mcp.tool
async def generate_eda_report(file_path: str, ctx: Context, minimal: bool = True) -> dict[str, Any]:
    """Build a full ydata-profiling HTML report with progress notifications.

    Args:
        file_path: Filename of an uploaded dataset.
        minimal: When true, use the minimal profile (faster, recommended).
    """
    from ydata_profiling import ProfileReport  # heavy

    path = _resolve(file_path)
    await ctx.info(f"Loading {path.name} for profiling")
    await ctx.report_progress(progress=5, total=100, message="Reading CSV")

    df = pd.read_csv(path) if path.suffix.lower() in {".csv", ".tsv"} else pd.read_parquet(path)
    await ctx.report_progress(progress=25, total=100, message="Computing summary statistics")

    profile = ProfileReport(
        df,
        title=f"Unisole Empower — Profile of {path.name}",
        minimal=minimal,
        explorative=False,
        progress_bar=False,
        correlations={"auto": {"calculate": True}},
    )
    await ctx.report_progress(progress=70, total=100, message="Rendering HTML")

    ts = int(time.time())
    stem = path.stem.replace(" ", "_")
    name = f"profile_{stem}_{ts}.html"
    out_path = REPORTS_DIR / name

    await asyncio.to_thread(profile.to_file, out_path)
    await ctx.report_progress(progress=95, total=100, message="Persisting report")

    missing_per_col = {c: int(v) for c, v in df.isna().sum().items() if v > 0}
    result = {
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
        "report_file": name,
        "report_url": f"/static/reports/{name}",
    }

    await ctx.info(f"Profile complete — {name}")
    await ctx.report_progress(progress=100, total=100, message="Done")
    return result


@mcp.tool
async def render_correlation_matrix(
    file_path: str,
    ctx: Context,
    method: str = "pearson",
    annot: bool = True,
) -> dict[str, Any]:
    """Render an annotated correlation heatmap PNG for the numeric columns.

    Args:
        file_path: Filename of an uploaded dataset.
        method: One of pearson | spearman | kendall.
        annot: Annotate cells with correlation values.
    """
    path = _resolve(file_path)
    df = pd.read_csv(path) if path.suffix.lower() in {".csv", ".tsv"} else pd.read_parquet(path)
    await ctx.info(f"Computing {method} correlations on {path.name}")
    await ctx.report_progress(20, 100, "Selecting numeric columns")

    numeric = df.select_dtypes(include="number")
    if numeric.shape[1] < 2:
        return {
            "file": path.name,
            "error": "Need at least 2 numeric columns to render a correlation matrix.",
        }

    if method not in {"pearson", "spearman", "kendall"}:
        method = "pearson"

    await ctx.report_progress(50, 100, f"Computing {method}")
    corr = numeric.corr(method=method, numeric_only=True)

    sns.set_theme(style="white", context="talk")
    n = corr.shape[1]
    fig, ax = plt.subplots(figsize=(min(1.1 * n + 3, 14), min(1.0 * n + 2, 12)))
    sns.heatmap(
        corr,
        annot=annot,
        fmt=".2f",
        cmap="RdBu_r",
        center=0,
        vmin=-1,
        vmax=1,
        ax=ax,
        cbar_kws={"shrink": 0.8},
        linewidths=0.5,
        linecolor="white",
    )
    ax.set_title(f"{method.title()} correlation — {path.name}", fontsize=14)
    fig.tight_layout()

    ts = int(time.time() * 1000)
    name = f"corr_{path.stem}_{method}_{ts}.png"
    out = PLOTS_DIR / name
    await asyncio.to_thread(fig.savefig, out, dpi=120, bbox_inches="tight")
    plt.close(fig)

    await ctx.report_progress(100, 100, "Saved heatmap")
    return {
        "file": path.name,
        "method": method,
        "n_features": int(corr.shape[1]),
        "plot_file": name,
        "plot_url": f"/static/plots/{name}",
        "markdown_embed": f"![Correlation Matrix](/static/plots/{name})",
        "top_correlations": _top_correlations(df),
    }


# ----------------------------------------------------------------------------
# Native MCP Prompt — `eda-deep-dive`
# ----------------------------------------------------------------------------
@mcp.prompt(
    name="eda-deep-dive",
    description="Drive a systematic 5-stage exploratory data analysis on the given dataset.",
)
def eda_deep_dive(dataset_name: str) -> str:
    """A reusable prompt template that orchestrates a deep EDA workflow.

    The LLM, upon invocation, will receive a comprehensive checklist of
    profiling, outlier-hunting, correlation-mining, and segmentation steps.
    """
    return f"""You are running a structured, multi-stage exploratory data analysis on the dataset `{dataset_name}`.

Follow this 5-stage protocol — call the required microservice tools in order, narrate findings between each stage in concise bullets, and propose follow-up questions to the user at the end.

### STAGE 1 — Shape & Schema Inventory
1. Call `ingest_dataset(file_path='{dataset_name}', n_preview_rows=10)` to confirm shape and dtypes.
2. Subscribe to the resource `dataset://{dataset_name}/schema` to obtain the full pandera-style schema.
3. Summarize: row count, column count, total memory, duplicate row count.

### STAGE 2 — Quality Diagnostics
1. Call `validate_schema_with_pandera(file_path='{dataset_name}')` to surface bad rows.
2. Identify the top 3 columns by null-rate. Flag any column with >20% missing.
3. List candidate ID columns (unique_count == row_count) and categorical columns (unique_count <= 20).

### STAGE 3 — Distribution & Outlier Sweep
1. Call `generate_eda_report(file_path='{dataset_name}', minimal=True)` and embed the report link.
2. Render `![Correlation matrix](URL)` using the result of `render_correlation_matrix`.
3. For each numeric column with skew > 2.0 or kurtosis > 5.0, flag it as a transformation candidate.

### STAGE 4 — Correlation Mining
1. Identify the top 5 absolute correlations from the EDA tool result.
2. For each pair, decide: drop-one-feature, retain-both-with-PCA, or interaction-engineering.
3. Highlight any pair with |corr| > 0.9 as a multicollinearity risk.

### STAGE 5 — Recommendations & Next Steps
1. Suggest a probable target column based on column names/dtypes and ask the user to confirm.
2. Recommend: classification or regression, given the inferred target.
3. Propose a `run_parallel_bake_off` invocation with concrete arguments.
4. End by asking the user which stage to deepen or whether to proceed to modeling.

Be concise. Use short paragraphs with bullets. Cite tool results inline as Markdown embeds where applicable.
"""


if __name__ == "__main__":
    log.info("Starting %s on http://127.0.0.1:%d/mcp", SERVICE_NAME, SERVICE_PORT)
    mcp.run(transport="streamable-http", host="127.0.0.1", port=SERVICE_PORT)