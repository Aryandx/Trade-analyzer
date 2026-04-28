"""
Morning Scanner — Daily + 5-min intraday analysis.

Workflow:
  9:00 AM  →  python morning_scanner.py          (picks top 3 from daily data)
  9:30 AM+ →  python morning_scanner.py --live   (adds 5-min VWAP/OR/trend check)
  After close → python morning_scanner.py --log +820
  Anytime  →  python morning_scanner.py --progress

Usage:
  python morning_scanner.py                   daily picks, ₹32k capital
  python morning_scanner.py --capital 50000   custom capital
  python morning_scanner.py --live            5-min live check on saved picks
  python morning_scanner.py --live --capital 32000
  python morning_scanner.py --log +820        log today P&L
  python morning_scanner.py --log -300
  python morning_scanner.py --progress        weekly tracker
"""

import os, sys, time, pickle, json, warnings
from datetime import datetime, date, timedelta

warnings.filterwarnings("ignore")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

import numpy as np
import pandas as pd
import yfinance as yf
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from config import STOCK_UNIVERSE, RESULTS_DIR, DATA_CACHE_DIR, SECTOR_STOCKS
from data_fetcher import _cache_path
from technical_analysis import add_indicators, get_latest
from signal_detector import detect_signals
from market_data import fetch_sector_indices, _pct_change, INDEX_TO_SECTOR

console = Console()

WEEKLY_LOG_PATH  = os.path.join(RESULTS_DIR, "weekly_pnl.json")
SAVED_PICKS_PATH = os.path.join(RESULTS_DIR, "morning_picks.json")

_WEBAPP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp", "public", "data")
WEBAPP_PICKS_PATH = os.path.join(_WEBAPP_DIR, "morning_picks.json")
WEEKLY_GOAL      = 4_000

BREAKOUT_SCORE = {
    "52W_HIGH": 30, "VCP": 28, "RESISTANCE": 25,
    "CONSOLIDATION": 20, "EMA_CROSS": 18,
}
BREAKOUT_LABEL = {
    "52W_HIGH":      "[bold red]52W HIGH[/bold red]",
    "VCP":           "[bold green]VCP[/bold green]",
    "RESISTANCE":    "[bold magenta]RES BREAK[/bold magenta]",
    "CONSOLIDATION": "[bold yellow]CONSOL[/bold yellow]",
    "EMA_CROSS":     "[bold cyan]EMA CROSS[/bold cyan]",
}

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


# ── Sector momentum ───────────────────────────────────────────────────────────

def _sector_momentum() -> dict[str, float]:
    _, nifty_pct = _pct_change("^NSEI")
    indices = fetch_sector_indices(nifty_pct)
    out: dict[str, float] = {}
    for idx_name, sectors in INDEX_TO_SECTOR.items():
        pct = indices.get(idx_name, {}).get("pct_change", 0.0)
        for s in sectors:
            out[s] = round(float(pct), 2)
    return out


# ── 5-minute data & analysis ──────────────────────────────────────────────────

def _fetch_5min(symbol: str) -> pd.DataFrame | None:
    """Fetch today's 5-minute OHLCV bars from yfinance."""
    try:
        df = yf.Ticker(symbol).history(period="2d", interval="5m",
                                       prepost=False, auto_adjust=True)
        if df is None or len(df) < 3:
            return None
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)
        df.columns = [c.lower() for c in df.columns]
        df = df[["open", "high", "low", "close", "volume"]].dropna()
        # Keep only today's session
        today = date.today()
        df = df[df.index.date == today]
        return df if len(df) >= 1 else None
    except Exception:
        return None


def _vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    return (typical * df["volume"]).cumsum() / df["volume"].cumsum()


def _analyze_5min(sym: str, prev_close: float, capital: int) -> dict:
    """
    Full 5-min intraday check.
    Returns signal: ENTER | WAIT | SKIP | NO_DATA
    """
    df5 = _fetch_5min(sym)
    now = datetime.now().time()

    if df5 is None or len(df5) == 0:
        return {
            "signal": "NO_DATA",
            "headline": "5-min data not available yet",
            "detail": "Market may not have opened — run again after 9:30 AM",
        }

    current_price = float(df5["close"].iloc[-1])
    open_price    = float(df5["open"].iloc[0])

    # Gap at open
    gap_pct = (open_price - prev_close) / prev_close * 100

    # Opening range = first 3 candles (9:15, 9:20, 9:25 → complete by 9:30)
    or_bars    = df5.iloc[:3]
    or_high    = float(or_bars["high"].max())
    or_low     = float(or_bars["low"].min())
    or_range   = round((or_high - or_low) / or_low * 100, 2)
    or_complete = len(df5) >= 3

    # VWAP
    vwap_series   = _vwap(df5)
    current_vwap  = float(vwap_series.iloc[-1])
    above_vwap    = current_price > current_vwap

    # 5-min EMA9 / EMA20
    ema9  = df5["close"].ewm(span=9,  adjust=False).mean()
    ema20 = df5["close"].ewm(span=20, adjust=False).mean()
    trend_up = float(ema9.iloc[-1]) > float(ema20.iloc[-1])

    # Volume: latest bar vs session average
    avg_vol    = float(df5["volume"].mean())
    latest_vol = float(df5["volume"].iloc[-1])
    vol_surge  = latest_vol > avg_vol * 1.3

    # Opening range breakout condition
    or_broken  = current_price > or_high * 1.002

    # ── Entry / stop based on OR ──────────────────────────────────────────
    safe_entry  = round(or_high * 1.002, 2)    # 0.2% above OR high
    or_stop     = round(or_low  * 0.998, 2)    # 0.2% below OR low
    risk_per_sh = safe_entry - or_stop
    shares      = max(1, int(capital / safe_entry))
    max_loss    = round(shares * risk_per_sh, 2)
    # Target = 2× risk minimum
    intraday_tgt = round(safe_entry + risk_per_sh * 2, 2)
    tgt_pct      = round((intraday_tgt - safe_entry) / safe_entry * 100, 2)
    profit_at_tgt = round(shares * (intraday_tgt - safe_entry), 2)

    # ── Decision logic ────────────────────────────────────────────────────
    if abs(gap_pct) > 3.0:
        signal   = "SKIP"
        headline = f"Gapped {gap_pct:+.1f}% at open — DO NOT ENTER"
        detail   = ("Gap > 3% means the move is mostly done. "
                    "Chasing here risks buying the top. Find another stock.")

    elif gap_pct < -2.0:
        signal   = "SKIP"
        headline = f"Gapped DOWN {gap_pct:.1f}% — thesis broken"
        detail   = "Daily breakout setup is invalidated. Sit out today."

    elif not or_complete:
        signal   = "WAIT"
        headline = f"Opening range in progress ({len(df5)}/3 candles)"
        detail   = (f"Wait until 9:30 AM. OR so far: "
                    f"High ₹{or_high:,.2f} / Low ₹{or_low:,.2f}. "
                    f"Run --live again at 9:30.")

    elif or_broken and above_vwap and trend_up:
        signal   = "ENTER"
        headline = f"OR BREAKOUT CONFIRMED — Enter now or on next pullback to ₹{or_high:,.2f}"
        detail   = (f"Price broke opening range high with VWAP support + 5-min trend up. "
                    f"Highest probability setup.")

    elif or_broken and above_vwap and not trend_up:
        signal   = "WAIT"
        headline = f"OR broken but 5-min trend not yet aligned"
        detail   = (f"Wait for EMA9 > EMA20 on 5-min. Price ₹{current_price:,.2f}, "
                    f"EMA9 ₹{ema9.iloc[-1]:,.2f}, EMA20 ₹{ema20.iloc[-1]:,.2f}.")

    elif above_vwap and not or_broken:
        signal   = "WAIT"
        headline = f"Above VWAP but OR high ₹{or_high:,.2f} not broken yet"
        detail   = (f"Set alert at ₹{safe_entry:,.2f}. "
                    f"Only enter on confirmed OR breakout with volume.")

    elif not above_vwap:
        signal   = "SKIP"
        headline = f"Below VWAP ₹{current_vwap:,.2f} — bearish intraday bias"
        detail   = ("When price is under VWAP the sellers control the day. "
                    "Do not enter a long here. Skip or wait for strong VWAP reclaim.")
    else:
        signal   = "WAIT"
        headline = "Mixed signals — watch for OR breakout with volume"
        detail   = f"Conditions not fully aligned. Check again in 15 min."

    return {
        "signal":        signal,
        "headline":      headline,
        "detail":        detail,
        "gap_pct":       round(gap_pct, 2),
        "open_price":    round(open_price, 2),
        "current_price": round(current_price, 2),
        "vwap":          round(current_vwap, 2),
        "or_high":       round(or_high, 2),
        "or_low":        round(or_low, 2),
        "or_range_pct":  or_range,
        "or_complete":   or_complete,
        "above_vwap":    above_vwap,
        "or_broken":     or_broken,
        "trend_up_5min": trend_up,
        "vol_surge":     vol_surge,
        "ema9":          round(float(ema9.iloc[-1]), 2),
        "ema20":         round(float(ema20.iloc[-1]), 2),
        "candles":       len(df5),
        # Safe entry plan
        "safe_entry":    safe_entry,
        "or_stop":       or_stop,
        "intraday_tgt":  intraday_tgt,
        "tgt_pct":       tgt_pct,
        "shares":        shares,
        "profit_at_tgt": profit_at_tgt,
        "max_loss":      max_loss,
    }


def _print_5min_panel(sym: str, a: dict) -> None:
    """Print the 5-min analysis panel for one stock."""
    signal_color = {
        "ENTER":   "bold green",
        "WAIT":    "bold yellow",
        "SKIP":    "bold red",
        "NO_DATA": "dim",
    }.get(a["signal"], "white")

    tick = {"ENTER": "✓", "WAIT": "⏳", "SKIP": "✗", "NO_DATA": "?"}.get(a["signal"], "?")

    lines: list[str] = []

    if a["signal"] != "NO_DATA":
        gap_col   = "green" if abs(a["gap_pct"]) < 1.5 else "red"
        vwap_str  = "[green]Price ABOVE[/green]" if a["above_vwap"] else "[red]Price BELOW[/red]"
        or_str    = "[green]COMPLETE[/green]" if a["or_complete"] else "[yellow]building...[/yellow]"
        trend_str = "[green]BULLISH[/green]" if a.get("trend_up_5min") else "[red]BEARISH[/red]"
        vol_str   = "[green]SURGE[/green]" if a.get("vol_surge") else "[dim]Normal[/dim]"
        lines += [
            f"Gap at open  : [{gap_col}]{a['gap_pct']:+.2f}%[/{gap_col}]"
            f"   Open ₹{a['open_price']:,.2f}   Now ₹{a['current_price']:,.2f}",
            f"VWAP         : ₹{a['vwap']:,.2f}   {vwap_str}",
            f"Opening Range: ₹{a['or_low']:,.2f} – ₹{a['or_high']:,.2f}"
            f"  ({a['or_range_pct']:.1f}% wide)  {or_str}",
            f"5-min trend  : EMA9 ₹{a.get('ema9',0):,.2f}  EMA20 ₹{a.get('ema20',0):,.2f}  {trend_str}",
            f"Volume       : {vol_str}",
            "",
        ]

    lines += [
        f"[{signal_color}]{tick} {a['headline']}[/{signal_color}]",
        f"[dim]{a['detail']}[/dim]",
    ]

    if a["signal"] == "ENTER" and "safe_entry" in a:
        lines += [
            "",
            f"[bold]SAFE ENTRY PLAN (OR Breakout)[/bold]",
            f"  Buy above  : [cyan]₹{a['safe_entry']:,.2f}[/cyan]",
            f"  Stop loss  : [red]₹{a['or_stop']:,.2f}[/red]  (below OR low)",
            f"  Target     : [green]₹{a['intraday_tgt']:,.2f}  (+{a['tgt_pct']}%)[/green]  (2× risk)",
            f"  Shares     : {a['shares']} × ₹{a['safe_entry']:,.2f}",
            f"  Max gain   : [green]+₹{a['profit_at_tgt']:,.0f}[/green]",
            f"  Max loss   : [red]-₹{a['max_loss']:,.0f}[/red]",
        ]
    elif a["signal"] == "WAIT" and "or_high" in a and a.get("or_complete"):
        lines += [
            "",
            f"[bold]Watch for:[/bold] price crosses [cyan]₹{a.get('safe_entry', a['or_high']):,.2f}[/cyan] with volume",
        ]

    border = {"ENTER": "green", "WAIT": "yellow", "SKIP": "red", "NO_DATA": "dim"}.get(a["signal"], "white")
    console.print(Panel(
        "\n".join(lines),
        title=f"[bold]{sym.replace('.NS','')} — 5-MIN CHECK[/bold]",
        border_style=border,
    ))
    console.print()


# ── Daily intraday scorer ─────────────────────────────────────────────────────

def _score_stock(sym: str, df: pd.DataFrame, sector_mom: dict, capital: int) -> dict | None:
    try:
        df_ind = add_indicators(df)
        if len(df_ind) < 50:
            return None

        lat   = get_latest(df_ind)
        price = lat["close"]
        if price < 50 or price > 4800:
            return None

        # Skip stocks that already moved >3% today — extended, profit-booking risk tomorrow
        prev_close = df_ind["close"].iloc[-2] if len(df_ind) >= 2 else price
        today_move = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0
        if abs(today_move) > 3.0:
            return None

        rsi, adx = lat["rsi"], lat["adx"]
        ema20, ema50 = lat["ema20"], lat["ema50"]

        score, reasons = 0, []

        if adx > 30:
            score += 25; reasons.append(f"ADX {adx:.0f} — strong trend, not noise")
        elif adx > 22:
            score += 15; reasons.append(f"ADX {adx:.0f} — moderate trend building")
        elif adx < 15:
            return None

        # RSI > 75 = overbought intraday — stock already extended, likely to reverse
        if rsi > 75:
            return None
        if 45 <= rsi <= 60:
            score += 20; reasons.append(f"RSI {rsi:.0f} — ideal zone, room to extend")
        elif 40 <= rsi <= 65:
            score += 12
        elif rsi > 65:
            score -= 20  # overbought penalty, stricter than before
        elif rsi < 35:
            score -= 8

        if price > ema20 > ema50:
            score += 15; reasons.append("Price > EMA20 > EMA50 — clean bullish structure")
        elif price > ema50:
            score += 8

        sigs  = detect_signals(df_ind)
        btype = sigs.get("breakout_type")
        if btype:
            # 52W_HIGH is a swing/position signal — bad for intraday (already extended)
            if btype == "52W_HIGH":
                score -= 10  # penalise: overbought, profit-booking risk intraday
                reasons.append("52W HIGH — caution: extended, profit-booking risk intraday")
            else:
                score += BREAKOUT_SCORE.get(btype, 15)
                labels = {
                    "VCP":           "VCP — 3-stage volatility squeeze about to release",
                    "RESISTANCE":    "Resistance broken — clean air above pivot level",
                    "CONSOLIDATION": f"Base breakout ({sigs['consol_range_pct']:.1f}% range) with volume",
                    "EMA_CROSS":     "20 EMA just crossed 50 EMA — fresh trend shift",
                }
                reasons.append(labels.get(btype, f"Breakout ({btype})"))
        elif sigs.get("squeeze_fired") and sigs.get("momentum_up"):
            score += 22; reasons.append("TTM Squeeze fired upward — explosive move initiating")

        if sigs.get("vol_surge"):
            score += 10; reasons.append("Volume surge — institutional participation today")

        supports = sigs["sr"].get("support", [])
        if supports and abs(price - supports[0]) / price < 0.02:
            score += 8; reasons.append(f"Near support ₹{supports[0]:,.0f} — tight stop available")

        if lat["macd"] > lat["macd_signal"] and lat["macd_hist"] > 0:
            score += 8; reasons.append("MACD bullish and accelerating")

        sectors = _STOCK_SECTOR.get(sym, [])
        best_mom, best_sec = 0.0, ""
        for sec in sectors:
            m = sector_mom.get(sec, 0.0)
            if m > best_mom:
                best_mom, best_sec = m, sec
        if best_mom > 1.5:
            score += 20; reasons.append(f"{best_sec.replace('_',' ')} sector +{best_mom:.1f}% — strong tailwind")
        elif best_mom > 0.5:
            score += 10
        elif best_mom < -1.0:
            score -= 15
            if score < 40:
                return None

        # No breakout pattern + no squeeze = weak intraday catalyst, needs higher bar
        if not btype and not (sigs.get("squeeze_fired") and sigs.get("momentum_up")):
            if score < 70:
                return None

        if score < 55:
            return None

        atr = max(lat["atr"], price * 0.005)
        raw_tgt_pct    = max(0.015, min(0.04, atr / price * 1.5))
        entry_low      = round(price * 0.997, 2)
        entry_high     = round(price * 1.003, 2)
        day_target     = round(price * (1 + raw_tgt_pct), 2)
        day_target_pct = round(raw_tgt_pct * 100, 2)
        shares         = max(1, int(capital / price))
        profit_at_tgt  = round(shares * (day_target - price), 2)

        return {
            "symbol": sym, "price": round(price, 2), "score": score,
            "entry_low": entry_low, "entry_high": entry_high,
            "day_target": day_target, "day_target_pct": day_target_pct,
            "rsi": round(rsi, 2), "adx": round(adx, 2),
            "shares": shares, "profit_at_tgt": profit_at_tgt,
            "breakout_type": btype,
            "sector": best_sec.replace("_", " "), "sector_mom": round(best_mom, 2),
            "reasons": reasons[:5],
        }
    except Exception:
        return None


# ── Weekly P&L tracker ────────────────────────────────────────────────────────

def _load_log() -> dict:
    try:
        if os.path.exists(WEEKLY_LOG_PATH):
            with open(WEEKLY_LOG_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return {"goal": WEEKLY_GOAL, "entries": []}


def log_pnl(amount: int) -> None:
    log   = _load_log()
    today = date.today().isoformat()
    log["entries"] = [e for e in log["entries"] if e["date"] != today]
    log["entries"].append({"date": today, "pnl": amount})
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(WEEKLY_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)
    total = sum(e["pnl"] for e in log["entries"])
    console.print(f"[green]Logged ₹{amount:+,} for {today}[/green]")
    console.print(f"[bold]Week total: ₹{total:+,} / ₹{log['goal']:,} goal[/bold]")
    # Sync updated P&L to webapp if picks file exists
    if os.path.exists(WEBAPP_PICKS_PATH):
        try:
            with open(WEBAPP_PICKS_PATH) as f:
                payload = json.load(f)
            payload["week_banked"]  = total
            payload["week_entries"] = log["entries"]
            with open(WEBAPP_PICKS_PATH, "w") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass


def show_progress() -> None:
    log     = _load_log()
    entries = log.get("entries", [])
    goal    = log.get("goal", WEEKLY_GOAL)
    total   = sum(e["pnl"] for e in entries)

    tbl = Table(title="Weekly P&L", box=box.SIMPLE, border_style="cyan")
    tbl.add_column("Date",    style="dim",    width=12)
    tbl.add_column("P&L",     justify="right",width=12)
    tbl.add_column("Running", justify="right",width=14)
    running = 0
    for e in sorted(entries, key=lambda x: x["date"]):
        running += e["pnl"]
        c = "green" if e["pnl"] >= 0 else "red"
        tbl.add_row(e["date"], f"[{c}]₹{e['pnl']:+,}[/{c}]", f"₹{running:+,}")
    console.print(tbl)

    pct = (total / goal * 100) if goal else 0
    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
    console.print(f"\n[bold]Goal ₹{goal:,}  Done ₹{total:+,}  Need ₹{max(0,goal-total):,}[/bold]")
    console.print(f"[cyan]{bar}[/cyan]  {pct:.0f}%")
    if entries and total > 0:
        avg = total / len(entries)
        proj = total + avg * max(0, 5 - len(entries))
        console.print(f"[dim]Avg ₹{avg:,.0f}/day → projected: ₹{proj:,.0f}[/dim]")


# ── Live 5-min check (run after 9:30 AM) ─────────────────────────────────────

def run_live_check(capital: int = 32_000) -> None:
    """Load saved morning picks and run 5-min analysis on each."""
    if not os.path.exists(SAVED_PICKS_PATH):
        console.print("[red]No saved picks. Run morning_scanner.py first (without --live).[/red]")
        return

    with open(SAVED_PICKS_PATH) as f:
        picks = json.load(f)

    now = datetime.now()
    console.print(Panel.fit(
        f"[bold cyan]5-Min Live Check[/bold cyan]  "
        f"[yellow]{now.strftime('%H:%M:%S')}[/yellow]\n"
        f"[dim]Checking {len(picks)} picks from this morning — fetching live 5-min data[/dim]",
        border_style="cyan"
    ))

    if now.hour < 9 or (now.hour == 9 and now.minute < 30):
        console.print("[yellow]Market opening range not complete yet (need 9:30 AM).[/yellow]")
        console.print("[dim]Run again after 9:30 AM for full ENTER/WAIT/SKIP signal.[/dim]\n")

    for p in picks:
        sym = p["symbol"]
        console.print(f"[dim]Fetching 5-min: {sym.replace('.NS','')}...[/dim]")
        analysis = _analyze_5min(sym, p["price"], capital)
        _print_5min_panel(sym, analysis)

    console.print("[dim]5-min check done. Prices update every 5 min — re-run to refresh.[/dim]")


# ── Morning scan (run at 9:00–9:10 AM) ───────────────────────────────────────

def run_morning_scan(capital: int = 32_000) -> list:
    console.print(Panel.fit(
        f"[bold cyan]Morning Scanner[/bold cyan]  "
        f"[yellow]{datetime.now().strftime('%A %d %b %Y  %H:%M')}[/yellow]\n"
        f"[dim]Capital: ₹{capital:,}  |  {len(STOCK_UNIVERSE)} stocks  |  ~2 min[/dim]",
        border_style="cyan"
    ))

    # Sector momentum
    console.print("[dim]Fetching sector momentum...[/dim]", end=" ")
    t0 = time.time()
    sec_mom = _sector_momentum()
    console.print(f"[green]done ({time.time()-t0:.0f}s)[/green]")
    if sec_mom:
        hot = sorted(sec_mom.items(), key=lambda x: -x[1])[:3]
        console.print("[dim]Hot: " + "  ".join(
            f"{k.replace('_',' ')} [green]{v:+.1f}%[/green]" for k, v in hot
        ) + "[/dim]")

    # Score all cached stocks
    console.print("[dim]Scoring cached data...[/dim]")
    results = []
    for sym in STOCK_UNIVERSE:
        df = _load_cache(sym)
        if df is None:
            continue
        r = _score_stock(sym, df, sec_mom, capital)
        if r:
            results.append(r)

    results.sort(key=lambda x: -x["score"])
    top3 = results[:3]

    if not top3:
        console.print(Panel(
            "[bold red]NO CLEAN SETUPS TODAY[/bold red]\n\n"
            "ADX is too low across the board — market is choppy.\n"
            "Best move: sit out, protect capital.\n"
            "[dim]Not trading is also a position.[/dim]",
            border_style="red"
        ))
        return []

    # Save picks for --live check + webapp
    log   = _load_log()
    done  = sum(e["pnl"] for e in log.get("entries", []))
    webapp_payload = {
        "date":         date.today().isoformat(),
        "generated_at": datetime.now().isoformat(timespec="minutes"),
        "capital":      capital,
        "weekly_goal":  WEEKLY_GOAL,
        "week_banked":  done,
        "week_entries": log.get("entries", []),
        "picks":        top3,
    }
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(SAVED_PICKS_PATH, "w") as f:
        json.dump(top3, f, indent=2)
    os.makedirs(_WEBAPP_DIR, exist_ok=True)
    with open(WEBAPP_PICKS_PATH, "w") as f:
        json.dump(webapp_payload, f, indent=2)
    console.print(f"[dim]✓ Picks synced to webapp[/dim]")

    # ── Print daily picks ──────────────────────────────────────────────────
    console.print()
    console.rule("[bold yellow]DAILY PICKS — Based on yesterday's close")

    for i, p in enumerate(top3, 1):
        bt_label = BREAKOUT_LABEL.get(p["breakout_type"] or "", "[dim]—[/dim]")
        sym      = p["symbol"].replace(".NS", "")
        body = (
            f"[bold white]{sym}[/bold white]   "
            f"CMP [cyan]₹{p['price']:,.2f}[/cyan]   "
            f"ADX [yellow]{p['adx']:.0f}[/yellow]   "
            f"RSI [yellow]{p['rsi']:.0f}[/yellow]   "
            f"{bt_label}\n\n"
            f"[bold]ENTRY ZONE :[/bold] ₹{p['entry_low']:,.2f} – ₹{p['entry_high']:,.2f}  (near open)\n"
            f"[bold green]DAY TARGET :[/bold green] ₹{p['day_target']:,.2f}  (+{p['day_target_pct']}%)\n"
            f"[bold]SHARES     :[/bold] {p['shares']} × ₹{p['price']:,.2f}  =  ₹{p['shares']*p['price']:,.0f}\n"
            f"[bold green]PROFIT     :[/bold green] +₹{p['profit_at_tgt']:,.0f} if target hit\n"
        )
        if p["sector"]:
            body += f"[dim]Sector: {p['sector']} ({p['sector_mom']:+.1f}% today)[/dim]\n"
        body += "\n[dim]WHY:[/dim]\n"
        for r in p["reasons"]:
            body += f"  [dim]▸[/dim] {r}\n"

        color = "yellow" if i == 1 else "cyan" if i == 2 else "white"
        title = f"#{i}  Score {p['score']}/100" + ("  ← BEST BET" if i == 1 else "")
        console.print(Panel(body.strip(), title=title, border_style=color))
        console.print()

    # ── 5-min note ────────────────────────────────────────────────────────
    console.rule()
    console.print(Panel(
        "[bold yellow]DO NOT BUY AT 9:15 AM BLINDLY[/bold yellow]\n\n"
        "Wait for the [bold]Opening Range[/bold] to form (9:15–9:30 AM, first 3 candles).\n"
        "Then confirm with VWAP + 5-min trend before entering.\n\n"
        f"[bold cyan]At 9:30 AM run:[/bold cyan]  python morning_scanner.py --live\n"
        f"[dim]This will fetch live 5-min data and tell you: ENTER / WAIT / SKIP[/dim]",
        border_style="cyan",
        title="NEXT STEP",
    ))

    # Weekly context
    log  = _load_log()
    done = sum(e["pnl"] for e in log.get("entries", []))
    need = max(0, WEEKLY_GOAL - done)
    console.print(
        f"\n[dim]Weekly goal ₹{WEEKLY_GOAL:,}  |  "
        f"Banked ₹{done:+,}  |  "
        f"Still need ₹{need:,}[/dim]"
    )
    return top3


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--log" in args:
        idx = args.index("--log")
        if idx + 1 < len(args):
            try:
                log_pnl(int(args[idx + 1].replace("+", "")))
            except ValueError:
                console.print("[red]Usage: --log +820  or  --log -300[/red]")
        sys.exit(0)

    if "--progress" in args:
        show_progress()
        sys.exit(0)

    capital = 32_000
    if "--capital" in args:
        idx = args.index("--capital")
        if idx + 1 < len(args):
            try:
                capital = int(args[idx + 1])
            except ValueError:
                pass

    if "--live" in args:
        run_live_check(capital=capital)
    else:
        run_morning_scan(capital=capital)
