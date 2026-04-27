import numpy as np
import pandas as pd
from technical_analysis import add_indicators, get_latest, calc_52w_stats, calc_manipulation_resistance, compute_weekly_df
from fundamental_analyzer import get_fundamentals, score_fundamentals
from signal_detector import detect_signals, compute_structured_target
from config import INVESTMENT_AMOUNT, REWARD_RISK_RATIO, MAX_PRICE, MIN_PRICE

ATR_STOP_MULT = 2.5    # 2.5× ATR — respects individual stock volatility
MIN_STOP_PCT  = 0.05
MAX_STOP_PCT  = 0.15


def score_stock(
    symbol: str,
    df: pd.DataFrame,
    nifty_df: pd.DataFrame,
    regime: dict,
    market_boost: int = 0,
    market_context: str = "",
    sector_rs: dict = None,
) -> dict | None:
    try:
        df_ind = add_indicators(df)
        if len(df_ind) < 200:
            return None

        lat   = get_latest(df_ind)
        price = lat["close"]

        if price > MAX_PRICE or price < MIN_PRICE:
            return None

        stats52 = calc_52w_stats(df_ind)
        manip   = calc_manipulation_resistance(df_ind, nifty_df)

        # ── Technical Score (0-40) ──────────────────────────────────────────
        tech = 0
        ema20, ema50, ema200 = lat["ema20"], lat["ema50"], lat["ema200"]
        rsi  = lat["rsi"]
        adx  = lat["adx"]

        if price > ema200:             tech += 8
        if price > ema50:              tech += 6
        if price > ema20:              tech += 4
        if ema20 > ema50 > ema200:     tech += 7

        if 45 <= rsi <= 62:            tech += 8
        elif 40 <= rsi <= 68:          tech += 5
        elif 35 <= rsi <= 72:          tech += 2

        macd_bullish = lat["macd"] > lat["macd_signal"]
        macd_accel   = lat["macd_hist"] > 0
        if macd_bullish and macd_accel: tech += 8
        elif macd_bullish:              tech += 4

        if adx > 30:                   tech += 6
        elif adx > 25:                 tech += 4
        elif adx > 20:                 tech += 2

        obv_trend = df_ind["obv"].iloc[-1] > df_ind["obv"].iloc[-20]
        if obv_trend:                  tech += 4

        if lat["vol_ratio"] > 1.2 and macd_bullish: tech += 4
        elif lat["vol_ratio"] > 0.8:                 tech += 2

        # Weekly confirmation (+5)
        weekly_macd_bull = False
        try:
            wdf = compute_weekly_df(df)
            if len(wdf) >= 20:
                wlat = get_latest(wdf)
                weekly_macd_bull = wlat["macd"] > wlat["macd_signal"]
                if weekly_macd_bull and wlat["close"] > wlat["ema50"]:
                    tech += 5
        except Exception:
            pass

        # ── Signal Quality (0-20) ───────────────────────────────────────────
        sigs = detect_signals(df_ind)
        sig_score = 0
        sig_reasons: list[str] = []

        if sigs["rsi_bull_div"]:
            sig_score += 8
            sig_reasons.append("RSI bullish divergence — price/momentum decoupling")
        if sigs["macd_bull_div"]:
            sig_score += 5
            sig_reasons.append("MACD histogram divergence — momentum reversal signal")
        if sigs["squeeze_fired"] and sigs["momentum_up"]:
            sig_score += 8
            sig_reasons.append("TTM Squeeze fired upward — compressed volatility releasing bullish")
        elif sigs["squeeze_active"]:
            sig_score += 3
            sig_reasons.append("TTM Squeeze active — coiling for a move")
        if sigs["breakout"]:
            btype = sigs.get("breakout_type") or "CONSOLIDATION"
            _btype_labels = {
                "CONSOLIDATION": f"Breakout from {sigs['consol_range_pct']:.1f}% consolidation with volume",
                "52W_HIGH":      "52-week high breakout — price at all-time momentum peak",
                "RESISTANCE":    "Resistance level broken with volume confirmation",
                "EMA_CROSS":     "20 EMA crossed above 50 EMA — bullish momentum shift",
                "VCP":           "Volatility Contraction Pattern — 3 squeeze stages, ready to launch",
            }
            sig_score += 7
            sig_reasons.append(_btype_labels.get(btype, f"Breakout ({btype}) with volume confirmation"))
        if sigs["candle_pattern"] and sigs["candle_bullish"]:
            sig_score += 4
            sig_reasons.append(f"{sigs['candle_pattern']} — bullish reversal candle")
        if sigs["rsi_bear_div"] or (sigs["candle_pattern"] and sigs["candle_bullish"] is False):
            sig_score -= 5

        sig_score = max(-8, min(20, sig_score))

        # ── Chart Pattern Score (-10 to +10) ───────────────────────────────
        pat_info    = sigs.get("patterns", {})
        pattern_adj = max(-10, min(10, pat_info.get("pattern_score", 0)))

        # ── Fundamental Score (-12 to +35) ─────────────────────────────────
        fundamentals = get_fundamentals(symbol)
        fund_score, fund_reasons = score_fundamentals(fundamentals)

        # ── Sector Relative Strength (0-20) ────────────────────────────────
        rs_info  = sector_rs or {}
        rs_score = rs_info.get("rs_score", 10)

        # ── Manipulation Resistance (0-25) ─────────────────────────────────
        stab = int(manip["manip_resistance_score"] * 25 / 100)

        # ── Entry Quality (0-20) ───────────────────────────────────────────
        entry  = 0
        bb_pct = lat["bb_pct"]
        if 0.25 <= bb_pct <= 0.55:    entry += 10
        elif bb_pct < 0.25:            entry += 14
        elif 0.55 < bb_pct <= 0.75:   entry += 6

        pct_from_high = stats52["pct_from_high"]
        if -15 <= pct_from_high <= -5:    entry += 6
        elif -30 <= pct_from_high <= -15: entry += 4

        # Bonus if entering near a known support level
        supports = sigs["sr"].get("support", [])
        if supports and abs(price - supports[0]) / price < 0.03:
            entry += 4

        # ── Momentum Continuation (0-15) ───────────────────────────────────
        mom   = 0
        roc10 = lat["roc_10"]
        roc20 = lat["roc_20"]
        if 2 <= roc10 <= 12:  mom += 8
        elif 0 <= roc10 < 2:  mom += 5
        if roc20 > roc10 > 0: mom += 7

        # ── Regime Alignment (0-10) ────────────────────────────────────────
        reg_bonus   = 0
        regime_name = regime.get("regime", "SIDEWAYS")
        if regime_name in ("STRONG_BULL", "BULL"):
            if ema20 > ema50 > ema200 and macd_bullish: reg_bonus = 10
            elif price > ema50:                          reg_bonus = 6
        elif regime_name == "SIDEWAYS":
            if lat["bb_pct"] < 0.35 and rsi < 50: reg_bonus = 10
            elif price > ema50:                    reg_bonus = 5
        elif regime_name in ("BEAR", "STRONG_BEAR"):
            if price > ema200 and ema20 > ema50: reg_bonus = 7

        # ── Market Data Boost (-15 to +15) ─────────────────────────────────
        market_adj = max(-15, min(15, market_boost))

        total = (tech + sig_score + fund_score + rs_score + stab
                 + entry + mom + reg_bonus + market_adj + pattern_adj)
        total = max(0, min(150, total))

        # ── ATR-Based Stop Loss ─────────────────────────────────────────────
        atr       = lat["atr"]
        raw_stop  = price - (atr * ATR_STOP_MULT)
        stop_loss = round(max(price * (1 - MAX_STOP_PCT), min(price * (1 - MIN_STOP_PCT), raw_stop)), 2)
        stop_pct  = round((price - stop_loss) / price * 100, 2)

        # ── Structure-Aware Target ──────────────────────────────────────────
        target = compute_structured_target(price, stop_loss, sigs["sr"], REWARD_RISK_RATIO)
        target_pct = round((target - price) / price * 100, 2)

        # ── Position Sizing (score-scaled) ─────────────────────────────────
        if total >= 100:   position_pct = 1.00
        elif total >= 80:  position_pct = 0.75
        elif total >= 65:  position_pct = 0.50
        else:              position_pct = 0.33

        budget          = round(INVESTMENT_AMOUNT * position_pct, 2)
        shares_possible = max(1, int(budget / price))
        invested        = round(shares_possible * price, 2)
        risk_per_share  = price - stop_loss
        max_loss        = round(shares_possible * risk_per_share, 2)
        max_gain        = round(shares_possible * (target - price), 2)

        # ── Composite Rationale ─────────────────────────────────────────────
        reasons: list[str] = []
        if ema20 > ema50 > ema200:      reasons.append("Full EMA alignment — clean bullish structure")
        if 45 <= rsi <= 62:             reasons.append(f"RSI {rsi:.0f} — ideal momentum zone, not overbought")
        if macd_bullish and macd_accel: reasons.append("MACD bullish and accelerating")
        if weekly_macd_bull:            reasons.append("Weekly MACD confirms — multi-timeframe confluence")
        if adx > 25:                    reasons.append(f"ADX {adx:.0f} — trending market, not noise")
        if manip["avg_daily_turnover_cr"] > 100:
            reasons.append(f"₹{manip['avg_daily_turnover_cr']:.0f} Cr avg daily turnover — highly liquid")
        if lat["bb_pct"] < 0.3:        reasons.append("Near Bollinger lower band — mean reversion setup")
        if obv_trend:                   reasons.append("OBV rising — institutional accumulation")
        reasons.extend(sig_reasons)
        reasons.extend(fund_reasons)
        if rs_info.get("sector_rank") and rs_info.get("sector_peers"):
            rank, peers = rs_info["sector_rank"], rs_info["sector_peers"]
            if rank <= max(1, peers // 4):
                reasons.append(f"Sector rank #{rank}/{peers} — top quartile in {rs_info.get('sector','').replace('_',' ')}")
        # Chart pattern rationale
        for pat in pat_info.get("bullish_patterns", []):
            reasons.append(f"{pat} pattern active — structural bullish setup")
        ts = pat_info.get("trend_structure", {})
        if ts.get("structure") == "HH/HL" and ts.get("confidence", 0) > 60:
            reasons.append("Higher highs / higher lows — intact uptrend structure")

        # ── ML probability overlay ─────────────────────────────────────────────
        ml_prob         = 0.5
        ml_adj_total    = total
        try:
            from ml_predictor import predict_proba, ml_adjust_score, is_ready
            if is_ready():
                ml_prob      = predict_proba(
                    df_ind, signals=sigs, stats52=stats52,
                    regime_str=regime.get("regime", "SIDEWAYS"),
                    vix=regime.get("india_vix") or 15.0,
                    rule_score=total,
                )
                ml_adj_total = ml_adjust_score(total, ml_prob)
        except Exception:
            pass

        return {
            "symbol":            symbol,
            "price":             round(price, 2),
            "shares":            shares_possible,
            "invested":          invested,
            "stop_loss":         stop_loss,
            "stop_pct":          stop_pct,
            "target":            target,
            "target_pct":        target_pct,
            "max_loss":          max_loss,
            "max_gain":          max_gain,
            "total_score":       ml_adj_total,
            "rule_score":        total,
            "ml_prob":           round(ml_prob, 4),
            "position_size_pct": int(position_pct * 100),
            "score_breakdown": {
                "technical":      tech,
                "signals":        sig_score,
                "chart_patterns": pattern_adj,
                "fundamental":    fund_score,
                "rel_strength":   rs_score,
                "stability":      stab,
                "entry_quality":  entry,
                "momentum":       mom,
                "regime_bonus":   reg_bonus,
                "market_boost":   market_adj,
            },
            "signals":         sigs,
            "fundamentals":    fundamentals,
            "sector_rs":       rs_info,
            "market_context":  market_context,
            "manip_resistance": manip,
            "stats_52w":       stats52,
            "rsi":             round(rsi, 2),
            "adx":             round(adx, 2),
            "ema_aligned":     bool(ema20 > ema50 > ema200),
            "macd_bullish":    bool(macd_bullish),
            "rationale":       reasons,
            # Pass df_ind so accuracy_tracker can save features (not serialised to JSON)
            "_df_ind":         df_ind,
        }

    except Exception:
        return None
