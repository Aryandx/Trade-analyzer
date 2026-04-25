"""
Rule-based chart pattern detector for Indian equity markets.
Patterns: Double Top/Bottom, Head & Shoulders (inc. Inverse), Bull/Bear Flag,
Ascending/Descending/Symmetrical Triangle, Rising/Falling Wedge,
Trend Structure (HH/HL vs LH/LL), Trendline Break.
Each detector returns: {detected, pattern, bias, confidence, ...key_levels}
"""
import numpy as np
import pandas as pd


def _swing_highs(arr: np.ndarray, w: int = 5) -> list:
    return [i for i in range(w, len(arr) - w)
            if arr[i] == max(arr[i - w: i + w + 1])]


def _swing_lows(arr: np.ndarray, w: int = 5) -> list:
    return [i for i in range(w, len(arr) - w)
            if arr[i] == min(arr[i - w: i + w + 1])]


def _slope(y: np.ndarray) -> float:
    n = len(y)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=float)
    return float(np.polyfit(x, y.astype(float), 1)[0])


def _base(name: str, bias: str) -> dict:
    return {"detected": False, "pattern": name, "bias": bias, "confidence": 0}


# ── Double Top ─────────────────────────────────────────────────────────────────
def detect_double_top(df: pd.DataFrame, lookback: int = 60) -> dict:
    """Two peaks at similar levels (within 3%) with a valley between. Bearish."""
    r = _base("Double Top", "bearish")
    data = df.tail(lookback)
    high = data["high"].values
    close = data["close"].values
    n = len(high)

    idx = _swing_highs(high, w=5)
    if len(idx) < 2:
        return r

    i1, i2 = idx[-2], idx[-1]
    h1, h2 = high[i1], high[i2]

    if abs(h1 - h2) / max(h1, h2) > 0.03:
        return r
    if i2 < n - 20:           # second peak not recent enough
        return r

    valley = float(min(high[i1: i2 + 1]))
    avg_peak = (h1 + h2) / 2
    if valley > avg_peak * 0.95:   # valley not deep enough
        return r
    if close[-1] >= h2 * 0.99:    # still at peak — not confirmed
        return r

    sym     = 1.0 - abs(h1 - h2) / max(h1, h2) / 0.03
    recency = max(0.0, 1.0 - (n - 1 - i2) / 20.0)
    r.update({
        "detected": True,
        "confidence": int(min(92, (sym * 0.6 + recency * 0.4) * 80 + 12)),
        "neckline": round(valley, 2),
        "peak_level": round(avg_peak, 2),
    })
    return r


# ── Double Bottom ──────────────────────────────────────────────────────────────
def detect_double_bottom(df: pd.DataFrame, lookback: int = 60) -> dict:
    """Two troughs at similar levels (within 3%) with a peak between. Bullish."""
    r = _base("Double Bottom", "bullish")
    data = df.tail(lookback)
    low = data["low"].values
    close = data["close"].values
    n = len(low)

    idx = _swing_lows(low, w=5)
    if len(idx) < 2:
        return r

    i1, i2 = idx[-2], idx[-1]
    l1, l2 = low[i1], low[i2]

    if abs(l1 - l2) / max(l1, l2) > 0.03:
        return r
    if i2 < n - 20:
        return r

    peak_val = float(max(close[i1: i2 + 1]))
    avg_trough = (l1 + l2) / 2
    if peak_val < avg_trough * 1.05:
        return r
    if close[-1] <= l2 * 1.01:
        return r

    sym     = 1.0 - abs(l1 - l2) / max(l1, l2) / 0.03
    recency = max(0.0, 1.0 - (n - 1 - i2) / 20.0)
    r.update({
        "detected": True,
        "confidence": int(min(92, (sym * 0.6 + recency * 0.4) * 80 + 12)),
        "neckline": round(peak_val, 2),
        "trough_level": round(avg_trough, 2),
    })
    return r


# ── Head & Shoulders ───────────────────────────────────────────────────────────
def detect_head_and_shoulders(df: pd.DataFrame, lookback: int = 80) -> dict:
    """Three peaks; middle (head) highest; shoulders within 10%. Bearish."""
    r = _base("Head & Shoulders", "bearish")
    data = df.tail(lookback)
    high = data["high"].values
    close = data["close"].values
    n = len(high)

    idx = _swing_highs(high, w=5)
    if len(idx) < 3:
        return r

    ls_i, hd_i, rs_i = idx[-3], idx[-2], idx[-1]
    ls, hd, rs = high[ls_i], high[hd_i], high[rs_i]

    if not (hd > ls * 1.02 and hd > rs * 1.02):
        return r
    if abs(ls - rs) / max(ls, rs) > 0.10:
        return r
    if rs_i < n - 15:
        return r

    t1 = float(min(close[ls_i: hd_i + 1])) if hd_i > ls_i else ls
    t2 = float(min(close[hd_i: rs_i + 1])) if rs_i > hd_i else rs
    neckline = (t1 + t2) / 2

    sym     = 1.0 - abs(ls - rs) / max(ls, rs) / 0.10
    recency = max(0.0, 1.0 - (n - 1 - rs_i) / 15.0)
    r.update({
        "detected": True,
        "confidence": int(min(88, (sym * 0.6 + recency * 0.4) * 76 + 12)),
        "neckline": round(neckline, 2),
        "head_level": round(float(hd), 2),
    })
    return r


# ── Inverse Head & Shoulders ───────────────────────────────────────────────────
def detect_inverse_head_and_shoulders(df: pd.DataFrame, lookback: int = 80) -> dict:
    """Three troughs; middle (head) deepest; shoulders within 10%. Bullish."""
    r = _base("Inv Head & Shoulders", "bullish")
    data = df.tail(lookback)
    low = data["low"].values
    close = data["close"].values
    n = len(low)

    idx = _swing_lows(low, w=5)
    if len(idx) < 3:
        return r

    ls_i, hd_i, rs_i = idx[-3], idx[-2], idx[-1]
    ls, hd, rs = low[ls_i], low[hd_i], low[rs_i]

    if not (hd < ls * 0.98 and hd < rs * 0.98):
        return r
    if abs(ls - rs) / max(ls, rs) > 0.10:
        return r
    if rs_i < n - 15:
        return r

    p1 = float(max(close[ls_i: hd_i + 1])) if hd_i > ls_i else ls
    p2 = float(max(close[hd_i: rs_i + 1])) if rs_i > hd_i else rs
    neckline = (p1 + p2) / 2

    sym     = 1.0 - abs(ls - rs) / max(ls, rs) / 0.10
    recency = max(0.0, 1.0 - (n - 1 - rs_i) / 15.0)
    r.update({
        "detected": True,
        "confidence": int(min(88, (sym * 0.6 + recency * 0.4) * 76 + 12)),
        "neckline": round(neckline, 2),
        "head_level": round(float(hd), 2),
    })
    return r


# ── Bull Flag ──────────────────────────────────────────────────────────────────
def detect_bull_flag(df: pd.DataFrame, lookback: int = 40) -> dict:
    """Strong pole (+8%+) → tight consolidation. Bullish continuation."""
    r = _base("Bull Flag", "bullish")
    if len(df) < lookback:
        return r

    close = df["close"].values[-lookback:]
    mid   = lookback // 2
    pole  = close[:mid]
    flag  = close[mid:]

    if min(pole) <= 0 or min(flag) <= 0:
        return r

    pole_ret   = (pole[-1] - pole[0]) / pole[0]
    flag_range = (max(flag) - min(flag)) / min(flag)
    correction = (pole[-1] - min(flag)) / (pole[-1] - pole[0]) if (pole[-1] - pole[0]) > 0 else 1.0

    if pole_ret < 0.08 or flag_range > 0.07 or correction > 0.55:
        return r

    strength  = min(1.0, pole_ret / 0.20)
    tightness = 1.0 - flag_range / 0.07
    r.update({
        "detected": True,
        "confidence": int(min(88, (strength * 0.5 + tightness * 0.5) * 74 + 14)),
        "pole_return_pct": round(pole_ret * 100, 1),
        "flag_range_pct":  round(flag_range * 100, 1),
    })
    return r


# ── Bear Flag ──────────────────────────────────────────────────────────────────
def detect_bear_flag(df: pd.DataFrame, lookback: int = 40) -> dict:
    """Strong pole (-8%-) → tight bounce consolidation. Bearish continuation."""
    r = _base("Bear Flag", "bearish")
    if len(df) < lookback:
        return r

    close = df["close"].values[-lookback:]
    mid   = lookback // 2
    pole  = close[:mid]
    flag  = close[mid:]

    if min(pole) <= 0 or min(flag) <= 0:
        return r

    pole_ret   = (pole[-1] - pole[0]) / pole[0]
    flag_range = (max(flag) - min(flag)) / min(flag)
    bounce     = (max(flag) - pole[-1]) / (pole[0] - pole[-1]) if (pole[0] - pole[-1]) > 0 else 1.0

    if pole_ret > -0.08 or flag_range > 0.07 or bounce > 0.55:
        return r

    strength  = min(1.0, abs(pole_ret) / 0.20)
    tightness = 1.0 - flag_range / 0.07
    r.update({
        "detected": True,
        "confidence": int(min(88, (strength * 0.5 + tightness * 0.5) * 74 + 14)),
        "pole_return_pct": round(pole_ret * 100, 1),
        "flag_range_pct":  round(flag_range * 100, 1),
    })
    return r


# ── Ascending Triangle ─────────────────────────────────────────────────────────
def detect_ascending_triangle(df: pd.DataFrame, lookback: int = 60) -> dict:
    """Flat resistance + rising support. Bullish continuation."""
    r = _base("Ascending Triangle", "bullish")
    data = df.tail(lookback)
    high = data["high"].values
    low  = data["low"].values
    close = data["close"].values

    hi_idx = _swing_highs(high, w=4)
    lo_idx = _swing_lows(low, w=4)
    if len(hi_idx) < 3 or len(lo_idx) < 3:
        return r

    r_highs = np.array([high[i] for i in hi_idx[-3:]], dtype=float)
    r_lows  = np.array([low[i]  for i in lo_idx[-3:]], dtype=float)

    high_range = (r_highs.max() - r_highs.min()) / r_highs.max()
    low_slp    = _slope(r_lows)

    if high_range > 0.025 or low_slp <= 0:
        return r

    resistance = float(r_highs.mean())
    if abs(close[-1] - resistance) / resistance > 0.05:
        return r

    flatness = 1.0 - high_range / 0.025
    rise     = min(1.0, low_slp / (resistance * 0.003))
    r.update({
        "detected": True,
        "confidence": int(min(85, (flatness * 0.5 + max(0.0, rise) * 0.5) * 72 + 13)),
        "resistance": round(resistance, 2),
    })
    return r


# ── Descending Triangle ────────────────────────────────────────────────────────
def detect_descending_triangle(df: pd.DataFrame, lookback: int = 60) -> dict:
    """Flat support + declining resistance. Bearish continuation."""
    r = _base("Descending Triangle", "bearish")
    data = df.tail(lookback)
    high = data["high"].values
    low  = data["low"].values
    close = data["close"].values

    hi_idx = _swing_highs(high, w=4)
    lo_idx = _swing_lows(low, w=4)
    if len(hi_idx) < 3 or len(lo_idx) < 3:
        return r

    r_highs = np.array([high[i] for i in hi_idx[-3:]], dtype=float)
    r_lows  = np.array([low[i]  for i in lo_idx[-3:]], dtype=float)

    low_range = (r_lows.max() - r_lows.min()) / r_lows.max()
    high_slp  = _slope(r_highs)

    if low_range > 0.025 or high_slp >= 0:
        return r

    support = float(r_lows.mean())
    if abs(close[-1] - support) / support > 0.05:
        return r

    flatness = 1.0 - low_range / 0.025
    decline  = min(1.0, abs(high_slp) / (support * 0.003))
    r.update({
        "detected": True,
        "confidence": int(min(85, (flatness * 0.5 + max(0.0, decline) * 0.5) * 72 + 13)),
        "support": round(support, 2),
    })
    return r


# ── Symmetrical Triangle ───────────────────────────────────────────────────────
def detect_symmetrical_triangle(df: pd.DataFrame, lookback: int = 60) -> dict:
    """Converging highs and lows — neutral, breakout direction determines bias."""
    r = _base("Symmetrical Triangle", "neutral")
    data = df.tail(lookback)
    high = data["high"].values
    low  = data["low"].values
    close = data["close"].values

    hi_idx = _swing_highs(high, w=4)
    lo_idx = _swing_lows(low, w=4)
    if len(hi_idx) < 3 or len(lo_idx) < 3:
        return r

    r_highs = np.array([high[i] for i in hi_idx[-3:]], dtype=float)
    r_lows  = np.array([low[i]  for i in lo_idx[-3:]], dtype=float)

    hs = _slope(r_highs)
    ls = _slope(r_lows)

    # Highs declining, lows rising = converging
    if hs >= 0 or ls <= 0:
        return r

    ratio = abs(hs) / abs(ls) if ls != 0 else 99
    if not (0.33 < ratio < 3.0):
        return r

    est_res = float(r_highs[-1])
    est_sup = float(r_lows[-1])
    if not (est_sup * 0.97 < close[-1] < est_res * 1.03):
        return r

    symmetry = max(0.0, 1.0 - abs(ratio - 1.0) / 2.67)
    r.update({
        "detected": True,
        "confidence": int(min(80, symmetry * 67 + 13)),
        "apex_estimate": round((est_res + est_sup) / 2, 2),
    })
    return r


# ── Falling Wedge ──────────────────────────────────────────────────────────────
def detect_falling_wedge(df: pd.DataFrame, lookback: int = 60) -> dict:
    """Both lines declining; upper falls faster → converging. Bullish reversal."""
    r = _base("Falling Wedge", "bullish")
    data = df.tail(lookback)
    high = data["high"].values
    low  = data["low"].values

    hi_idx = _swing_highs(high, w=4)
    lo_idx = _swing_lows(low, w=4)
    if len(hi_idx) < 3 or len(lo_idx) < 3:
        return r

    hs = _slope(np.array([high[i] for i in hi_idx[-3:]], dtype=float))
    ls = _slope(np.array([low[i]  for i in lo_idx[-3:]], dtype=float))

    # Both negative; upper line must fall faster (|hs| > |ls|)
    if hs >= 0 or ls >= 0:
        return r
    if not (abs(hs) > abs(ls) * 1.15):
        return r

    conv = (abs(hs) - abs(ls)) / abs(hs)
    r.update({
        "detected": True,
        "confidence": int(min(82, max(0.0, conv) * 58 + 24)),
    })
    return r


# ── Rising Wedge ───────────────────────────────────────────────────────────────
def detect_rising_wedge(df: pd.DataFrame, lookback: int = 60) -> dict:
    """Both lines rising; lower rises faster → converging. Bearish reversal."""
    r = _base("Rising Wedge", "bearish")
    data = df.tail(lookback)
    high = data["high"].values
    low  = data["low"].values

    hi_idx = _swing_highs(high, w=4)
    lo_idx = _swing_lows(low, w=4)
    if len(hi_idx) < 3 or len(lo_idx) < 3:
        return r

    hs = _slope(np.array([high[i] for i in hi_idx[-3:]], dtype=float))
    ls = _slope(np.array([low[i]  for i in lo_idx[-3:]], dtype=float))

    # Both positive; lower line must rise faster (ls > hs)
    if hs <= 0 or ls <= 0:
        return r
    if not (ls > hs * 1.15):
        return r

    conv = (ls - hs) / ls
    r.update({
        "detected": True,
        "confidence": int(min(82, max(0.0, conv) * 58 + 24)),
    })
    return r


# ── Trend Structure ─────────────────────────────────────────────────────────────
def detect_trend_structure(df: pd.DataFrame, lookback: int = 60) -> dict:
    """HH/HL = uptrend, LH/LL = downtrend, mixed = chop."""
    data  = df.tail(lookback)
    high  = data["high"].values
    low   = data["low"].values

    hi_idx = _swing_highs(high, w=5)
    lo_idx = _swing_lows(low,  w=5)

    if len(hi_idx) < 2 or len(lo_idx) < 2:
        return {"structure": "undefined", "bias": "neutral", "confidence": 0,
                "last_high": None, "last_low": None}

    h1, h2 = high[hi_idx[-2]], high[hi_idx[-1]]
    l1, l2 = low[lo_idx[-2]],  low[lo_idx[-1]]

    hh, hl = h2 > h1, l2 > l1

    if hh and hl:
        structure, bias = "HH/HL", "bullish"
        strength = min(1.0, ((h2 - h1) / h1 + (l2 - l1) / l1) / 0.04)
    elif not hh and not hl:
        structure, bias = "LH/LL", "bearish"
        strength = min(1.0, ((h1 - h2) / h1 + (l1 - l2) / l1) / 0.04)
    elif hh and not hl:
        structure, bias, strength = "expanding", "neutral", 0.4
    else:
        structure, bias, strength = "contracting", "neutral", 0.5

    return {
        "structure":  structure,
        "bias":       bias,
        "confidence": int(min(90, max(0.0, strength) * 70 + 20)),
        "last_high":  round(float(h2), 2),
        "last_low":   round(float(l2), 2),
    }


# ── Trendline Break ─────────────────────────────────────────────────────────────
def detect_trendline_break(df: pd.DataFrame, lookback: int = 40) -> dict:
    """Break above a downward trendline (bullish) or below upward trendline (bearish)."""
    result = {"bullish_break": False, "bearish_break": False,
               "bias": "neutral", "confidence": 0, "trendline_level": None}
    data  = df.tail(lookback)
    high  = data["high"].values
    low   = data["low"].values
    close = data["close"].values
    n     = len(high)

    hi_idx = _swing_highs(high, w=5)
    if len(hi_idx) >= 2:
        i1, i2 = hi_idx[-2], hi_idx[-1]
        h1, h2 = high[i1], high[i2]
        if h1 > h2:                                    # downward trendline
            slope  = (h2 - h1) / max(1, i2 - i1)
            tl_now = h2 + slope * (n - 1 - i2)
            if close[-1] > tl_now * 1.005:            # bullish break
                strength = (close[-1] - tl_now) / tl_now
                result.update({
                    "bullish_break":   True,
                    "bias":            "bullish",
                    "confidence":      int(min(80, strength * 600 + 40)),
                    "trendline_level": round(float(tl_now), 2),
                })
                return result

    lo_idx = _swing_lows(low, w=5)
    if len(lo_idx) >= 2:
        i1, i2 = lo_idx[-2], lo_idx[-1]
        l1, l2 = low[i1], low[i2]
        if l1 < l2:                                    # upward trendline
            slope  = (l2 - l1) / max(1, i2 - i1)
            tl_now = l2 + slope * (n - 1 - i2)
            if close[-1] < tl_now * 0.995:            # bearish break
                strength = (tl_now - close[-1]) / tl_now
                result.update({
                    "bearish_break":   True,
                    "bias":            "bearish",
                    "confidence":      int(min(80, strength * 600 + 40)),
                    "trendline_level": round(float(tl_now), 2),
                })

    return result


# ── Master Aggregator ──────────────────────────────────────────────────────────
def detect_all_patterns(df: pd.DataFrame) -> dict:
    """
    Run every detector and return a unified dict with pattern lists + net score.
    pattern_score: -10 (strongly bearish patterns) to +10 (strongly bullish).
    """
    empty = {
        "patterns": [], "bullish_patterns": [], "bearish_patterns": [],
        "neutral_patterns": [], "pattern_score": 0, "pattern_bias": "neutral",
        "trend_structure": {"structure": "undefined", "bias": "neutral",
                            "confidence": 0, "last_high": None, "last_low": None},
        "trendline": {"bullish_break": False, "bearish_break": False, "bias": "neutral"},
    }
    if len(df) < 80:
        return empty

    detectors = [
        detect_double_bottom, detect_double_top,
        detect_inverse_head_and_shoulders, detect_head_and_shoulders,
        detect_bull_flag, detect_bear_flag,
        detect_ascending_triangle, detect_descending_triangle,
        detect_symmetrical_triangle,
        detect_falling_wedge, detect_rising_wedge,
    ]

    trendline    = detect_trendline_break(df)
    trend_struct = detect_trend_structure(df)
    found: list  = []

    for fn in detectors:
        try:
            res = fn(df)
            if res.get("detected"):
                found.append(res)
        except Exception:
            pass

    if trendline.get("bullish_break") or trendline.get("bearish_break"):
        found.append({
            "detected": True,
            "pattern":    "Trendline Break",
            "bias":       trendline["bias"],
            "confidence": trendline["confidence"],
        })

    bullish = [p for p in found if p.get("bias") == "bullish"]
    bearish = [p for p in found if p.get("bias") == "bearish"]
    neutral = [p for p in found if p.get("bias") == "neutral"]

    score = 0
    for p in bullish:
        score += max(1, int(p.get("confidence", 50) / 50 * 3))
    for p in bearish:
        score -= max(1, int(p.get("confidence", 50) / 50 * 3))
    score += len(neutral)     # neutral patterns = coiling energy

    if trend_struct["bias"] == "bullish" and trend_struct["confidence"] > 60:
        score += 2
    elif trend_struct["bias"] == "bearish" and trend_struct["confidence"] > 60:
        score -= 2

    score = max(-10, min(10, score))
    bias  = "bullish" if score > 1 else ("bearish" if score < -1 else "neutral")

    return {
        "patterns":         found,
        "bullish_patterns": [p["pattern"] for p in bullish],
        "bearish_patterns": [p["pattern"] for p in bearish],
        "neutral_patterns": [p["pattern"] for p in neutral],
        "pattern_score":    score,
        "pattern_bias":     bias,
        "trend_structure":  trend_struct,
        "trendline":        trendline,
    }
