import os
import json
import time
import pickle
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from rich.console import Console
from config import ANALYSIS_LOOKBACK, DATA_CACHE_DIR, NIFTY_SYMBOL, INDIA_VIX

console = Console()
os.makedirs(DATA_CACHE_DIR, exist_ok=True)


def _cache_path(symbol: str) -> str:
    safe = symbol.replace(".", "_").replace("^", "").replace("&", "AND")
    return os.path.join(DATA_CACHE_DIR, f"{safe}.pkl")


def _is_cache_fresh(path: str, max_age_hours: int = 18) -> bool:
    if not os.path.exists(path):
        return False
    age = time.time() - os.path.getmtime(path)
    return age < max_age_hours * 3600


def fetch_stock_data(symbol: str, period: str = ANALYSIS_LOOKBACK, use_cache: bool = True) -> pd.DataFrame | None:
    cache = _cache_path(symbol)
    if use_cache and _is_cache_fresh(cache):
        try:
            with open(cache, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, auto_adjust=True)
        if df is None or len(df) < 50:
            return None
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df.columns = [c.lower() for c in df.columns]
        df = df[["open", "high", "low", "close", "volume"]].dropna()
        with open(cache, "wb") as f:
            pickle.dump(df, f)
        return df
    except Exception as e:
        console.print(f"[red]Error fetching {symbol}: {e}[/red]")
        return None


def fetch_bulk_stocks(symbols: list[str], delay: float = 0.3) -> dict[str, pd.DataFrame]:
    results = {}
    total = len(symbols)
    for i, sym in enumerate(symbols, 1):
        console.print(f"  [{i}/{total}] {sym}", end="\r")
        df = fetch_stock_data(sym)
        if df is not None and len(df) >= 200:
            results[sym] = df
        time.sleep(delay)
    console.print()
    return results


def fetch_nifty_data(period: str = ANALYSIS_LOOKBACK) -> pd.DataFrame | None:
    return fetch_stock_data(NIFTY_SYMBOL, period=period)


def fetch_india_vix(period: str = "6mo") -> pd.DataFrame | None:
    return fetch_stock_data(INDIA_VIX, period=period)


def get_stock_info(symbol: str) -> dict:
    cache = _cache_path(f"info_{symbol}")
    if _is_cache_fresh(cache, max_age_hours=24):
        try:
            with open(cache, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    try:
        info = yf.Ticker(symbol).info
        with open(cache, "wb") as f:
            pickle.dump(info, f)
        return info
    except Exception:
        return {}
