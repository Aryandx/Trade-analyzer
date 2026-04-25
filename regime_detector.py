import numpy as np
import pandas as pd
from technical_analysis import add_indicators, get_latest
from data_fetcher import fetch_nifty_data, fetch_india_vix
from rich.console import Console

console = Console()

REGIMES = {
    "STRONG_BULL": "Strong Uptrend — Buy momentum leaders",
    "BULL": "Uptrend — Favor quality growth stocks",
    "SIDEWAYS": "Consolidation — Buy near support, tight stop",
    "BEAR": "Downtrend — Very selective; defensive only",
    "STRONG_BEAR": "Strong Downtrend — Avoid long positions",
    "VOLATILE": "High Volatility — Reduce position size",
}


def detect_regime() -> dict:
    console.print("[cyan]Detecting market regime (Nifty 50)...[/cyan]")
    df = fetch_nifty_data()
    if df is None or len(df) < 200:
        return {"regime": "UNKNOWN", "description": "Could not fetch Nifty data", "vix": None}

    df = add_indicators(df)
    lat = get_latest(df)

    close = lat["close"]
    ema20 = lat["ema20"]
    ema50 = lat["ema50"]
    ema200 = lat["ema200"]
    adx = lat["adx"]
    rsi = lat["rsi"]
    macd = lat["macd"]
    macd_signal = lat["macd_signal"]

    # 1-month and 3-month performance
    ret_1m = float(df["close"].pct_change(21).iloc[-1])
    ret_3m = float(df["close"].pct_change(63).iloc[-1])

    # VIX
    vix_df = fetch_india_vix(period="3mo")
    vix_val = None
    if vix_df is not None and len(vix_df) > 0:
        vix_val = round(float(vix_df["close"].iloc[-1]), 2)

    # Regime logic
    above_200 = close > ema200
    above_50 = close > ema50
    above_20 = close > ema20
    ema_aligned = ema20 > ema50 > ema200
    trending = adx > 20
    strong_trend = adx > 30
    macd_bullish = macd > macd_signal

    # Weighted bull/bear signal sets — used for real confidence calculation
    bull_signals = [above_200, ema_aligned, strong_trend, macd_bullish, rsi > 55, ret_1m > 0, ret_3m > 0]
    bear_signals = [not above_200, not ema_aligned, rsi < 45, not macd_bullish, ret_1m < -0.03, ret_3m < -0.05]
    bull_pct = sum(bull_signals) / len(bull_signals)
    bear_pct = sum(bear_signals) / len(bear_signals)

    regime = "SIDEWAYS"
    confidence = 50

    if vix_val and vix_val > 22:
        regime = "VOLATILE"
        # How far above the 22 threshold: more extreme VIX = higher confidence
        confidence = min(95, int(50 + (vix_val - 22) * 3))
    elif above_200 and ema_aligned and strong_trend and macd_bullish and rsi > 55:
        regime = "STRONG_BULL"
        confidence = int(bull_pct * 100)
    elif above_200 and above_50 and macd_bullish:
        regime = "BULL"
        confidence = int(bull_pct * 100)
    elif not above_200 and not ema_aligned and adx > 20 and rsi < 45:
        regime = "STRONG_BEAR"
        confidence = int(bear_pct * 100)
    elif not above_50 and not macd_bullish:
        regime = "BEAR"
        confidence = int(bear_pct * 100)
    else:
        regime = "SIDEWAYS"
        # High confidence when signals are genuinely split (neither bull nor bear dominates)
        confidence = int((1 - abs(bull_pct - 0.5) * 2) * 100)

    result = {
        "regime": regime,
        "description": REGIMES.get(regime, "Unknown"),
        "confidence_pct": confidence,
        "nifty_close": round(close, 2),
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "ema200": round(ema200, 2),
        "adx": round(adx, 2),
        "rsi": round(rsi, 2),
        "macd_bullish": bool(macd_bullish),
        "ret_1m_pct": round(ret_1m * 100, 2),
        "ret_3m_pct": round(ret_3m * 100, 2),
        "india_vix": vix_val,
    }

    emoji = {"STRONG_BULL": "🚀", "BULL": "📈", "SIDEWAYS": "➡️",
             "BEAR": "📉", "STRONG_BEAR": "⛔", "VOLATILE": "⚡", "UNKNOWN": "❓"}
    console.print(
        f"[bold green]Regime: {emoji.get(regime, '')} {regime}[/bold green] "
        f"| Nifty: {close:.0f} | ADX: {adx:.1f} | RSI: {rsi:.1f} | VIX: {vix_val}"
    )
    return result
