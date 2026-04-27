"""
Extracts a consistent 40-element float32 feature vector from any stock data snapshot.
Works in two modes:
  - Full mode  (inference): pass df_ind + pre-computed signals + rule_score
  - Lite mode  (bootstrap): pass df_ind only; signals auto-detected from df_ind

Feature layout (indices are stable — never reorder):
  [0-25]  Technical indicators
  [26-34] Signal flags
  [35-37] Chart pattern metrics
  [38-39] Context (regime score, normalised rule score)
"""

import numpy as np
import pandas as pd
from typing import Optional

FEATURE_NAMES = [
    # Technical (26)
    "rsi", "rsi_zone", "adx", "di_spread",
    "macd_hist_norm", "macd_bull", "macd_accel",
    "bb_pct", "bb_width", "stoch_k", "stoch_d",
    "price_vs_ema20", "price_vs_ema50", "price_vs_ema200",
    "ema20_vs_50", "ema50_vs_200", "ema_aligned",
    "vol_ratio", "obv_trend", "roc_10", "roc_20",
    "atr_pct", "weekly_return", "monthly_return",
    "pct_from_high", "pct_from_low",
    # Signals (9)
    "rsi_bull_div", "rsi_bear_div", "macd_bull_div",
    "squeeze_fired", "squeeze_active", "breakout",
    "vol_surge", "candle_signal", "consol_range_pct",
    # Patterns (3)
    "net_pattern_score", "trend_hhhl", "trend_confidence",
    # Context (2)
    "regime_score", "rule_score_norm",
]

N_FEATURES = len(FEATURE_NAMES)   # 40


# ── Helpers ───────────────────────────────────────────────────────────────────

def _f(val, default: float = 0.0, clip: float = 1e6) -> float:
    try:
        v = float(val)
        return float(default) if not np.isfinite(v) else float(np.clip(v, -clip, clip))
    except (TypeError, ValueError):
        return float(default)


_REGIME_SCORES = {
    "STRONG_BULL": 2.0, "BULL": 1.0, "SIDEWAYS": 0.0,
    "VOLATILE": 0.0, "BEAR": -1.0, "STRONG_BEAR": -2.0,
}


# ── Core extraction ───────────────────────────────────────────────────────────

def extract_features(
    df_ind: pd.DataFrame,
    signals: Optional[dict] = None,
    stats52: Optional[dict] = None,
    regime_str: str = "SIDEWAYS",
    vix: float = 15.0,
    rule_score: Optional[float] = None,
) -> np.ndarray:
    """
    Returns a float32 array of shape (40,).

    If signals is None, they are computed from df_ind (slower but correct).
    rule_score: raw 0-150 total from stock_scorer; None → neutral 0.5.
    """
    from technical_analysis import calc_52w_stats

    lat  = df_ind.iloc[-1].to_dict()
    prev = df_ind.iloc[-2].to_dict() if len(df_ind) >= 2 else lat

    price    = _f(lat.get("close"), 1.0)
    ema20    = _f(lat.get("ema20"),  price)
    ema50    = _f(lat.get("ema50"),  price)
    ema200   = _f(lat.get("ema200"), price)
    rsi      = _f(lat.get("rsi"),    50.0)
    adx      = _f(lat.get("adx"),    20.0)
    adx_pos  = _f(lat.get("adx_pos"), 20.0)
    adx_neg  = _f(lat.get("adx_neg"), 20.0)
    macd_h   = _f(lat.get("macd_hist"),  0.0)
    prev_h   = _f(prev.get("macd_hist"), 0.0)
    macd     = _f(lat.get("macd"),   0.0)
    macd_sig = _f(lat.get("macd_signal"), 0.0)
    bb_pct   = _f(lat.get("bb_pct"), 0.5)
    bb_up    = _f(lat.get("bb_upper"), price * 1.02)
    bb_lo    = _f(lat.get("bb_lower"), price * 0.98)
    bb_mid   = _f(lat.get("bb_mid"),   price)
    stoch_k  = _f(lat.get("stoch_k"), 50.0)
    stoch_d  = _f(lat.get("stoch_d"), 50.0)
    vol_ratio = _f(lat.get("vol_ratio"), 1.0, 20.0)
    roc10    = _f(lat.get("roc_10"), 0.0, 100.0)
    roc20    = _f(lat.get("roc_20"), 0.0, 150.0)
    atr      = _f(lat.get("atr"), price * 0.02)
    w_ret    = _f(lat.get("weekly_return"),  0.0, 60.0)
    m_ret    = _f(lat.get("monthly_return"), 0.0, 120.0)

    # Derived technical
    macd_hist_norm = _f((macd_h / price) * 100 if price > 0 else 0.0, 0.0, 10.0)
    macd_bull      = float(macd > macd_sig)
    macd_accel     = float(macd_h > prev_h)
    bb_width       = _f((bb_up - bb_lo) / bb_mid if bb_mid > 0 else 0.04, 0.04, 1.0)
    p_ema20        = _f((price / ema20 - 1) * 100  if ema20  > 0 else 0.0, 0.0, 60.0)
    p_ema50        = _f((price / ema50 - 1) * 100  if ema50  > 0 else 0.0, 0.0, 100.0)
    p_ema200       = _f((price / ema200 - 1) * 100 if ema200 > 0 else 0.0, 0.0, 150.0)
    e20_50         = _f((ema20 / ema50 - 1)  * 100 if ema50  > 0 else 0.0, 0.0, 40.0)
    e50_200        = _f((ema50 / ema200 - 1) * 100 if ema200 > 0 else 0.0, 0.0, 60.0)
    ema_aligned    = float(ema20 > ema50 > ema200)
    atr_pct        = _f((atr / price) * 100 if price > 0 else 2.0, 2.0, 25.0)

    # OBV trend (rising over last 20 bars)
    obv_arr    = df_ind["obv"].values if "obv" in df_ind.columns else np.zeros(21)
    obv_trend  = float(obv_arr[-1] > obv_arr[-20]) if len(obv_arr) >= 20 else 0.5

    # 52-week stats
    if stats52 is None:
        try:
            stats52 = calc_52w_stats(df_ind)
        except Exception:
            stats52 = {}
    pct_high = _f(stats52.get("pct_from_high"), 0.0, 80.0)
    pct_low  = _f(stats52.get("pct_from_low"),  0.0, 300.0)

    # Signals — auto-detect if not supplied
    if signals is None:
        try:
            from signal_detector import detect_signals
            signals = detect_signals(df_ind)
        except Exception:
            signals = {}

    rsi_bd  = float(signals.get("rsi_bull_div",  False))
    rsi_brd = float(signals.get("rsi_bear_div",  False))
    macd_bd = float(signals.get("macd_bull_div", False))
    sq_fire = float(signals.get("squeeze_fired", False))
    sq_act  = float(signals.get("squeeze_active",False))
    bo      = float(signals.get("breakout",      False))
    vs      = float(signals.get("vol_surge",     False))
    cb      = signals.get("candle_bullish")
    c_sig   = 1.0 if cb is True else (-1.0 if cb is False else 0.0)
    consol  = _f(signals.get("consol_range_pct"), 0.0, 50.0)

    # Chart patterns
    pat         = signals.get("patterns") or {}
    bull_n      = len(pat.get("bullish_patterns", []))
    bear_n      = len(pat.get("bearish_patterns", []))
    net_pat     = _f(pat.get("pattern_score", 0) + bull_n - bear_n, 0.0, 20.0)
    ts          = pat.get("trend_structure") or {}
    struct      = ts.get("structure", "")
    trend_hhhl  = 1.0 if struct == "HH/HL" else (-1.0 if struct == "LH/LL" else 0.0)
    trend_conf  = _f(ts.get("confidence", 0), 0.0, 100.0) / 100.0

    # Context
    regime_score = _REGIME_SCORES.get(regime_str.upper(), 0.0)
    rule_norm    = _f(rule_score / 150.0 if rule_score is not None else 0.5, 0.5, 1.0)

    vec = np.array([
        rsi, (rsi - 50) / 50, adx, adx_pos - adx_neg,
        macd_hist_norm, macd_bull, macd_accel,
        bb_pct, bb_width, stoch_k, stoch_d,
        p_ema20, p_ema50, p_ema200,
        e20_50, e50_200, ema_aligned,
        vol_ratio, obv_trend, roc10, roc20,
        atr_pct, w_ret, m_ret,
        pct_high, pct_low,
        # signals
        rsi_bd, rsi_brd, macd_bd,
        sq_fire, sq_act, bo,
        vs, c_sig, consol,
        # patterns
        net_pat, trend_hhhl, trend_conf,
        # context
        regime_score, rule_norm,
    ], dtype=np.float32)

    assert len(vec) == N_FEATURES, f"Feature count mismatch: {len(vec)} != {N_FEATURES}"
    return vec
