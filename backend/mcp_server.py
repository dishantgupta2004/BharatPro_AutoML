"""Local MCP server exposing AutoML tools over stdio.

Run directly:  python mcp_server.py
The FastAPI backend spawns this as a subprocess via PythonStdioTransport.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from core.logger import get_logger
from tools.code_generator import generate_training_script
from tools.data_analysis import (
    analyze_csv_head as _analyze_csv_head,
    detect_problem_type as _detect_problem_type,
    get_dataset_info as _get_dataset_info,
    list_uploaded_files as _list_uploaded_files,
)
from tools.eda import generate_eda_report as _generate_eda_report
from tools.ml_training import train_baseline_model as _train_baseline_model
from tools.visualization import create_visualization as _create_visualization

log = get_logger("mcp.server")

mcp = FastMCP(name="automl-mcp-server")


@mcp.tool
def list_uploaded_files() -> dict[str, Any]:
    """List all CSV/TSV files available in the upload directory.

    Use this first when the user has not specified a file, or to verify which
    datasets are available before calling any file-specific tool.

    Returns the upload directory path, total file count, and a list of files
    with `filename`, `size_kb`, and `modified_unix` for each entry.
    """
    log.info("tool=list_uploaded_files")
    return _list_uploaded_files()


@mcp.tool
def analyze_csv_head(file_path: str, n_rows: int = 5) -> dict[str, Any]:
    """Read a CSV and return the first N rows plus schema info.

    Args:
        file_path: Filename inside the upload directory (e.g. "iris.csv") or an
            absolute path inside that directory.
        n_rows: How many rows to preview. Defaults to 5.

    Returns the file name, row/column counts, column list, per-column dtypes,
    and the first `n_rows` rows as a list of dicts.
    """
    log.info("tool=analyze_csv_head file=%s n=%d", file_path, n_rows)
    return _analyze_csv_head(file_path=file_path, n_rows=n_rows)


@mcp.tool
def get_dataset_info(file_path: str) -> dict[str, Any]:
    """Return a richer overview of a dataset: shape, dtypes, missing-value
    counts, duplicate-row count, and column groupings (numeric vs categorical
    vs datetime).

    Call this when the user asks "tell me about my data" or before deciding
    which visualization or model to recommend.
    """
    log.info("tool=get_dataset_info file=%s", file_path)
    return _get_dataset_info(file_path=file_path)


@mcp.tool
def detect_problem_type(file_path: str, target_column: str) -> dict[str, Any]:
    """Inspect the target column and decide whether the task is
    classification or regression.

    Uses a simple heuristic: non-numeric → classification; numeric with few
    unique values → classification; otherwise regression. Returns the
    detected problem type plus diagnostics.
    """
    log.info("tool=detect_problem_type file=%s target=%s", file_path, target_column)
    return _detect_problem_type(file_path=file_path, target_column=target_column)


@mcp.tool
def generate_eda_report(file_path: str) -> dict[str, Any]:
    """Generate a full EDA report for a CSV file: numeric summary statistics,
    top correlated numeric feature pairs, categorical value counts, and
    missing-value counts.

    Also writes a markdown report to the outputs directory and returns its
    filename under `report_file` for download.
    """
    log.info("tool=generate_eda_report file=%s", file_path)
    return _generate_eda_report(file_path=file_path)


@mcp.tool
def create_visualization(
    file_path: str,
    chart_type: str,
    columns: list[str] | None = None,
    target_column: str | None = None,
) -> dict[str, Any]:
    """Create a visualization saved as a PNG inside the outputs directory.

    Args:
        file_path: Dataset filename in the upload directory.
        chart_type: One of "histogram", "bar", "scatter", "box",
            "correlation_heatmap", "missing_matrix", "target_distribution".
        columns: Optional list of column names. Required for scatter (2
            numeric columns); optional for histogram/bar/box.
        target_column: Used by "scatter" (as hue) and required for
            "target_distribution".

    Returns the chart type, the columns used, and the saved PNG filename
    under `file` for download.
    """
    log.info(
        "tool=create_visualization file=%s chart=%s cols=%s target=%s",
        file_path, chart_type, columns, target_column,
    )
    return _create_visualization(
        file_path=file_path,
        chart_type=chart_type,
        columns=columns,
        target_column=target_column,
    )


@mcp.tool
def train_baseline_model(
    file_path: str,
    target_column: str,
    test_size: float = 0.2,
    random_state: int = 42,
) -> dict[str, Any]:
    """Train a baseline Random Forest model on the dataset.

    Auto-detects classification vs regression from the target column, runs a
    standard preprocessing pipeline (median/mode imputation, scaling for
    numerics, one-hot for categoricals), trains a 200-tree Random Forest,
    and reports metrics on a held-out test split.

    For classification returns accuracy and F1 (binary or weighted). For
    regression returns RMSE, MAE, and R^2. Also returns the top-10 feature
    importances and saves the fitted pipeline to the outputs directory.
    """
    log.info(
        "tool=train_baseline_model file=%s target=%s test_size=%s",
        file_path, target_column, test_size,
    )
    return _train_baseline_model(
        file_path=file_path,
        target_column=target_column,
        test_size=test_size,
        random_state=random_state,
    )


@mcp.tool
def download_main_code_file(file_path: str, target_column: str) -> dict[str, Any]:
    """Generate a standalone, runnable Python training script for the given
    dataset and target column.

    The script reproduces the baseline pipeline (preprocessing + Random
    Forest), is fully self-contained, and is saved to the outputs directory.
    The returned `script_file` can be downloaded and executed locally with
    `python <script_file>`.
    """
    log.info("tool=download_main_code_file file=%s target=%s", file_path, target_column)
    return generate_training_script(file_path=file_path, target_column=target_column)


if __name__ == "__main__":
    log.info("Starting AutoML MCP server on stdio transport")
    mcp.run()
