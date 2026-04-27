"""
Daily ML retraining orchestrator.

Called from main.py after each full analysis run.
Checks if enough new resolved predictions exist to justify retraining,
builds the combined dataset, trains models, and reloads the predictor.

Standalone usage:
    python ml_retrainer.py            # retrain with current data
    python ml_retrainer.py --force    # force retrain + rebuild bootstrap
"""

import os
import sys
import json
from datetime import datetime, date
from rich.console import Console

from config import RESULTS_DIR
from ml_dataset_builder import build_combined_dataset
from ml_trainer import train, load_training_stats, load_feature_importance

console      = Console()
STATS_PATH   = os.path.join(RESULTS_DIR, "models", "training_stats.json")
MIN_NEW_PREDS = 3   # only retrain when ≥ this many NEW resolved predictions exist


def _count_new_resolved_since_last_train() -> int:
    """
    Counts resolved prediction-log entries logged after the last training run.
    Returns a large number if never trained (force first training).
    """
    stats = load_training_stats()
    if not stats:
        return 9999   # never trained → always retrain

    last_train = stats.get("trained_at", "")
    if not last_train:
        return 9999

    try:
        last_dt = datetime.fromisoformat(last_train)
    except Exception:
        return 9999

    log_path = os.path.join(RESULTS_DIR, "prediction_log.json")
    if not os.path.exists(log_path):
        return 0

    with open(log_path) as f:
        log = json.load(f)

    new_resolved = 0
    for p in log.get("predictions", []):
        if p["status"] not in ("target_hit", "stop_hit"):
            continue
        resolved_date = p.get("resolved_date") or ""
        if not resolved_date:
            continue
        try:
            rd = datetime.fromisoformat(resolved_date)
            if rd > last_dt:
                new_resolved += 1
        except Exception:
            continue

    return new_resolved


def run_daily_retrain(force: bool = False, force_bootstrap: bool = False) -> dict:
    """
    Main entry point called from main.py.
    Returns stats dict (empty if skipped).
    """
    new_preds = _count_new_resolved_since_last_train()

    if not force and new_preds < MIN_NEW_PREDS:
        console.print(
            f"[dim]ML: {new_preds} new resolved prediction(s) since last train "
            f"(need {MIN_NEW_PREDS}) — skipping retrain[/dim]"
        )
        return {}

    if new_preds == 9999:
        console.print("[cyan]ML: first-time training — building bootstrap dataset…[/cyan]")
    else:
        console.print(f"[cyan]ML: {new_preds} new resolved predictions — retraining…[/cyan]")

    X, y, dataset_stats = build_combined_dataset(force_bootstrap=force_bootstrap)

    if len(y) < 200:
        console.print(f"[yellow]ML: only {len(y)} total samples — skipping (need ≥200)[/yellow]")
        return {}

    stats = train(X, y, dataset_stats)

    if stats:
        # Reload predictor so next scoring run uses the fresh models immediately
        try:
            from ml_predictor import reload_models
            reload_models()
        except Exception:
            pass

        _print_feature_importance()

    return stats


def _print_feature_importance() -> None:
    top = load_feature_importance(top_n=10)
    if not top:
        return
    console.print("[dim]  Top ML features:[/dim]")
    for i, item in enumerate(top, 1):
        bar = "█" * int(item["importance"] / max(top[0]["importance"], 1) * 20)
        console.print(f"  [dim]{i:2}. {item['feature']:<22} {bar}[/dim]")


def print_ml_status(console_obj=None) -> None:
    """
    Print a one-line ML status summary (used in main.py banner).
    """
    c = console_obj or console
    stats = load_training_stats()
    if not stats:
        c.print("[dim]ML Engine: not trained yet — will train after first analysis run[/dim]")
        return

    trained_at = stats.get("trained_at", "unknown")
    ds         = stats.get("dataset", {})
    ens        = stats.get("holdout", {}).get("ensemble", {})
    n_samples  = ds.get("total_samples", 0)
    auc        = ens.get("auc", 0)
    accuracy   = ens.get("accuracy", 0)
    precision  = ens.get("precision", 0)

    color = "green" if auc >= 0.65 else ("yellow" if auc >= 0.58 else "red")
    c.print(
        f"[bold cyan]ML Engine:[/bold cyan] "
        f"[{color}]AUC {auc:.3f} | Acc {accuracy:.1f}% | Precision {precision:.1f}%[/{color}]  "
        f"| {n_samples:,} training samples | trained {trained_at[:10]}"
    )


# ── Standalone entry ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    force          = "--force"     in sys.argv
    force_boot     = "--rebuild"   in sys.argv
    run_daily_retrain(force=force or True, force_bootstrap=force_boot)
