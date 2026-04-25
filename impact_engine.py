"""
Translates real market data into sector impact scores.
Pure quantitative logic — no keywords, no headlines, no guessing.

Each factor has explicit reasoning tied to the actual economic mechanism.
"""

from market_data import INDEX_TO_SECTOR
from config import SECTOR_STOCKS


def calculate_sector_impacts(md: dict) -> dict[str, dict]:
    """
    Takes output of fetch_all_market_data() and returns per-sector impacts.

    Returns:
        {sector_name: {score, reasons, data_points, direction}}
    """
    raw: dict[str, list] = {}   # sector -> [(score_delta, reason, data_point)]

    def add(sector: str, pts: int, reason: str, data: str) -> None:
        raw.setdefault(sector, []).append((pts, reason, data))

    factors = md.get("global_factors", {})
    sectors = md.get("sector_indices", {})
    fii     = md.get("fii_dii", {})

    # ─────────────────────────────────────────────────────────────────────────
    # 1. BRENT CRUDE — India imports ~85% of oil needs. Single biggest macro.
    #    Direct, quantifiable relationship to margin of multiple sectors.
    # ─────────────────────────────────────────────────────────────────────────
    crude = factors.get("Brent Crude", {})
    cp    = crude.get("pct_change", 0)

    if cp <= -8:
        add("Energy_Downstream", +4, "Crude -8%+: OMC marketing margin expands sharply", f"Brent {cp:+.1f}%")
        add("Paints",            +4, "Crude -8%+: TiO2/resin/monomer costs drop significantly", f"Brent {cp:+.1f}%")
        add("Chemicals",         +3, "Crude -8%+: Petrochemical feedstock much cheaper", f"Brent {cp:+.1f}%")
        add("Auto",              +2, "Crude -8%+: Fuel costs fall; vehicle economics improve", f"Brent {cp:+.1f}%")
        add("FMCG",              +2, "Crude -8%+: Packaging/logistics cost relief", f"Brent {cp:+.1f}%")
        add("Energy_Upstream",   -4, "Crude -8%+: ONGC realization falls proportionally", f"Brent {cp:+.1f}%")
    elif cp <= -4:
        add("Energy_Downstream", +3, "Crude -4%+: Meaningful input cost relief for OMCs", f"Brent {cp:+.1f}%")
        add("Paints",            +3, "Crude -4%+: Raw material cost tailwind for paint cos", f"Brent {cp:+.1f}%")
        add("Chemicals",         +2, "Crude -4%+: Feedstock cheaper", f"Brent {cp:+.1f}%")
        add("Auto",              +1, "Crude -4%+: Fuel cost relief supports demand", f"Brent {cp:+.1f}%")
        add("Energy_Upstream",   -3, "Crude -4%+: E&P realization falls", f"Brent {cp:+.1f}%")
    elif cp <= -1.5:
        add("Energy_Downstream", +1, "Crude softening: modest margin benefit for OMCs", f"Brent {cp:+.1f}%")
        add("Paints",            +1, "Crude softening: mild input cost benefit", f"Brent {cp:+.1f}%")
        add("Energy_Upstream",   -1, "Crude softening: E&P realization dips", f"Brent {cp:+.1f}%")
    elif cp >= 8:
        add("Energy_Upstream",   +4, "Crude +8%+: ONGC/Oil India realization surges", f"Brent {cp:+.1f}%")
        add("Energy_Downstream", -4, "Crude +8%+: OMC under-recovery risk returns", f"Brent {cp:+.1f}%")
        add("Paints",            -4, "Crude +8%+: Input cost squeeze on paint margins", f"Brent {cp:+.1f}%")
        add("Chemicals",         -3, "Crude +8%+: Petrochemical margins compressed", f"Brent {cp:+.1f}%")
        add("Auto",              -2, "Crude +8%+: Fuel costs dent consumer sentiment", f"Brent {cp:+.1f}%")
        add("FMCG",              -2, "Crude +8%+: Logistics and packaging costs rise", f"Brent {cp:+.1f}%")
    elif cp >= 4:
        add("Energy_Upstream",   +3, "Crude +4%: E&P realization improves", f"Brent {cp:+.1f}%")
        add("Energy_Downstream", -3, "Crude +4%: OMC input cost pressure", f"Brent {cp:+.1f}%")
        add("Paints",            -3, "Crude +4%: Raw material cost headwind", f"Brent {cp:+.1f}%")
    elif cp >= 1.5:
        add("Energy_Upstream",   +1, "Crude firming: mild E&P benefit", f"Brent {cp:+.1f}%")
        add("Energy_Downstream", -1, "Crude firming: mild OMC pressure", f"Brent {cp:+.1f}%")
        add("Paints",            -1, "Crude firming: mild input cost headwind", f"Brent {cp:+.1f}%")

    # ─────────────────────────────────────────────────────────────────────────
    # 2. USD/INR — Every 1% rupee depreciation = ~1% revenue boost for IT/Pharma.
    #    Most IT companies earn 70%+ in USD; most pharma exports are USD-billed.
    # ─────────────────────────────────────────────────────────────────────────
    usdinr = factors.get("USD/INR", {})
    up     = usdinr.get("pct_change", 0)   # positive = rupee weakened

    if up >= 1.0:
        add("IT",    +3, f"Rupee -{up:.1f}%: ~{up:.0f}% boost to USD-billed IT revenues in INR", f"USD/INR {up:+.2f}%")
        add("Pharma",+2, f"Rupee -{up:.1f}%: Export-heavy pharma earns more in INR", f"USD/INR {up:+.2f}%")
        add("Energy_Downstream", -1, "Rupee weak: crude import bill rises in INR", f"USD/INR {up:+.2f}%")
    elif up >= 0.3:
        add("IT",    +2, f"Rupee softening: mild USD revenue tailwind for IT", f"USD/INR {up:+.2f}%")
        add("Pharma",+1, f"Rupee softening: export pharma marginally benefits", f"USD/INR {up:+.2f}%")
    elif up <= -1.0:
        add("IT",    -3, f"Rupee +{abs(up):.1f}%: USD revenues lose value in INR terms", f"USD/INR {up:+.2f}%")
        add("Pharma",-2, f"Rupee strengthening: export margin compression", f"USD/INR {up:+.2f}%")
        add("Metals", +1, "Rupee strong: metal imports cheaper", f"USD/INR {up:+.2f}%")
    elif up <= -0.3:
        add("IT",    -2, "Rupee firm: mild USD revenue headwind for IT", f"USD/INR {up:+.2f}%")
        add("Pharma",-1, "Rupee firm: mild export margin pressure", f"USD/INR {up:+.2f}%")

    # ─────────────────────────────────────────────────────────────────────────
    # 3. US 10Y YIELD — Rising yield makes US treasuries more attractive vs
    #    Indian equities → FIIs reduce India allocation → broad selling pressure.
    #    Banks/NBFCs/Realty most sensitive (rate-sensitive sectors).
    # ─────────────────────────────────────────────────────────────────────────
    y10    = factors.get("US 10Y Yield", {})
    y10p   = y10.get("pct_change", 0)
    y10val = y10.get("price", 4.5)

    if y10p <= -3:
        add("Banks",  +3, "US yields falling fast: FII EM allocation increases → flows into India banks", f"10Y {y10val:.2f}% ({y10p:+.1f}%)")
        add("NBFC",   +3, "US yields falling: risk appetite for EM financials rises", f"10Y {y10val:.2f}% ({y10p:+.1f}%)")
        add("Realty", +2, "US yields falling: rate-sensitive realty benefits from inflow", f"10Y {y10val:.2f}% ({y10p:+.1f}%)")
    elif y10p <= -1.5:
        add("Banks",  +2, "US yields easing: moderate FII India inflow", f"10Y {y10val:.2f}%")
        add("NBFC",   +2, "US yields easing: positive for EM financials", f"10Y {y10val:.2f}%")
        add("Realty", +1, "US yields easing: realty sector benefits", f"10Y {y10val:.2f}%")
    elif y10p >= 3:
        add("Banks",  -3, "US yields surging: FII exits EM → Indian banks face selling", f"10Y {y10val:.2f}% ({y10p:+.1f}%)")
        add("NBFC",   -2, "US yields surging: EM financial allocation cut", f"10Y {y10val:.2f}%")
        add("Realty", -2, "US yields surging: rate-sensitive realty under pressure", f"10Y {y10val:.2f}%")
    elif y10p >= 1.5:
        add("Banks",  -2, "US yields rising: moderate FII India outflow risk", f"10Y {y10val:.2f}%")
        add("NBFC",   -1, "US yields rising: EM financial headwind", f"10Y {y10val:.2f}%")
        add("Realty", -1, "US yields rising: realty under mild pressure", f"10Y {y10val:.2f}%")

    # ─────────────────────────────────────────────────────────────────────────
    # 4. S&P 500 — Proxy for global risk-on/off → FII behavior in India.
    #    When US markets rise strongly, FIIs typically add EM risk.
    # ─────────────────────────────────────────────────────────────────────────
    sp  = factors.get("S&P 500", {})
    spp = sp.get("pct_change", 0)

    if spp >= 1.5:
        add("Banks",   +2, "S&P +1.5%+: Risk-on globally; FII India inflow likely", f"S&P {spp:+.1f}%")
        add("IT",      +1, "S&P up strongly: global tech sentiment positive", f"S&P {spp:+.1f}%")
    elif spp >= 0.5:
        add("Banks",   +1, "S&P positive: mild global risk appetite", f"S&P {spp:+.1f}%")
    elif spp <= -1.5:
        add("Banks",   -2, "S&P -1.5%+: Risk-off; FII India outflow risk", f"S&P {spp:+.1f}%")
        add("IT",      -1, "S&P falling: global tech sentiment weak", f"S&P {spp:+.1f}%")
    elif spp <= -0.5:
        add("Banks",   -1, "S&P weak: mild global risk-off", f"S&P {spp:+.1f}%")

    # ─────────────────────────────────────────────────────────────────────────
    # 5. HANG SENG — China consumes ~50% of world's metals. HSI moves are
    #    the best real-time proxy for Chinese industrial demand.
    # ─────────────────────────────────────────────────────────────────────────
    hsi  = factors.get("Hang Seng", {})
    hsip = hsi.get("pct_change", 0)

    if hsip >= 2:
        add("Metals", +3, "HSI +2%: China demand optimism directly boosts steel/aluminium/copper", f"HSI {hsip:+.1f}%")
    elif hsip >= 1:
        add("Metals", +1, "HSI positive: mild China demand support for metals", f"HSI {hsip:+.1f}%")
    elif hsip <= -2:
        add("Metals", -3, "HSI -2%: China demand pessimism → Indian metals under pressure", f"HSI {hsip:+.1f}%")
    elif hsip <= -1:
        add("Metals", -1, "HSI weak: mild China demand concern for metals", f"HSI {hsip:+.1f}%")

    # ─────────────────────────────────────────────────────────────────────────
    # 6. GOLD — Rising gold = either risk-off (safe haven) or inflation fears.
    #    Direct India impact: NBFC gold-loan books (Muthoot, Manappuram) benefit
    #    as collateral value rises. Also signals potential FII caution.
    # ─────────────────────────────────────────────────────────────────────────
    gold  = factors.get("Gold", {})
    goldp = gold.get("pct_change", 0)

    if goldp >= 1.5:
        add("NBFC", +2, "Gold +1.5%: Muthoot/Manappuram collateral value rises → gold-loan AUM grows", f"Gold {goldp:+.1f}%")
    elif goldp >= 0.5:
        add("NBFC", +1, "Gold up: positive for gold-loan NBFCs", f"Gold {goldp:+.1f}%")
    elif goldp <= -1.5:
        add("NBFC", -2, "Gold -1.5%: Gold-loan collateral value falls → NPA risk for gold NBFCs", f"Gold {goldp:+.1f}%")
    elif goldp <= -0.5:
        add("NBFC", -1, "Gold softening: mild headwind for gold-loan NBFCs", f"Gold {goldp:+.1f}%")

    # ─────────────────────────────────────────────────────────────────────────
    # 7. FII / DII FLOWS — The most direct signal. This is actual institutional
    #    money moving. FII buys/sells large-caps disproportionately.
    #    DII flows (LIC, mutual funds) often counter FII, providing support.
    # ─────────────────────────────────────────────────────────────────────────
    fii_net = fii.get("fii_net_cr")
    dii_net = fii.get("dii_net_cr")

    if fii_net is not None:
        if fii_net >= 3000:
            add("Banks",   +4, f"FII bought ₹{fii_net:,.0f} Cr: Heavy institutional buying in financials", f"FII ₹{fii_net:+,.0f} Cr")
            add("IT",      +2, f"FII ₹{fii_net:,.0f} Cr buying: IT large-caps receive FII flows", f"FII ₹{fii_net:+,.0f} Cr")
            add("Pharma",  +1, "Strong FII buying: broad large-cap tailwind", f"FII ₹{fii_net:+,.0f} Cr")
        elif fii_net >= 1000:
            add("Banks",   +2, f"FII bought ₹{fii_net:,.0f} Cr: Meaningful institutional inflow", f"FII ₹{fii_net:+,.0f} Cr")
            add("IT",      +1, "Moderate FII buying: large-cap IT benefits", f"FII ₹{fii_net:+,.0f} Cr")
        elif fii_net >= 200:
            add("Banks",   +1, "Mild FII buying: slight positive for financials", f"FII ₹{fii_net:+,.0f} Cr")
        elif fii_net <= -3000:
            add("Banks",   -4, f"FII sold ₹{abs(fii_net):,.0f} Cr: Heavy institutional selling → financial sector pressure", f"FII ₹{fii_net:+,.0f} Cr")
            add("IT",      -2, "Heavy FII selling: IT large-caps face outflow", f"FII ₹{fii_net:+,.0f} Cr")
        elif fii_net <= -1000:
            add("Banks",   -2, f"FII sold ₹{abs(fii_net):,.0f} Cr: Meaningful outflow from financials", f"FII ₹{fii_net:+,.0f} Cr")
            add("IT",      -1, "Moderate FII selling: IT sees outflow", f"FII ₹{fii_net:+,.0f} Cr")
        elif fii_net <= -200:
            add("Banks",   -1, "Mild FII selling: slight headwind for financials", f"FII ₹{fii_net:+,.0f} Cr")

    if dii_net is not None and dii_net >= 2000:
        # Strong DII support often cushions market even when FII sells
        add("Banks", +1, f"DII bought ₹{dii_net:,.0f} Cr: domestic institutions providing support", f"DII ₹{dii_net:+,.0f} Cr")

    # ─────────────────────────────────────────────────────────────────────────
    # 8. SECTOR INDEX RELATIVE STRENGTH — The ground truth of where real money
    #    is flowing TODAY. If Nifty Bank is +2% while Nifty 50 is flat, banks
    #    are receiving active rotation. This is already price-confirmed.
    # ─────────────────────────────────────────────────────────────────────────
    nifty_pct = md.get("nifty_1d_pct", 0)

    for idx_name, idx_data in sectors.items():
        rel = idx_data.get("relative_strength", 0)
        mapped_sectors = INDEX_TO_SECTOR.get(idx_name, [])

        if rel >= 2.0:
            for s in mapped_sectors:
                add(s, +3, f"{idx_name} outperforming Nifty by {rel:+.1f}%: active sector rotation in", f"{idx_name} RS {rel:+.2f}%")
        elif rel >= 1.0:
            for s in mapped_sectors:
                add(s, +2, f"{idx_name} outperforming Nifty by {rel:+.1f}%: sector inflow confirmed", f"{idx_name} RS {rel:+.2f}%")
        elif rel >= 0.4:
            for s in mapped_sectors:
                add(s, +1, f"{idx_name} mild outperformance vs Nifty", f"{idx_name} RS {rel:+.2f}%")
        elif rel <= -2.0:
            for s in mapped_sectors:
                add(s, -3, f"{idx_name} underperforming Nifty by {abs(rel):.1f}%: sector rotation out", f"{idx_name} RS {rel:+.2f}%")
        elif rel <= -1.0:
            for s in mapped_sectors:
                add(s, -2, f"{idx_name} underperforming Nifty by {abs(rel):.1f}%: sector outflow", f"{idx_name} RS {rel:+.2f}%")
        elif rel <= -0.4:
            for s in mapped_sectors:
                add(s, -1, f"{idx_name} mild underperformance vs Nifty", f"{idx_name} RS {rel:+.2f}%")

    # ── Compile results ───────────────────────────────────────────────────────
    results: dict[str, dict] = {}
    for sector, entries in raw.items():
        score    = sum(e[0] for e in entries)
        reasons  = [e[1] for e in entries]
        data_pts = [e[2] for e in entries]
        results[sector] = {
            "score":       score,
            "direction":   "POSITIVE" if score > 0 else "NEGATIVE" if score < 0 else "NEUTRAL",
            "reasons":     reasons,
            "data_points": data_pts,
            "stocks":      SECTOR_STOCKS.get(sector, []),
        }

    return results


def compute_stock_boost(symbol: str, sector_impacts: dict, stock_sector_map: dict) -> tuple[int, list[str]]:
    """
    Given per-sector impacts, return net boost for a single stock.
    Boost capped at ±15 to preserve primacy of technical score.
    Returns (boost_pts, reason_strings).
    """
    sectors  = stock_sector_map.get(symbol, [])
    total    = 0
    contexts = []

    for sector in sectors:
        if sector not in sector_impacts:
            continue
        sc  = sector_impacts[sector]["score"]
        # Scale: each sector score unit = 3 pts (more conservative than before)
        pts = max(-12, min(12, sc * 3))
        total += pts
        if sc != 0:
            top_reason = sector_impacts[sector]["reasons"][0] if sector_impacts[sector]["reasons"] else ""
            contexts.append(f"{sector.replace('_',' ')}: {top_reason}")

    return max(-15, min(15, total)), contexts
