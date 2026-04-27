"""
Tracks prediction accuracy. Saves to results/prediction_log.json.
Called each analysis run to: (a) check pending predictions against current prices,
(b) log new top-pick predictions. After enough data, shows win rates per pattern.
"""
import json
import os
from datetime import date
from config import RESULTS_DIR

PREDICTION_LOG   = os.path.join(RESULTS_DIR, "prediction_log.json")
MAX_HOLDING_DAYS = 90   # mark as expired after this many calendar days


def _load() -> dict:
    if os.path.exists(PREDICTION_LOG):
        try:
            with open(PREDICTION_LOG) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "predictions":    [],
        "daily_accuracy": {},
        "pattern_accuracy": {},
        "overall": {"total": 0, "target_hit": 0, "stop_hit": 0, "expired": 0},
    }


def _save(log: dict) -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(PREDICTION_LOG, "w") as f:
        json.dump(log, f, indent=2, default=str)


def save_predictions(top_picks: list) -> int:
    """
    Log today's top picks as new predictions.
    Skips symbols already logged today. Returns count added.
    """
    log   = _load()
    today = date.today().isoformat()
    existing_today = {p["symbol"] for p in log["predictions"] if p["date"] == today}
    added = 0

    for p in top_picks:
        sym = p["symbol"]
        if sym in existing_today:
            continue

        sigs     = p.get("signals", {})
        pat_info = sigs.get("patterns", {})

        names: list = (
            list(pat_info.get("bullish_patterns", [])) +
            list(pat_info.get("bearish_patterns",  [])) +
            list(pat_info.get("neutral_patterns",  []))
        )
        ts = pat_info.get("trend_structure", {}).get("structure", "")
        if ts and ts not in ("undefined", "mixed", "expanding", "contracting"):
            names.append(f"Trend:{ts}")

        # Legacy signal-level patterns
        if sigs.get("rsi_bull_div"):               names.append("RSI Divergence")
        if sigs.get("macd_bull_div"):              names.append("MACD Divergence")
        if sigs.get("squeeze_fired"):              names.append("TTM Squeeze")
        if sigs.get("breakout"):                   names.append("Breakout")
        candle = sigs.get("candle_pattern")
        if candle and sigs.get("candle_bullish"):  names.append(candle)

        # Save ML feature vector so future retraining doesn't need re-extraction
        ml_features: list = []
        try:
            from ml_predictor import get_feature_vector
            df_ind = p.get("_df_ind")
            if df_ind is not None:
                ml_features = get_feature_vector(
                    df_ind,
                    signals=p.get("signals"),
                    stats52=p.get("stats_52w"),
                    regime_str=p.get("market_context", "SIDEWAYS"),
                    vix=15.0,
                    rule_score=p.get("rule_score") or p.get("total_score"),
                )
        except Exception:
            pass

        log["predictions"].append({
            "date":           today,
            "symbol":         sym,
            "entry_price":    p["price"],
            "target":         p["target"],
            "stop_loss":      p["stop_loss"],
            "total_score":    p.get("total_score", 0),
            "rule_score":     p.get("rule_score", p.get("total_score", 0)),
            "ml_prob":        p.get("ml_prob", 0.5),
            "ml_features":    ml_features,
            "patterns":       list(set(names)),
            "status":         "pending",
            "resolved_date":  None,
            "resolved_price": None,
            "return_pct":     None,
        })
        added += 1

    _save(log)
    return added


def check_accuracy(stock_data: dict) -> dict:
    """
    Compare all pending predictions against current prices.
    Marks resolved: target_hit / stop_hit / expired.
    Returns summary dict for display.
    """
    log            = _load()
    today          = date.today().isoformat()
    resolved_today = []

    for pred in log["predictions"]:
        if pred["status"] != "pending":
            continue

        df = stock_data.get(pred["symbol"])
        if df is None or len(df) == 0:
            continue

        current      = float(df["close"].iloc[-1])
        days_held    = (date.today() - date.fromisoformat(pred["date"])).days

        if current >= pred["target"]:
            status = "target_hit"
        elif current <= pred["stop_loss"]:
            status = "stop_hit"
        elif days_held > MAX_HOLDING_DAYS:
            status = "expired"
        else:
            continue

        pred["status"]         = status
        pred["resolved_date"]  = today
        pred["resolved_price"] = round(current, 2)
        pred["return_pct"]     = round((current - pred["entry_price"]) / pred["entry_price"] * 100, 2)
        resolved_today.append(pred)

        log["overall"]["total"] += 1
        if status in log["overall"]:
            log["overall"][status] += 1

        for pat in pred.get("patterns", []):
            if pat not in log["pattern_accuracy"]:
                log["pattern_accuracy"][pat] = {
                    "total": 0, "target_hit": 0, "stop_hit": 0, "expired": 0
                }
            log["pattern_accuracy"][pat]["total"] += 1
            if status in log["pattern_accuracy"][pat]:
                log["pattern_accuracy"][pat][status] += 1

    if resolved_today:
        log["daily_accuracy"][today] = {
            "resolved":   len(resolved_today),
            "target_hit": sum(1 for r in resolved_today if r["status"] == "target_hit"),
            "stop_hit":   sum(1 for r in resolved_today if r["status"] == "stop_hit"),
            "expired":    sum(1 for r in resolved_today if r["status"] == "expired"),
        }

    _save(log)

    overall = log["overall"]
    total   = overall["total"]

    pattern_stats = {}
    for pat, s in log["pattern_accuracy"].items():
        t = s["total"]
        pattern_stats[pat] = {
            **s,
            "win_rate": round(s["target_hit"] / t * 100, 1) if t > 0 else 0.0,
        }

    return {
        "resolved_today":   resolved_today,
        "overall_win_rate": round(overall["target_hit"] / total * 100, 1) if total > 0 else None,
        "total_predictions": total,
        "target_hit":       overall["target_hit"],
        "stop_hit":         overall.get("stop_hit", 0),
        "expired":          overall.get("expired", 0),
        "pattern_stats":    pattern_stats,
        "pending":          sum(1 for p in log["predictions"] if p["status"] == "pending"),
    }


def print_accuracy_report(stats: dict, console) -> None:
    """Print accuracy summary to a rich Console."""
    from rich.table import Table
    from rich import box as rbox

    pending = stats["pending"]
    total   = stats["total_predictions"]

    if total == 0 and pending == 0:
        console.print("[dim]Accuracy tracker: no predictions logged yet. Will start tracking after first run.[/dim]")
        return

    if total > 0:
        wr    = stats["overall_win_rate"] or 0
        color = "green" if wr >= 60 else ("yellow" if wr >= 45 else "red")
        console.print(
            f"\n[bold cyan]Self-Accuracy:[/bold cyan] [{color}]{wr:.1f}% win rate[/{color}]  "
            f"({stats['target_hit']} targets / {stats['stop_hit']} stops / "
            f"{stats['expired']} expired — {total} resolved, {pending} pending)"
        )
    else:
        console.print(
            f"[dim]Accuracy tracker: {pending} prediction(s) pending, none resolved yet.[/dim]"
        )

    if stats["resolved_today"]:
        console.print(f"[cyan]  Resolved today ({len(stats['resolved_today'])}):[/cyan]")
        for r in stats["resolved_today"]:
            sym = r["symbol"].replace(".NS", "")
            pct = r["return_pct"]
            if r["status"] == "target_hit":
                console.print(f"    [green]TARGET HIT  {sym}  {r['resolved_price']}  ({pct:+.1f}%)[/green]")
            elif r["status"] == "stop_hit":
                console.print(f"    [red]STOP HIT    {sym}  {r['resolved_price']}  ({pct:+.1f}%)[/red]")
            else:
                console.print(f"    [dim]EXPIRED     {sym}  {r['resolved_price']}  ({pct:+.1f}%)[/dim]")

    if stats["pattern_stats"]:
        table = Table(title="Pattern Win Rates (self-audit)",
                      box=rbox.SIMPLE, header_style="bold cyan")
        table.add_column("Pattern",   style="cyan",        width=26)
        table.add_column("Calls",     justify="right",     width=6)
        table.add_column("Wins",      justify="right",     style="green", width=6)
        table.add_column("Losses",    justify="right",     style="red",   width=7)
        table.add_column("Win Rate",  justify="right",     style="bold yellow", width=9)

        sorted_pats = sorted(stats["pattern_stats"].items(), key=lambda x: -x[1]["total"])
        for pat, s in sorted_pats[:14]:
            table.add_row(pat, str(s["total"]), str(s["target_hit"]),
                          str(s["stop_hit"]), f"{s['win_rate']:.1f}%")
        console.print(table)
