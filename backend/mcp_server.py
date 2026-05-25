"""Local MCP server exposing AutoML tools over stdio."""
from __future__ import annotations

import asyncio
from typing import Any

from fastmcp import Context, FastMCP

from core.logger import get_logger
from tools.code_generator import generate_training_script
from tools.data_analysis import (
    analyze_csv_head as _analyze_csv_head,
    detect_problem_type as _detect_problem_type,
    get_dataset_info as _get_dataset_info,
    list_uploaded_files as _list_uploaded_files,
)
from tools.data_profiling import run_data_profiling_sync
from tools.explainability import generate_model_explanations_sync
from tools.model_bakeoff import run_model_bake_off_sync
from tools.visualization import create_visualization as _create_visualization

log = get_logger("mcp.server")
mcp = FastMCP(name="automl-mcp-server")


@mcp.tool
def list_uploaded_files() -> dict[str, Any]:
    """List all CSV/TSV files available in the upload directory."""
    return _list_uploaded_files()


@mcp.tool
def analyze_csv_head(file_path: str, n_rows: int = 5) -> dict[str, Any]:
    """Read a CSV and return the first N rows plus schema info."""
    return _analyze_csv_head(file_path=file_path, n_rows=n_rows)


@mcp.tool
def get_dataset_info(file_path: str) -> dict[str, Any]:
    """Shape, dtypes, missing-value counts, duplicates, and column groupings."""
    return _get_dataset_info(file_path=file_path)


@mcp.tool
def detect_problem_type(file_path: str, target_column: str) -> dict[str, Any]:
    """Decide classification vs regression for the given target column."""
    return _detect_problem_type(file_path=file_path, target_column=target_column)


@mcp.tool
async def run_data_profiling(file_path: str, ctx: Context) -> dict[str, Any]:
    """Generate a full ydata-profiling HTML report and return summary statistics.

    Returns a high-level dict (row/col counts, missing counts, top correlations)
    plus `report_url` that can be linked in chat.
    """
    await ctx.info(f"Starting ydata-profiling on {file_path}")
    await ctx.report_progress(progress=5, total=100, message="Loading CSV…")
    await asyncio.sleep(0)  # let event loop flush
    await ctx.report_progress(progress=20, total=100, message="Building profile report")
    result = await asyncio.to_thread(run_data_profiling_sync, file_path)
    await ctx.report_progress(progress=95, total=100, message="Saving HTML report")
    await ctx.info(f"Report saved: {result['report_file']}")
    await ctx.report_progress(progress=100, total=100, message="Done")
    return result


@mcp.tool
async def run_model_bake_off(
    file_path: str,
    target_column: str,
    tune_budget_mins: int = 0,
    ctx: Context = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Train RF, XGBoost, LightGBM, and a linear baseline in parallel with CV.

    Returns a sorted leaderboard (accuracy / F1 for classification, RMSE / R² for
    regression) plus training times, the champion model artifact path, and an
    Optuna tuning summary when `tune_budget_mins > 0`.
    """
    if ctx:
        await ctx.info(f"Starting bake-off on {file_path}, target={target_column}")
        await ctx.report_progress(5, 100, "Preparing data and CV splits")

    # Wrap sync core; emit synthetic progress while training thread runs
    loop = asyncio.get_running_loop()
    task = loop.run_in_executor(
        None, run_model_bake_off_sync, file_path, target_column, tune_budget_mins
    )

    if ctx:
        await ctx.report_progress(15, 100, "Training RandomForest / XGBoost / LightGBM in parallel")
        # Heartbeat progress while task runs
        ticks = 0
        while not task.done():
            await asyncio.sleep(2.0)
            ticks += 1
            pct = min(15 + ticks * 5, 85)
            await ctx.report_progress(pct, 100, f"Training in progress… ({ticks * 2}s)")

    result = await task

    if ctx:
        await ctx.info(f"Champion: {result['champion_model']}")
        if result.get("tuning"):
            await ctx.info(
                f"Optuna ran {result['tuning']['n_trials']} trials, "
                f"best score {result['tuning']['best_value']:.4f}"
            )
        await ctx.report_progress(100, 100, "Bake-off complete")
    return result


@mcp.tool
async def generate_model_explanations(
    model_artifact_path: str,
    x_train_sample_path: str,
    ctx: Context,
    max_samples: int = 200,
) -> dict[str, Any]:
    """Generate SHAP summary plot for the champion model. Returns a static URL
    that the LLM can render in chat as Markdown."""
    await ctx.info("Computing SHAP values…")
    await ctx.report_progress(10, 100, "Loading champion model")
    result = await asyncio.to_thread(
        generate_model_explanations_sync,
        model_artifact_path,
        x_train_sample_path,
        max_samples,
    )
    await ctx.report_progress(100, 100, "Plot saved")
    return result


@mcp.tool
def create_visualization(
    file_path: str,
    chart_type: str,
    columns: list[str] | None = None,
    target_column: str | None = None,
) -> dict[str, Any]:
    """Create a chart (histogram, bar, scatter, box, correlation_heatmap,
    missing_matrix, target_distribution) and save it as PNG."""
    return _create_visualization(
        file_path=file_path,
        chart_type=chart_type,
        columns=columns,
        target_column=target_column,
    )


@mcp.tool
def download_main_code_file(file_path: str, target_column: str) -> dict[str, Any]:
    """Generate a standalone runnable Python training script."""
    return generate_training_script(file_path=file_path, target_column=target_column)


if __name__ == "__main__":
    log.info("Starting AutoML MCP server on stdio transport")
    mcp.run()