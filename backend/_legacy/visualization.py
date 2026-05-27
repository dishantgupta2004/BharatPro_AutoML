from __future__ import annotations

import time
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from core.paths import output_file_path, resolve_upload_file

SUPPORTED_CHARTS = {"histogram", "bar", "scatter", "box", "correlation_heatmap", "missing_matrix", "target_distribution"}


def _save_fig(fig, stem: str, chart_type: str) -> tuple[str, str]:
    ts = int(time.time() * 1000)
    name = f"plot_{chart_type}_{stem}_{ts}.png"
    path = output_file_path(name)
    fig.tight_layout()
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return name, str(path)


def create_visualization(
    file_path: str,
    chart_type: str,
    columns: list[str] | None = None,
    target_column: str | None = None,
) -> dict[str, Any]:
    chart_type = chart_type.strip().lower()
    if chart_type not in SUPPORTED_CHARTS:
        raise ValueError(
            f"chart_type '{chart_type}' not supported. Choose one of: {sorted(SUPPORTED_CHARTS)}"
        )

    path = resolve_upload_file(file_path)
    df = pd.read_csv(path)
    sns.set_theme(style="whitegrid", context="talk")
    stem = path.stem.replace(" ", "_")

    if chart_type == "histogram":
        cols = columns or df.select_dtypes(include="number").columns.tolist()[:1]
        if not cols:
            raise ValueError("No numeric column available for histogram.")
        col = cols[0]
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not in dataset.")
        fig, ax = plt.subplots(figsize=(9, 5.5))
        sns.histplot(df[col].dropna(), kde=True, ax=ax, color="#4f46e5")
        ax.set_title(f"Distribution of {col}")
        name, full = _save_fig(fig, stem, "histogram")
        return {"chart_type": chart_type, "column": col, "file": name, "path": full}

    if chart_type == "bar":
        cols = columns or df.select_dtypes(include=["object", "category", "bool"]).columns.tolist()[:1]
        if not cols:
            raise ValueError("No categorical column available for bar chart.")
        col = cols[0]
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not in dataset.")
        vc = df[col].value_counts(dropna=False).head(20)
        fig, ax = plt.subplots(figsize=(10, 5.5))
        sns.barplot(x=vc.index.astype(str), y=vc.values, ax=ax, color="#4f46e5")
        ax.set_title(f"Value counts — {col}")
        ax.set_xlabel(col)
        ax.set_ylabel("count")
        for label in ax.get_xticklabels():
            label.set_rotation(35)
            label.set_horizontalalignment("right")
        name, full = _save_fig(fig, stem, "bar")
        return {"chart_type": chart_type, "column": col, "file": name, "path": full}

    if chart_type == "scatter":
        if not columns or len(columns) < 2:
            numeric = df.select_dtypes(include="number").columns.tolist()
            if len(numeric) < 2:
                raise ValueError("Need at least 2 numeric columns for scatter.")
            x, y = numeric[0], numeric[1]
        else:
            x, y = columns[0], columns[1]
        for c in (x, y):
            if c not in df.columns:
                raise ValueError(f"Column '{c}' not in dataset.")
        fig, ax = plt.subplots(figsize=(9, 6))
        hue = target_column if target_column and target_column in df.columns else None
        sns.scatterplot(data=df, x=x, y=y, hue=hue, ax=ax, alpha=0.7, palette="viridis")
        ax.set_title(f"{y} vs {x}" + (f" (color = {hue})" if hue else ""))
        name, full = _save_fig(fig, stem, "scatter")
        return {"chart_type": chart_type, "x": x, "y": y, "hue": hue, "file": name, "path": full}

    if chart_type == "box":
        cols = columns or df.select_dtypes(include="number").columns.tolist()[:6]
        cols = [c for c in cols if c in df.columns]
        if not cols:
            raise ValueError("No valid numeric columns for box plot.")
        long = df[cols].melt(var_name="feature", value_name="value")
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.boxplot(data=long, x="feature", y="value", ax=ax, palette="viridis")
        ax.set_title("Boxplot of selected numeric features")
        for label in ax.get_xticklabels():
            label.set_rotation(25)
            label.set_horizontalalignment("right")
        name, full = _save_fig(fig, stem, "box")
        return {"chart_type": chart_type, "columns": cols, "file": name, "path": full}

    if chart_type == "correlation_heatmap":
        numeric = df.select_dtypes(include="number")
        if numeric.shape[1] < 2:
            raise ValueError("Need at least 2 numeric columns for a correlation heatmap.")
        corr = numeric.corr(numeric_only=True)
        fig, ax = plt.subplots(figsize=(min(1.1 * corr.shape[1] + 3, 14), min(1.0 * corr.shape[1] + 2, 12)))
        sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", center=0, ax=ax, cbar_kws={"shrink": 0.8})
        ax.set_title("Correlation heatmap")
        name, full = _save_fig(fig, stem, "correlation_heatmap")
        return {"chart_type": chart_type, "n_features": int(corr.shape[1]), "file": name, "path": full}

    if chart_type == "missing_matrix":
        missing = df.isna()
        if missing.sum().sum() == 0:
            return {"chart_type": chart_type, "note": "No missing values present.", "file": None, "path": None}
        fig, ax = plt.subplots(figsize=(min(0.4 * df.shape[1] + 4, 14), 6))
        sns.heatmap(missing, cbar=False, yticklabels=False, cmap="rocket_r", ax=ax)
        ax.set_title("Missing value matrix (yellow = missing)")
        name, full = _save_fig(fig, stem, "missing_matrix")
        return {"chart_type": chart_type, "file": name, "path": full}

    if chart_type == "target_distribution":
        if not target_column or target_column not in df.columns:
            raise ValueError("target_column required and must exist in dataset.")
        target = df[target_column].dropna()
        fig, ax = plt.subplots(figsize=(9, 5.5))
        if pd.api.types.is_numeric_dtype(target) and target.nunique() > 20:
            sns.histplot(target, kde=True, ax=ax, color="#4f46e5")
        else:
            vc = target.value_counts().head(30)
            sns.barplot(x=vc.index.astype(str), y=vc.values, ax=ax, color="#4f46e5")
            for label in ax.get_xticklabels():
                label.set_rotation(35)
                label.set_horizontalalignment("right")
        ax.set_title(f"Target distribution — {target_column}")
        name, full = _save_fig(fig, stem, "target_distribution")
        return {"chart_type": chart_type, "target": target_column, "file": name, "path": full}

    raise ValueError(f"Unhandled chart_type: {chart_type}")
