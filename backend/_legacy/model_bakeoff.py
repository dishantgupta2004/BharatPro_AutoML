"""Parallel multi-model bake-off + optional Optuna tuning."""
from __future__ import annotations

import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, StandardScaler

from core.config import settings
from core.paths import resolve_upload_file
from tools.data_analysis import detect_problem_type

warnings.filterwarnings("ignore")


def _build_preprocessor(X: pd.DataFrame) -> ColumnTransformer:
    num_cols = X.select_dtypes(include="number").columns.tolist()
    cat_cols = X.select_dtypes(include=["object", "category", "bool"]).columns.tolist()
    transformers = []
    if num_cols:
        transformers.append(
            (
                "num",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="median")),
                        ("scale", StandardScaler()),
                    ]
                ),
                num_cols,
            )
        )
    if cat_cols:
        transformers.append(
            (
                "cat",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("ohe", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                    ]
                ),
                cat_cols,
            )
        )
    if not transformers:
        raise ValueError("No usable feature columns.")
    return ColumnTransformer(transformers=transformers, remainder="drop")


def _classification_models(random_state: int) -> dict[str, Any]:
    from lightgbm import LGBMClassifier
    from xgboost import XGBClassifier

    return {
        "RandomForest": RandomForestClassifier(
            n_estimators=200, random_state=random_state, n_jobs=-1
        ),
        "XGBoost": XGBClassifier(
            n_estimators=200,
            random_state=random_state,
            n_jobs=-1,
            eval_metric="logloss",
            verbosity=0,
            use_label_encoder=False,
        ),
        "LightGBM": LGBMClassifier(
            n_estimators=200, random_state=random_state, n_jobs=-1, verbose=-1
        ),
        "LogisticRegression": LogisticRegression(
            max_iter=1000, random_state=random_state, n_jobs=-1
        ),
    }


def _regression_models(random_state: int) -> dict[str, Any]:
    from lightgbm import LGBMRegressor
    from xgboost import XGBRegressor

    return {
        "RandomForest": RandomForestRegressor(
            n_estimators=200, random_state=random_state, n_jobs=-1
        ),
        "XGBoost": XGBRegressor(
            n_estimators=200,
            random_state=random_state,
            n_jobs=-1,
            verbosity=0,
        ),
        "LightGBM": LGBMRegressor(
            n_estimators=200, random_state=random_state, n_jobs=-1, verbose=-1
        ),
        "Ridge": Ridge(random_state=random_state),
    }


def _train_one(
    name: str,
    estimator: Any,
    preprocessor: ColumnTransformer,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    problem: str,
    cv: int,
) -> dict[str, Any]:
    pipe = Pipeline([("pre", preprocessor), ("model", estimator)])
    t0 = time.time()
    scoring = "f1_weighted" if problem == "classification" else "r2"
    try:
        cv_scores = cross_val_score(pipe, X_train, y_train, cv=cv, scoring=scoring, n_jobs=-1)
        pipe.fit(X_train, y_train)
        preds = pipe.predict(X_test)
        if problem == "classification":
            metrics = {
                "accuracy": float(accuracy_score(y_test, preds)),
                "f1": float(
                    f1_score(
                        y_test,
                        preds,
                        average="binary" if pd.Series(y_train).nunique() <= 2 else "weighted",
                        zero_division=0,
                    )
                ),
                "primary": "f1",
            }
        else:
            metrics = {
                "rmse": float(np.sqrt(mean_squared_error(y_test, preds))),
                "r2": float(r2_score(y_test, preds)),
                "primary": "r2",
            }
        return {
            "model": name,
            "cv_mean": float(cv_scores.mean()),
            "cv_std": float(cv_scores.std()),
            "metrics": metrics,
            "train_seconds": round(time.time() - t0, 3),
            "pipeline": pipe,
            "error": None,
        }
    except Exception as exc:
        return {
            "model": name,
            "cv_mean": None,
            "cv_std": None,
            "metrics": {},
            "train_seconds": round(time.time() - t0, 3),
            "pipeline": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _optuna_tune(
    best_name: str,
    preprocessor: ColumnTransformer,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    problem: str,
    budget_seconds: int,
    random_state: int,
) -> dict[str, Any]:
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: optuna.Trial) -> float:
        if best_name in ("RandomForest",):
            from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

            params = {
                "n_estimators": trial.suggest_int("n_estimators", 100, 600),
                "max_depth": trial.suggest_int("max_depth", 3, 30),
                "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
                "random_state": random_state,
                "n_jobs": -1,
            }
            est = (
                RandomForestClassifier(**params)
                if problem == "classification"
                else RandomForestRegressor(**params)
            )
        elif best_name == "XGBoost":
            from xgboost import XGBClassifier, XGBRegressor

            params = {
                "n_estimators": trial.suggest_int("n_estimators", 100, 600),
                "max_depth": trial.suggest_int("max_depth", 3, 12),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
                "random_state": random_state,
                "n_jobs": -1,
                "verbosity": 0,
            }
            est = XGBClassifier(**params) if problem == "classification" else XGBRegressor(**params)
        elif best_name == "LightGBM":
            from lightgbm import LGBMClassifier, LGBMRegressor

            params = {
                "n_estimators": trial.suggest_int("n_estimators", 100, 600),
                "num_leaves": trial.suggest_int("num_leaves", 15, 127),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "feature_fraction": trial.suggest_float("feature_fraction", 0.6, 1.0),
                "random_state": random_state,
                "n_jobs": -1,
                "verbose": -1,
            }
            est = (
                LGBMClassifier(**params)
                if problem == "classification"
                else LGBMRegressor(**params)
            )
        else:
            return float("-inf")

        pipe = Pipeline([("pre", preprocessor), ("model", est)])
        scoring = "f1_weighted" if problem == "classification" else "r2"
        scores = cross_val_score(pipe, X_train, y_train, cv=3, scoring=scoring, n_jobs=-1)
        return float(scores.mean())

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=random_state))
    study.optimize(objective, timeout=budget_seconds, show_progress_bar=False, n_jobs=1)
    return {
        "n_trials": len(study.trials),
        "best_value": float(study.best_value),
        "best_params": study.best_params,
    }


def run_model_bake_off_sync(
    file_path: str,
    target_column: str,
    tune_budget_mins: int = 0,
    test_size: float = 0.2,
    random_state: int = 42,
    cv: int = 3,
) -> dict[str, Any]:
    path = resolve_upload_file(file_path)
    df = pd.read_csv(path).dropna(subset=[target_column])
    if target_column not in df.columns:
        raise ValueError(f"Target '{target_column}' not in dataset.")

    problem = detect_problem_type(file_path, target_column)["problem_type"]
    y_raw = df[target_column]
    X = df.drop(columns=[target_column])

    if problem == "classification" and not pd.api.types.is_numeric_dtype(y_raw):
        le = LabelEncoder()
        y = pd.Series(le.fit_transform(y_raw.astype(str)), index=y_raw.index)
    else:
        y = y_raw

    preprocessor = _build_preprocessor(X)
    stratify = y if problem == "classification" and y.nunique() > 1 and y.value_counts().min() >= 2 else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=stratify
    )

    candidates = (
        _classification_models(random_state)
        if problem == "classification"
        else _regression_models(random_state)
    )

    leaderboard: list[dict[str, Any]] = []
    pipelines: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=min(4, len(candidates))) as ex:
        futures = {
            ex.submit(
                _train_one, name, est, preprocessor, X_train, y_train, X_test, y_test, problem, cv
            ): name
            for name, est in candidates.items()
        }
        for fut in as_completed(futures):
            row = fut.result()
            if row["pipeline"] is not None:
                pipelines[row["model"]] = row["pipeline"]
            leaderboard.append(
                {k: v for k, v in row.items() if k != "pipeline"}
            )

    primary_key = "f1" if problem == "classification" else "r2"
    leaderboard.sort(
        key=lambda r: (r["metrics"].get(primary_key) if r["error"] is None else -1e9),
        reverse=True,
    )

    valid = [r for r in leaderboard if r["error"] is None]
    if not valid:
        raise RuntimeError("All candidate models failed to train.")

    champion_name = valid[0]["model"]
    tuning_summary: dict[str, Any] | None = None
    if tune_budget_mins > 0 and champion_name in {"RandomForest", "XGBoost", "LightGBM"}:
        tuning_summary = _optuna_tune(
            champion_name,
            preprocessor,
            X_train,
            y_train,
            problem,
            budget_seconds=tune_budget_mins * 60,
            random_state=random_state,
        )

    ts = int(time.time())
    stem = path.stem.replace(" ", "_")
    model_name = f"champion_{stem}_{ts}.joblib"
    model_path = settings.models_path / model_name
    joblib.dump(
        {
            "pipeline": pipelines[champion_name],
            "feature_columns": X_train.columns.tolist(),
            "problem_type": problem,
            "target_column": target_column,
        },
        model_path,
    )

    # Persist X_train sample for later SHAP use
    sample_name = f"xtrain_{stem}_{ts}.parquet"
    sample_path = settings.models_path / sample_name
    X_train.head(500).to_parquet(sample_path)

    return {
        "file": path.name,
        "target_column": target_column,
        "problem_type": problem,
        "leaderboard": leaderboard,
        "champion_model": champion_name,
        "tuning": tuning_summary,
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "model_file": model_name,
        "model_artifact_path": str(model_path),
        "x_train_sample_path": str(sample_path),
    }