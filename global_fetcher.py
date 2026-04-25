"""
Fetches global market data: crude, DXY, gold, US/Asian indices, US yields.
Translates global moves into Indian sector impact scores automatically.
"""

import yfinance as yf
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

GLOBAL_SYMBOLS = {
    "Brent Crude":   "BZ=F",
    "WTI Crude":     "CL=F",
    "Gold":          "GC=F",
    "DXY (Dollar)":  "DX-Y.NYB",
    "S&P 500":       "^GSPC",
    "Nasdaq":        "^IXIC",
    "Nikkei 225":    "^N225",
    "Hang Seng":     "^HSI",
    "US 10Y Yield":  "^TNX",
    "US VIX":        "^VIX",
}

# Thresholds for triggering sector impact (% moves)
_CRUDE_STRONG  = 2.0
_CRUDE_MILD    = 1.0
_DXY_STRONG    = 0.5
_DXY_MILD      = 0.2
_EQ_STRONG     = 1.0
_EQ_MILD       = 0.5
_YIELD_STRONG  = 3.0   # % change in yield level
_YIELD_MILD    = 1.5
_HSI_STRONG    = 2.0


def fetch_global_context() -> dict:
    """
    Fetch 1-day % change for each global symbol.
    Returns name -> {symbol, price, pct_change, trend}.
    Falls back gracefully — missing data simply excluded.
    """
    ctx = {}
    for name, symbol in GLOBAL_SYMBOLS.items():
        try:
            hist = yf.Ticker(symbol).history(period="5d", auto_adjust=True)
            if hist is None or len(hist) < 2:
                continue
            cur  = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            pct  = (cur - prev) / prev * 100
            ctx[name] = {
                "symbol":     symbol,
                "price":      round(cur, 2),
                "pct_change": round(pct, 2),
                "trend":      "up" if pct > 0 else "down",
            }
        except Exception:
            pass
    return ctx


def render_global_table(ctx: dict) -> None:
    table = Table(title="Global Market Snapshot", box=box.SIMPLE_HEAD, border_style="blue")
    table.add_column("Market", width=18)
    table.add_column("Price", justify="right", width=14)
    table.add_column("1D Change", justify="right", width=12)
    table.add_column("Signal", width=30)

    signals = _derive_signals(ctx)
    signal_map = {s["name"]: s["signal"] for s in signals}

    for name, data in ctx.items():
        pct   = data["pct_change"]
        color = "green" if pct > 0 else "red"
        sig   = signal_map.get(name, "")
        table.add_row(
            name,
            f"{data['price']:,.2f}",
            f"[{color}]{pct:+.2f}%[/{color}]",
            f"[dim]{sig}[/dim]",
        )
    console.print(table)


def _derive_signals(ctx: dict) -> list[dict]:
    """Return human-readable signals from global data (for display)."""
    sigs = []

    crude = ctx.get("Brent Crude") or ctx.get("WTI Crude") or {}
    cp = crude.get("pct_change", 0)
    if abs(cp) >= _CRUDE_MILD:
        sigs.append({"name": "Brent Crude",
                     "signal": f"Crude {'up' if cp > 0 else 'DOWN'} {cp:+.1f}% → OMCs/Paints {'hurt' if cp > 0 else 'benefit'}"})

    dxy = ctx.get("DXY (Dollar)") or {}
    dp = dxy.get("pct_change", 0)
    if abs(dp) >= _DXY_MILD:
        sigs.append({"name": "DXY (Dollar)",
                     "signal": f"Dollar {'strong' if dp > 0 else 'weak'} → INR {'weak' if dp > 0 else 'strong'} → IT exports {'↑' if dp > 0 else '↓'}"})

    sp = (ctx.get("S&P 500") or {}).get("pct_change", 0)
    if abs(sp) >= _EQ_MILD:
        sigs.append({"name": "S&P 500",
                     "signal": f"US markets {'up' if sp > 0 else 'DOWN'} → FII {'inflow' if sp > 0 else 'outflow'} risk"})

    vix = (ctx.get("US VIX") or {}).get("price", 20)
    if vix > 28:
        sigs.append({"name": "US VIX", "signal": f"VIX {vix:.0f} — HIGH FEAR → risk-off, avoid leveraged plays"})
    elif vix < 15:
        sigs.append({"name": "US VIX", "signal": f"VIX {vix:.0f} — low fear → risk-on environment"})

    hsi = (ctx.get("Hang Seng") or {}).get("pct_change", 0)
    if abs(hsi) >= _HSI_STRONG:
        sigs.append({"name": "Hang Seng",
                     "signal": f"China markets {'up' if hsi > 0 else 'down'} → metals demand {'optimism' if hsi > 0 else 'concern'}"})

    return sigs


def global_to_sector_impact(ctx: dict) -> dict[str, int]:
    """
    Translate global market moves to Indian sector impact integers.
    Returns {sector_name: score} where positive = bullish, negative = bearish.
    """
    impacts: dict[str, int] = {}

    def add(sector: str, pts: int) -> None:
        impacts[sector] = impacts.get(sector, 0) + pts

    # ── Crude Oil ──────────────────────────────────────────────────────────
    crude = ctx.get("Brent Crude") or ctx.get("WTI Crude") or {}
    cp = crude.get("pct_change", 0)
    if cp < -_CRUDE_STRONG:
        add("Energy_Upstream",   -3); add("Energy_Downstream", +3)
        add("Paints",            +2); add("Chemicals",         +2)
        add("Auto",              +1); add("FMCG",              +1)
    elif cp < -_CRUDE_MILD:
        add("Energy_Upstream",   -1); add("Energy_Downstream", +1)
        add("Paints",            +1); add("Auto",              +1)
    elif cp > _CRUDE_STRONG:
        add("Energy_Upstream",   +3); add("Energy_Downstream", -3)
        add("Paints",            -2); add("Chemicals",         -2)
        add("Auto",              -1); add("FMCG",              -1)
    elif cp > _CRUDE_MILD:
        add("Energy_Upstream",   +1); add("Energy_Downstream", -1)
        add("Paints",            -1)

    # ── US Dollar Index (DXY) → INR impact ────────────────────────────────
    dxy = ctx.get("DXY (Dollar)") or {}
    dp = dxy.get("pct_change", 0)
    if dp > _DXY_STRONG:     # Strong dollar → weak rupee → IT/Pharma exports benefit
        add("IT",     +2); add("Pharma",  +1)
        add("Metals", -1); add("Energy_Downstream", -1)
    elif dp > _DXY_MILD:
        add("IT",     +1); add("Pharma",  +1)
    elif dp < -_DXY_STRONG:  # Weak dollar → strong rupee → IT/Pharma margins hurt
        add("IT",    -2); add("Pharma",  -1)
        add("Metals", +1)
    elif dp < -_DXY_MILD:
        add("IT",    -1); add("Pharma",  -1)

    # ── S&P 500 → FII sentiment proxy ────────────────────────────────────
    sp = (ctx.get("S&P 500") or {}).get("pct_change", 0)
    if sp > _EQ_STRONG:
        add("Banks", +2); add("IT", +1); add("NBFC", +1)
    elif sp > _EQ_MILD:
        add("Banks", +1)
    elif sp < -_EQ_STRONG:
        add("Banks", -2); add("IT", -1); add("NBFC", -1)
    elif sp < -_EQ_MILD:
        add("Banks", -1)

    # ── US VIX → risk appetite ────────────────────────────────────────────
    vix_price = (ctx.get("US VIX") or {}).get("price", 20)
    if vix_price > 30:
        add("Banks", -2); add("NBFC", -1); add("Realty", -1)
    elif vix_price > 25:
        add("Banks", -1)
    elif vix_price < 15:
        add("Banks", +1); add("NBFC", +1)

    # ── US 10Y Yield → EM capital flows ──────────────────────────────────
    y10p = (ctx.get("US 10Y Yield") or {}).get("pct_change", 0)
    if y10p > _YIELD_STRONG:
        add("Banks", -3); add("NBFC", -2); add("Realty", -2)
    elif y10p > _YIELD_MILD:
        add("Banks", -1); add("NBFC", -1); add("Realty", -1)
    elif y10p < -_YIELD_STRONG:
        add("Banks", +3); add("NBFC", +2); add("Realty", +2)
    elif y10p < -_YIELD_MILD:
        add("Banks", +1); add("NBFC", +1); add("Realty", +1)

    # ── Hang Seng → China demand → metals ────────────────────────────────
    hsi = (ctx.get("Hang Seng") or {}).get("pct_change", 0)
    if hsi > _HSI_STRONG:
        add("Metals", +2)
    elif hsi > 1:
        add("Metals", +1)
    elif hsi < -_HSI_STRONG:
        add("Metals", -2)
    elif hsi < -1:
        add("Metals", -1)

    # ── Gold → gold-loan NBFCs ────────────────────────────────────────────
    gp = (ctx.get("Gold") or {}).get("pct_change", 0)
    if gp > 1.0:
        add("NBFC", +2)
    elif gp > 0.5:
        add("NBFC", +1)
    elif gp < -1.0:
        add("NBFC", -1)

    # ── Nikkei → Japan/Asia risk sentiment ───────────────────────────────
    nk = (ctx.get("Nikkei 225") or {}).get("pct_change", 0)
    if nk > 1.5:
        add("IT", +1); add("Auto", +1)
    elif nk < -1.5:
        add("IT", -1); add("Auto", -1)

    return impacts


def summarize_global_impact(ctx: dict) -> str:
    """One-line plain-english summary of global factors for the report."""
    parts = []
    crude = (ctx.get("Brent Crude") or {}).get("pct_change", 0)
    if abs(crude) > 0.5:
        parts.append(f"Brent {crude:+.1f}%")
    dxy = (ctx.get("DXY (Dollar)") or {}).get("pct_change", 0)
    if abs(dxy) > 0.2:
        parts.append(f"DXY {dxy:+.2f}% ({'weak INR' if dxy > 0 else 'strong INR'})")
    sp = (ctx.get("S&P 500") or {}).get("pct_change", 0)
    if abs(sp) > 0.3:
        parts.append(f"S&P500 {sp:+.1f}%")
    vix = (ctx.get("US VIX") or {}).get("price", 20)
    parts.append(f"VIX {vix:.0f}")
    return " | ".join(parts) if parts else "Global data unavailable"
