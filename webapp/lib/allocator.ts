import type { StockPick, AllocatedPick, PortfolioAllocation, WeeklyEvent } from "./types";

function isBreakout(p: StockPick): boolean {
  const s = p.signals;
  const pats = s.patterns?.bullish_patterns ?? [];
  return (
    s.breakout ||
    (s.squeeze_fired && s.momentum_up) ||
    pats.length > 0 ||
    p.total_score >= 115
  );
}

function urgency(p: StockPick): "high" | "medium" | "low" {
  const btype = p.signals.breakout_type;
  // Highest urgency: explosive or time-sensitive setups
  if (btype === "52W_HIGH" || btype === "VCP" || btype === "RESISTANCE") return "high";
  if (p.signals.breakout || (p.signals.squeeze_fired && p.signals.momentum_up)) return "high";
  // Medium urgency: momentum shift signals
  if (btype === "EMA_CROSS" || btype === "CONSOLIDATION") return "medium";
  if (p.signals.rsi_bull_div || p.signals.macd_bull_div) return "medium";
  return "low";
}

function weeklyTargetPct(p: StockPick): number {
  // Conservative weekly target = target / holding weeks (assume 12 weeks horizon)
  return Math.round((p.target_pct / 12) * 10) / 10;
}

export function allocateCapital(capital: number, picks: StockPick[], goalReturnPct?: number): PortfolioAllocation {
  if (!picks.length) {
    return {
      total_capital: capital, core_budget: 0, breakout_budget: 0, reserve: 0,
      core_picks: [], breakout_picks: [], weekly_plan: [], deployed: 0, cash: capital,
    };
  }

  // Split into breakout vs long-term
  const breakoutCandidates = picks.filter(isBreakout).slice(0, 2);
  const coreCandidates     = picks.filter(p => !breakoutCandidates.includes(p)).slice(0, 3);

  // Budget split — shifts toward breakouts when profit goal is aggressive
  let breakoutRatio: number;
  let reserveRatio: number;
  if (goalReturnPct && goalReturnPct > 25) {
    breakoutRatio = breakoutCandidates.length > 0 ? 0.45 : 0;
    reserveRatio  = 0.05;
  } else if (goalReturnPct && goalReturnPct > 15) {
    breakoutRatio = breakoutCandidates.length > 0 ? 0.35 : 0;
    reserveRatio  = 0.07;
  } else {
    breakoutRatio = breakoutCandidates.length > 0 ? 0.30 : 0;
    reserveRatio  = 0.10;
  }
  const coreRatio = 1 - breakoutRatio - reserveRatio;

  const breakoutBudget = Math.round(capital * breakoutRatio);
  const reserve        = Math.round(capital * reserveRatio);
  const coreBudget     = capital - breakoutBudget - reserve;

  function allocate(p: StockPick, amount: number, type: "core" | "breakout", allPct: number): AllocatedPick {
    const shares   = Math.max(1, Math.floor(amount / p.price));
    const invested = Math.round(shares * p.price * 100) / 100;
    // Recalculate gain/loss from actual allocated shares, not the Python-side fixed values
    const maxGain  = Math.round(shares * p.price * (p.target_pct / 100));
    const maxLoss  = Math.round(shares * p.price * (p.stop_pct  / 100));
    return {
      ...p,
      allocated_amount:  amount,
      allocated_shares:  shares,
      actual_invested:   invested,
      max_gain:          maxGain,
      max_loss:          maxLoss,
      allocation_type:   type,
      allocation_pct:    allPct,
      weekly_target_pct: weeklyTargetPct(p),
      urgency:           urgency(p),
    };
  }

  const corePerStock     = coreCandidates.length  ? Math.floor(coreBudget     / coreCandidates.length)  : 0;
  const breakoutPerStock = breakoutCandidates.length ? Math.floor(breakoutBudget / breakoutCandidates.length) : 0;

  const corePct     = Math.round(coreRatio     * 100);
  const breakoutPct = Math.round(breakoutRatio * 100);

  const core_picks     = coreCandidates.map(p     => allocate(p, corePerStock,     "core",     Math.round(corePct     / (coreCandidates.length     || 1))));
  const breakout_picks = breakoutCandidates.map(p => allocate(p, breakoutPerStock, "breakout", Math.round(breakoutPct / (breakoutCandidates.length || 1))));

  const deployed = [...core_picks, ...breakout_picks].reduce((s, p) => s + p.actual_invested, 0);

  // Weekly plan generator
  const allPicks = [...breakout_picks, ...core_picks];
  const weekly_plan: WeeklyEvent[] = [
    {
      week: 1,
      label: "Week 1 — Deploy Core",
      type: "entry",
      description: `Enter all ${core_picks.length} core positions with limit orders 0.5% below current price. Set GTT stop losses immediately after fill.`,
      stocks: core_picks.map(p => p.symbol.replace(".NS", "")),
    },
    ...(breakout_picks.length > 0
      ? [{
          week: 1,
          label: "Week 1 — Breakout Entry",
          type: "entry" as const,
          description: `Deploy breakout capital into ${breakout_picks.map(p => p.symbol.replace(".NS", "")).join(", ")}. These are time-sensitive — enter within 2 sessions.`,
          stocks: breakout_picks.map(p => p.symbol.replace(".NS", "")),
        }]
      : []),
    {
      week: 2,
      label: "Week 2 — First Review",
      type: "review",
      description: `Check all positions. If any breakout stock is up ${breakout_picks[0]?.weekly_target_pct ?? 5}%+ within the week, book 40% profit and raise stop to breakeven on the rest.`,
      stocks: allPicks.map(p => p.symbol.replace(".NS", "")),
    },
    {
      week: 4,
      label: "Week 4 — Rebalance",
      type: "rebalance",
      description: `Move any freed capital from exits back into the best-performing core position or next-ranked breakout opportunity from fresh scan.`,
      stocks: [],
    },
    {
      week: 8,
      label: "Week 8 — Mid-Review",
      type: "review",
      description: `Raise all trailing stops to lock in at least breakeven. Exit any position that hasn't moved +5% and reinvest into top scorer from next scan.`,
      stocks: allPicks.map(p => p.symbol.replace(".NS", "")),
    },
    {
      week: 12,
      label: "Week 12 — Target Review",
      type: "exit",
      description: `Evaluate which positions have reached 60%+ of target. Consider partial exits (50% of shares) to lock in profit. Let remaining ride with trailing stops.`,
      stocks: allPicks.slice(0, 2).map(p => p.symbol.replace(".NS", "")),
    },
  ];

  return {
    total_capital: capital,
    core_budget:     coreBudget,
    breakout_budget: breakoutBudget,
    reserve,
    core_picks,
    breakout_picks,
    weekly_plan,
    deployed,
    cash: capital - deployed,
  };
}
