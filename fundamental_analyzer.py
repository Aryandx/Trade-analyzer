import yfinance as yf
from data_fetcher import get_stock_info

_cache: dict = {}


def get_fundamentals(symbol: str) -> dict:
    if symbol in _cache:
        return _cache[symbol]
    try:
        info = get_stock_info(symbol)

        roe             = info.get("returnOnEquity")       # decimal
        de_ratio        = info.get("debtToEquity")
        profit_margins  = info.get("profitMargins")
        revenue_growth  = info.get("revenueGrowth")
        earnings_growth = info.get("earningsGrowth")
        pe_ratio        = info.get("trailingPE")
        promoter_pct    = info.get("heldPercentInsiders")
        free_cashflow   = info.get("freeCashflow")         # absolute INR
        total_revenue   = info.get("totalRevenue")
        op_cashflow     = info.get("operatingCashflow")
        total_debt      = info.get("totalDebt")
        ebitda          = info.get("ebitda")
        current_ratio   = info.get("currentRatio")

        # Normalise D/E (yfinance sometimes returns % form)
        if de_ratio is not None and de_ratio > 10:
            de_ratio = de_ratio / 100

        # FCF margin
        fcf_margin = None
        if free_cashflow is not None and total_revenue and total_revenue > 0:
            fcf_margin = free_cashflow / total_revenue * 100

        # Cash conversion (operating CF / revenue) — how efficiently earnings become cash
        cash_conversion = None
        if op_cashflow is not None and total_revenue and total_revenue > 0:
            cash_conversion = op_cashflow / total_revenue * 100

        # Interest coverage = EBITDA / estimated interest expense
        # Approximate interest expense as totalDebt × 8% (typical Indian corporate rate)
        interest_coverage = None
        if ebitda is not None and total_debt and total_debt > 0 and ebitda > 0:
            est_interest = total_debt * 0.08
            interest_coverage = ebitda / est_interest

        result = {
            "roe_pct":            round(roe * 100, 2)            if roe             is not None else None,
            "debt_to_equity":     round(de_ratio, 2)             if de_ratio        is not None else None,
            "profit_margin_pct":  round(profit_margins * 100, 2) if profit_margins  is not None else None,
            "revenue_growth_pct": round(revenue_growth * 100, 2) if revenue_growth  is not None else None,
            "earnings_growth_pct":round(earnings_growth * 100, 2)if earnings_growth is not None else None,
            "pe_ratio":           round(pe_ratio, 2)             if pe_ratio        is not None else None,
            "promoter_pct":       round(promoter_pct * 100, 2)   if promoter_pct    is not None else None,
            "fcf_margin_pct":     round(fcf_margin, 2)           if fcf_margin      is not None else None,
            "cash_conversion_pct":round(cash_conversion, 2)      if cash_conversion is not None else None,
            "interest_coverage":  round(interest_coverage, 2)    if interest_coverage is not None else None,
            "current_ratio":      round(current_ratio, 2)        if current_ratio   is not None else None,
        }
        _cache[symbol] = result
        return result
    except Exception:
        result = {}
        _cache[symbol] = result
        return result


def score_fundamentals(f: dict) -> tuple[int, list[str]]:
    """Returns (score –12 to +35, rationale lines)."""
    score = 0
    reasons: list[str] = []

    roe          = f.get("roe_pct")
    de           = f.get("debt_to_equity")
    margin       = f.get("profit_margin_pct")
    rev_growth   = f.get("revenue_growth_pct")
    earn_growth  = f.get("earnings_growth_pct")
    fcf          = f.get("fcf_margin_pct")
    icr          = f.get("interest_coverage")
    promoter     = f.get("promoter_pct")
    curr_ratio   = f.get("current_ratio")

    # ── Return on Equity (0–8) ──────────────────────────────────────────────
    if roe is not None:
        if roe >= 20:
            score += 8
            reasons.append(f"ROE {roe:.1f}% — strong capital returns")
        elif roe >= 15:
            score += 5
            reasons.append(f"ROE {roe:.1f}% — good capital efficiency")
        elif roe >= 10:
            score += 3
        elif roe < 0:
            score -= 4
            reasons.append(f"ROE {roe:.1f}% — negative equity returns")

    # ── Debt / Equity (0–6) ─────────────────────────────────────────────────
    if de is not None:
        if de < 0.3:
            score += 6
            reasons.append(f"D/E {de:.2f} — near debt-free")
        elif de < 0.7:
            score += 4
            reasons.append(f"D/E {de:.2f} — manageable leverage")
        elif de < 1.2:
            score += 2
        elif de > 2.0:
            score -= 3
            reasons.append(f"D/E {de:.2f} — elevated leverage")

    # ── Revenue growth YoY (0–5) ────────────────────────────────────────────
    if rev_growth is not None:
        if rev_growth >= 15:
            score += 5
            reasons.append(f"Revenue +{rev_growth:.1f}% YoY")
        elif rev_growth >= 8:
            score += 3
            reasons.append(f"Revenue +{rev_growth:.1f}% YoY")
        elif rev_growth >= 0:
            score += 1
        else:
            score -= 2
            reasons.append(f"Revenue declining {rev_growth:.1f}% YoY")

    # ── Earnings growth YoY (0–5) ───────────────────────────────────────────
    if earn_growth is not None:
        if earn_growth >= 20:
            score += 5
            reasons.append(f"Earnings +{earn_growth:.1f}% YoY")
        elif earn_growth >= 10:
            score += 3
            reasons.append(f"Earnings +{earn_growth:.1f}% YoY")
        elif earn_growth >= 0:
            score += 1
        else:
            score -= 2
            reasons.append(f"Earnings declining {earn_growth:.1f}% YoY")

    # ── Net profit margin (0–5) ─────────────────────────────────────────────
    if margin is not None:
        if margin >= 20:
            score += 5
            reasons.append(f"Net margin {margin:.1f}% — high-quality business")
        elif margin >= 12:
            score += 3
            reasons.append(f"Net margin {margin:.1f}%")
        elif margin >= 5:
            score += 1
        elif margin < 0:
            score -= 3
            reasons.append(f"Negative net margin {margin:.1f}%")

    # ── Free Cash Flow margin (0–4) ─────────────────────────────────────────
    if fcf is not None:
        if fcf >= 15:
            score += 4
            reasons.append(f"FCF margin {fcf:.1f}% — strong cash generation")
        elif fcf >= 8:
            score += 3
            reasons.append(f"FCF margin {fcf:.1f}%")
        elif fcf >= 0:
            score += 1
        else:
            score -= 2
            reasons.append(f"Negative FCF margin {fcf:.1f}%")

    # ── Interest Coverage (0–3) ─────────────────────────────────────────────
    if icr is not None:
        if icr >= 8:
            score += 3
            reasons.append(f"Interest coverage {icr:.1f}x — very safe debt service")
        elif icr >= 4:
            score += 2
            reasons.append(f"Interest coverage {icr:.1f}x")
        elif icr >= 1.5:
            score += 1
        else:
            score -= 2
            reasons.append(f"Interest coverage {icr:.1f}x — debt service risk")

    # ── Liquidity: Current Ratio (0–1) ─────────────────────────────────────
    if curr_ratio is not None and curr_ratio >= 1.5:
        score += 1

    # ── Promoter bonus (0–2) ────────────────────────────────────────────────
    if promoter is not None and promoter >= 50:
        score += 2
        reasons.append(f"Promoter {promoter:.1f}% — aligned incentives")

    return max(-12, min(35, score)), reasons
