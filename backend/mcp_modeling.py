"""Unisole Empower — Parallel AutoML Engine Microservice (Port 8003)

Responsibilities:
  - `run_parallel_bake_off`: RandomForest vs XGBoost vs LightGBM CV race.
  - `trigger_hyperparameter_sweep`: Optuna study with time-bound budget.

Transport: streamable-http on http://127.0.0.1:8003/mcp
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from fastmcp import Context, FastMCP
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

warnings.filterwarnings("ignore")

SERVICE_NAME = "mcp-modeling"
SERVICE_PORT = 8003
BACKEND_ROOT = Path(__file__).resolve().parent
UPLOAD_DIR = (BACKEND_ROOT / "uploads").resolve()
MODELS_DIR = (BACKEND_ROOT / "outputs" / "models").resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | mcp_modeling | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(SERVICE_NAME)

mcp = FastMCP(name=SERVICE_NAME)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _resolve(file_path: str) -> Path:
    raw = Path(file_path)
    candidate = (raw if raw.is_absolute() else (UPLOAD_DIR / raw.name)).resolve()
    candidate.relative_to(UPLOAD_DIR)
    if not candidate.exists():
        raise FileNotFoundError(f"Not found: {candidate}")
    return candidate


def _load(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".csv", ".tsv"}:
        return pd.read_csv(path)
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported extension: {path.suffix}")


def _detect_problem(target: pd.Series) -> str:
    target = target.dropna()
    is_numeric = pd.api.types.is_numeric_dtype(target)
    unique = int(target.nunique())
    if not is_numeric:
        return "classification"
    return "classification" if unique <= max(20, int(len(target) * 0.05)) else "regression"


def _build_preprocessor(X: pd.DataFrame) -> ColumnTransformer:
    num = X.select_dtypes(include="number").columns.tolist()
    cat = X.select_dtypes(include=["object", "category", "bool"]).columns.tolist()
    transformers: list[Any] = []
    if num:
        transformers.append(
            (
                "num",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="median")),
                        ("scale", StandardScaler()),
                    ]
                ),
                num,
            )
        )
    if cat:
        transformers.append(
            (
                "cat",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("ohe", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                    ]
                ),
                cat,
            )
        )
    if not transformers:
        raise ValueError("No usable feature columns.")
    return ColumnTransformer(transformers=transformers, remainder="drop")


def _candidates(problem: str, seed: int) -> dict[str, Any]:
    from lightgbm import LGBMClassifier, LGBMRegressor
    from xgboost import XGBClassifier, XGBRegressor

    if problem == "classification":
        return {
            "RandomForest": RandomForestClassifier(n_estimators=200, random_state=seed, n_jobs=-1),
            "XGBoost": XGBClassifier(
                n_estimators=200, random_state=seed, n_jobs=-1,
                eval_metric="logloss", verbosity=0,
            ),
            "LightGBM": LGBMClassifier(n_estimators=200, random_state=seed, n_jobs=-1, verbose=-1),
            "LogisticRegression": LogisticRegression(max_iter=1000, random_state=seed, n_jobs=-1),
        }
    return {
        "RandomForest": RandomForestRegressor(n_estimators=200, random_state=seed, n_jobs=-1),
        "XGBoost": XGBRegressor(n_estimators=200, random_state=seed, n_jobs=-1, verbosity=0),
        "LightGBM": LGBMRegressor(n_estimators=200, random_state=seed, n_jobs=-1, verbose=-1),
        "Ridge": Ridge(random_state=seed),
    }


def _train_one(
    name: str,
    estimator: Any,
    pre: ColumnTransformer,
    Xtr: pd.DataFrame,
    ytr: pd.Series,
    Xte: pd.DataFrame,
    yte: pd.Series,
    problem: str,
    cv: int,
) -> dict[str, Any]:
    pipe = Pipeline([("pre", pre), ("model", estimator)])
    t0 = time.time()
    scoring = "f1_weighted" if problem == "classification" else "r2"
    try:
        cv_scores = cross_val_score(pipe, Xtr, ytr, cv=cv, scoring=scoring, n_jobs=-1)
        pipe.fit(Xtr, ytr)
        preds = pipe.predict(Xte)
        if problem == "classification":
            metrics = {
                "accuracy": float(accuracy_score(yte, preds)),
                "f1": float(
                    f1_score(
                        yte, preds,
                        average="binary" if pd.Series(ytr).nunique() <= 2 else "weighted",
                        zero_division=0,
                    )
                ),
                "primary_metric": "f1",
            }
        else:
            metrics = {
                "rmse": float(np.sqrt(mean_squared_error(yte, preds))),
                "r2": float(r2_score(yte, preds)),
                "primary_metric": "r2",
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


# ----------------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------------
@mcp.tool
async def run_parallel_bake_off(
    file_path: str,
    target_column: str,
    ctx: Context,
    test_size: float = 0.2,
    cv: int = 3,
    random_state: int = 42,
) -> dict[str, Any]:
    """Parallel CV race across RandomForest, XGBoost, LightGBM, and a baseline.

    Args:
        file_path: Filename of the uploaded dataset.
        target_column: Name of the target column.
        test_size: Holdout fraction (default 0.2).
        cv: Number of CV folds (default 3).
        random_state: Seed.
    """
    path = _resolve(file_path)
    df = _load(path).dropna(subset=[target_column])
    if target_column not in df.columns:
        return {"error": f"Target '{target_column}' missing", "columns": list(df.columns)}

    problem = _detect_problem(df[target_column])
    await ctx.info(f"Detected problem type: {problem}")
    await ctx.report_progress(5, 100, f"{problem} task on {path.name}")

    y_raw = df[target_column]
    X = df.drop(columns=[target_column])

    if problem == "classification" and not pd.api.types.is_numeric_dtype(y_raw):
        le = LabelEncoder()
        y = pd.Series(le.fit_transform(y_raw.astype(str)), index=y_raw.index)
    else:
        y = y_raw

    pre = _build_preprocessor(X)
    stratify = y if problem == "classification" and y.nunique() > 1 and y.value_counts().min() >= 2 else None
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=stratify
    )

    candidates = _candidates(problem, random_state)
    await ctx.info(f"Training {len(candidates)} models in parallel")
    await ctx.report_progress(15, 100, "Spawning thread pool")

    leaderboard: list[dict[str, Any]] = []
    pipelines: dict[str, Any] = {}

    loop = asyncio.get_running_loop()

    def _runner() -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        pipes: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=min(4, len(candidates))) as ex:
            futures = {
                ex.submit(_train_one, n, e, pre, Xtr, ytr, Xte, yte, problem, cv): n
                for n, e in candidates.items()
            }
            for fut in as_completed(futures):
                row = fut.result()
                if row["pipeline"] is not None:
                    pipes[row["model"]] = row["pipeline"]
                rows.append({k: v for k, v in row.items() if k != "pipeline"})
        return rows, pipes

    task = loop.run_in_executor(None, _runner)
    ticks = 0
    while not task.done():
        await asyncio.sleep(2.0)
        ticks += 1
        pct = min(15 + ticks * 8, 80)
        await ctx.report_progress(pct, 100, f"Training… ({ticks * 2}s elapsed)")

    leaderboard, pipelines = await task

    primary = "f1" if problem == "classification" else "r2"
    leaderboard.sort(
        key=lambda r: (r["metrics"].get(primary) if r["error"] is None else -1e9),
        reverse=True,
    )
    valid = [r for r in leaderboard if r["error"] is None]
    if not valid:
        return {"error": "All candidate models failed.", "leaderboard": leaderboard}

    champion = valid[0]["model"]
    await ctx.info(f"Champion: {champion}")
    await ctx.report_progress(90, 100, "Persisting champion artifact")

    ts = int(time.time())
    stem = path.stem.replace(" ", "_")
    model_name = f"champion_{stem}_{ts}.joblib"
    model_path = MODELS_DIR / model_name
    joblib.dump(
        {
            "pipeline": pipelines[champion],
            "feature_columns": Xtr.columns.tolist(),
            "problem_type": problem,
            "target_column": target_column,
            "champion_name": champion,
        },
        model_path,
    )

    sample_name = f"xtrain_{stem}_{ts}.parquet"
    sample_path = MODELS_DIR / sample_name
    Xtr.head(500).to_parquet(sample_path)

    await ctx.report_progress(100, 100, "Bake-off complete")
    return {
        "file": path.name,
        "target_column": target_column,
        "problem_type": problem,
        "leaderboard": leaderboard,
        "champion_model": champion,
        "model_id": model_name.replace(".joblib", ""),
        "model_file": model_name,
        "model_artifact_path": str(model_path),
        "x_train_sample_path": str(sample_path),
        "n_train": int(len(Xtr)),
        "n_test": int(len(Xte)),
    }


@mcp.tool
async def trigger_hyperparameter_sweep(
    file_path: str,
    target_column: str,
    model_family: str,
    ctx: Context,
    time_budget_seconds: int = 60,
    cv: int = 3,
    random_state: int = 42,
) -> dict[str, Any]:
    """Optuna TPE sweep with a time-bound budget. Returns best params + score.

    Args:
        file_path: Filename of the dataset.
        target_column: Target column.
        model_family: One of `RandomForest`, `XGBoost`, `LightGBM`.
        time_budget_seconds: Hard wall-clock budget (default 60s).
        cv: CV folds inside the objective (default 3).
        random_state: TPE seed.
    """
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    family = model_family.strip()
    if family not in {"RandomForest", "XGBoost", "LightGBM"}:
        return {"error": f"Unsupported model_family: {family}"}

    path = _resolve(file_path)
    df = _load(path).dropna(subset=[target_column])
    problem = _detect_problem(df[target_column])
    y_raw = df[target_column]
    X = df.drop(columns=[target_column])
    if problem == "classification" and not pd.api.types.is_numeric_dtype(y_raw):
        y = pd.Series(LabelEncoder().fit_transform(y_raw.astype(str)), index=y_raw.index)
    else:
        y = y_raw

    pre = _build_preprocessor(X)
    await ctx.info(f"Starting {time_budget_seconds}s Optuna sweep on {family}")
    await ctx.report_progress(5, 100, "Configuring sampler")

    def objective(trial: optuna.Trial) -> float:
        if family == "RandomForest":
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 100, 600),
                "max_depth": trial.suggest_int("max_depth", 3, 30),
                "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
                "random_state": random_state,
                "n_jobs": -1,
            }
            est: Any = (
                RandomForestClassifier(**params)
                if problem == "classification"
                else RandomForestRegressor(**params)
            )
        elif family == "XGBoost":
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
        else:  # LightGBM
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
        pipe = Pipeline([("pre", pre), ("model", est)])
        scoring = "f1_weighted" if problem == "classification" else "r2"
        scores = cross_val_score(pipe, X, y, cv=cv, scoring=scoring, n_jobs=-1)
        return float(scores.mean())

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=random_state),
    )

    loop = asyncio.get_running_loop()
    task = loop.run_in_executor(
        None,
        lambda: study.optimize(
            objective, timeout=time_budget_seconds, show_progress_bar=False, n_jobs=1
        ),
    )

    elapsed = 0
    while not task.done():
        await asyncio.sleep(2.0)
        elapsed += 2
        pct = min(5 + int(85 * elapsed / max(time_budget_seconds, 1)), 90)
        await ctx.report_progress(pct, 100, f"Trial {len(study.trials)} — best so far: {study.best_value:.4f}" if study.trials else f"Warming up… ({elapsed}s)")

    await task
    await ctx.report_progress(100, 100, "Sweep complete")
    return {
        "model_family": family,
        "problem_type": problem,
        "target_column": target_column,
        "n_trials": len(study.trials),
        "best_value": float(study.best_value),
        "best_params": study.best_params,
        "time_budget_seconds": time_budget_seconds,
    }


if __name__ == "__main__":
    log.info("Starting %s on http://127.0.0.1:%d/mcp", SERVICE_NAME, SERVICE_PORT)
    mcp.run(transport="streamable-http", host="127.0.0.1", port=SERVICE_PORT)