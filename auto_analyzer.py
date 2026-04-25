"""
Fully autonomous market analyzer — zero inputs, zero RSS.

Fetches structured market data, computes sector impacts from real numbers,
scores all stocks, generates a full HTML report.

Usage:
  python auto_analyzer.py              # full auto run
  python auto_analyzer.py --days 5     # wider lookback for sector indices
  python auto_analyzer.py --refresh    # force-refresh stock price cache first
"""

import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import pickle
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from config import SECTOR_STOCKS, RESULTS_DIR, STOCK_UNIVERSE
from market_data import fetch_all_market_data, render_market_data
from impact_engine import calculate_sector_impacts, compute_stock_boost
from regime_detector import detect_regime
from data_fetcher import fetch_bulk_stocks
from stock_scorer import score_stock
from peer_analyzer import build_sector_rs_map

console = Console()
os.makedirs(RESULTS_DIR, exist_ok=True)

DATA_CACHE_DIR = os.path.join(RESULTS_DIR, "cache")


def _load_cached(symbol: str):
    path = os.path.join(DATA_CACHE_DIR, symbol.replace(".", "_").replace("&", "AND") + ".pkl")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _build_sector_map() -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for sector, stocks in SECTOR_STOCKS.items():
        for sym in stocks:
            mapping.setdefault(sym, []).append(sector)
    return mapping


# ── Terminal Renders ──────────────────────────────────────────────────────────

def _render_impacts(impacts: dict) -> None:
    table = Table(title="Sector Impacts — Data-Driven", box=box.ROUNDED, border_style="cyan")
    table.add_column("Sector",    style="bold", width=24)
    table.add_column("Score",     justify="center", width=8)
    table.add_column("Direction", width=12)
    table.add_column("Top Reason", width=60)
    table.add_column("Key Stocks", width=35)

    for sector, data in sorted(impacts.items(), key=lambda x: -abs(x[1]["score"])):
        sc  = data["score"]
        c   = "green" if sc > 0 else "red" if sc < 0 else "yellow"
        arrow = "POSITIVE" if sc > 0 else "NEGATIVE" if sc < 0 else "NEUTRAL"
        reason = data["reasons"][0][:59] if data["reasons"] else ""
        stocks = ", ".join(s.replace(".NS", "") for s in data["stocks"][:4])
        table.add_row(
            sector.replace("_", " "),
            f"[{c} bold]{sc:+d}[/{c} bold]",
            f"[{c}]{arrow}[/{c}]",
            f"[dim]{reason}[/dim]",
            stocks,
        )
    console.print(table)


def _render_picks(picks: list[dict]) -> None:
    table = Table(title="Event-Adjusted Stock Picks", box=box.ROUNDED, border_style="green")
    table.add_column("Rank",   style="dim",        width=5)
    table.add_column("Symbol", style="bold cyan",   width=14)
    table.add_column("Price",  justify="right",     width=10)
    table.add_column("Target", style="green",       justify="right", width=11)
    table.add_column("Stop",   style="red",         justify="right", width=10)
    table.add_column("+%",     style="green bold",  justify="right", width=7)
    table.add_column("Score",  style="yellow bold", justify="right", width=7)
    table.add_column("Boost",  justify="center",    width=8)
    table.add_column("Sectors", width=28)

    for i, p in enumerate(picks[:12], 1):
        b  = p.get("market_boost", p.get("score_breakdown", {}).get("market_boost", 0))
        bc = "green" if b > 0 else "red" if b < 0 else "dim"
        secs = ", ".join(s.replace("_", " ") for s in p.get("sectors", [])[:2])
        table.add_row(
            f"#{i}",
            p["symbol"].replace(".NS", ""),
            f"{p['price']:,.2f}",
            f"{p['target']:,.2f}",
            f"{p['stop_loss']:,.2f}",
            f"+{p['target_pct']}%",
            str(p["total_score"]),
            f"[{bc}]{b:+d}[/{bc}]",
            secs,
        )
    console.print(table)

    if picks:
        p   = picks[0]
        b   = p.get("market_boost", p.get("score_breakdown", {}).get("market_boost", 0))
        bc  = "green" if b > 0 else "red" if b < 0 else "yellow"
        ctx = (p.get("market_context") or "")[:120]
        console.print(Panel(
            f"[bold yellow]{p['symbol'].replace('.NS','')}[/bold yellow]\n\n"
            f"Entry Rs{p['price']}  |  Target Rs{p['target']} (+{p['target_pct']}%)  |  Stop Rs{p['stop_loss']}\n"
            f"Score: {p['total_score']}/150  |  Market boost: [{bc}]{b:+d}[/{bc}]\n"
            f"[cyan]Why:[/cyan] {ctx}\n\n" +
            "\n".join(f"  • {r}" for r in p["rationale"]),
            border_style="yellow", title="Top Autonomous Pick",
        ))


# ── HTML Report ───────────────────────────────────────────────────────────────

def _global_html(factors: dict) -> str:
    LABELS = {
        "Brent Crude":  "OMCs, Paints, Chemicals, Auto",
        "Gold":         "NBFC gold-loan stocks",
        "USD/INR":      "IT & Pharma export revenues",
        "S&P 500":      "FII risk appetite → Banks",
        "US 10Y Yield": "FII EM allocation → Banks/NBFC",
        "Hang Seng":    "Metals (China demand proxy)",
    }
    rows = ""
    for name, d in factors.items():
        pct = d["pct_change"]
        c   = "#56d364" if pct > 0 else "#ff7b72"
        lbl = LABELS.get(name, "")
        rows += f"<tr><td style='color:#58a6ff'>{name}</td><td style='text-align:right'>{d['price']:,.4g}</td><td style='text-align:right;color:{c};font-weight:bold'>{pct:+.2f}%</td><td style='color:#8b949e;font-size:0.82em'>{lbl}</td></tr>"
    return f"<table style='width:100%;border-collapse:collapse;background:#161b22;border-radius:8px;overflow:hidden'><thead><tr style='background:#21262d'><th style='padding:8px;text-align:left;color:#8b949e'>Factor</th><th style='padding:8px;text-align:right;color:#8b949e'>Price</th><th style='padding:8px;text-align:right;color:#8b949e'>1D</th><th style='padding:8px;text-align:left;color:#8b949e'>India Impact On</th></tr></thead><tbody style='color:#e6edf3'>{rows}</tbody></table>"


def _sectors_html(impacts: dict) -> str:
    rows = ""
    for s, d in sorted(impacts.items(), key=lambda x: -abs(x[1]["score"])):
        sc  = d["score"]
        c   = "#56d364" if sc > 0 else "#ff7b72" if sc < 0 else "#f0c040"
        reason = d["reasons"][0][:65] if d["reasons"] else ""
        stocks = ", ".join(x.replace(".NS","") for x in d["stocks"][:5])
        dp     = d["data_points"][0] if d["data_points"] else ""
        rows  += f"<tr><td style='font-weight:bold'>{s.replace('_',' ')}</td><td style='text-align:center;color:{c};font-weight:bold;font-size:1.1em'>{sc:+d}</td><td style='color:{c};font-weight:bold'>{d['direction']}</td><td style='color:#8b949e;font-size:0.82em'>{reason}</td><td style='color:#58a6ff;font-size:0.8em'>{dp}</td><td style='color:#8b949e;font-size:0.8em'>{stocks}</td></tr>"
    return f"<table style='width:100%;border-collapse:collapse;background:#161b22;border-radius:8px;overflow:hidden'><thead><tr style='background:#21262d'><th style='padding:8px;text-align:left;color:#8b949e'>Sector</th><th style='padding:8px;text-align:center;color:#8b949e'>Score</th><th style='padding:8px;color:#8b949e'>Direction</th><th style='padding:8px;text-align:left;color:#8b949e'>Why</th><th style='padding:8px;text-align:left;color:#8b949e'>Driven by</th><th style='padding:8px;text-align:left;color:#8b949e'>Stocks</th></tr></thead><tbody style='color:#e6edf3'>{rows}</tbody></table>"


def _picks_html(picks: list[dict]) -> str:
    if not picks:
        return "<p style='color:#8b949e'>No cached data — run main.py first to populate cache.</p>"
    rows = ""
    for i, p in enumerate(picks[:15], 1):
        b  = p.get("market_boost", p.get("score_breakdown", {}).get("market_boost", 0))
        bc = "#56d364" if b > 0 else "#ff7b72" if b < 0 else "#8b949e"
        sc = "#56d364" if p["total_score"] >= 75 else "#f0c040" if p["total_score"] >= 55 else "#ff7b72"
        rs = "; ".join(p.get("rationale", [])[:2])
        ctx = (p.get("market_context") or rs)[:80]
        rows += f"<tr><td style='color:#8b949e;text-align:center'>#{i}</td><td style='color:#58a6ff;font-weight:bold'>{p['symbol'].replace('.NS','')}</td><td>Rs {p['price']:,.2f}</td><td style='color:#56d364'>Rs {p['target']:,.2f} (+{p['target_pct']}%)</td><td style='color:#ff7b72'>Rs {p['stop_loss']:,.2f}</td><td style='color:{sc};font-weight:bold'>{p['total_score']}/150</td><td style='color:{bc};font-weight:bold'>{b:+d}</td><td style='color:#8b949e;font-size:0.8em'>{ctx}</td></tr>"
    return f"<table style='width:100%;border-collapse:collapse;background:#161b22;border-radius:8px;overflow:hidden'><thead><tr style='background:#21262d'><th style='padding:8px;color:#8b949e'>#</th><th style='padding:8px;text-align:left;color:#8b949e'>Symbol</th><th style='padding:8px;color:#8b949e'>Price</th><th style='padding:8px;color:#8b949e'>Target</th><th style='padding:8px;color:#8b949e'>Stop</th><th style='padding:8px;color:#8b949e'>Score</th><th style='padding:8px;color:#8b949e'>Boost</th><th style='padding:8px;text-align:left;color:#8b949e'>Why</th></tr></thead><tbody style='color:#e6edf3'>{rows}</tbody></table>"


def _fii_html(fii: dict, sector_idx: dict) -> str:
    fii_net = fii.get("fii_net_cr")
    dii_net = fii.get("dii_net_cr")
    fii_c   = "#56d364" if (fii_net or 0) > 0 else "#ff7b72"
    dii_c   = "#56d364" if (dii_net or 0) > 0 else "#ff7b72"
    fii_str = f"<span style='color:{fii_c};font-size:1.3em;font-weight:bold'>FII: ₹{fii_net:+,.0f} Cr</span>" if fii_net is not None else "<span style='color:#8b949e'>FII: N/A</span>"
    dii_str = f"<span style='color:{dii_c};font-size:1.3em;font-weight:bold'>DII: ₹{dii_net:+,.0f} Cr</span>" if dii_net is not None else "<span style='color:#8b949e'>DII: N/A</span>"

    idx_rows = ""
    for name, d in sorted(sector_idx.items(), key=lambda x: -x[1]["relative_strength"]):
        pct = d["pct_change"]
        rel = d["relative_strength"]
        pc  = "#56d364" if pct > 0 else "#ff7b72"
        rc  = "#56d364" if rel > 0.5 else "#ff7b72" if rel < -0.5 else "#f0c040"
        idx_rows += f"<tr><td>{name}</td><td style='text-align:right;color:{pc}'>{pct:+.2f}%</td><td style='text-align:right;color:{rc};font-weight:bold'>{rel:+.2f}%</td></tr>"

    return f"""
    <div style='display:grid;grid-template-columns:1fr 1fr;gap:20px'>
      <div style='background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px'>
        <div style='color:#8b949e;font-size:0.8em;margin-bottom:8px'>INSTITUTIONAL FLOWS ({fii.get('date','')})</div>
        <div style='margin-bottom:6px'>{fii_str}</div>
        <div>{dii_str}</div>
      </div>
      <div>
        <table style='width:100%;border-collapse:collapse;background:#161b22;border-radius:8px;overflow:hidden'>
          <thead><tr style='background:#21262d'><th style='padding:6px;text-align:left;color:#8b949e'>Sector Index</th><th style='padding:6px;text-align:right;color:#8b949e'>1D%</th><th style='padding:6px;text-align:right;color:#8b949e'>vs Nifty</th></tr></thead>
          <tbody style='color:#e6edf3'>{idx_rows}</tbody>
        </table>
      </div>
    </div>"""


def generate_html_report(regime, md, impacts, picks) -> str:
    ts  = datetime.now().strftime("%d %b %Y %H:%M")
    reg = regime.get("regime", "UNKNOWN")
    rc  = {"STRONG_BULL":"#00c853","BULL":"#64dd17","SIDEWAYS":"#ff9800","BEAR":"#ff5252","STRONG_BEAR":"#d50000","VOLATILE":"#aa00ff"}.get(reg, "#90a4ae")
    factors   = md.get("global_factors", {})
    sec_idx   = md.get("sector_indices", {})
    fii       = md.get("fii_dii", {})

    top_html = ""
    if picks:
        p   = picks[0]
        b   = p.get("market_boost", p.get("score_breakdown", {}).get("market_boost", 0))
        bc  = "#56d364" if b > 0 else "#ff7b72" if b < 0 else "#8b949e"
        sc  = "#56d364" if p["total_score"] >= 75 else "#f0c040"
        rs  = "<br>".join(f"• {r}" for r in p.get("rationale", []))
        ctx = (p.get("market_context") or "")[:140]
        top_html = f"""
        <div style='background:#161b22;border:2px solid #f0c040;border-radius:12px;padding:20px;margin-bottom:24px'>
          <div style='color:#8b949e;font-size:0.8em'>TOP AUTONOMOUS PICK</div>
          <div style='font-size:2em;font-weight:bold;color:#58a6ff;margin:4px 0'>{p['symbol'].replace('.NS','')}</div>
          <div style='display:flex;gap:16px;flex-wrap:wrap;margin:12px 0'>
            <div style='background:#21262d;padding:10px 16px;border-radius:8px'><div style='color:#8b949e;font-size:0.7em'>ENTRY</div><div style='font-weight:bold'>Rs {p['price']:,.2f}</div></div>
            <div style='background:#21262d;padding:10px 16px;border-radius:8px'><div style='color:#56d364;font-size:0.7em'>TARGET (+{p['target_pct']}%)</div><div style='font-weight:bold;color:#56d364'>Rs {p['target']:,.2f}</div></div>
            <div style='background:#21262d;padding:10px 16px;border-radius:8px'><div style='color:#ff7b72;font-size:0.7em'>STOP LOSS</div><div style='font-weight:bold;color:#ff7b72'>Rs {p['stop_loss']:,.2f}</div></div>
            <div style='background:#21262d;padding:10px 16px;border-radius:8px'><div style='color:#8b949e;font-size:0.7em'>SCORE</div><div style='font-weight:bold;color:{sc}'>{p['total_score']}/150</div></div>
            <div style='background:#21262d;padding:10px 16px;border-radius:8px'><div style='color:#8b949e;font-size:0.7em'>MARKET BOOST</div><div style='font-weight:bold;color:{bc}'>{b:+d} pts</div></div>
          </div>
          <div style='color:#8b949e;font-size:0.85em;margin-top:6px'><strong style='color:#e6edf3'>What's driving it:</strong> {ctx}</div>
          <div style='color:#8b949e;font-size:0.85em;margin-top:6px'>{rs}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Autonomous Analysis — {ts}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',sans-serif;background:#0d1117;color:#e6edf3;padding:24px;max-width:1500px;margin:0 auto}}
  h1{{color:#58a6ff;font-size:2em;margin-bottom:4px}}
  h2{{color:#58a6ff;font-size:1.25em;margin:28px 0 10px;border-bottom:1px solid #21262d;padding-bottom:6px}}
  .sub{{color:#8b949e;font-size:0.9em;margin-bottom:24px}}
  .regime{{background:#161b22;border-left:5px solid {rc};padding:16px;border-radius:8px;margin-bottom:24px}}
  .regime-title{{font-size:1.4em;color:{rc};font-weight:bold}}
  .stats{{display:flex;gap:12px;margin-top:10px;flex-wrap:wrap}}
  .stat{{background:#21262d;padding:8px 12px;border-radius:6px;font-size:0.85em}}
  .stat .l{{color:#8b949e}}.stat .v{{color:#e6edf3;font-weight:bold}}
  table td,table th{{padding:10px 14px;border-bottom:1px solid #21262d}}
  .note{{margin-top:30px;padding:12px;background:#161b22;border:1px solid #f0c04044;border-radius:8px;color:#8b949e;font-size:0.8em}}
</style>
</head>
<body>
<h1>Autonomous Market Analyzer</h1>
<p class="sub">Generated: {ts} | {len(picks)} stocks scored | {len(impacts)} sectors impacted | No RSS — pure data</p>

<div class="regime">
  <div class="regime-title">Regime: {reg} — {regime.get('description','')}</div>
  <div class="stats">
    <div class="stat"><span class="l">Nifty </span><span class="v">{regime.get('nifty_close','')}</span></div>
    <div class="stat"><span class="l">ADX </span><span class="v">{regime.get('adx','')}</span></div>
    <div class="stat"><span class="l">RSI </span><span class="v">{regime.get('rsi','')}</span></div>
    <div class="stat"><span class="l">India VIX </span><span class="v">{regime.get('india_vix','')}</span></div>
    <div class="stat"><span class="l">1M Ret </span><span class="v">{regime.get('ret_1m_pct','')}%</span></div>
    <div class="stat"><span class="l">3M Ret </span><span class="v">{regime.get('ret_3m_pct','')}%</span></div>
  </div>
</div>

{top_html}

<h2>Institutional Flows & Sector Rotation</h2>
{_fii_html(fii, sec_idx)}

<h2>India-Relevant Global Factors</h2>
{_global_html(factors)}

<h2>Sector Impact (Quantitative)</h2>
{_sectors_html(impacts)}

<h2>Stock Picks — Market-Adjusted</h2>
{_picks_html(picks)}

<div class="note">
  <strong>Methodology:</strong> Technical (EMAs, RSI, MACD, ADX, OBV, weekly confluence) +
  Fundamental quality (ROE, D/E, revenue growth, earnings growth, net margin, promoter holding) +
  Stability (liquidity by daily turnover, spike/gap frequency) +
  Entry quality (Bollinger bands, 52W position) + Momentum (ROC) +
  Regime alignment + Market data boost (FII/DII flows, crude, USD/INR, US yields, sector rotation).
  Stop losses are ATR-based (2.5× ATR). Position size scales with score confidence. Scores out of 130.
</div>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def run_auto_analysis(refresh_cache: bool = False) -> dict:
    console.print(Panel.fit(
        "[bold cyan]Autonomous Market Analyzer[/bold cyan]\n"
        "[yellow]FII flows + Crude + USD/INR + Sector indices + Technical[/yellow]\n"
        f"[dim]{datetime.now().strftime('%A, %d %B %Y %H:%M')} | No RSS[/dim]",
        border_style="cyan",
    ))

    console.rule("[bold blue]Step 1/4 — Market Data")
    md = fetch_all_market_data()
    render_market_data(md)

    console.rule("[bold blue]Step 2/4 — Sector Impact Calculation")
    impacts = calculate_sector_impacts(md)
    _render_impacts(impacts)

    console.rule("[bold blue]Step 3/4 — Market Regime")
    from data_fetcher import fetch_nifty_data
    nifty_df = fetch_nifty_data()
    regime   = detect_regime()

    if refresh_cache:
        console.print("[yellow]Refreshing stock price cache...[/yellow]")
        fetch_bulk_stocks(STOCK_UNIVERSE, delay=0.25)

    console.rule("[bold blue]Step 4/4 — Stock Scoring")
    sector_map = _build_sector_map()
    all_symbols = sorted(set(sym for stocks in SECTOR_STOCKS.values() for sym in stocks))

    # Pre-load all cached data for sector RS computation
    all_stock_data = {}
    for sym in all_symbols:
        df = _load_cached(sym)
        if df is not None and len(df) >= 200:
            all_stock_data[sym] = df

    sector_rs_map = build_sector_rs_map(all_stock_data)

    picks = []
    skipped = 0
    for sym in all_symbols:
        df = all_stock_data.get(sym)
        if df is None:
            skipped += 1
            continue

        boost, ctx = compute_stock_boost(sym, impacts, sector_map)
        result = score_stock(sym, df, nifty_df, regime,
                             market_boost=boost, market_context="; ".join(ctx[:2]),
                             sector_rs=sector_rs_map.get(sym))
        if result:
            result["market_boost"] = boost
            result["sectors"]      = sector_map.get(sym, [])
            picks.append(result)

    picks.sort(key=lambda x: x["total_score"], reverse=True)
    console.print(f"[green]Scored {len(picks)} stocks | {skipped} skipped (no cache — run main.py --refresh)[/green]")

    _render_picks(picks)

    html = generate_html_report(regime, md, impacts, picks)
    path = os.path.join(RESULTS_DIR, "auto_analysis.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    console.print(f"\n[bold green]Done.[/bold green] Report: {path}")

    try:
        os.startfile(path)
    except Exception:
        pass

    return {"regime": regime, "impacts": impacts, "picks": picks[:15], "market_data": md}


if __name__ == "__main__":
    refresh = "--refresh" in sys.argv
    run_auto_analysis(refresh_cache=refresh)
