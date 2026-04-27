"""
Indian Market Analyzer — Main Analysis Runner
Usage: python main.py
Runs full analysis (~30-60 min), saves results, then shows notification.
"""
import os
import sys

# Force UTF-8 for Windows terminals (needed for emoji/unicode output)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import time
import json
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from config import STOCK_UNIVERSE, INVESTMENT_AMOUNT, RESULTS_DIR
from data_fetcher import fetch_bulk_stocks, fetch_nifty_data
from regime_detector import detect_regime
from market_data import fetch_all_market_data, render_market_data
from impact_engine import calculate_sector_impacts, compute_stock_boost
from event_analyzer import _build_stock_sector_map
from stock_scorer import score_stock
from peer_analyzer import build_sector_rs_map
from report_generator import save_json, generate_html
from accuracy_tracker import check_accuracy, save_predictions, print_accuracy_report

console = Console()
os.makedirs(RESULTS_DIR, exist_ok=True)


def banner():
    console.print(Panel.fit(
        "[bold cyan]📊 Indian Market Analyzer[/bold cyan]\n"
        f"[yellow]Budget: ₹{INVESTMENT_AMOUNT:,}  |  Universe: {len(STOCK_UNIVERSE)} stocks  |  Mode: Long-term (1-3 months)[/yellow]\n"
        f"[dim]{datetime.now().strftime('%A, %d %B %Y %H:%M')}[/dim]",
        border_style="cyan"
    ))


def run_analysis(quick: bool = False) -> dict:
    banner()

    # ── Step 1: Market Regime ──────────────────────────────────────────────
    console.rule("[bold]Step 1/5 — Market Regime Detection")
    regime = detect_regime()

    if regime["regime"] in ("STRONG_BEAR",) and not quick:
        console.print(
            "[bold red]⚠️  Market is in STRONG BEAR regime. "
            "Analysis will continue but long positions carry high risk.[/bold red]"
        )

    # ── Step 2: Fetch Nifty reference data ────────────────────────────────
    console.rule("[bold]Step 2/5 — Fetching Nifty 50 reference data")
    nifty_df = fetch_nifty_data()
    if nifty_df is None:
        console.print("[red]Could not fetch Nifty data. Using fallback correlation.[/red]")

    # ── Step 3: Fetch Stock Data ───────────────────────────────────────────
    universe = STOCK_UNIVERSE[:30] if quick else STOCK_UNIVERSE
    console.rule(f"[bold]Step 3/5 — Downloading {len(universe)} stocks (cached if fresh)")
    t0 = time.time()
    stock_data = fetch_bulk_stocks(universe, delay=0.25)
    console.print(f"[green]✓ Downloaded {len(stock_data)} stocks in {time.time()-t0:.0f}s[/green]")

    # ── Accuracy Check: resolve yesterday's predictions ────────────────────
    console.rule("[bold dim]Self-Audit — Previous Prediction Accuracy")
    accuracy_stats = check_accuracy(stock_data)
    print_accuracy_report(accuracy_stats, console)

    # ── Step 4: Market Data (FII/DII, Crude, USD/INR, Sector Indices) ────────
    console.rule("[bold]Step 4/5 — Market Data: FII Flows + Global Factors + Sector Indices")
    market_data = fetch_all_market_data()
    render_market_data(market_data)
    sector_impacts = calculate_sector_impacts(market_data)
    stock_sector_map = _build_stock_sector_map()
    fii = market_data.get("fii_dii", {})
    fii_status = f"FII ₹{fii.get('fii_net_cr',0):+,.0f} Cr" if fii.get("fii_net_cr") is not None else "FII: N/A"
    console.print(f"[green]✓ {len(sector_impacts)} sectors scored | {fii_status}[/green]")

    # ── Step 5: Score Every Stock ──────────────────────────────────────────
    console.rule("[bold]Step 5/5 — Scoring & Ranking Stocks")
    sector_rs_map = build_sector_rs_map(stock_data)
    scores = []
    failed = 0
    for sym, df in stock_data.items():
        boost, ctx = compute_stock_boost(sym, sector_impacts, stock_sector_map)
        result = score_stock(sym, df, nifty_df, regime,
                             market_boost=boost, market_context="; ".join(ctx[:2]),
                             sector_rs=sector_rs_map.get(sym))
        if result:
            scores.append(result)
        else:
            failed += 1

    if not scores:
        console.print("[red]No stocks could be scored. Check internet connection.[/red]")
        return {}

    scores.sort(key=lambda x: x["total_score"], reverse=True)
    console.print(f"[green]✓ Scored {len(scores)} stocks | {failed} skipped (price/data filter)[/green]")

    # ── ML status line ─────────────────────────────────────────────────────
    try:
        from ml_retrainer import print_ml_status
        print_ml_status(console)
    except Exception:
        pass

    # Strip internal df_ind reference before serialisation
    for s in scores:
        s.pop("_df_ind", None)

    top_picks = scores[:10]

    # ── Print Summary Table ────────────────────────────────────────────────
    table = Table(title="Top 10 Stock Picks", box=box.ROUNDED, border_style="cyan")
    table.add_column("Rank",    style="dim",         width=5)
    table.add_column("Symbol",  style="bold cyan",   width=12)
    table.add_column("Price",   justify="right",     width=10)
    table.add_column("Stop",    style="red",         justify="right", width=10)
    table.add_column("Target",  style="green",       justify="right", width=10)
    table.add_column("+%",      style="green bold",  justify="right", width=7)
    table.add_column("Score",   style="yellow bold", justify="right", width=8)
    table.add_column("Pos%",    justify="right",     width=6)
    table.add_column("Fund",    justify="right",     width=7)
    table.add_column("RS",      justify="right",     width=6)
    table.add_column("Sector",  style="dim",         width=18)

    for i, p in enumerate(top_picks, 1):
        sb     = p.get("score_breakdown", {})
        sector = (p.get("sector_rs") or {}).get("sector", "")
        table.add_row(
            f"#{i}",
            p["symbol"].replace(".NS", ""),
            f"{p['price']:,.2f}",
            f"{p['stop_loss']:,.2f} (-{p.get('stop_pct',0):.1f}%)",
            f"{p['target']:,.2f}",
            f"+{p['target_pct']}%",
            f"{p['total_score']}/150",
            f"{p.get('position_size_pct',100)}%",
            str(sb.get("fundamental", 0)),
            str(sb.get("rel_strength", 0)),
            (sector or "").replace("_", " "),
        )
    console.print(table)

    # ── Print Top Pick Detail ──────────────────────────────────────────────
    if top_picks:
        p = top_picks[0]
        console.print(Panel(
            f"[bold yellow]BEST PICK: {p['symbol'].replace('.NS','')}[/bold yellow]\n\n"
            f"Price: ₹{p['price']}  |  Buy {p['shares']} shares @ ₹{p['invested']} total\n"
            f"Target: ₹{p['target']} (+{p['target_pct']}%)  |  Stop Loss: ₹{p['stop_loss']}\n"
            f"Max Gain: +₹{p['max_gain']}  |  Max Loss: -₹{p['max_loss']}\n"
            f"Score: {p['total_score']}/150  |  Manip Resist: {p['manip_resistance']['manip_resistance_score']}/100  |  Position: {p.get('position_size_pct',100)}%\n"
            f"Stop: {p['stop_pct']}% ATR-based  |  Fund: {p['score_breakdown'].get('fundamental',0)}/35  |  RS: {p['score_breakdown'].get('rel_strength',0)}/20\n\n"
            f"[cyan]Why:[/cyan]\n" +
            "\n".join(f"  • {r}" for r in p["rationale"]),
            border_style="yellow",
            title="🏆 #1 Recommendation"
        ))

    # ── Save & Generate Reports ────────────────────────────────────────────
    # Build sparkline price lists for top picks (last 60 closes)
    price_cache = {}
    for p in top_picks:
        sym = p["symbol"]
        df  = stock_data.get(sym)
        if df is not None:
            price_cache[sym] = df["close"].tail(60).tolist()

    output = {
        "generated_at": datetime.now().isoformat(timespec="minutes"),
        "regime": regime,
        "market_data": {
            "fii_dii":        market_data.get("fii_dii", {}),
            "nifty_1d_pct":   market_data.get("nifty_1d_pct", 0),
            "global_factors": {k: v["pct_change"] for k, v in market_data.get("global_factors", {}).items()},
        },
        "top_picks":        top_picks,
        "total_analyzed":   len(scores),
        "investment_budget": INVESTMENT_AMOUNT,
        "_price_cache":     price_cache,   # used for sparklines only, not saved to JSON
    }
    save_json({k: v for k, v in output.items() if k != "_price_cache"})
    generate_html(output)

    # ── Log predictions for tomorrow's accuracy check ──────────────────────
    added = save_predictions(top_picks)
    if added:
        console.print(f"[dim]✓ Logged {added} new predictions for accuracy tracking[/dim]")

    # ── ML daily retrain ──────────────────────────────────────────────────
    console.rule("[bold dim]ML Engine — Daily Retrain")
    try:
        from ml_retrainer import run_daily_retrain
        run_daily_retrain()
    except Exception as e:
        console.print(f"[dim]ML retrain skipped: {e}[/dim]")

    # ── Sync to webapp ─────────────────────────────────────────────────────
    try:
        import push_to_webapp
        push_to_webapp.main()
        console.print("[dim]✓ Analysis synced to webapp[/dim]")
    except Exception:
        pass

    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "market_report.html")
    console.print(f"\n[bold green]✓ Analysis complete![/bold green]")
    console.print(f"  JSON: {os.path.join(RESULTS_DIR, 'latest_analysis.json')}")
    console.print(f"  HTML: {html_path}")

    # Open report in browser
    try:
        os.startfile(html_path)
        console.print("[cyan]Opening HTML report in browser...[/cyan]")
    except Exception:
        pass

    return output


if __name__ == "__main__":
    args = set(sys.argv[1:])
    quick       = "--quick"       in args
    event_only  = "--event"       in args
    run_strait  = "--strait"      in args
    run_pm      = "--pm"          in args
    auto_mode   = "--auto"        in args
    with_events = "--with-events" in args
    refresh     = "--refresh"     in args

    days = 3
    if "--days" in sys.argv:
        idx = sys.argv.index("--days")
        if idx + 1 < len(sys.argv):
            try:
                days = int(sys.argv[idx + 1])
            except ValueError:
                pass

    if auto_mode:
        # Fully autonomous: global data + news themes + technical scoring
        from auto_analyzer import run_auto_analysis
        run_auto_analysis(days=days, refresh_cache=refresh)

    elif event_only or run_strait or run_pm:
        from event_analyzer import run_event_analysis
        run_event_analysis(
            run_pm=run_pm or event_only,
            run_strait=run_strait or event_only,
            days=days,
        )
    else:
        if quick:
            console.print("[yellow]Quick mode: analyzing first 30 stocks only[/yellow]")
        result = run_analysis(quick=quick)

        if with_events:
            from event_analyzer import run_event_analysis
            run_event_analysis(run_pm=True, run_strait=True, days=days)
