"""
Builds ML training datasets from two sources:

1. Bootstrap  — slides through 3 years of cached OHLCV for every universe stock.
   Generates ~20-25k labelled samples without waiting for live predictions.
   Label: price rose ≥3% in 10 trading days AND never hit ATR-based stop first.

2. Prediction log — converts resolved accuracy-tracker entries into labelled rows.
   Each resolved prediction had its features saved alongside it; these rows are
   weighted 3× relative to bootstrap (real-market feedback matters more).

Output: (X: np.ndarray, y: np.ndarray, meta: list[dict])
  X shape: (n_samples, N_FEATURES)
  y shape: (n_samples,) — binary 0/1
  meta: list of {'symbol', 'date', 'source'} for debugging
"""

import os
import pickle
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
from rich.console import Console

from config import STOCK_UNIVERSE, DATA_CACHE_DIR, RESULTS_DIR
from technical_analysis import add_indicators, calc_52w_stats
from ml_feature_extractor import extract_features, N_FEATURES

console = Console()

PREDICTION_LOG   = os.path.join(RESULTS_DIR, "prediction_log.json")
BOOTSTRAP_CACHE  = os.path.join(RESULTS_DIR, "ml_bootstrap_cache.pkl")
BOOTSTRAP_STRIDE = 5     # sample every N trading days (reduces correlation between samples)
FORWARD_DAYS     = 10    # label horizon: 10 trading days (~2 weeks)
TARGET_RETURN    = 0.03  # 3% move = "success"
STOP_ATR_MULT    = 2.5   # stop = entry - 2.5 × ATR (matches stock_scorer)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_pkl(path: str) -> Optional[pd.DataFrame]:
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _cache_path(symbol: str) -> str:
    safe = symbol.replace(".", "_").replace("^", "").replace("&", "AND")
    return os.path.join(DATA_CACHE_DIR, f"{safe}.pkl")


def _approx_regime(lat: dict) -> str:
    """Fast regime approximation from a single indicator row — avoids Nifty fetch."""
    ema20  = lat.get("ema20",  0)
    ema50  = lat.get("ema50",  0)
    ema200 = lat.get("ema200", 0)
    macd   = lat.get("macd",   0)
    macd_s = lat.get("macd_signal", 0)
    close  = lat.get("close",  0)
    if ema20 > ema50 > ema200 and macd > macd_s:
        return "STRONG_BULL" if close > ema200 * 1.05 else "BULL"
    if close < ema200 and macd < macd_s:
        return "BEAR"
    return "SIDEWAYS"


def _label_forward(df_ind: pd.DataFrame, i: int) -> int:
    """
    Compute binary label at bar index i.
    Returns 1 if price reaches +3% before hitting ATR stop within 10 bars.
    """
    entry  = float(df_ind.iloc[i]["close"])
    atr    = float(df_ind.iloc[i]["atr"])
    stop   = entry - STOP_ATR_MULT * atr
    target = entry * (1 + TARGET_RETURN)

    future = df_ind.iloc[i + 1: i + 1 + FORWARD_DAYS]
    for _, row in future.iterrows():
        lo = float(row["low"])
        hi = float(row["high"])
        if lo <= stop:        # stop hit first
            return 0
        if hi >= target:      # target hit
            return 1
    return 0                  # neither within window


# ── Bootstrap dataset ─────────────────────────────────────────────────────────

def build_bootstrap_dataset(force_rebuild: bool = False) -> tuple[np.ndarray, np.ndarray, list]:
    """
    Build / load the bootstrap dataset.
    Cached to disk so it only runs once (or when force_rebuild=True).
    Returns (X, y, meta).
    """
    if not force_rebuild and os.path.exists(BOOTSTRAP_CACHE):
        try:
            with open(BOOTSTRAP_CACHE, "rb") as f:
                data = pickle.load(f)
            console.print(f"[dim]ML bootstrap: loaded {len(data['y'])} cached samples[/dim]")
            return data["X"], data["y"], data["meta"]
        except Exception:
            pass

    console.print("[cyan]ML bootstrap: building training dataset from price cache (one-time)…[/cyan]")

    X_rows, y_rows, meta = [], [], []
    skipped = 0

    for sym in STOCK_UNIVERSE:
        path = _cache_path(sym)
        if not os.path.exists(path):
            skipped += 1
            continue

        df_raw = _load_pkl(path)
        if df_raw is None or len(df_raw) < 230:
            skipped += 1
            continue

        try:
            df_ind = add_indicators(df_raw)
        except Exception:
            skipped += 1
            continue

        if len(df_ind) < 220:
            skipped += 1
            continue

        # Slide through history, sampling every BOOTSTRAP_STRIDE bars
        # Start at 200 (warmup), stop FORWARD_DAYS before end
        n = len(df_ind)
        indices = range(200, n - FORWARD_DAYS, BOOTSTRAP_STRIDE)

        sym_added = 0
        for i in indices:
            try:
                df_slice = df_ind.iloc[:i + 1]
                lat      = df_ind.iloc[i].to_dict()

                regime_str = _approx_regime(lat)

                try:
                    stats52 = calc_52w_stats(df_slice)
                except Exception:
                    stats52 = {}

                # Detect signals on the slice (no look-ahead)
                try:
                    from signal_detector import detect_signals
                    sigs = detect_signals(df_slice)
                except Exception:
                    sigs = {}

                feat = extract_features(
                    df_slice, signals=sigs, stats52=stats52,
                    regime_str=regime_str, vix=15.0, rule_score=None,
                )

                label = _label_forward(df_ind, i)

                X_rows.append(feat)
                y_rows.append(label)
                meta.append({"symbol": sym, "date": str(df_ind.index[i])[:10], "source": "bootstrap"})
                sym_added += 1

            except Exception:
                continue

    if not X_rows:
        console.print("[red]ML bootstrap: no samples generated — run main.py first to cache stock data[/red]")
        return np.zeros((0, N_FEATURES), dtype=np.float32), np.zeros(0, dtype=np.int8), []

    X = np.array(X_rows, dtype=np.float32)
    y = np.array(y_rows, dtype=np.int8)

    # Persist so next run is instant
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(BOOTSTRAP_CACHE, "wb") as f:
        pickle.dump({"X": X, "y": y, "meta": meta}, f)

    pos_rate = y.mean() * 100
    console.print(
        f"[green]ML bootstrap: {len(y):,} samples from {len(STOCK_UNIVERSE)-skipped} stocks "
        f"| positive rate {pos_rate:.1f}% | saved to cache[/green]"
    )
    return X, y, meta


# ── Prediction-log dataset ────────────────────────────────────────────────────

def build_from_prediction_log() -> tuple[np.ndarray, np.ndarray, list]:
    """
    Extract training rows from resolved entries in prediction_log.json.
    Returns (X, y, meta) — may be empty arrays if log has no resolved entries.

    Each row uses the saved feature vector if present, otherwise re-extracts
    from the price cache at the prediction date.
    """
    if not os.path.exists(PREDICTION_LOG):
        return np.zeros((0, N_FEATURES), dtype=np.float32), np.zeros(0, dtype=np.int8), []

    with open(PREDICTION_LOG) as f:
        log = json.load(f)

    resolved = [p for p in log.get("predictions", []) if p["status"] in ("target_hit", "stop_hit")]
    if not resolved:
        return np.zeros((0, N_FEATURES), dtype=np.float32), np.zeros(0, dtype=np.int8), []

    X_rows, y_rows, meta = [], [], []

    for entry in resolved:
        sym    = entry["symbol"]
        label  = 1 if entry["status"] == "target_hit" else 0
        date_s = entry["date"]       # ISO format

        # Use saved feature vector if available (added going forward)
        if "ml_features" in entry and entry["ml_features"]:
            try:
                feat = np.array(entry["ml_features"], dtype=np.float32)
                if len(feat) == N_FEATURES:
                    X_rows.append(feat)
                    y_rows.append(label)
                    meta.append({"symbol": sym, "date": date_s, "source": "prediction_log"})
                    continue
            except Exception:
                pass

        # Fallback: re-extract features from cache at the prediction date
        path = _cache_path(sym)
        if not os.path.exists(path):
            continue

        df_raw = _load_pkl(path)
        if df_raw is None or len(df_raw) < 220:
            continue

        try:
            df_ind = add_indicators(df_raw)
        except Exception:
            continue

        try:
            pred_date = pd.Timestamp(date_s)
            df_till   = df_ind[df_ind.index <= pred_date]
            if len(df_till) < 200:
                continue

            lat       = df_till.iloc[-1].to_dict()
            regime    = _approx_regime(lat)
            stats52   = calc_52w_stats(df_till)

            from signal_detector import detect_signals
            sigs = detect_signals(df_till)

            feat = extract_features(
                df_till, signals=sigs, stats52=stats52,
                regime_str=regime, vix=15.0,
                rule_score=entry.get("total_score"),
            )
            X_rows.append(feat)
            y_rows.append(label)
            meta.append({"symbol": sym, "date": date_s, "source": "prediction_log"})

        except Exception:
            continue

    if not X_rows:
        return np.zeros((0, N_FEATURES), dtype=np.float32), np.zeros(0, dtype=np.int8), []

    return (
        np.array(X_rows, dtype=np.float32),
        np.array(y_rows, dtype=np.int8),
        meta,
    )


# ── Combined dataset with weighting ──────────────────────────────────────────

def build_combined_dataset(force_bootstrap: bool = False) -> tuple[np.ndarray, np.ndarray, dict]:
    """
    Merge bootstrap + prediction-log datasets.
    Prediction-log rows are duplicated 3× (real feedback outweighs synthetic data).
    Returns (X, y, stats_dict).
    """
    X_boot, y_boot, meta_boot = build_bootstrap_dataset(force_rebuild=force_bootstrap)
    X_pred, y_pred, meta_pred = build_from_prediction_log()

    # Upweight real predictions 3×
    if len(y_pred) > 0:
        X_pred_w = np.tile(X_pred, (3, 1))
        y_pred_w = np.tile(y_pred, 3)
        X = np.vstack([X_boot, X_pred_w]) if len(y_boot) > 0 else X_pred_w
        y = np.concatenate([y_boot, y_pred_w]) if len(y_boot) > 0 else y_pred_w
    else:
        X, y = X_boot, y_boot

    stats = {
        "bootstrap_samples":   int(len(y_boot)),
        "prediction_samples":  int(len(y_pred)),
        "total_samples":       int(len(y)),
        "positive_rate_pct":   round(float(y.mean()) * 100, 1) if len(y) > 0 else 0.0,
    }
    return X, y, stats
