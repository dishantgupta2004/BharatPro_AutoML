"""AutoML MCP — Explainable AI (in-process)."""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from fastmcp import Context, FastMCP

from core.config import settings
from core.workspace import artifact_path, save_artifact

SERVICE_NAME = "mcp-explain"

logging.basicConfig(
    stream=sys.stderr, level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | mcp_explain | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(SERVICE_NAME)

mcp = FastMCP(name=SERVICE_NAME)


def _workspace() -> Path:
    p = settings.tmp_path / "explain"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_model_artifact(model_id: str) -> tuple[Path, dict[str, Any]]:
    """Resolve a model artifact id to its local path + loaded joblib dict."""
    local = artifact_path(model_id)
    return local, joblib.load(local)


@mcp.tool
async def calculate_shap_values(
    model_id: str,
    x_train_sample_id: str,
    ctx: Context,
    max_samples: int = 200,
) -> dict[str, Any]:
    """Compute SHAP values for the champion model and save a summary plot.

    Args:
        model_id: Artifact id of the champion joblib model from run_parallel_bake_off.
        x_train_sample_id: Artifact id of the X_train parquet sample from run_parallel_bake_off.
        max_samples: Number of samples to explain (default 200).
    """
    import shap

    await ctx.info(f"Loading champion model {model_id}")
    model_path, artifact = _load_model_artifact(model_id)
    pipeline = artifact["pipeline"]
    feature_cols = artifact["feature_columns"]
    problem = artifact["problem_type"]

    await ctx.report_progress(20, 100, "Reading X_train sample")
    xtrain_local = artifact_path(x_train_sample_id)
    X = pd.read_parquet(xtrain_local)
    X = X[feature_cols].head(max_samples)

    pre = pipeline.named_steps["pre"]
    model = pipeline.named_steps["model"]
    X_t = pre.transform(X)

    try:
        feature_names = list(pre.get_feature_names_out())
    except Exception:
        feature_names = [f"f{i}" for i in range(X_t.shape[1])]

    await ctx.report_progress(45, 100, "Selecting explainer")
    cls = type(model).__name__
    if any(tok in cls for tok in ("Forest", "XGB", "LGBM", "GradientBoosting")):
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_t)
    else:
        background = shap.sample(X_t, min(100, X_t.shape[0]))
        predict_fn = (model.predict_proba
                      if hasattr(model, "predict_proba") and problem == "classification"
                      else model.predict)
        explainer = shap.KernelExplainer(predict_fn, background)
        shap_values = explainer.shap_values(X_t, nsamples=100)

    if isinstance(shap_values, list):
        shap_for_plot = np.mean([np.abs(sv) for sv in shap_values], axis=0)
    else:
        shap_for_plot = shap_values

    abs_mean = np.abs(shap_for_plot).mean(axis=0)
    order = np.argsort(abs_mean)[::-1][:20]
    global_importance = [
        {"feature": str(feature_names[i]), "mean_abs_shap": float(abs_mean[i])}
        for i in order
    ]

    await ctx.report_progress(75, 100, "Rendering SHAP summary plot")
    fig = plt.figure(figsize=(9, 6))
    shap.summary_plot(shap_for_plot, X_t, feature_names=feature_names, show=False)
    fig = plt.gcf()
    fig.tight_layout()
    ts = int(time.time())
    name = f"shap_{Path(model_path).stem}_{ts}.png"
    tmp_path = _workspace() / name
    fig.savefig(tmp_path, dpi=120, bbox_inches="tight")
    plt.close(fig)

    await ctx.report_progress(90, 100, "Saving plot artifact")
    plot_art = save_artifact(
        local_path=tmp_path, kind="plot",
        metadata={"source_model_id": model_id, "explainer_kind": type(explainer).__name__},
    )

    await ctx.report_progress(100, 100, "SHAP complete")
    return {
        "model_id": model_id,
        "artifact_id": plot_art.id,
        "plot_file": plot_art.filename,
        "path": plot_art.path,
        "n_samples_explained": int(X_t.shape[0]),
        "n_features": int(X_t.shape[1]),
        "global_importance": global_importance,
        "explainer_kind": type(explainer).__name__,
    }


@mcp.tool
async def generate_feature_importance_plot(
    model_id: str,
    ctx: Context,
    top_k: int = 15,
) -> dict[str, Any]:
    """Native feature_importances_ bar chart for tree-based models.

    Args:
        model_id: Artifact id of the champion joblib model from run_parallel_bake_off.
        top_k: Number of top features to display (default 15).
    """
    await ctx.info(f"Loading {model_id}")
    model_path, artifact = _load_model_artifact(model_id)
    pipeline = artifact["pipeline"]
    pre = pipeline.named_steps["pre"]
    model = pipeline.named_steps["model"]

    try:
        feature_names = list(pre.get_feature_names_out())
    except Exception:
        feature_names = None

    if not hasattr(model, "feature_importances_"):
        return {
            "model_id": model_id,
            "error": f"Model {type(model).__name__} has no feature_importances_; use calculate_shap_values instead.",
        }

    await ctx.report_progress(40, 100, "Sorting importances")
    importances = model.feature_importances_
    if feature_names is None or len(feature_names) != len(importances):
        feature_names = [f"f{i}" for i in range(len(importances))]
    order = np.argsort(importances)[::-1][:top_k]
    feats = [feature_names[i] for i in order]
    vals = [float(importances[i]) for i in order]

    fig, ax = plt.subplots(figsize=(9, max(4, top_k * 0.35)))
    ax.barh(feats[::-1], vals[::-1], color="#6366f1")
    ax.set_xlabel("Importance")
    ax.set_title(f"Top {top_k} feature importances")
    fig.tight_layout()

    ts = int(time.time())
    name = f"importance_{Path(model_path).stem}_{ts}.png"
    tmp_path = _workspace() / name
    fig.savefig(tmp_path, dpi=120, bbox_inches="tight")
    plt.close(fig)

    plot_art = save_artifact(
        local_path=tmp_path, kind="plot",
        metadata={"source_model_id": model_id, "top_k": top_k},
    )

    await ctx.report_progress(100, 100, "Done")
    return {
        "model_id": model_id,
        "artifact_id": plot_art.id,
        "plot_file": plot_art.filename,
        "path": plot_art.path,
        "top_features": [{"feature": f, "importance": v} for f, v in zip(feats, vals)],
    }
