import json
import os
import numpy as np
from datetime import datetime
from config import REPORT_JSON, REPORT_HTML, INVESTMENT_AMOUNT


def save_json(data: dict) -> None:
    os.makedirs(os.path.dirname(REPORT_JSON), exist_ok=True)
    with open(REPORT_JSON, "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_json() -> dict | None:
    if not os.path.exists(REPORT_JSON):
        return None
    with open(REPORT_JSON) as f:
        return json.load(f)


def _regime_color(regime: str) -> str:
    return {
        "STRONG_BULL": "#00c853", "BULL": "#64dd17", "SIDEWAYS": "#ff9800",
        "BEAR": "#ff5252", "STRONG_BEAR": "#d50000", "VOLATILE": "#aa00ff",
    }.get(regime, "#90a4ae")


def _sparkline(prices: list, w: int = 120, h: int = 38) -> str:
    if len(prices) < 5:
        return ""
    mn, mx = min(prices), max(prices)
    if mx == mn:
        return ""
    def px(i): return round(i / (len(prices) - 1) * w, 1)
    def py(p): return round(h - (p - mn) / (mx - mn) * (h - 4) - 2, 1)
    pts = " ".join(f"{px(i)},{py(p)}" for i, p in enumerate(prices))
    color = "#56d364" if prices[-1] >= prices[0] else "#ff7b72"
    # Area fill
    area_pts = f"0,{h} {pts} {w},{h}"
    return (
        f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" style="display:block">'
        f'<defs><linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.25"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0.02"/>'
        f'</linearGradient></defs>'
        f'<polygon points="{area_pts}" fill="url(#sg)"/>'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.8"/>'
        f'</svg>'
    )


def _val(v, suffix="", positive_green=True, fmt=".1f"):
    if v is None:
        return '<span style="color:#444">—</span>'
    color = ("#56d364" if v > 0 else "#ff7b72") if positive_green else ("#ff7b72" if v > 1.5 else "#56d364")
    return f'<span style="color:{color};font-weight:bold">{v:{fmt}}{suffix}</span>'


def _signal_badge(label: str, color: str, tip: str = "") -> str:
    return (f'<span style="background:{color}22;border:1px solid {color}66;color:{color};'
            f'padding:2px 8px;border-radius:10px;font-size:0.72em;font-weight:bold" title="{tip}">{label}</span>')


def _score_bar(label: str, score: int, max_score: int, color: str) -> str:
    pct = max(0, min(100, int(score / max_score * 100))) if max_score > 0 else 0
    sign = "+" if score > 0 else ""
    return (f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:3px">'
            f'<span style="font-size:0.7em;color:#8b949e;width:76px;flex-shrink:0">{label} {sign}{score}/{max_score}</span>'
            f'<div style="flex:1;background:#21262d;border-radius:3px;height:7px;overflow:hidden">'
            f'<div style="width:{pct}%;background:{color};height:100%;border-radius:3px"></div></div></div>')


def _build_card(i: int, p: dict, df_prices: list | None) -> str:
    score   = p.get("total_score", 0)
    sb      = p.get("score_breakdown", {})
    fund    = p.get("fundamentals", {})
    sigs    = p.get("signals", {})
    rs_info = p.get("sector_rs", {})
    manip   = p.get("manip_resistance", {})

    score_color = "#00c853" if score >= 100 else "#64dd17" if score >= 80 else "#ff9800" if score >= 65 else "#ff5252"
    ema_ok  = p.get("ema_aligned", False)
    macd_ok = p.get("macd_bullish", False)
    spark   = _sparkline(df_prices) if df_prices else ""

    # ── Signal badges ──────────────────────────────────────────────────────
    badge_html = ""
    if sigs.get("rsi_bull_div"):
        badge_html += _signal_badge("RSI Divergence", "#00b0ff", "Bullish RSI divergence")
    if sigs.get("macd_bull_div"):
        badge_html += _signal_badge("MACD Divergence", "#00b0ff", "MACD histogram divergence")
    if sigs.get("squeeze_fired") and sigs.get("momentum_up"):
        badge_html += _signal_badge("Squeeze Fired", "#aa00ff", "TTM Squeeze released upward")
    elif sigs.get("squeeze_active"):
        badge_html += _signal_badge("Squeeze Coiling", "#7c4dff", "Volatility compressed — awaiting release")
    if sigs.get("breakout"):
        badge_html += _signal_badge("Breakout", "#f0c040", f"Breakout from {sigs.get('consol_range_pct',0):.1f}% range")
    if sigs.get("candle_pattern") and sigs.get("candle_bullish"):
        badge_html += _signal_badge(sigs["candle_pattern"], "#56d364", "Bullish candlestick pattern")
    elif sigs.get("candle_pattern") and sigs.get("candle_bullish") is False:
        badge_html += _signal_badge(sigs["candle_pattern"], "#ff5252", "Bearish candlestick pattern — caution")
    if not badge_html:
        badge_html = '<span style="color:#555;font-size:0.75em">No special signals</span>'

    # ── Chart pattern badges ───────────────────────────────────────────────
    pat_info     = sigs.get("patterns", {})
    bull_pats    = pat_info.get("bullish_patterns", [])
    bear_pats    = pat_info.get("bearish_patterns", [])
    neut_pats    = pat_info.get("neutral_patterns", [])
    trend_struct = pat_info.get("trend_structure", {})
    tl_break     = pat_info.get("trendline", {})
    pat_score    = pat_info.get("pattern_score", 0)

    pat_badge_html = ""
    for pt in bull_pats:
        pat_badge_html += _signal_badge(pt, "#43a047", f"Bullish chart pattern: {pt}")
    for pt in bear_pats:
        pat_badge_html += _signal_badge(pt, "#c62828", f"Bearish chart pattern: {pt}")
    for pt in neut_pats:
        pat_badge_html += _signal_badge(pt, "#546e7a", f"Neutral — awaiting breakout: {pt}")
    ts_struct = trend_struct.get("structure", "")
    ts_bias   = trend_struct.get("bias", "neutral")
    ts_conf   = trend_struct.get("confidence", 0)
    if ts_struct and ts_struct not in ("undefined", "mixed"):
        ts_col = "#56d364" if ts_bias == "bullish" else ("#ff7b72" if ts_bias == "bearish" else "#8b949e")
        pat_badge_html += _signal_badge(
            f"Trend: {ts_struct}",
            ts_col,
            f"Trend structure: {ts_struct} (confidence {ts_conf}%)"
        )
    if not pat_badge_html:
        pat_badge_html = '<span style="color:#444;font-size:0.72em">No structural patterns</span>'

    # ── SR levels ──────────────────────────────────────────────────────────
    sr     = sigs.get("sr", {})
    res    = sr.get("resistance", [])
    sup    = sr.get("support", [])
    res_str = " | ".join(f"₹{r:,.2f}" for r in res[:2]) or "—"
    sup_str = " | ".join(f"₹{s:,.2f}" for s in sup[:2]) or "—"

    # ── Fundamentals grid ──────────────────────────────────────────────────
    roe   = fund.get("roe_pct")
    de    = fund.get("debt_to_equity")
    mar   = fund.get("profit_margin_pct")
    rev_g = fund.get("revenue_growth_pct")
    e_g   = fund.get("earnings_growth_pct")
    fcf   = fund.get("fcf_margin_pct")
    icr   = fund.get("interest_coverage")
    pe    = fund.get("pe_ratio")
    cr    = fund.get("current_ratio")

    def fv(v, s="", pg=True, fmt=".1f"):
        return _val(v, s, pg, fmt)

    fund_grid = f"""
      <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin-bottom:8px">
        <div style="background:#0d1117;border:1px solid #21262d;border-radius:5px;padding:5px 4px;text-align:center">
          <div style="font-size:0.62em;color:#8b949e">ROE</div><div style="font-size:0.88em">{fv(roe,'%')}</div></div>
        <div style="background:#0d1117;border:1px solid #21262d;border-radius:5px;padding:5px 4px;text-align:center">
          <div style="font-size:0.62em;color:#8b949e">D/E</div><div style="font-size:0.88em">{fv(de,'',False,'.2f')}</div></div>
        <div style="background:#0d1117;border:1px solid #21262d;border-radius:5px;padding:5px 4px;text-align:center">
          <div style="font-size:0.62em;color:#8b949e">Net Margin</div><div style="font-size:0.88em">{fv(mar,'%')}</div></div>
        <div style="background:#0d1117;border:1px solid #21262d;border-radius:5px;padding:5px 4px;text-align:center">
          <div style="font-size:0.62em;color:#8b949e">Rev Growth</div><div style="font-size:0.88em">{fv(rev_g,'%')}</div></div>
        <div style="background:#0d1117;border:1px solid #21262d;border-radius:5px;padding:5px 4px;text-align:center">
          <div style="font-size:0.62em;color:#8b949e">EPS Growth</div><div style="font-size:0.88em">{fv(e_g,'%')}</div></div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:8px">
        <div style="background:#0d1117;border:1px solid #21262d;border-radius:5px;padding:5px 4px;text-align:center">
          <div style="font-size:0.62em;color:#8b949e">FCF Margin</div><div style="font-size:0.88em">{fv(fcf,'%')}</div></div>
        <div style="background:#0d1117;border:1px solid #21262d;border-radius:5px;padding:5px 4px;text-align:center">
          <div style="font-size:0.62em;color:#8b949e">Int Coverage</div><div style="font-size:0.88em">{fv(icr,'x',True,'.1f')}</div></div>
        <div style="background:#0d1117;border:1px solid #21262d;border-radius:5px;padding:5px 4px;text-align:center">
          <div style="font-size:0.62em;color:#8b949e">P/E</div><div style="font-size:0.88em">{fv(pe,'',False,'.1f')}</div></div>
        <div style="background:#0d1117;border:1px solid #21262d;border-radius:5px;padding:5px 4px;text-align:center">
          <div style="font-size:0.62em;color:#8b949e">Curr Ratio</div><div style="font-size:0.88em">{fv(cr,'x',True,'.2f')}</div></div>
      </div>"""

    # ── Sector RS ──────────────────────────────────────────────────────────
    sector_name  = (rs_info.get("sector") or "").replace("_", " ")
    sector_rank  = rs_info.get("sector_rank")
    sector_peers = rs_info.get("sector_peers")
    own50        = rs_info.get("own_ret_50d_pct")
    avg50        = rs_info.get("sector_avg_50d_pct")
    rs_color     = "#56d364" if rs_info.get("rs_score", 10) >= 14 else "#ff9800" if rs_info.get("rs_score", 10) >= 8 else "#ff7b72"
    rs_row = ""
    if sector_name:
        rank_str = f"#{sector_rank}/{sector_peers}" if sector_rank else "—"
        own_str  = f"{own50:+.1f}%" if own50 is not None else "—"
        avg_str  = f"{avg50:+.1f}%" if avg50 is not None else "—"
        rs_row = (f'<div style="background:#0d1117;border:1px solid #21262d;border-radius:5px;'
                  f'padding:6px 10px;font-size:0.78em;margin-bottom:8px;display:flex;gap:16px;flex-wrap:wrap">'
                  f'<span style="color:#8b949e">Sector: <strong style="color:#58a6ff">{sector_name}</strong></span>'
                  f'<span style="color:#8b949e">Rank: <strong style="color:{rs_color}">{rank_str}</strong></span>'
                  f'<span style="color:#8b949e">50D RS: <strong style="color:{rs_color}">{own_str}</strong>'
                  f' vs avg <strong style="color:#8b949e">{avg_str}</strong></span></div>')

    # ── Score breakdown bars ───────────────────────────────────────────────
    bars = (
        _score_bar("Technical",    sb.get("technical", 0),      40, "#58a6ff") +
        _score_bar("Signals",      sb.get("signals", 0),        20, "#aa00ff") +
        _score_bar("Patterns",     sb.get("chart_patterns", 0), 10, "#43a047") +
        _score_bar("Fundamental",  sb.get("fundamental", 0),    35, "#56d364") +
        _score_bar("Rel Strength", sb.get("rel_strength", 0),   20, "#f0c040") +
        _score_bar("Stability",    sb.get("stability", 0),      25, "#ff9800") +
        _score_bar("Entry",        sb.get("entry_quality", 0),  24, "#00bcd4") +
        _score_bar("Momentum",     sb.get("momentum", 0),       15, "#ff5252")
    )

    reasons_html = "".join(f"<li>{r}</li>" for r in p.get("rationale", [])[:8])
    sent = str(p.get("market_context", ""))[:40]
    adt  = manip.get("avg_daily_turnover_cr", 0)

    rank_border = {1: "#f0c040", 2: "#c0c0c0", 3: "#cd7f32"}.get(i, "#30363d")
    rank_shadow = {1: "box-shadow:0 0 16px #f0c04033;", 2: "", 3: ""}.get(i, "")

    return f"""
    <div style="background:#161b22;border:1px solid {rank_border};border-radius:12px;padding:18px;{rank_shadow}">

      <!-- Header -->
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap">
        <span style="background:#21262d;color:#8b949e;font-size:0.78em;padding:3px 8px;border-radius:4px">#{i}</span>
        <span style="font-size:1.45em;font-weight:bold;color:#58a6ff;flex-grow:1">{p['symbol'].replace('.NS','')}</span>
        <span style="background:{score_color}22;border:1px solid {score_color}66;color:{score_color};padding:4px 10px;border-radius:16px;font-weight:bold;font-size:0.85em">{score}/150</span>
        <span style="background:#21262d;border:1px solid #58a6ff44;color:#58a6ff;padding:3px 8px;border-radius:10px;font-size:0.75em;font-weight:bold">Deploy {p.get('position_size_pct',100)}%</span>
        <div style="margin-left:auto">{spark}</div>
      </div>

      <!-- Trade Plan -->
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:10px">
        <div style="background:#21262d;padding:8px;border-radius:6px;text-align:center">
          <div style="font-size:0.67em;color:#8b949e">ENTRY</div>
          <div style="font-weight:bold;color:#58a6ff;font-size:1.05em">&#8377;{p['price']:,.2f}</div></div>
        <div style="background:#21262d;padding:8px;border-radius:6px;text-align:center">
          <div style="font-size:0.67em;color:#ff7b72">STOP LOSS (-{p.get('stop_pct',0):.1f}%)</div>
          <div style="font-weight:bold;color:#ff7b72;font-size:1.05em">&#8377;{p['stop_loss']:,.2f}</div></div>
        <div style="background:#21262d;padding:8px;border-radius:6px;text-align:center">
          <div style="font-size:0.67em;color:#56d364">TARGET (+{p['target_pct']}%)</div>
          <div style="font-weight:bold;color:#56d364;font-size:1.05em">&#8377;{p['target']:,.2f}</div></div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:10px">
        <div style="background:#21262d;padding:7px;border-radius:6px;text-align:center">
          <div style="font-size:0.63em;color:#8b949e">SHARES</div>
          <div style="font-weight:bold">{p['shares']}</div></div>
        <div style="background:#21262d;padding:7px;border-radius:6px;text-align:center">
          <div style="font-size:0.63em;color:#ff7b72">MAX LOSS</div>
          <div style="font-weight:bold;color:#ff7b72">-&#8377;{p['max_loss']:,.0f}</div></div>
        <div style="background:#21262d;padding:7px;border-radius:6px;text-align:center">
          <div style="font-size:0.63em;color:#56d364">MAX GAIN</div>
          <div style="font-weight:bold;color:#56d364">+&#8377;{p['max_gain']:,.0f}</div></div>
      </div>

      <!-- SR Levels -->
      <div style="display:flex;gap:16px;margin-bottom:10px;font-size:0.78em;flex-wrap:wrap">
        <span style="color:#8b949e">Resistance: <strong style="color:#ff7b72">{res_str}</strong></span>
        <span style="color:#8b949e">Support: <strong style="color:#56d364">{sup_str}</strong></span>
        <span style="color:#8b949e">ADX {p['adx']:.0f} | RSI {p['rsi']:.0f} |
          {"&#x2705; EMA" if ema_ok else "&#x26A0;&#xFE0F; EMA"} |
          {"&#x2705; MACD" if macd_ok else "&#x274C; MACD"} |
          &#8377;{adt:.0f}Cr/day | Manip {manip.get('manip_resistance_score',0)}/100</span>
      </div>

      <!-- Signals -->
      <div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:6px">
        {badge_html}
        {"" if not sent else f'<span style="background:#21262d;border:1px solid #30363d;color:#8b949e;padding:2px 8px;border-radius:10px;font-size:0.7em" title="{sent}">Macro: {sent[:35]}</span>'}
      </div>

      <!-- Chart Patterns -->
      <div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px;padding:6px 8px;background:#0d1117;border-radius:6px;border:1px solid #21262d">
        <span style="font-size:0.68em;color:#8b949e;align-self:center;margin-right:4px">PATTERNS</span>
        {pat_badge_html}
        <span style="margin-left:auto;font-size:0.7em;color:{'#43a047' if pat_score>0 else '#c62828' if pat_score<0 else '#555'};font-weight:bold">
          {'+' if pat_score>0 else ''}{pat_score}/10
        </span>
      </div>

      <!-- Fundamentals -->
      {fund_grid}
      {rs_row}

      <!-- Score Breakdown -->
      <div style="margin-bottom:10px">{bars}</div>

      <!-- Rationale -->
      <div style="background:#0d1117;border-radius:6px;padding:8px 12px">
        <ul style="padding-left:14px;color:#8b949e;font-size:0.78em;line-height:1.7;margin:0">
          {reasons_html}
        </ul>
      </div>
    </div>"""


def generate_html(data: dict) -> None:
    picks       = data.get("top_picks", [])
    regime      = data.get("regime", {})
    market_sent = data.get("market_sentiment", {})
    ts          = data.get("generated_at", "N/A")
    reg_name    = regime.get("regime", "UNKNOWN")
    reg_color   = _regime_color(reg_name)

    # Build cards — pass price history if available
    price_cache = data.get("_price_cache", {})
    cards_html  = ""
    for i, p in enumerate(picks[:5], 1):
        sym    = p["symbol"]
        prices = price_cache.get(sym, [])
        cards_html += _build_card(i, p, prices)

    conf_pct = regime.get("confidence_pct", "N/A")
    conf_color = "#56d364" if (conf_pct or 0) >= 70 else "#ff9800" if (conf_pct or 0) >= 50 else "#ff7b72"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Market Analyzer — {ts}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0d1117;color:#e6edf3;padding:24px;max-width:1600px;margin:0 auto}}
  h1{{color:#58a6ff;font-size:1.9em;margin-bottom:4px}}
  .sub{{color:#8b949e;font-size:0.88em;margin-bottom:22px}}
  .regime-box{{background:#161b22;border-left:5px solid {reg_color};padding:16px 20px;border-radius:10px;margin-bottom:22px}}
  .regime-title{{font-size:1.35em;color:{reg_color};font-weight:bold;margin-bottom:8px}}
  .regime-stats{{display:flex;gap:12px;flex-wrap:wrap}}
  .rs{{background:#21262d;padding:7px 12px;border-radius:6px;font-size:0.83em}}
  .rs .l{{color:#8b949e}} .rs .v{{color:#e6edf3;font-weight:bold}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(500px,1fr));gap:18px}}
  .note{{margin-top:28px;padding:12px;background:#161b22;border:1px solid #21262d;border-radius:8px;color:#8b949e;font-size:0.78em;line-height:1.6}}
</style>
</head>
<body>
<h1>Indian Market Analyzer</h1>
<p class="sub">Generated: {ts} &nbsp;|&nbsp; Budget: &#8377;{INVESTMENT_AMOUNT:,} &nbsp;|&nbsp; Universe: Nifty 100 + Quality Midcap &nbsp;|&nbsp; Max score: 150</p>

<div class="regime-box">
  <div class="regime-title">Market Regime: {reg_name} &mdash; {regime.get('description','')}</div>
  <div class="regime-stats">
    <div class="rs"><span class="l">Nifty 50 </span><span class="v">{regime.get('nifty_close','N/A')}</span></div>
    <div class="rs"><span class="l">ADX </span><span class="v">{regime.get('adx','N/A')}</span></div>
    <div class="rs"><span class="l">RSI </span><span class="v">{regime.get('rsi','N/A')}</span></div>
    <div class="rs"><span class="l">India VIX </span><span class="v">{regime.get('india_vix','N/A')}</span></div>
    <div class="rs"><span class="l">1M Return </span><span class="v">{regime.get('ret_1m_pct','N/A')}%</span></div>
    <div class="rs"><span class="l">3M Return </span><span class="v">{regime.get('ret_3m_pct','N/A')}%</span></div>
    <div class="rs"><span class="l">Signal Confidence </span><span class="v" style="color:{conf_color}">{conf_pct}%</span></div>
    <div class="rs"><span class="l">Market Sentiment </span><span class="v">{market_sent.get('overall_sentiment','N/A')}</span></div>
  </div>
</div>

<div class="cards">{cards_html}</div>

<div class="note">
  <strong>Scoring (max 150):</strong>
  Technical 40 (EMA structure, RSI, MACD, ADX, OBV, weekly confluence) +
  Signals 20 (RSI/MACD divergence, TTM squeeze, breakout, candlestick) +
  Chart Patterns &plusmn;10 (Double Top/Bottom, H&amp;S, Flags, Triangles, Wedges, Trendline breaks) +
  Fundamental 35 (ROE, D/E, rev/EPS growth, net margin, FCF, interest coverage) +
  Relative Strength 20 (50-day RS vs sector peers) +
  Stability 25 (ADT liquidity, spike freq, gap freq) +
  Entry Quality 24 (Bollinger position, 52W structure, near support) +
  Momentum 15 (ROC10, ROC20) + Regime 10 + Market Boost &plusmn;15 (FII, crude, USD/INR).<br>
  Stops are ATR-based (2.5&times; ATR). Targets snap to nearest structural resistance pivot.
  Pattern accuracy self-tracked daily in <code>results/prediction_log.json</code>.
  <strong style="color:#ff9800">&nbsp;&#x26A0; Markets carry significant risk. Always respect your stop-losses.</strong>
</div>
</body>
</html>"""

    os.makedirs(os.path.dirname(REPORT_HTML), exist_ok=True)
    with open(REPORT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
