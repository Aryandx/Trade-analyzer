"""
Event-driven sector impact analyzer for Indian markets.

Analyzes news events (PM speeches, geopolitical events) and maps their impact
to specific sectors and stocks, also flagging unusual price/volume movers.

Usage:
  python event_analyzer.py              # Full analysis (PM speech + Strait)
  python event_analyzer.py --pm         # PM speech analysis only
  python event_analyzer.py --strait     # Strait of Hormuz analysis only
  python event_analyzer.py --days 3     # Look back N days for news (default: 3)
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
from datetime import datetime, timedelta
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

import pandas as pd
from config import (
    SECTOR_STOCKS, EVENT_SECTOR_IMPACTS, EVENT_RSS_FEEDS,
    DATA_CACHE_DIR, RESULTS_DIR, INVESTMENT_AMOUNT,
    STOP_LOSS_PCT, REWARD_RISK_RATIO, MAX_PRICE, MIN_PRICE,
)
from news_fetcher import fetch_event_news, score_sentiment
from data_fetcher import fetch_nifty_data
from regime_detector import detect_regime
from stock_scorer import score_stock
from technical_analysis import add_indicators

console = Console()


# ── Stock-to-Sector reverse lookup ──────────────────────────────────────────

def _build_stock_sector_map() -> dict[str, list[str]]:
    """Build reverse map: symbol -> [sectors it belongs to]."""
    mapping: dict[str, list[str]] = {}
    for sector, stocks in SECTOR_STOCKS.items():
        for sym in stocks:
            mapping.setdefault(sym, []).append(sector)
    return mapping


def _compute_event_boost(symbol: str, all_sector_impacts: dict[str, dict], stock_sector_map: dict) -> tuple[int, list[str]]:
    """
    Given combined sector impacts from all events, compute net event boost for a stock.
    Returns (boost_points, [context_strings]).
    """
    sectors = stock_sector_map.get(symbol, [])
    total_boost = 0
    contexts = []
    for sector in sectors:
        if sector in all_sector_impacts:
            score = all_sector_impacts[sector]["score"]
            # Scale: each sector score unit = 4 pts, cap per sector at ±12
            sector_boost = max(-12, min(12, score * 4))
            total_boost += sector_boost
            direction = "+" if score > 0 else ""
            reasons = "; ".join(list(all_sector_impacts[sector]["reasons"])[:1])
            contexts.append(f"{sector.replace('_',' ')} ({direction}{score}): {reasons}")
    return max(-15, min(15, total_boost)), contexts


# ── Event-Boosted Stock Suggestions ─────────────────────────────────────────

def generate_event_suggestions(all_sector_impacts: dict[str, dict]) -> list[dict]:
    """
    Score all stocks whose sectors are affected by current events.
    Uses cached data + technical scoring + event boost.
    Returns sorted list of suggestions.
    """
    stock_sector_map = _build_stock_sector_map()
    affected_stocks = set()
    for sector in all_sector_impacts:
        for sym in SECTOR_STOCKS.get(sector, []):
            affected_stocks.add(sym)

    if not affected_stocks:
        return []

    console.print(f"[cyan]Scoring {len(affected_stocks)} event-affected stocks...[/cyan]")

    regime = detect_regime()
    nifty_df = fetch_nifty_data()

    results = []
    for sym in sorted(affected_stocks):
        df = _load_cached(sym)
        if df is None or len(df) < 200:
            continue
        try:
            df_ind = add_indicators(df)
            if len(df_ind) < 200:
                continue
        except Exception:
            continue

        boost, ctx = _compute_event_boost(sym, all_sector_impacts, stock_sector_map)
        event_context = " | ".join(ctx[:2])

        result = score_stock(
            sym, df_ind, nifty_df, regime,
            news_sentiment={"sentiment": 0.0},
            event_boost=boost,
            event_context=event_context,
        )
        if result:
            result["event_boost"] = boost
            result["event_context"] = event_context
            result["sectors"] = stock_sector_map.get(sym, [])
            results.append(result)

    results.sort(key=lambda x: x["total_score"], reverse=True)
    return results


# ── Unusual Mover Detection ──────────────────────────────────────────────────

def _load_cached(symbol: str):
    """Load cached price dataframe if available."""
    path = os.path.join(DATA_CACHE_DIR, symbol.replace(".", "_").replace("&", "AND") + ".pkl")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def detect_unusual_movers(symbols: list[str]) -> list[dict]:
    """
    Scan cached stock data for unusual price/volume activity over the last 5 days.
    Returns list of movers sorted by unusualness score.
    """
    movers = []
    for sym in symbols:
        df = _load_cached(sym)
        if df is None or len(df) < 25:
            continue
        try:
            recent = df.iloc[-1]
            prev = df.iloc[-2]
            price = float(recent["Close"])
            prev_price = float(prev["Close"])
            pct_change = (price - prev_price) / prev_price * 100

            vol_today = float(recent["Volume"])
            avg_vol_20 = float(df["Volume"].iloc[-21:-1].mean())
            vol_ratio = vol_today / avg_vol_20 if avg_vol_20 > 0 else 1.0

            # 5-day price range
            high_5d = float(df["High"].iloc[-5:].max())
            low_5d = float(df["Low"].iloc[-5:].min())
            range_5d_pct = (high_5d - low_5d) / low_5d * 100

            unusualness = abs(pct_change) * vol_ratio
            if abs(pct_change) >= 2.0 or vol_ratio >= 1.8:
                movers.append({
                    "symbol": sym,
                    "price": round(price, 2),
                    "pct_change": round(pct_change, 2),
                    "vol_ratio": round(vol_ratio, 2),
                    "range_5d_pct": round(range_5d_pct, 2),
                    "unusualness": round(unusualness, 2),
                })
        except Exception:
            continue
    movers.sort(key=lambda x: x["unusualness"], reverse=True)
    return movers


# ── Event Impact Analysis ────────────────────────────────────────────────────

def analyze_event(event_key: str, articles: list[dict]) -> dict:
    """
    Given an event key and fetched articles, compute sector impact scores.
    Returns sector -> {impact, confidence, matched_articles, stocks} dict.
    """
    impact_rules = EVENT_SECTOR_IMPACTS.get(event_key, [])
    sector_impacts: dict[str, dict] = {}

    for art in articles:
        text = (art["title"] + " " + art["summary"]).lower()
        for keyword, sector, direction, reason in impact_rules:
            if keyword.lower() in text:
                if sector not in sector_impacts:
                    sector_impacts[sector] = {
                        "score": 0,
                        "article_count": 0,
                        "reasons": set(),
                        "stocks": SECTOR_STOCKS.get(sector, []),
                        "articles": [],
                    }
                sector_impacts[sector]["score"] += direction
                sector_impacts[sector]["article_count"] += 1
                sector_impacts[sector]["reasons"].add(reason)
                if len(sector_impacts[sector]["articles"]) < 3:
                    sector_impacts[sector]["articles"].append(art["title"][:80])

    for sector, data in sector_impacts.items():
        data["reasons"] = list(data["reasons"])
        if data["score"] > 0:
            data["direction"] = "POSITIVE"
        elif data["score"] < 0:
            data["direction"] = "NEGATIVE"
        else:
            data["direction"] = "NEUTRAL"

    return sector_impacts


# ── Strait of Hormuz Combined Analysis ──────────────────────────────────────

def strait_analysis(days: int = 3) -> dict:
    console.rule("[bold cyan]Strait of Hormuz — Market Impact")
    articles = fetch_event_news(
        keywords=["strait", "hormuz", "iran", "oil supply", "crude", "shipping", "ceasefire"],
        extra_feeds=EVENT_RSS_FEEDS.get("geopolitical", []),
        max_age_days=days,
    )
    console.print(f"[green]Fetched {len(articles)} relevant articles[/green]")

    impact = analyze_event("strait_hormuz", articles)

    _render_sector_table(
        impact, "Strait of Hormuz Open — Sector Impact",
        preamble=(
            "Iran strait open → crude supply normalizes → oil prices fall.\n"
            "Downstream/refining benefits; upstream E&P and defense face headwinds."
        )
    )

    all_affected_stocks = []
    for data in impact.values():
        all_affected_stocks.extend(data["stocks"])
    movers = detect_unusual_movers(list(set(all_affected_stocks)))
    if movers:
        _render_movers_table(movers, "Unusual Movers in Affected Sectors")

    return {"event": "strait_hormuz", "sector_impacts": impact, "unusual_movers": movers, "articles": len(articles)}


# ── PM Speech Analysis ───────────────────────────────────────────────────────

def pm_speech_analysis(days: int = 3) -> dict:
    console.rule("[bold yellow]PM Speech — Market Impact")

    # Fetch from both standard feeds and government/PIB sources
    articles = fetch_event_news(
        keywords=[
            "modi speech", "prime minister", "pm modi", "modi announces",
            "budget", "infrastructure", "capex", "defence", "digital india",
            "make in india", "pli", "renewable", "solar", "green energy",
            "ayushman", "health", "railways", "highway", "startup",
            "atmanirbhar", "investment", "policy"
        ],
        extra_feeds=EVENT_RSS_FEEDS.get("government", []),
        max_age_days=days,
    )
    console.print(f"[green]Fetched {len(articles)} PM speech-related articles[/green]")

    if not articles:
        console.print(
            "[yellow]No PM speech articles found yet. "
            "Run this again Monday morning after the speech news has propagated to RSS feeds.[/yellow]"
        )

    # Combine all PM speech sub-events into unified sector impact
    combined_impact: dict[str, dict] = {}
    for event_key in ["pm_speech_infra", "pm_speech_defense", "pm_speech_digital",
                      "pm_speech_energy", "pm_speech_health", "pm_speech_agri",
                      "pm_speech_manufacturing"]:
        partial = analyze_event(event_key, articles)
        for sector, data in partial.items():
            if sector not in combined_impact:
                combined_impact[sector] = data
            else:
                combined_impact[sector]["score"] += data["score"]
                combined_impact[sector]["article_count"] += data["article_count"]
                combined_impact[sector]["reasons"] = list(
                    set(combined_impact[sector]["reasons"]) | set(data["reasons"])
                )
                combined_impact[sector]["articles"] += data["articles"]

    for sector, data in combined_impact.items():
        if data["score"] > 0:
            data["direction"] = "POSITIVE"
        elif data["score"] < 0:
            data["direction"] = "NEGATIVE"
        else:
            data["direction"] = "NEUTRAL"

    _render_sector_table(combined_impact, "PM Speech — Sector Impact Analysis")

    all_affected_stocks = []
    for data in combined_impact.values():
        all_affected_stocks.extend(data["stocks"])
    movers = detect_unusual_movers(list(set(all_affected_stocks)))
    if movers:
        _render_movers_table(movers, "Unusual Movers in PM Speech-Sensitive Sectors")

    # Show speech summary if we found articles
    if articles:
        _show_top_articles(articles[:8], "Top PM Speech Articles Found")

    return {"event": "pm_speech", "sector_impacts": combined_impact, "unusual_movers": movers, "articles": len(articles)}


# ── Rendering Helpers ────────────────────────────────────────────────────────

def _render_sector_table(impact: dict, title: str, preamble: str = "") -> None:
    if preamble:
        console.print(Panel(preamble, border_style="dim"))

    if not impact:
        console.print("[dim]No sector impacts detected from available articles.[/dim]")
        return

    table = Table(title=title, box=box.ROUNDED, border_style="cyan")
    table.add_column("Sector", style="bold", width=22)
    table.add_column("Impact", width=10, justify="center")
    table.add_column("Score", justify="center", width=7)
    table.add_column("Articles", justify="center", width=9)
    table.add_column("Key Stocks", width=42)
    table.add_column("Why", width=45)

    for sector, data in sorted(impact.items(), key=lambda x: -abs(x[1]["score"])):
        direction = data["direction"]
        color = "green" if direction == "POSITIVE" else "red" if direction == "NEGATIVE" else "yellow"
        arrow = "⬆ POSITIVE" if direction == "POSITIVE" else "⬇ NEGATIVE" if direction == "NEGATIVE" else "→ NEUTRAL"
        stocks_display = ", ".join(s.replace(".NS", "") for s in data["stocks"][:5])
        if len(data["stocks"]) > 5:
            stocks_display += f" +{len(data['stocks'])-5} more"
        reason_text = "; ".join(list(data["reasons"])[:2])[:44]
        table.add_row(
            sector.replace("_", " "),
            f"[{color}]{arrow}[/{color}]",
            f"[{color}]{data['score']:+d}[/{color}]",
            str(data["article_count"]),
            stocks_display,
            reason_text,
        )
    console.print(table)


def _render_movers_table(movers: list[dict], title: str) -> None:
    table = Table(title=title, box=box.SIMPLE_HEAD, border_style="yellow")
    table.add_column("Symbol", style="bold cyan", width=14)
    table.add_column("Price (Rs)", justify="right", width=10)
    table.add_column("1D Change", justify="right", width=10)
    table.add_column("Vol Ratio", justify="right", width=10)
    table.add_column("5D Range %", justify="right", width=11)

    for m in movers[:12]:
        pct_color = "green" if m["pct_change"] > 0 else "red"
        vol_color = "yellow" if m["vol_ratio"] > 2.0 else "white"
        table.add_row(
            m["symbol"].replace(".NS", ""),
            f"{m['price']:,.2f}",
            f"[{pct_color}]{m['pct_change']:+.2f}%[/{pct_color}]",
            f"[{vol_color}]{m['vol_ratio']:.2f}x[/{vol_color}]",
            f"{m['range_5d_pct']:.2f}%",
        )
    console.print(table)


def _show_top_articles(articles: list[dict], title: str) -> None:
    table = Table(title=title, box=box.SIMPLE_HEAD, border_style="dim")
    table.add_column("Title", width=70)
    table.add_column("Source", width=20)
    for art in articles:
        table.add_row(art["title"][:70], art.get("source", "")[:20])
    console.print(table)


def _render_suggestions_table(picks: list[dict], title: str) -> None:
    table = Table(title=title, box=box.ROUNDED, border_style="green")
    table.add_column("Rank", style="dim", width=5)
    table.add_column("Symbol", style="bold cyan", width=14)
    table.add_column("Price (Rs)", justify="right", width=10)
    table.add_column("Target (Rs)", style="green", justify="right", width=11)
    table.add_column("Stop (Rs)", style="red", justify="right", width=10)
    table.add_column("Target %", style="green bold", justify="right", width=9)
    table.add_column("Score", style="yellow bold", justify="right", width=7)
    table.add_column("Event Boost", justify="center", width=12)
    table.add_column("Sectors", width=30)

    for i, p in enumerate(picks[:10], 1):
        boost = p.get("event_boost", 0)
        boost_color = "green" if boost > 0 else "red" if boost < 0 else "dim"
        boost_str = f"[{boost_color}]{boost:+d}[/{boost_color}]"
        sectors = ", ".join(s.replace("_", " ") for s in p.get("sectors", [])[:2])
        table.add_row(
            f"#{i}",
            p["symbol"].replace(".NS", ""),
            f"{p['price']:,.2f}",
            f"{p['target']:,.2f}",
            f"{p['stop_loss']:,.2f}",
            f"+{p['target_pct']}%",
            str(p["total_score"]),
            boost_str,
            sectors,
        )
    console.print(table)

    if picks:
        top = picks[0]
        boost = top.get("event_boost", 0)
        boost_label = f"Event Tailwind: +{boost} pts" if boost > 0 else f"Event Headwind: {boost} pts" if boost < 0 else "Neutral"
        ctx = top.get("event_context", "")
        console.print(Panel(
            f"[bold yellow]BEST EVENT PICK: {top['symbol'].replace('.NS','')}[/bold yellow]\n\n"
            f"Price: Rs{top['price']}  |  Target: Rs{top['target']} (+{top['target_pct']}%)  |  Stop: Rs{top['stop_loss']}\n"
            f"Score: {top['total_score']}/125  |  {boost_label}\n"
            f"[cyan]Event Context:[/cyan] {ctx}\n\n"
            f"[cyan]Technical Rationale:[/cyan]\n" +
            "\n".join(f"  • {r}" for r in top["rationale"]),
            border_style="yellow",
            title="🏆 Top Event-Driven Pick",
        ))


# ── HTML Report Section ──────────────────────────────────────────────────────

def generate_event_html_section(results: list[dict], suggestions: list[dict] | None = None) -> str:
    """Generate HTML section for event analysis, to embed in main report."""
    if not results:
        return ""

    rows = ""
    for res in results:
        event_label = "PM Speech" if res["event"] == "pm_speech" else "Strait of Hormuz"
        for sector, data in res.get("sector_impacts", {}).items():
            direction = data.get("direction", "NEUTRAL")
            color = "#56d364" if direction == "POSITIVE" else "#ff7b72" if direction == "NEGATIVE" else "#f0c040"
            stocks = ", ".join(s.replace(".NS", "") for s in data["stocks"][:5])
            reasons = "; ".join(list(data["reasons"])[:2])[:60]
            rows += f"""
            <tr>
              <td style="color:#58a6ff;font-weight:bold">{event_label}</td>
              <td>{sector.replace('_',' ')}</td>
              <td style="color:{color};font-weight:bold">{direction}</td>
              <td style="color:{color}">{data['score']:+d}</td>
              <td style="color:#8b949e;font-size:0.85em">{stocks}</td>
              <td style="color:#8b949e;font-size:0.8em">{reasons}</td>
            </tr>"""

    movers_rows = ""
    for res in results:
        for m in res.get("unusual_movers", [])[:6]:
            pct_color = "#56d364" if m["pct_change"] > 0 else "#ff7b72"
            movers_rows += f"""
            <tr>
              <td style="color:#58a6ff;font-weight:bold">{m['symbol'].replace('.NS','')}</td>
              <td>Rs {m['price']:,.2f}</td>
              <td style="color:{pct_color}">{m['pct_change']:+.2f}%</td>
              <td style="color:#f0c040">{m['vol_ratio']:.2f}x avg</td>
              <td>{m['range_5d_pct']:.2f}%</td>
            </tr>"""

    picks_rows = ""
    for i, p in enumerate((suggestions or [])[:10], 1):
        boost = p.get("event_boost", 0)
        boost_color = "#56d364" if boost > 0 else "#ff7b72" if boost < 0 else "#8b949e"
        score_color = "#56d364" if p["total_score"] >= 75 else "#f0c040" if p["total_score"] >= 55 else "#ff7b72"
        ctx = p.get("event_context", "")[:70]
        picks_rows += f"""
            <tr>
              <td style="color:#8b949e">#{i}</td>
              <td style="color:#58a6ff;font-weight:bold">{p['symbol'].replace('.NS','')}</td>
              <td>Rs {p['price']:,.2f}</td>
              <td style="color:#56d364">Rs {p['target']:,.2f} (+{p['target_pct']}%)</td>
              <td style="color:#ff7b72">Rs {p['stop_loss']:,.2f}</td>
              <td style="color:{score_color};font-weight:bold">{p['total_score']}</td>
              <td style="color:{boost_color};font-weight:bold">{boost:+d}</td>
              <td style="color:#8b949e;font-size:0.8em">{ctx}</td>
            </tr>"""

    picks_table = ""
    if picks_rows:
        picks_table = f"""
      <h3 style="color:#56d364;margin:24px 0 8px">Event-Boosted Stock Picks</h3>
      <table style="width:100%;border-collapse:collapse;background:#161b22;border-radius:8px;overflow:hidden;margin-bottom:20px">
        <thead>
          <tr style="background:#21262d">
            <th style="padding:8px;text-align:left;color:#8b949e">#</th>
            <th style="padding:8px;text-align:left;color:#8b949e">Symbol</th>
            <th style="padding:8px;text-align:left;color:#8b949e">Price</th>
            <th style="padding:8px;text-align:left;color:#8b949e">Target</th>
            <th style="padding:8px;text-align:left;color:#8b949e">Stop Loss</th>
            <th style="padding:8px;text-align:left;color:#8b949e">Score/125</th>
            <th style="padding:8px;text-align:left;color:#8b949e">Event Boost</th>
            <th style="padding:8px;text-align:left;color:#8b949e">Why</th>
          </tr>
        </thead>
        <tbody style="color:#e6edf3">{picks_rows}</tbody>
      </table>"""

    return f"""
    <div style="margin-top:30px">
      <h2 style="color:#58a6ff;margin-bottom:12px">Event-Driven Sector Analysis</h2>

      <table style="width:100%;border-collapse:collapse;background:#161b22;border-radius:8px;overflow:hidden;margin-bottom:20px">
        <thead>
          <tr style="background:#21262d">
            <th style="padding:10px;text-align:left;color:#8b949e">Event</th>
            <th style="padding:10px;text-align:left;color:#8b949e">Sector</th>
            <th style="padding:10px;text-align:left;color:#8b949e">Impact</th>
            <th style="padding:10px;text-align:left;color:#8b949e">Score</th>
            <th style="padding:10px;text-align:left;color:#8b949e">Key Stocks</th>
            <th style="padding:10px;text-align:left;color:#8b949e">Reason</th>
          </tr>
        </thead>
        <tbody style="color:#e6edf3">{rows}</tbody>
      </table>

      {"<h3 style='color:#f0c040;margin-bottom:8px'>Unusual Movers</h3><table style='width:100%;border-collapse:collapse;background:#161b22;border-radius:8px;overflow:hidden;margin-bottom:20px'><thead><tr style='background:#21262d'><th style='padding:8px;text-align:left;color:#8b949e'>Symbol</th><th style='padding:8px;text-align:left;color:#8b949e'>Price</th><th style='padding:8px;text-align:left;color:#8b949e'>1D %</th><th style='padding:8px;text-align:left;color:#8b949e'>Volume</th><th style='padding:8px;text-align:left;color:#8b949e'>5D Range</th></tr></thead><tbody style='color:#e6edf3'>" + movers_rows + "</tbody></table>" if movers_rows else ""}
      {picks_table}
    </div>"""


# ── Main ─────────────────────────────────────────────────────────────────────

def run_event_analysis(run_pm: bool = True, run_strait: bool = True, days: int = 3) -> list[dict]:
    console.print(Panel.fit(
        "[bold cyan]Event-Driven Market Impact Analyzer[/bold cyan]\n"
        f"[yellow]Events: {'PM Speech  ' if run_pm else ''}{'Strait of Hormuz' if run_strait else ''}[/yellow]\n"
        f"[dim]News lookback: {days} days | {datetime.now().strftime('%d %b %Y %H:%M')}[/dim]",
        border_style="cyan"
    ))

    results = []
    if run_strait:
        results.append(strait_analysis(days=days))
    if run_pm:
        results.append(pm_speech_analysis(days=days))

    # ── Combined event-boosted stock suggestions ───────────────────────────
    combined_impacts: dict[str, dict] = {}
    for res in results:
        for sector, data in res.get("sector_impacts", {}).items():
            if sector not in combined_impacts:
                combined_impacts[sector] = dict(data)
            else:
                combined_impacts[sector]["score"] += data["score"]

    if combined_impacts:
        console.rule("[bold green]Event-Boosted Stock Suggestions")
        suggestions = generate_event_suggestions(combined_impacts)
        if suggestions:
            _render_suggestions_table(suggestions, "Top Picks — Adjusted for Current Events")
        else:
            console.print("[yellow]No cached stock data found. Run main.py first to populate cache.[/yellow]")

    # Save event HTML report
    html_section = generate_event_html_section(results, suggestions if combined_impacts else [])
    event_html_path = os.path.join(RESULTS_DIR, "event_analysis.html")
    _save_event_html(html_section, results, event_html_path)
    console.print(f"\n[bold green]Event analysis saved:[/bold green] {event_html_path}")

    try:
        os.startfile(event_html_path)
    except Exception:
        pass

    return results


def _save_event_html(section: str, results: list[dict], path: str) -> None:
    summary_items = ""
    for r in results:
        label = "PM Speech" if r["event"] == "pm_speech" else "Strait of Hormuz"
        summary_items += f"<li><strong>{label}</strong>: {r['articles']} articles, {len(r['sector_impacts'])} sectors affected, {len(r['unusual_movers'])} unusual movers</li>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Event Analysis — Indian Markets</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', sans-serif; background: #0d1117; color: #e6edf3; padding: 24px; max-width: 1400px; margin: 0 auto; }}
  h1 {{ color: #58a6ff; font-size: 1.8em; margin-bottom: 4px; }}
  .subtitle {{ color: #8b949e; font-size: 0.9em; margin-bottom: 24px; }}
  .summary {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 24px; }}
  .summary ul {{ padding-left: 20px; line-height: 1.8; color: #8b949e; }}
  table td, table th {{ padding: 10px 14px; border-bottom: 1px solid #21262d; }}
  .disclaimer {{ margin-top: 30px; padding: 12px; background: #161b22; border: 1px solid #f0c04044; border-radius: 8px; color: #8b949e; font-size: 0.8em; }}
</style>
</head>
<body>
<h1>Event-Driven Market Impact — Indian Stocks</h1>
<p class="subtitle">Generated: {datetime.now().strftime('%d %b %Y %H:%M')} | PM Speech + Strait of Hormuz Analysis</p>
<div class="summary">
  <strong style="color:#e6edf3">Analysis Summary</strong>
  <ul>{summary_items}</ul>
</div>
{section}
<div class="disclaimer">
  ⚠️ <strong>Risk Notice:</strong> Market reactions depend on many factors beyond event content.
  Verify news from official sources and respect your position sizing before acting on sector signals.
</div>
</body>
</html>"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    run_pm = "--pm" in sys.argv or "--all" in sys.argv or (
        "--pm" not in sys.argv and "--strait" not in sys.argv
    )
    run_strait = "--strait" in sys.argv or "--all" in sys.argv or (
        "--pm" not in sys.argv and "--strait" not in sys.argv
    )
    days = 3
    if "--days" in sys.argv:
        idx = sys.argv.index("--days")
        if idx + 1 < len(sys.argv):
            try:
                days = int(sys.argv[idx + 1])
            except ValueError:
                pass

    run_event_analysis(run_pm=run_pm, run_strait=run_strait, days=days)
