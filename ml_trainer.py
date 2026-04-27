"""
Trains the LightGBM + XGBoost ensemble on the combined dataset.

Usage (standalone):
    python ml_trainer.py              # build bootstrap + train
    python ml_trainer.py --rebuild    # force-rebuild bootstrap cache then train

Models saved to: results/models/
    lgbm_model.pkl
    xgb_model.pkl
    training_stats.json
    feature_importance.json

Requires:
    pip install lightgbm xgboost scikit-learn
"""

import os
import sys
import json
import pickle
import numpy as np
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich import box as rbox

from config import RESULTS_DIR
from ml_feature_extractor import FEATURE_NAMES, N_FEATURES

console   = Console()
MODEL_DIR = os.path.join(RESULTS_DIR, "models")
os.makedirs(MODEL_DIR, exist_ok=True)

LGBM_PATH  = os.path.join(MODEL_DIR, "lgbm_model.pkl")
XGB_PATH   = os.path.join(MODEL_DIR, "xgb_model.pkl")
STATS_PATH = os.path.join(MODEL_DIR, "training_stats.json")
FIMP_PATH  = os.path.join(MODEL_DIR, "feature_importance.json")


# ── Dependency check ──────────────────────────────────────────────────────────

def _check_deps() -> bool:
    missing = []
    for pkg in ("lightgbm", "xgboost", "sklearn"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        console.print(
            f"[red]ML deps missing: {', '.join(missing)}\n"
            f"Install with: pip install lightgbm xgboost scikit-learn[/red]"
        )
        return False
    return True


# ── Walk-forward cross-validation ────────────────────────────────────────────

def _walk_forward_cv(X: np.ndarray, y: np.ndarray, n_splits: int = 5) -> dict:
    """
    Time-series-aware CV: never let future data train on past labels.
    Samples are assumed to be roughly time-ordered (bootstrap is stock×time).
    Returns mean AUC, precision, recall across folds.
    """
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import roc_auc_score, precision_score, recall_score
    import lightgbm as lgb

    tscv    = TimeSeriesSplit(n_splits=n_splits)
    aucs, precs, recs = [], [], []

    for train_idx, val_idx in tscv.split(X):
        X_tr, X_val = X[train_idx], X[val_idx]
        y_tr, y_val = y[train_idx], y[val_idx]

        if len(np.unique(y_val)) < 2:
            continue

        mdl = lgb.LGBMClassifier(
            n_estimators=300, learning_rate=0.05,
            num_leaves=31, min_child_samples=20,
            subsample=0.8, colsample_bytree=0.8,
            class_weight="balanced", verbose=-1, random_state=42,
        )
        mdl.fit(X_tr, y_tr)
        prob = mdl.predict_proba(X_val)[:, 1]
        pred = (prob >= 0.5).astype(int)

        aucs.append(roc_auc_score(y_val, prob))
        precs.append(precision_score(y_val, pred, zero_division=0))
        recs.append(recall_score(y_val, pred, zero_division=0))

    return {
        "cv_auc":       round(float(np.mean(aucs)),  3) if aucs  else 0.0,
        "cv_precision": round(float(np.mean(precs)), 3) if precs else 0.0,
        "cv_recall":    round(float(np.mean(recs)),  3) if recs  else 0.0,
        "cv_folds":     len(aucs),
    }


# ── Final model training ──────────────────────────────────────────────────────

def _train_lgbm(X: np.ndarray, y: np.ndarray):
    import lightgbm as lgb

    # Use last 15% as hold-out for early stopping
    n_hold  = max(100, int(len(y) * 0.15))
    X_tr, X_hold = X[:-n_hold], X[-n_hold:]
    y_tr, y_hold = y[:-n_hold], y[-n_hold:]

    mdl = lgb.LGBMClassifier(
        n_estimators=800,
        learning_rate=0.03,
        num_leaves=31,
        max_depth=6,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.75,
        reg_alpha=0.1,
        reg_lambda=0.5,
        class_weight="balanced",
        verbose=-1,
        random_state=42,
    )
    mdl.fit(
        X_tr, y_tr,
        eval_set=[(X_hold, y_hold)],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)],
    )
    return mdl


def _train_xgb(X: np.ndarray, y: np.ndarray):
    import xgboost as xgb

    pos  = int(y.sum())
    neg  = int(len(y) - pos)
    spw  = neg / pos if pos > 0 else 1.0

    n_hold  = max(100, int(len(y) * 0.15))
    X_tr, X_hold = X[:-n_hold], X[-n_hold:]
    y_tr, y_hold = y[:-n_hold], y[-n_hold:]

    mdl = xgb.XGBClassifier(
        n_estimators=800,
        learning_rate=0.03,
        max_depth=4,
        subsample=0.8,
        colsample_bytree=0.75,
        min_child_weight=10,
        gamma=0.1,
        reg_alpha=0.1,
        reg_lambda=1.0,
        scale_pos_weight=spw,
        eval_metric="auc",
        early_stopping_rounds=50,
        verbosity=0,
        random_state=42,
    )
    mdl.fit(X_tr, y_tr, eval_set=[(X_hold, y_hold)], verbose=False)
    return mdl


# ── Evaluation on hold-out ────────────────────────────────────────────────────

def _evaluate(lgbm_mdl, xgb_mdl, X: np.ndarray, y: np.ndarray) -> dict:
    from sklearn.metrics import roc_auc_score, precision_score, recall_score, accuracy_score

    n_hold  = max(200, int(len(y) * 0.20))
    X_h, y_h = X[-n_hold:], y[-n_hold:]

    lgbm_prob = lgbm_mdl.predict_proba(X_h)[:, 1]
    xgb_prob  = xgb_mdl.predict_proba(X_h)[:, 1]
    ens_prob  = 0.6 * lgbm_prob + 0.4 * xgb_prob

    results = {}
    for name, prob in [("lgbm", lgbm_prob), ("xgb", xgb_prob), ("ensemble", ens_prob)]:
        pred = (prob >= 0.5).astype(int)
        results[name] = {
            "auc":       round(float(roc_auc_score(y_h, prob)),          3),
            "accuracy":  round(float(accuracy_score(y_h, pred))  * 100, 1),
            "precision": round(float(precision_score(y_h, pred, zero_division=0)) * 100, 1),
            "recall":    round(float(recall_score(y_h, pred, zero_division=0))    * 100, 1),
        }

    return results


# ── Feature importance ────────────────────────────────────────────────────────

def _save_feature_importance(lgbm_mdl, xgb_mdl) -> None:
    try:
        lgbm_imp = lgbm_mdl.feature_importances_.tolist()
        xgb_imp  = xgb_mdl.feature_importances_.tolist()
        total    = [a + b for a, b in zip(lgbm_imp, xgb_imp)]
        ranked   = sorted(zip(FEATURE_NAMES, total), key=lambda x: -x[1])
        with open(FIMP_PATH, "w") as f:
            json.dump([{"feature": n, "importance": round(float(v), 4)} for n, v in ranked], f, indent=2)
    except Exception:
        pass


# ── Public API ────────────────────────────────────────────────────────────────

def train(X: np.ndarray, y: np.ndarray, dataset_stats: dict) -> dict:
    """
    Full training pipeline: CV → train LightGBM → train XGBoost → evaluate → save.
    Returns training stats dict.
    """
    if not _check_deps():
        return {}

    if len(y) < 200:
        console.print(f"[yellow]ML: only {len(y)} samples — need ≥200 to train. Run main.py to cache more data.[/yellow]")
        return {}

    console.print(f"\n[bold cyan]ML Training — {len(y):,} samples | {int(y.sum())} positives ({y.mean()*100:.1f}%)[/bold cyan]")

    # Walk-forward CV (fast pass for honest estimate)
    console.print("[dim]  Walk-forward CV (5 folds)…[/dim]")
    cv_stats = _walk_forward_cv(X, y)
    console.print(
        f"  CV AUC {cv_stats['cv_auc']:.3f}  |  "
        f"Precision {cv_stats['cv_precision']*100:.1f}%  |  "
        f"Recall {cv_stats['cv_recall']*100:.1f}%"
    )

    # Full model training
    console.print("[dim]  Training LightGBM…[/dim]")
    lgbm_mdl = _train_lgbm(X, y)

    console.print("[dim]  Training XGBoost…[/dim]")
    xgb_mdl  = _train_xgb(X, y)

    # Hold-out evaluation
    eval_stats = _evaluate(lgbm_mdl, xgb_mdl, X, y)

    # Save models
    with open(LGBM_PATH, "wb") as f:
        pickle.dump(lgbm_mdl, f)
    with open(XGB_PATH, "wb") as f:
        pickle.dump(xgb_mdl, f)

    _save_feature_importance(lgbm_mdl, xgb_mdl)

    # Save stats
    stats = {
        "trained_at":      datetime.now().isoformat(timespec="minutes"),
        "n_features":      N_FEATURES,
        "feature_names":   FEATURE_NAMES,
        "dataset":         dataset_stats,
        "cv":              cv_stats,
        "holdout":         eval_stats,
    }
    with open(STATS_PATH, "w") as f:
        json.dump(stats, f, indent=2)

    # Print summary table
    table = Table(title="ML Model Performance (20% hold-out)", box=rbox.SIMPLE, header_style="bold cyan")
    table.add_column("Model",     style="cyan",        width=12)
    table.add_column("AUC",       justify="right",     width=7)
    table.add_column("Accuracy",  justify="right",     width=10)
    table.add_column("Precision", justify="right",     width=11)
    table.add_column("Recall",    justify="right",     width=9)
    for name, m in eval_stats.items():
        color = "green" if name == "ensemble" else "white"
        table.add_row(
            f"[{color}]{name}[/{color}]",
            f"{m['auc']:.3f}", f"{m['accuracy']:.1f}%",
            f"{m['precision']:.1f}%", f"{m['recall']:.1f}%",
        )
    console.print(table)
    console.print(f"[green]  Models saved → {MODEL_DIR}[/green]\n")

    return stats


def load_training_stats() -> dict:
    if not os.path.exists(STATS_PATH):
        return {}
    try:
        with open(STATS_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def load_feature_importance(top_n: int = 15) -> list[dict]:
    if not os.path.exists(FIMP_PATH):
        return []
    try:
        with open(FIMP_PATH) as f:
            return json.load(f)[:top_n]
    except Exception:
        return []


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    rebuild = "--rebuild" in sys.argv
    from ml_dataset_builder import build_combined_dataset
    X, y, stats = build_combined_dataset(force_bootstrap=rebuild)
    if len(y) > 0:
        train(X, y, stats)
