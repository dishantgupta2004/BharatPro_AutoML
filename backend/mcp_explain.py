"""Unisole Empower — Explainable AI Microservice (Port 8004)

Responsibilities:
  - `calculate_shap_values`: Compute SHAP values (TreeExplainer / KernelExplainer)
    for the champion model, render a summary plot.
  - `generate_feature_importance_plot`: native sklearn feature_importance bar chart.
  - Resource: `model://{model_id}/explainability-card` — structured global + local
    explanation text card.

Transport: streamable-http on http://127.0.0.1:8004/mcp
"""
from __future__ import annotations

import json
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

SERVICE_NAME = "mcp-explain"
SERVICE_PORT = 8004
BACKEND_ROOT = Path(__file__).resolve().parent
MODELS_DIR = (BACKEND_ROOT / "outputs" / "models").resolve()
PLOTS_DIR = (BACKEND_ROOT / "outputs" / "plots").resolve()
for d in (MODELS_DIR, PLOTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | mcp_explain | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(SERVICE_NAME)

mcp = FastMCP(name=SERVICE_NAME)


def _load_artifact(model_id_or_path: str) -> tuple[Path, dict[str, Any]]:
    """Resolve a model id or full filename to the on-disk artifact."""
    name = model_id_or_path.strip()
    if not name.endswith(".joblib"):
        name = f"{name}.joblib"
    candidate = (MODELS_DIR / Path(name).name).resolve()
    candidate.relative_to(MODELS_DIR)
    if not candidate.exists():
        raise FileNotFoundError(f"Model artifact not found: {candidate}")
    return candidate, joblib.load(candidate)


# ----------------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------------
@mcp.tool
async def calculate_shap_values(
    model_id: str,
    x_train_sample_path: str,
    ctx: Context,
    max_samples: int = 200,
) -> dict[str, Any]:
    """Compute SHAP values and persist a summary plot PNG.

    Args:
        model_id: id or filename returned by `run_parallel_bake_off`.
        x_train_sample_path: path to the X_train parquet sample.
        max_samples: cap on rows used for SHAP (default 200).
    """
    import shap

    await ctx.info(f"Loading champion model {model_id}")
    model_path, artifact = _load_artifact(model_id)
    pipeline = artifact["pipeline"]
    feature_cols = artifact["feature_columns"]
    problem = artifact["problem_type"]

    await ctx.report_progress(20, 100, "Reading X_train sample")
    X = pd.read_parquet(x_train_sample_path)
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
        predict_fn = (
            model.predict_proba
            if hasattr(model, "predict_proba") and problem == "classification"
            else model.predict
        )
        explainer = shap.KernelExplainer(predict_fn, background)
        shap_values = explainer.shap_values(X_t, nsamples=100)

    if isinstance(shap_values, list):
        shap_for_plot = np.mean([np.abs(sv) for sv in shap_values], axis=0)
    else:
        shap_for_plot = shap_values

    # Global importance
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
    out = PLOTS_DIR / name
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)

    await ctx.report_progress(100, 100, "SHAP complete")
    return {
        "model_id": Path(model_path).stem,
        "plot_file": name,
        "plot_url": f"/static/plots/{name}",
        "markdown_embed": f"![SHAP Summary](/static/plots/{name})",
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
    """Render a horizontal bar chart of the model's native feature_importances_.

    Args:
        model_id: id returned by `run_parallel_bake_off`.
        top_k: number of top features to plot.
    """
    await ctx.info(f"Loading {model_id}")
    model_path, artifact = _load_artifact(model_id)
    pipeline = artifact["pipeline"]
    pre = pipeline.named_steps["pre"]
    model = pipeline.named_steps["model"]

    try:
        feature_names = list(pre.get_feature_names_out())
    except Exception:
        feature_names = None

    if not hasattr(model, "feature_importances_"):
        return {
            "model_id": Path(model_path).stem,
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
    ax.set_title(f"Top {top_k} feature importances — {Path(model_path).stem}")
    fig.tight_layout()

    ts = int(time.time())
    name = f"importance_{Path(model_path).stem}_{ts}.png"
    out = PLOTS_DIR / name
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)

    await ctx.report_progress(100, 100, "Done")
    return {
        "model_id": Path(model_path).stem,
        "plot_file": name,
        "plot_url": f"/static/plots/{name}",
        "markdown_embed": f"![Feature importance](/static/plots/{name})",
        "top_features": [{"feature": f, "importance": v} for f, v in zip(feats, vals)],
    }


# ----------------------------------------------------------------------------
# Resource — `model://{model_id}/explainability-card`
# ----------------------------------------------------------------------------
@mcp.resource("model://{model_id}/explainability-card")
def model_explainability_card(model_id: str) -> str:
    """Structured explainability card combining model metadata + global importances.

    The LLM can read this URI to obtain a rich summary without firing a tool call.
    """
    try:
        model_path, artifact = _load_artifact(model_id)
    except FileNotFoundError as exc:
        return json.dumps({"error": str(exc), "model_id": model_id})

    pipeline = artifact["pipeline"]
    model = pipeline.named_steps["model"]
    pre = pipeline.named_steps["pre"]

    try:
        feature_names = list(pre.get_feature_names_out())
    except Exception:
        feature_names = []

    top_importances: list[dict[str, Any]] = []
    if hasattr(model, "feature_importances_"):
        imp = model.feature_importances_
        order = np.argsort(imp)[::-1][:15]
        top_importances = [
            {"feature": feature_names[i] if i < len(feature_names) else f"f{i}",
             "importance": float(imp[i])}
            for i in order
        ]

    card = {
        "model_id": Path(model_path).stem,
        "champion_name": artifact.get("champion_name"),
        "problem_type": artifact.get("problem_type"),
        "target_column": artifact.get("target_column"),
        "n_features": len(feature_names),
        "estimator_class": type(model).__name__,
        "preprocessor_class": type(pre).__name__,
        "top_global_importances": top_importances,
        "feature_columns": artifact.get("feature_columns", []),
    }

    md_lines = [
        f"# Explainability Card — `{card['model_id']}`",
        "",
        f"- **Champion Model:** {card['champion_name']}",
        f"- **Problem Type:** {card['problem_type']}",
        f"- **Target Column:** `{card['target_column']}`",
        f"- **Estimator:** `{card['estimator_class']}`",
        f"- **Feature Count:** {card['n_features']}",
        "",
    ]
    if top_importances:
        md_lines += [
            "## Top Global Feature Importances",
            "",
            "| Rank | Feature | Importance |",
            "|---|---|---|",
        ]
        for i, row in enumerate(top_importances, 1):
            md_lines.append(f"| {i} | `{row['feature']}` | {row['importance']:.4f} |")
        md_lines.append("")
    else:
        md_lines.append("_No native feature_importances_ available — run `calculate_shap_values` for local + global SHAP attributions._")

    return json.dumps({"markdown": "\n".join(md_lines), "json": card}, default=str)


if __name__ == "__main__":
    log.info("Starting %s on http://127.0.0.1:%d/mcp", SERVICE_NAME, SERVICE_PORT)
    mcp.run(transport="streamable-http", host="127.0.0.1", port=SERVICE_PORT)