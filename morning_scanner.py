"""
Morning Scanner — Fast intraday pick generator.
Run at 9:00–9:10 AM before market opens.
Uses yesterday's cached OHLCV + today's live sector momentum.
Outputs top 3 actionable intraday setups in under 3 minutes.

Usage:
  python morning_scanner.py                  # default ₹32,000 capital
  python morning_scanner.py --capital 50000  # custom capital
  python morning_scanner.py --log +820       # log today's P&L after market close
  python morning_scanner.py --progress       # show weekly goal progress
"""

import os
import sys
import time
import pickle
import json
import warnings
from datetime import datetime, date

warnings.filterwarnings("ignore")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

import numpy as np
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from config import STOCK_UNIVERSE, RESULTS_DIR, DATA_CACHE_DIR, SECTOR_STOCKS
from data_fetcher import _cache_path
from technical_analysis import add_indicators, get_latest
from signal_detector import detect_signals
from market_data import fetch_sector_indices, _pct_change, SECTOR_INDICES, INDEX_TO_SECTOR

console = Console()

WEEKLY_LOG_PATH = os.path.join(RESULTS_DIR, "weekly_pnl.json")
WEEKLY_GOAL     = 4_000   # INR

BREAKOUT_SCORE = {
    "52W_HIGH":     30,
    "VCP":          28,
    "RESISTANCE":   25,
    "CONSOLIDATION":20,
    "EMA_CROSS":    18,
}

BREAKOUT_LABEL = {
    "52W_HIGH":     "[bold red]52W HIGH[/bold red]",
    "VCP":          "[bold green]VCP[/bold green]",
    "RESISTANCE":   "[bold magenta]RES BREAK[/bold magenta]",
    "CONSOLIDATION":"[bold yellow]CONSOL[/bold yellow]",
    "EMA_CROSS":    "[bold cyan]EMA CROSS[/bold cyan]",
}

# Stock → sectors lookup
_STOCK_SECTOR: dict[str, list[str]] = {}
for _sec, _syms in SECTOR_STOCKS.items():
    for _s in _syms:
        _STOCK_SECTOR.setdefault(_s, []).append(_sec)


# ── Cache loader ──────────────────────────────────────────────────────────────

def _load_cache(symbol: str) -> pd.DataFrame | None:
    path = _cache_path(symbol)
    try:
        if os.path.exists(path):
            with open(path, "rb") as f:
                return pickle.load(f)
    except Exception:
        pass
    return None


# ── Sector momentum map ───────────────────────────────────────────────────────

def _build_sector_momentum() -> dict[str, float]:
    """Returns {sector_key: pct_change_today}"""
    nifty_price, nifty_pct = _pct_change("^NSEI")
    indices = fetch_sector_indices(nifty_pct)

    momentum: dict[str, float] = {}
    for index_name, sectors in INDEX_TO_SECTOR.items():
        data = indices.get(index_name, {})
        pct  = data.get("pct_change", 0.0)
        for sec in sectors:
            momentum[sec] = round(float(pct), 2)
    return momentum


# ── Per-stock intraday scorer ─────────────────────────────────────────────────

def _score_stock(sym: str, df: pd.DataFrame, sector_mom: dict, capital: int) -> dict | None:
    try:
        df_ind = add_indicators(df)
        if len(df_ind) < 50:
            return None

        lat   = get_latest(df_ind)
        price = lat["close"]

        if price < 50 or price > 4800:
            return None

        rsi  = lat["rsi"]
        adx  = lat["adx"]
        ema20 = lat["ema20"]
        ema50 = lat["ema50"]

        score   = 0
        reasons = []

        # ── Trend strength (ADX) — most important for intraday ─────────────
        if adx > 30:
            score += 25
            reasons.append(f"ADX {adx:.0f} — strong trend, not noise")
        elif adx > 22:
            score += 15
            reasons.append(f"ADX {adx:.0f} — moderate trend building")
        elif adx < 15:
            return None   # Too choppy to trade intraday

        # ── RSI — has room to run, not overbought ──────────────────────────
        if 45 <= rsi <= 60:
            score += 20
            reasons.append(f"RSI {rsi:.0f} — ideal zone, room to extend")
        elif 40 <= rsi <= 65:
            score += 12
        elif rsi > 70:
            score -= 15   # Already stretched, fade risk
        elif rsi < 35:
            score -= 8

        # ── EMA structure ─────────────────────────────────────────────────
        if price > ema20 > ema50:
            score += 15
            reasons.append("Price > EMA20 > EMA50 — clean bullish structure")
        elif price > ema50:
            score += 8

        # ── Breakout type — biggest weight ────────────────────────────────
        sigs  = detect_signals(df_ind)
        btype = sigs.get("breakout_type")
        if btype:
            score += BREAKOUT_SCORE.get(btype, 15)
            if btype == "52W_HIGH":
                reasons.append("52-week HIGH breakout — max momentum, path clear")
            elif btype == "VCP":
                reasons.append("VCP — 3-stage volatility squeeze about to release")
            elif btype == "RESISTANCE":
                reasons.append(f"Resistance broken — clean air above pivot level")
            elif btype == "CONSOLIDATION":
                reasons.append(f"Base breakout ({sigs['consol_range_pct']:.1f}% range) with volume")
            elif btype == "EMA_CROSS":
                reasons.append("20 EMA just crossed 50 EMA — fresh trend shift")
        elif sigs.get("squeeze_fired") and sigs.get("momentum_up"):
            score += 22
            reasons.append("TTM Squeeze fired upward — explosive move initiating")

        # ── Volume confirmation ───────────────────────────────────────────
        if sigs.get("vol_surge"):
            score += 10
            reasons.append("Volume surge — institutional participation today")

        # ── Near support (tight entry risk) ──────────────────────────────
        supports = sigs["sr"].get("support", [])
        if supports and abs(price - supports[0]) / price < 0.02:
            score += 8
            reasons.append(f"Near support ₹{supports[0]:,.0f} — tight stop available")

        # ── MACD confirmation ─────────────────────────────────────────────
        if lat["macd"] > lat["macd_signal"] and lat["macd_hist"] > 0:
            score += 8
            reasons.append("MACD bullish and accelerating")

        # ── Sector momentum today ─────────────────────────────────────────
        sectors         = _STOCK_SECTOR.get(sym, [])
        best_mom        = 0.0
        best_sec_name   = ""
        for sec in sectors:
            m = sector_mom.get(sec, 0.0)
            if m > best_mom:
                best_mom      = m
                best_sec_name = sec

        if best_mom > 1.5:
            score += 20
            reasons.append(f"{best_sec_name.replace('_',' ')} sector +{best_mom:.1f}% — strong tailwind")
        elif best_mom > 0.5:
            score += 10
        elif best_mom < -1.0:
            score -= 15   # Headwind — skip
            if score < 40:
                return None

        # Minimum bar
        if score < 45:
            return None

        # ── Intraday targets (ATR-based, floored at 1.5%, capped at 4%) ──
        atr             = max(lat["atr"], price * 0.005)
        raw_tgt_pct     = max(0.015, min(0.04, atr / price * 1.5))
        entry_low       = round(price * 0.997, 2)
        entry_high      = round(price * 1.003, 2)
        day_target      = round(price * (1 + raw_tgt_pct), 2)
        day_target_pct  = round(raw_tgt_pct * 100, 2)

        shares          = max(1, int(capital / price))
        profit_at_tgt   = round(shares * (day_target - price), 2)

        return {
            "symbol":           sym,
            "price":            round(price, 2),
            "score":            score,
            "entry_low":        entry_low,
            "entry_high":       entry_high,
            "day_target":       day_target,
            "day_target_pct":   day_target_pct,
            "rsi":              round(rsi, 2),
            "adx":              round(adx, 2),
            "shares":           shares,
            "profit_at_tgt":    profit_at_tgt,
            "breakout_type":    btype,
            "sector":           best_sec_name.replace("_", " "),
            "sector_mom":       round(best_mom, 2),
            "reasons":          reasons[:5],
        }
    except Exception:
        return None


# ── Weekly P&L tracker ────────────────────────────────────────────────────────

def _load_weekly_log() -> dict:
    try:
        if os.path.exists(WEEKLY_LOG_PATH):
            with open(WEEKLY_LOG_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return {"goal": WEEKLY_GOAL, "entries": []}


def _save_weekly_log(log: dict) -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(WEEKLY_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)


def log_pnl(amount: int) -> None:
    """Log today's actual P&L. amount can be negative."""
    log = _load_weekly_log()
    today = date.today().isoformat()
    # Remove existing entry for today if re-logging
    log["entries"] = [e for e in log["entries"] if e["date"] != today]
    log["entries"].append({"date": today, "pnl": amount})
    _save_weekly_log(log)
    total = sum(e["pnl"] for e in log["entries"])
    console.print(f"[green]Logged ₹{amount:+,} for {today}[/green]")
    console.print(f"[bold]Weekly total: ₹{total:+,} / ₹{log['goal']:,} goal[/bold]")


def show_progress() -> None:
    log    = _load_weekly_log()
    goal   = log.get("goal", WEEKLY_GOAL)
    entries = log.get("entries", [])
    total   = sum(e["pnl"] for e in entries)
    remaining = goal - total
    days_done = len(entries)

    table = Table(title="Weekly P&L Tracker", box=box.SIMPLE, border_style="cyan")
    table.add_column("Date",   style="dim",   width=12)
    table.add_column("P&L",    justify="right", width=12)
    table.add_column("Running",justify="right", width=14)

    running = 0
    for e in sorted(entries, key=lambda x: x["date"]):
        running += e["pnl"]
        color = "green" if e["pnl"] >= 0 else "red"
        table.add_row(
            e["date"],
            f"[{color}]₹{e['pnl']:+,}[/{color}]",
            f"₹{running:+,}",
        )
    console.print(table)

    pct = (total / goal * 100) if goal else 0
    bar = int(pct / 5)
    bar_str = "█" * bar + "░" * (20 - bar)
    console.print(f"\n[bold]Goal: ₹{goal:,}  |  Done: ₹{total:+,}  |  Need: ₹{remaining:,}[/bold]")
    console.print(f"[cyan]{bar_str}[/cyan]  {pct:.0f}%")
    if days_done > 0 and total > 0:
        daily_avg = total / days_done
        days_left = max(0, 5 - days_done)
        projected = total + daily_avg * days_left
        console.print(f"[dim]Avg ₹{daily_avg:,.0f}/day → projected week-end: ₹{projected:,.0f}[/dim]")


# ── Main scanner ──────────────────────────────────────────────────────────────

def run_morning_scan(capital: int = 32_000) -> list:
    console.print(Panel.fit(
        f"[bold cyan]Morning Scanner[/bold cyan]  "
        f"[yellow]{datetime.now().strftime('%A %d %b %Y  %H:%M')}[/yellow]\n"
        f"[dim]Capital: ₹{capital:,}  |  {len(STOCK_UNIVERSE)} stocks  |  ~2 min[/dim]",
        border_style="cyan"
    ))

    # Step 1: Today's sector momentum (live)
    console.print("[dim]Fetching sector momentum...[/dim]", end=" ")
    t0 = time.time()
    sector_mom = _build_sector_momentum()
    console.print(f"[green]done ({time.time()-t0:.0f}s)[/green]")

    if sector_mom:
        hot = sorted(sector_mom.items(), key=lambda x: -x[1])[:3]
        console.print("[dim]Hot: " + "  ".join(f"{k.replace('_',' ')} [green]{v:+.1f}%[/green]" for k, v in hot) + "[/dim]")

    # Step 2: Score all cached stocks (no downloads)
    console.print("[dim]Scoring cached data...[/dim]")
    results = []
    for sym in STOCK_UNIVERSE:
        df = _load_cache(sym)
        if df is None:
            continue
        r = _score_stock(sym, df, sector_mom, capital)
        if r:
            results.append(r)

    results.sort(key=lambda x: -x["score"])
    top3 = results[:3]

    if not top3:
        console.print(Panel(
            "[bold red]NO CLEAN SETUPS TODAY[/bold red]\n\n"
            "Market is too choppy — ADX low across the board.\n"
            "Best move: sit out, protect capital.\n"
            "[dim]This is also a valid trade.[/dim]",
            border_style="red"
        ))
        return []

    # Display picks
    console.print()
    console.rule("[bold yellow]TODAY'S INTRADAY PICKS")

    for i, p in enumerate(top3, 1):
        bt_label = BREAKOUT_LABEL.get(p["breakout_type"] or "", "[dim]—[/dim]")
        sym      = p["symbol"].replace(".NS", "")

        body = (
            f"[bold white]{sym}[/bold white]   "
            f"CMP [cyan]₹{p['price']:,.2f}[/cyan]   "
            f"ADX [yellow]{p['adx']:.0f}[/yellow]   "
            f"RSI [yellow]{p['rsi']:.0f}[/yellow]   "
            f"{bt_label}\n\n"
            f"[bold]BUY ZONE :[/bold]  ₹{p['entry_low']:,.2f}  –  ₹{p['entry_high']:,.2f}\n"
            f"[bold green]DAY TARGET:[/bold green] ₹{p['day_target']:,.2f}  (+{p['day_target_pct']}%)\n"
            f"[bold]SHARES    :[/bold] {p['shares']} × ₹{p['price']:,.2f}  =  ₹{p['shares']*p['price']:,.0f}\n"
            f"[bold green]PROFIT    :[/bold green] +₹{p['profit_at_tgt']:,.0f} if target hit\n"
        )
        if p["sector"]:
            body += f"[dim]Sector: {p['sector']} ({p['sector_mom']:+.1f}% today)[/dim]\n"

        body += "\n[dim]WHY TODAY:[/dim]\n"
        for r in p["reasons"]:
            body += f"  [dim]▸[/dim] {r}\n"

        color = "yellow" if i == 1 else "cyan" if i == 2 else "white"
        title = f"#{i}  Score {p['score']}/100" + ("  ← BEST BET" if i == 1 else "")
        console.print(Panel(body.strip(), title=title, border_style=color))
        console.print()

    # Weekly context
    log   = _load_weekly_log()
    done  = sum(e["pnl"] for e in log.get("entries", []))
    need  = max(0, WEEKLY_GOAL - done)
    console.rule()
    console.print(
        f"Weekly goal ₹{WEEKLY_GOAL:,}  |  "
        f"Banked ₹{done:+,}  |  "
        f"Still need ₹{need:,}\n"
        f"[dim]After market: python morning_scanner.py --log +{top3[0]['profit_at_tgt']:.0f}[/dim]"
    )

    return top3


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    # --log +820  or  --log -300
    if "--log" in args:
        idx = args.index("--log")
        if idx + 1 < len(args):
            try:
                amount = int(args[idx + 1].replace("+", ""))
                log_pnl(amount)
            except ValueError:
                console.print("[red]Usage: --log +820  or  --log -300[/red]")
        sys.exit(0)

    # --progress
    if "--progress" in args:
        show_progress()
        sys.exit(0)

    # --capital XXXXX
    capital = 32_000
    if "--capital" in args:
        idx = args.index("--capital")
        if idx + 1 < len(args):
            try:
                capital = int(args[idx + 1])
            except ValueError:
                pass

    run_morning_scan(capital=capital)
