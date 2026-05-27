from __future__ import annotations

import time
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from core.paths import output_file_path, resolve_upload_file
from tools.data_analysis import detect_problem_type


def _build_preprocessor(X: pd.DataFrame) -> ColumnTransformer:
    numeric_cols = X.select_dtypes(include="number").columns.tolist()
    categorical_cols = X.select_dtypes(include=["object", "category", "bool"]).columns.tolist()

    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )

    transformers = []
    if numeric_cols:
        transformers.append(("num", numeric_pipeline, numeric_cols))
    if categorical_cols:
        transformers.append(("cat", categorical_pipeline, categorical_cols))

    if not transformers:
        raise ValueError("Dataset has no usable feature columns after dropping the target.")

    return ColumnTransformer(transformers=transformers, remainder="drop")


def train_baseline_model(
    file_path: str,
    target_column: str,
    test_size: float = 0.2,
    random_state: int = 42,
) -> dict[str, Any]:
    path = resolve_upload_file(file_path)
    df = pd.read_csv(path)

    if target_column not in df.columns:
        raise ValueError(
            f"Target column '{target_column}' not found. Available: {list(df.columns)}"
        )

    df = df.dropna(subset=[target_column])
    if len(df) < 20:
        raise ValueError("Dataset has fewer than 20 rows with a non-null target — too small to train.")

    detect = detect_problem_type(file_path, target_column)
    problem_type = detect["problem_type"]

    y = df[target_column]
    X = df.drop(columns=[target_column])

    if X.shape[1] == 0:
        raise ValueError("No feature columns left after dropping the target.")

    preprocessor = _build_preprocessor(X)
    if problem_type == "classification":
        model = RandomForestClassifier(
            n_estimators=200, random_state=random_state, n_jobs=-1
        )
    else:
        model = RandomForestRegressor(
            n_estimators=200, random_state=random_state, n_jobs=-1
        )

    pipeline = Pipeline(steps=[("preprocess", preprocessor), ("model", model)])

    stratify = y if problem_type == "classification" and y.nunique() > 1 and (y.value_counts().min() >= 2) else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=stratify
    )

    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)

    metrics: dict[str, Any] = {}
    if problem_type == "classification":
        metrics["accuracy"] = float(accuracy_score(y_test, y_pred))
        avg = "binary" if y.nunique() <= 2 else "weighted"
        metrics["f1_score"] = float(f1_score(y_test, y_pred, average=avg, zero_division=0))
        metrics["averaging"] = avg
        metrics["n_classes"] = int(y.nunique())
    else:
        rmse_val = float(np.sqrt(mean_squared_error(y_test, y_pred)))
        metrics["rmse"] = rmse_val
        metrics["mae"] = float(mean_absolute_error(y_test, y_pred))
        metrics["r2"] = float(r2_score(y_test, y_pred))

    try:
        feature_names = pipeline.named_steps["preprocess"].get_feature_names_out()
        importances = pipeline.named_steps["model"].feature_importances_
        order = np.argsort(importances)[::-1][:10]
        top_features = [
            {"feature": str(feature_names[i]), "importance": float(importances[i])}
            for i in order
        ]
    except Exception:
        top_features = []

    stem = path.stem.replace(" ", "_")
    ts = int(time.time())
    model_name = f"model_{stem}_{ts}.joblib"
    model_path = output_file_path(model_name)
    joblib.dump(pipeline, model_path)

    return {
        "file": path.name,
        "target_column": target_column,
        "problem_type": problem_type,
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "n_features_input": int(X.shape[1]),
        "metrics": metrics,
        "top_features": top_features,
        "model_file": model_name,
        "model_path": str(model_path),
    }
