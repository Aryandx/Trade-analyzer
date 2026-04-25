"""
Signal detectors: divergence, TTM squeeze, breakout, support/resistance, candlestick patterns,
and full chart-pattern detection (double top/bottom, H&S, flags, triangles, wedges).
All functions accept a df_ind (output of add_indicators) as input.
"""
import numpy as np
import pandas as pd
from pattern_detector import detect_all_patterns


def _swing_lows(arr: np.ndarray, w: int = 5) -> list[int]:
    return [i for i in range(w, len(arr) - w) if arr[i] == min(arr[i - w: i + w + 1])]


def _swing_highs(arr: np.ndarray, w: int = 5) -> list[int]:
    return [i for i in range(w, len(arr) - w) if arr[i] == max(arr[i - w: i + w + 1])]


def detect_rsi_divergence(df: pd.DataFrame, lookback: int = 50) -> dict:
    """
    Bullish: price lower low, RSI higher low  → accumulation signal.
    Bearish: price higher high, RSI lower high → distribution signal.
    """
    recent = df.tail(lookback)
    price  = recent["close"].values
    rsi    = recent["rsi"].values

    bullish, bearish = False, False

    lows = _swing_lows(price)
    if len(lows) >= 2:
        i1, i2 = lows[-2], lows[-1]
        if price[i2] < price[i1] and rsi[i2] > rsi[i1] + 2:
            bullish = True

    highs = _swing_highs(price)
    if len(highs) >= 2:
        i1, i2 = highs[-2], highs[-1]
        if price[i2] > price[i1] and rsi[i2] < rsi[i1] - 2:
            bearish = True

    return {"rsi_bull_div": bullish, "rsi_bear_div": bearish}


def detect_macd_divergence(df: pd.DataFrame, lookback: int = 50) -> dict:
    recent = df.tail(lookback)
    price  = recent["close"].values
    hist   = recent["macd_hist"].values

    bullish, bearish = False, False

    lows = _swing_lows(price)
    if len(lows) >= 2:
        i1, i2 = lows[-2], lows[-1]
        h1, h2 = hist[i1], hist[i2]
        if price[i2] < price[i1] and h2 > h1:
            bullish = True

    highs = _swing_highs(price)
    if len(highs) >= 2:
        i1, i2 = highs[-2], highs[-1]
        h1, h2 = hist[i1], hist[i2]
        if price[i2] > price[i1] and h2 < h1:
            bearish = True

    return {"macd_bull_div": bullish, "macd_bear_div": bearish}


def detect_ttm_squeeze(df: pd.DataFrame) -> dict:
    """
    TTM Squeeze: Bollinger Bands contract inside Keltner Channel = energy coiling.
    Release (BB expands beyond KC) = explosive directional move imminent.
    """
    if len(df) < 25:
        return {"squeeze_active": False, "squeeze_fired": False, "momentum_up": False}

    kc_mid   = df["ema20"]
    kc_upper = kc_mid + 1.5 * df["atr"]
    kc_lower = kc_mid - 1.5 * df["atr"]

    squeezed = (df["bb_upper"] < kc_upper) & (df["bb_lower"] > kc_lower)

    last5   = squeezed.values[-5:]
    sq_now  = bool(last5[-1])
    # Fired = was squeezed in at least 3 of last 5 bars, now not squeezed
    sq_fired = bool(sum(last5[:-1]) >= 2 and not last5[-1])

    hist = df["macd_hist"].values
    mom_up = bool(hist[-1] > hist[-3]) if len(hist) >= 3 else False

    return {"squeeze_active": sq_now, "squeeze_fired": sq_fired, "momentum_up": mom_up}


def detect_breakout(df: pd.DataFrame, lookback: int = 25) -> dict:
    """
    Breakout above a tight consolidation range with volume confirmation.
    """
    if len(df) < lookback + 5:
        return {"breakout": False, "vol_surge": False, "consol_range_pct": 0}

    consol = df.iloc[-(lookback + 5): -5]
    last5  = df.iloc[-5:]

    consol_high = consol["close"].max()
    consol_low  = consol["close"].min()
    range_pct   = (consol_high - consol_low) / consol_low

    avg_vol    = consol["volume"].mean()
    recent_vol = last5["volume"].mean()
    vol_surge  = bool(recent_vol > avg_vol * 1.25)

    current = df["close"].values[-1]
    tight   = range_pct < 0.10
    broke   = current > consol_high * 1.003

    return {
        "breakout":        bool(tight and broke and vol_surge),
        "vol_surge":       vol_surge,
        "consol_range_pct": round(range_pct * 100, 2),
    }


def find_support_resistance(df: pd.DataFrame, lookback: int = 80) -> dict:
    """
    Pivot-based support and resistance using last `lookback` bars.
    Clusters nearby pivots (within 1.5%) into single levels.
    """
    recent  = df.tail(lookback)
    high    = recent["high"].values
    low     = recent["low"].values
    current = recent["close"].values[-1]

    pivot_res = [high[i] for i in _swing_highs(high, w=4) if high[i] > current * 1.008]
    pivot_sup = [low[i]  for i in _swing_lows(low,   w=4) if low[i]  < current * 0.992]

    def cluster(levels, tol=0.015):
        if not levels: return []
        levels = sorted(set(levels))
        clusters, group = [], [levels[0]]
        for lvl in levels[1:]:
            if (lvl - group[0]) / group[0] < tol:
                group.append(lvl)
            else:
                clusters.append(round(float(np.mean(group)), 2))
                group = [lvl]
        clusters.append(round(float(np.mean(group)), 2))
        return clusters

    resistances = cluster(pivot_res)[:4]
    supports    = cluster(pivot_sup)[:4][::-1]   # closest first

    return {"resistance": resistances, "support": supports}


def detect_candlestick(df: pd.DataFrame) -> dict:
    """Detect last meaningful bullish/bearish candlestick pattern (last 5 bars)."""
    if len(df) < 5:
        return {"candle_pattern": None, "candle_bullish": None}

    o = df["open"].values[-5:]
    h = df["high"].values[-5:]
    l = df["low"].values[-5:]
    c = df["close"].values[-5:]

    pattern, bullish = None, None

    body     = abs(c[-1] - o[-1])
    lo_wick  = min(o[-1], c[-1]) - l[-1]
    hi_wick  = h[-1] - max(o[-1], c[-1])

    # Hammer
    if body > 0 and lo_wick > 2 * body and hi_wick < body and c[-1] > o[-1]:
        pattern, bullish = "Hammer", True

    # Bullish Engulfing
    if (c[-2] < o[-2] and c[-1] > o[-1] and
            o[-1] <= c[-2] and c[-1] >= o[-2]):
        pattern, bullish = "Bullish Engulfing", True

    # Morning Star
    mid_body  = abs(c[-2] - o[-2])
    prev_body = abs(c[-3] - o[-3])
    if (c[-3] < o[-3] and mid_body < prev_body * 0.35 and c[-1] > o[-1] and
            c[-1] > (o[-3] + c[-3]) / 2):
        pattern, bullish = "Morning Star", True

    # Shooting Star (bearish)
    if body > 0 and hi_wick > 2 * body and lo_wick < body and c[-1] < o[-1]:
        pattern, bullish = "Shooting Star", False

    # Bearish Engulfing
    if (c[-2] > o[-2] and c[-1] < o[-1] and
            o[-1] >= c[-2] and c[-1] <= o[-2]):
        pattern, bullish = "Bearish Engulfing", False

    return {"candle_pattern": pattern, "candle_bullish": bullish}


def compute_structured_target(price: float, stop_loss: float, sr: dict, rr_ratio: float) -> float:
    """
    Use nearest valid resistance as target if it gives at least 1.5:1 RR.
    Fall back to formula (RR × risk) otherwise.
    """
    risk          = price - stop_loss
    formula_target = price + risk * rr_ratio

    resistances = [r for r in sr.get("resistance", []) if r > price * 1.03]
    if resistances:
        nearest = resistances[0]
        actual_rr = (nearest - price) / risk if risk > 0 else 0
        if 1.5 <= actual_rr <= 6:
            return round(nearest, 2)

    return round(formula_target, 2)


def detect_signals(df_ind: pd.DataFrame) -> dict:
    """Run all detectors and return a unified signal dict."""
    return {
        **detect_rsi_divergence(df_ind),
        **detect_macd_divergence(df_ind),
        **detect_ttm_squeeze(df_ind),
        **detect_breakout(df_ind),
        **detect_candlestick(df_ind),
        "sr":       find_support_resistance(df_ind),
        "patterns": detect_all_patterns(df_ind),
    }
