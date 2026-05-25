from __future__ import annotations

import time
from typing import Any

from core.paths import output_file_path, resolve_upload_file
from tools.data_analysis import detect_problem_type


SCRIPT_TEMPLATE = '''"""Auto-generated baseline training script.

Dataset:        {file_name}
Target column:  {target_column}
Problem type:   {problem_type}
Generated:      {timestamp}
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import {estimator_class}
from sklearn.impute import SimpleImputer
from sklearn.metrics import {metric_imports}
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


DATA_PATH = Path("{file_name}")
TARGET_COLUMN = "{target_column}"
RANDOM_STATE = 42
TEST_SIZE = 0.2
MODEL_OUT = Path("baseline_model.joblib")


def build_preprocessor(X: pd.DataFrame) -> ColumnTransformer:
    numeric_cols = X.select_dtypes(include="number").columns.tolist()
    categorical_cols = X.select_dtypes(include=["object", "category", "bool"]).columns.tolist()

    numeric_pipeline = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])
    categorical_pipeline = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])

    transformers = []
    if numeric_cols:
        transformers.append(("num", numeric_pipeline, numeric_cols))
    if categorical_cols:
        transformers.append(("cat", categorical_pipeline, categorical_cols))
    return ColumnTransformer(transformers=transformers, remainder="drop")


def main() -> None:
    df = pd.read_csv(DATA_PATH)
    df = df.dropna(subset=[TARGET_COLUMN])
    y = df[TARGET_COLUMN]
    X = df.drop(columns=[TARGET_COLUMN])

    preprocessor = build_preprocessor(X)
    model = {estimator_class}(n_estimators=200, random_state=RANDOM_STATE, n_jobs=-1)
    pipeline = Pipeline(steps=[("preprocess", preprocessor), ("model", model)])

    {stratify_line}
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=stratify
    )

    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)

{metric_block}

    joblib.dump(pipeline, MODEL_OUT)
    print(f"\\nModel saved to {{MODEL_OUT.resolve()}}")


if __name__ == "__main__":
    main()
'''


def _classification_block() -> tuple[str, str, str, str]:
    estimator = "RandomForestClassifier"
    metrics = "accuracy_score, f1_score"
    stratify_line = "stratify = y if y.nunique() > 1 and y.value_counts().min() >= 2 else None"
    metric_block = (
        '    acc = accuracy_score(y_test, y_pred)\n'
        '    avg = "binary" if y.nunique() <= 2 else "weighted"\n'
        '    f1 = f1_score(y_test, y_pred, average=avg, zero_division=0)\n'
        '    print(f"Accuracy: {acc:.4f}")\n'
        '    print(f"F1 ({avg}): {f1:.4f}")'
    )
    return estimator, metrics, stratify_line, metric_block


def _regression_block() -> tuple[str, str, str, str]:
    estimator = "RandomForestRegressor"
    metrics = "mean_absolute_error, mean_squared_error, r2_score"
    stratify_line = "stratify = None"
    metric_block = (
        '    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))\n'
        '    mae = mean_absolute_error(y_test, y_pred)\n'
        '    r2 = r2_score(y_test, y_pred)\n'
        '    print(f"RMSE: {rmse:.4f}")\n'
        '    print(f"MAE:  {mae:.4f}")\n'
        '    print(f"R^2:  {r2:.4f}")'
    )
    return estimator, metrics, stratify_line, metric_block


def generate_training_script(file_path: str, target_column: str) -> dict[str, Any]:
    path = resolve_upload_file(file_path)
    detect = detect_problem_type(file_path, target_column)
    problem_type = detect["problem_type"]

    if problem_type == "classification":
        estimator, metric_imports, stratify_line, metric_block = _classification_block()
    else:
        estimator, metric_imports, stratify_line, metric_block = _regression_block()

    script = SCRIPT_TEMPLATE.format(
        file_name=path.name,
        target_column=target_column,
        problem_type=problem_type,
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        estimator_class=estimator,
        metric_imports=metric_imports,
        stratify_line=stratify_line,
        metric_block=metric_block,
    )

    stem = path.stem.replace(" ", "_")
    ts = int(time.time())
    script_name = f"train_{stem}_{ts}.py"
    script_path = output_file_path(script_name)
    script_path.write_text(script, encoding="utf-8")

    return {
        "file": path.name,
        "target_column": target_column,
        "problem_type": problem_type,
        "script_file": script_name,
        "script_path": str(script_path),
        "line_count": len(script.splitlines()),
    }
