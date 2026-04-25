"""
Sector-relative strength analysis.
Call build_sector_rs_map() once after all stock data is loaded,
then pass the resulting dict into score_stock() as sector_rs=map.get(symbol).
"""
import numpy as np
import pandas as pd
from config import SECTOR_STOCKS

_STOCK_TO_SECTOR: dict[str, str] = {
    sym: sector
    for sector, stocks in SECTOR_STOCKS.items()
    for sym in stocks
}


def build_sector_rs_map(all_stock_data: dict[str, pd.DataFrame]) -> dict[str, dict]:
    """
    Compute 50-day and 20-day relative strength for every stock vs its sector peers.
    Returns {symbol: {rs_score_20, rs_score_50, sector, sector_rank, ...}}.
    """
    # Pre-compute returns for all stocks once
    ret50: dict[str, float] = {}
    ret20: dict[str, float] = {}
    for sym, df in all_stock_data.items():
        if len(df) >= 50:
            ret50[sym] = float(df["close"].pct_change(50).iloc[-1])
        if len(df) >= 20:
            ret20[sym] = float(df["close"].pct_change(20).iloc[-1])

    result: dict[str, dict] = {}
    for sym in all_stock_data:
        sector = _STOCK_TO_SECTOR.get(sym)
        if not sector:
            result[sym] = {"rs_score": 10, "sector": None}
            continue

        peers = [s for s in SECTOR_STOCKS[sector] if s != sym]

        def percentile_rank(own_ret: float, peer_rets: list[float]) -> float:
            all_r = peer_rets + [own_ret]
            rank  = sorted(all_r, reverse=True).index(own_ret) + 1
            return 1 - (rank - 1) / len(all_r)

        # 50-day RS
        pr50 = [ret50[p] for p in peers if p in ret50]
        own50 = ret50.get(sym)
        pct50 = percentile_rank(own50, pr50) if own50 is not None and pr50 else 0.5

        # 20-day RS
        pr20 = [ret20[p] for p in peers if p in ret20]
        own20 = ret20.get(sym)
        pct20 = percentile_rank(own20, pr20) if own20 is not None and pr20 else 0.5

        # Combined score 0-20: weight 50-day more (long-term orientation)
        rs_score = int((pct50 * 0.65 + pct20 * 0.35) * 20)

        sector_rank = int((1 - pct50) * (len(pr50) + 1)) + 1 if pr50 else None

        result[sym] = {
            "rs_score":          rs_score,
            "sector":            sector,
            "sector_rank":       sector_rank,
            "sector_peers":      len(pr50) + 1,
            "own_ret_50d_pct":   round(own50 * 100, 2) if own50 is not None else None,
            "sector_avg_50d_pct": round(float(np.mean(pr50)) * 100, 2) if pr50 else None,
            "own_ret_20d_pct":   round(own20 * 100, 2) if own20 is not None else None,
        }

    return result
