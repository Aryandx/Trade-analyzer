"""
Fetches all structured, quantitative market data that directly affects Indian stocks.
No RSS. No keyword guessing. Real numbers only.

Sources:
  - NSE FII/DII daily flows     (actual institutional money movement)
  - USD/INR rate                (directly affects IT, Pharma exports; OMC import costs)
  - Brent crude oil             (India imports 85% of oil — biggest macro driver)
  - US 10Y Treasury yield       (drives FII allocation to/from India)
  - S&P 500                     (global risk appetite proxy → FII flow direction)
  - Hang Seng                   (China demand proxy → metals sector)
  - Gold futures                (NBFC gold-loan stocks; India's CAD pressure)
  - Nifty sector indices        (actual money rotation between sectors today)
"""

import time
import yfinance as yf
import requests
from datetime import datetime, timedelta
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

# ── India-relevant global symbols only ───────────────────────────────────────
GLOBAL_SYMBOLS = {
    "Brent Crude":   "BZ=F",      # India imports 85% of crude — single biggest macro factor
    "Gold":          "GC=F",      # Drives NBFC gold-loan books; India's CAD
    "USD/INR":       "INR=X",     # Direct revenue impact on IT, Pharma exports
    "S&P 500":       "^GSPC",     # FII risk appetite proxy
    "US 10Y Yield":  "^TNX",      # Rising yield → FII exits EM including India
    "Hang Seng":     "^HSI",      # China demand proxy → TATASTEEL, JSWSTEEL, HINDALCO
}

# Nifty sector indices — tells you where real money is actually flowing today
SECTOR_INDICES = {
    "Nifty Bank":        "^NSEBANK",
    "Nifty IT":          "^CNXIT",
    "Nifty Pharma":      "^CNXPHARMA",
    "Nifty Auto":        "^CNXAUTO",
    "Nifty Metal":       "^CNXMETAL",
    "Nifty Energy":      "^CNXENERGY",
    "Nifty FMCG":        "^CNXFMCG",
    "Nifty Realty":      "^CNXREALTY",
    "Nifty Infra":       "^CNXINFRA",
}

# Map sector index name → config sector key
INDEX_TO_SECTOR = {
    "Nifty Bank":   ["Banks", "NBFC", "Insurance"],
    "Nifty IT":     ["IT"],
    "Nifty Pharma": ["Pharma"],
    "Nifty Auto":   ["Auto"],
    "Nifty Metal":  ["Metals"],
    "Nifty Energy": ["Energy_Upstream", "Energy_Downstream", "Energy_Renewables"],
    "Nifty FMCG":   ["FMCG", "Agriculture"],
    "Nifty Realty": ["Realty", "Cement"],
    "Nifty Infra":  ["Infrastructure", "Ports_Logistics"],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pct_change(ticker_symbol: str, period: str = "5d") -> tuple[float, float]:
    """Returns (latest_price, 1d_pct_change). Returns (0, 0) on failure."""
    try:
        hist = yf.Ticker(ticker_symbol).history(period=period, auto_adjust=True)
        if hist is None or len(hist) < 2:
            return 0.0, 0.0
        cur  = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2])
        return cur, (cur - prev) / prev * 100
    except Exception:
        return 0.0, 0.0


# ── FII / DII Flows ───────────────────────────────────────────────────────────

def fetch_fii_dii() -> dict:
    """
    Fetch latest FII and DII net buy/sell data from NSE.
    Returns dict with fii_net_cr, dii_net_cr, date, and interpretation.
    """
    headers = {
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer":         "https://www.nseindia.com/market-data/fii-dii-activity",
        "X-Requested-With": "XMLHttpRequest",
    }
    result = {"fii_net_cr": None, "dii_net_cr": None, "date": None, "source": "unavailable"}
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=8)
        time.sleep(1.2)
        resp = session.get(
            "https://www.nseindia.com/api/fiidiiTradeReact",
            headers=headers, timeout=8,
        )
        if resp.status_code != 200:
            return result
        rows = resp.json()
        # rows is a list; most recent entry first
        for row in rows[:3]:
            cat = row.get("category", "").upper()
            if "FII" in cat or "FPI" in cat:
                result["fii_net_cr"] = round(float(row.get("netValue", 0)), 2)
                result["date"]       = row.get("date", "")
                result["source"]     = "NSE"
            elif "DII" in cat:
                result["dii_net_cr"] = round(float(row.get("netValue", 0)), 2)
        return result
    except Exception:
        return result


# ── Global Factors ────────────────────────────────────────────────────────────

def fetch_global_factors() -> dict[str, dict]:
    """
    Fetch only India-relevant global data. Returns {name: {price, pct_change}}.
    Skips anything that doesn't directly affect Indian equities.
    """
    factors = {}
    for name, sym in GLOBAL_SYMBOLS.items():
        price, pct = _pct_change(sym)
        if price:
            factors[name] = {"symbol": sym, "price": round(price, 4), "pct_change": round(pct, 3)}
    return factors


# ── Nifty Sector Indices ──────────────────────────────────────────────────────

def fetch_sector_indices(nifty_pct: float) -> dict[str, dict]:
    """
    Fetch sector index 1D performance and compute relative strength vs Nifty 50.
    relative_strength > 0 means sector is outperforming → real money rotation in.
    """
    indices = {}
    for name, sym in SECTOR_INDICES.items():
        price, pct = _pct_change(sym)
        if price:
            indices[name] = {
                "price":             round(price, 2),
                "pct_change":        round(pct, 3),
                "relative_strength": round(pct - nifty_pct, 3),
            }
    return indices


# ── Master Fetch ──────────────────────────────────────────────────────────────

def fetch_all_market_data() -> dict:
    """
    Single call to fetch everything. Returns unified market data dict.
    Used by impact_engine.py to compute sector impacts.
    """
    console.print("[cyan]Fetching FII/DII flows...[/cyan]", end=" ")
    fii_dii = fetch_fii_dii()
    status = f"FII ₹{fii_dii['fii_net_cr']} Cr" if fii_dii["fii_net_cr"] is not None else "FII: unavailable"
    console.print(f"[green]{status}[/green]")

    console.print("[cyan]Fetching global factors...[/cyan]", end=" ")
    global_f = fetch_global_factors()
    console.print(f"[green]{len(global_f)} factors fetched[/green]")

    # Get Nifty 50 1D pct for relative strength calculation
    _, nifty_pct = _pct_change("^NSEI")

    console.print("[cyan]Fetching Nifty sector indices...[/cyan]", end=" ")
    sectors = fetch_sector_indices(nifty_pct)
    console.print(f"[green]{len(sectors)} indices fetched[/green]")

    return {
        "fii_dii":        fii_dii,
        "global_factors": global_f,
        "sector_indices": sectors,
        "nifty_1d_pct":   round(nifty_pct, 3),
        "fetched_at":     datetime.now().isoformat(timespec="minutes"),
    }


# ── Display ───────────────────────────────────────────────────────────────────

def render_market_data(md: dict) -> None:
    fii = md.get("fii_dii", {})
    factors = md.get("global_factors", {})
    sectors = md.get("sector_indices", {})

    # Global factors table
    t1 = Table(title="India-Relevant Global Factors", box=box.SIMPLE_HEAD, border_style="blue")
    t1.add_column("Factor",    width=18)
    t1.add_column("Price",     justify="right", width=14)
    t1.add_column("1D Change", justify="right", width=12)
    t1.add_column("India Impact", width=42)

    impact_labels = {
        "Brent Crude":  lambda p: f"OMCs {'benefit' if p < 0 else 'hurt'} | Paints {'↑' if p < 0 else '↓'} | ONGC {'↓' if p < 0 else '↑'}",
        "Gold":         lambda p: f"NBFC gold-loans {'↑' if p > 0 else '↓'} | CAD pressure {'↑' if p > 0 else '↓'}",
        "USD/INR":      lambda p: f"IT/Pharma exports {'↑ INR revenue' if p > 0 else '↓ margin'} | Imports {'costlier' if p > 0 else 'cheaper'}",
        "S&P 500":      lambda p: f"FII {'inflow likely' if p > 0 else 'outflow risk'} | {'Risk-on' if p > 0 else 'Risk-off'}",
        "US 10Y Yield": lambda p: f"EM allocation {'shrinks' if p > 0 else 'grows'} | Banks/NBFC {'↓' if p > 0 else '↑'}",
        "Hang Seng":    lambda p: f"Metals {'↑' if p > 0 else '↓'} (China demand proxy)",
    }

    for name, data in factors.items():
        pct = data["pct_change"]
        c   = "green" if pct > 0 else "red"
        lbl = impact_labels.get(name, lambda _: "")(pct)
        t1.add_row(name, f"{data['price']:,.4g}", f"[{c}]{pct:+.2f}%[/{c}]", f"[dim]{lbl}[/dim]")
    console.print(t1)

    # FII/DII
    if fii.get("fii_net_cr") is not None:
        fii_c = "green" if fii["fii_net_cr"] > 0 else "red"
        dii_c = "green" if (fii.get("dii_net_cr") or 0) > 0 else "red"
        fii_v = fii["fii_net_cr"]
        dii_v = fii.get("dii_net_cr") or 0
        console.print(
            f"  FII net: [{fii_c}]₹{fii_v:+,.0f} Cr[/{fii_c}]"
            f"  |  DII net: [{dii_c}]₹{dii_v:+,.0f} Cr[/{dii_c}]"
            f"  |  Date: {fii.get('date','')}"
        )
    else:
        console.print("  [yellow]FII/DII: NSE data unavailable[/yellow]")

    # Sector indices
    t2 = Table(title="Nifty Sector Performance vs Nifty 50", box=box.SIMPLE_HEAD, border_style="cyan")
    t2.add_column("Sector Index",    width=18)
    t2.add_column("1D %",   justify="right", width=10)
    t2.add_column("vs Nifty",  justify="right", width=12)
    t2.add_column("Signal",    width=20)

    for name, data in sorted(sectors.items(), key=lambda x: -x[1]["relative_strength"]):
        pct  = data["pct_change"]
        rel  = data["relative_strength"]
        pc   = "green" if pct > 0 else "red"
        rc   = "green bold" if rel > 1 else "green" if rel > 0 else "red" if rel < -1 else "red dim"
        sig  = "INFLOW" if rel > 1.5 else "outperforming" if rel > 0.5 else "OUTFLOW" if rel < -1.5 else "underperforming" if rel < -0.5 else "neutral"
        t2.add_row(name, f"[{pc}]{pct:+.2f}%[/{pc}]", f"[{rc}]{rel:+.2f}%[/{rc}]", sig)
    console.print(t2)
