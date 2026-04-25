import numpy as np
import pandas as pd
import ta


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]

    # Trend EMAs
    for w in [9, 20, 50, 200]:
        df[f"ema{w}"] = ta.trend.EMAIndicator(c, window=w).ema_indicator()

    # RSI
    df["rsi"] = ta.momentum.RSIIndicator(c, window=14).rsi()

    # MACD
    macd = ta.trend.MACD(c, window_fast=12, window_slow=26, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()

    # ADX (trend strength)
    adx = ta.trend.ADXIndicator(h, l, c, window=14)
    df["adx"] = adx.adx()
    df["adx_pos"] = adx.adx_pos()
    df["adx_neg"] = adx.adx_neg()

    # ATR (volatility)
    df["atr"] = ta.volatility.AverageTrueRange(h, l, c, window=14).average_true_range()

    # Bollinger Bands
    bb = ta.volatility.BollingerBands(c, window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_mid"] = bb.bollinger_mavg()
    df["bb_pct"] = bb.bollinger_pband()  # 0=lower, 1=upper

    # Stochastic RSI
    stoch = ta.momentum.StochRSIIndicator(c, window=14, smooth1=3, smooth2=3)
    df["stoch_k"] = stoch.stochrsi_k()
    df["stoch_d"] = stoch.stochrsi_d()

    # Volume indicators
    df["vol_sma20"] = v.rolling(20).mean()
    df["vol_ratio"] = v / df["vol_sma20"]          # > 1 = above average volume
    df["obv"] = ta.volume.OnBalanceVolumeIndicator(c, v).on_balance_volume()
    df["obv_ema"] = ta.trend.EMAIndicator(df["obv"], window=20).ema_indicator()

    # Momentum
    df["roc_10"] = ta.momentum.ROCIndicator(c, window=10).roc()
    df["roc_20"] = ta.momentum.ROCIndicator(c, window=20).roc()

    # Squeeze momentum (ATR vs BB width)
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]

    # Price change metrics
    df["daily_return"] = c.pct_change()
    df["weekly_return"] = c.pct_change(5)
    df["monthly_return"] = c.pct_change(21)

    return df.dropna(subset=["ema200", "adx", "rsi", "macd"])


def compute_weekly_df(df: pd.DataFrame) -> pd.DataFrame:
    weekly = df.resample("W-FRI").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum"
    }).dropna()
    return add_indicators(weekly)


def get_latest(df: pd.DataFrame) -> dict:
    return df.iloc[-1].to_dict()


def calc_52w_stats(df: pd.DataFrame) -> dict:
    recent = df.tail(252)
    high52 = recent["high"].max()
    low52 = recent["low"].min()
    last = df["close"].iloc[-1]
    return {
        "high52": round(high52, 2),
        "low52": round(low52, 2),
        "pct_from_high": round((last - high52) / high52 * 100, 2),
        "pct_from_low": round((last - low52) / low52 * 100, 2),
    }


def calc_manipulation_resistance(df: pd.DataFrame, nifty_df: pd.DataFrame) -> dict:
    returns = df["close"].pct_change().dropna()

    # Spike frequency (days with >3% move in either direction)
    spike_freq = float((returns.abs() > 0.03).mean())

    # Volume consistency — lower CV = more predictable = harder to manipulate
    vol_cv = float(df["volume"].std() / df["volume"].mean())

    # Average Daily Turnover in Cr INR (20-day) — primary liquidity proxy
    # Large turnover = enormous capital required to move price = manipulation-resistant
    recent = df.tail(20)
    avg_daily_turnover_cr = float((recent["close"] * recent["volume"]).mean() / 1e7)

    # Gap frequency (overnight gaps > 2% = vulnerable to thin-market manipulation)
    gaps = ((df["open"] - df["close"].shift(1)) / df["close"].shift(1)).abs().dropna()
    gap_freq = float((gaps > 0.02).mean())

    # Composite manipulation resistance score (0-100)
    score = 0

    # Spike frequency (0-25): frequent large moves = easier to manufacture
    if spike_freq < 0.025: score += 25
    elif spike_freq < 0.04: score += 17
    elif spike_freq < 0.06: score += 8

    # Average Daily Turnover (0-35): harder to manipulate with real capital required
    if avg_daily_turnover_cr > 500:  score += 35
    elif avg_daily_turnover_cr > 100: score += 25
    elif avg_daily_turnover_cr > 20:  score += 15
    elif avg_daily_turnover_cr > 5:   score += 8

    # Volume consistency (0-20)
    if vol_cv < 0.4: score += 20
    elif vol_cv < 0.65: score += 12
    elif vol_cv < 0.9: score += 6

    # Gap frequency (0-20)
    if gap_freq < 0.02: score += 20
    elif gap_freq < 0.035: score += 12
    elif gap_freq < 0.05: score += 6

    return {
        "spike_freq": round(spike_freq, 4),
        "vol_cv": round(vol_cv, 4),
        "avg_daily_turnover_cr": round(avg_daily_turnover_cr, 1),
        "gap_freq": round(gap_freq, 4),
        "manip_resistance_score": min(100, score),
    }
