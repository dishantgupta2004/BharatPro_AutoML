"""SHAP explanations for the bake-off champion model."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from core.config import settings


def generate_model_explanations_sync(
    model_artifact_path: str,
    x_train_sample_path: str,
    max_samples: int = 200,
) -> dict[str, Any]:
    import shap

    artifact = joblib.load(model_artifact_path)
    pipeline = artifact["pipeline"]
    feature_cols = artifact["feature_columns"]
    problem = artifact["problem_type"]

    X = pd.read_parquet(x_train_sample_path)
    X = X[feature_cols].head(max_samples)

    pre = pipeline.named_steps["pre"]
    model = pipeline.named_steps["model"]
    X_transformed = pre.transform(X)

    try:
        feature_names = list(pre.get_feature_names_out())
    except Exception:
        feature_names = [f"f{i}" for i in range(X_transformed.shape[1])]

    # Choose explainer based on model family
    model_cls = type(model).__name__
    if any(token in model_cls for token in ("Forest", "XGB", "LGBM", "GradientBoosting")):
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_transformed)
    else:
        background = shap.sample(X_transformed, min(100, X_transformed.shape[0]))
        explainer = shap.KernelExplainer(
            model.predict_proba if hasattr(model, "predict_proba") and problem == "classification"
            else model.predict,
            background,
        )
        shap_values = explainer.shap_values(X_transformed, nsamples=100)

    # For multiclass classification shap returns list; pick class 1 (or mean abs across classes)
    if isinstance(shap_values, list):
        import numpy as np
        shap_for_plot = np.mean([abs(sv) for sv in shap_values], axis=0)
    else:
        shap_for_plot = shap_values

    fig = plt.figure(figsize=(9, 6))
    shap.summary_plot(
        shap_for_plot,
        X_transformed,
        feature_names=feature_names,
        show=False,
        plot_size=None,
    )
    fig = plt.gcf()

    ts = int(time.time())
    stem = Path(model_artifact_path).stem
    plot_name = f"shap_{stem}_{ts}.png"
    plot_path = settings.plots_path / plot_name
    fig.tight_layout()
    fig.savefig(plot_path, dpi=120, bbox_inches="tight")
    plt.close(fig)

    return {
        "plot_file": plot_name,
        "plot_url": f"/static/plots/{plot_name}",
        "markdown_embed": f"![SHAP summary](/static/plots/{plot_name})",
        "n_samples_explained": int(X_transformed.shape[0]),
        "n_features": int(X_transformed.shape[1]),
    }