"use client";

import { useState, useEffect, useCallback } from "react";
import type {
  Analysis, AllocatedPick, PortfolioAllocation, StockPick, WeeklyEvent,
  UserPosition, ProfitGoal,
} from "@/lib/types";
import { allocateCapital } from "@/lib/allocator";

// ── Formatters ────────────────────────────────────────────────────────────────
const fmtINR = (n: number) =>
  "₹" + new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(Math.abs(n));
const fmtDec = (n: number) =>
  new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(n);
const sign = (n: number) => (n >= 0 ? "+" : "−");

type AdviceItem = { text: string; type: "positive" | "warning" | "action" | "info" };

// ── Mobile breakpoint hook ────────────────────────────────────────────────────
function useIsMobile() {
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);
  return isMobile;
}

// ── Live clock ────────────────────────────────────────────────────────────────
function LiveClock() {
  const [t, setT] = useState("");
  useEffect(() => {
    const tick = () =>
      setT(new Date().toLocaleTimeString("en-IN", {
        timeZone: "Asia/Kolkata", hour12: false,
        hour: "2-digit", minute: "2-digit", second: "2-digit",
      }));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return <span className="mono">{t} IST</span>;
}

// ── Dynamic advice generator ──────────────────────────────────────────────────
function generateAdvice(
  positions: UserPosition[],
  goal: ProfitGoal | null,
  analysis: Analysis,
  currentPrices: Record<string, number>,
): AdviceItem[] {
  const advice: AdviceItem[] = [];
  const { regime } = analysis;
  const isBull = regime.regime === "BULL" || regime.regime === "STRONG_BULL";
  const isBear = regime.regime === "BEAR" || regime.regime === "STRONG_BEAR";

  if (regime.regime === "STRONG_BULL") {
    advice.push({ text: `Strong bull regime — momentum accelerating. Hold all positions, add on EMA pullbacks.`, type: "positive" });
  } else if (isBull) {
    advice.push({ text: `Bull regime confirmed (ADX ${regime.adx?.toFixed(0) ?? "—"}, RSI ${regime.rsi?.toFixed(0) ?? "—"}) — stay long, trail stops.`, type: "positive" });
  } else if (isBear) {
    advice.push({ text: `Bear regime active — tighten all stops to −3%. Avoid new long entries until regime recovers.`, type: "warning" });
  } else if (regime.regime === "VOLATILE") {
    advice.push({ text: `High VIX environment — use limit orders only, reduce position sizes by 30%.`, type: "warning" });
  } else {
    advice.push({ text: `Sideways market — take partial profits at resistance. Hold only high-conviction positions.`, type: "info" });
  }

  if (positions.length === 0) {
    advice.push({ text: "Add your live positions above to get stock-specific recommendations.", type: "info" });
    return advice;
  }

  const totalInvested = positions.reduce((s, p) => s + p.avgPrice * p.qty, 0);
  const currentValue  = positions.reduce((s, p) => s + (currentPrices[p.symbol] ?? p.avgPrice) * p.qty, 0);
  const totalPnl = currentValue - totalInvested;

  for (const pos of positions) {
    const cur = currentPrices[pos.symbol];
    if (cur === undefined) continue;
    const pct = ((cur - pos.avgPrice) / pos.avgPrice) * 100;
    const pick = analysis.top_picks.find(p => p.symbol.replace(".NS", "") === pos.symbol);
    const targetPct = pick?.target_pct ?? 12;

    if (pct >= targetPct * 0.8) {
      advice.push({ text: `${pos.symbol} at +${pct.toFixed(1)}% — near target. Book 40% profit, trail remaining with tight stop.`, type: "action" });
    } else if (pct <= -5 && isBear) {
      advice.push({ text: `${pos.symbol} −${Math.abs(pct).toFixed(1)}% in bear market — consider full exit to preserve capital.`, type: "warning" });
    } else if (pct <= -4) {
      advice.push({ text: `${pos.symbol} at ${pct.toFixed(1)}% — near stop zone. Hold only if fundamentals still intact.`, type: "warning" });
    } else if (pct >= 12) {
      advice.push({ text: `${pos.symbol} up ${pct.toFixed(1)}% — raise stop to breakeven, lock in minimum gain.`, type: "action" });
    } else if (pick && isBull) {
      advice.push({ text: `${pos.symbol} scores ${pick.total_score}/150 — system still bullish on this. Hold.`, type: "positive" });
    }
  }

  if (goal && totalInvested > 0) {
    const progress = goal.targetAmount > 0 ? (totalPnl / goal.targetAmount) * 100 : 0;
    if (totalPnl >= goal.targetAmount) {
      advice.push({ text: `Goal achieved! ₹${goal.targetAmount.toLocaleString("en-IN")} target reached — consider locking in profits now.`, type: "positive" });
    } else if (progress >= 50) {
      advice.push({ text: `${progress.toFixed(0)}% toward ₹${goal.targetAmount.toLocaleString("en-IN")} goal — on track. Maintain discipline.`, type: "positive" });
    } else {
      const needed = ((goal.targetAmount - totalPnl) / totalInvested) * 100;
      advice.push({ text: `Need +${needed.toFixed(1)}% more to hit goal — ${isBull ? "bull regime supports this" : "challenging in current regime"}.`, type: needed > 20 ? "warning" : "info" });
    }
  }

  return advice.slice(0, 6);
}

// ── Dynamic roadmap generator ─────────────────────────────────────────────────
function generateDynamicRoadmap(
  alloc: PortfolioAllocation,
  userPositions: UserPosition[],
  currentPrices: Record<string, number>,
  analysis: Analysis,
  goal: ProfitGoal | null,
  currentWeek: number | null,
): WeeklyEvent[] {
  const { regime } = analysis;
  const isBull = regime.regime === "BULL" || regime.regime === "STRONG_BULL";
  const isBear = regime.regime === "BEAR" || regime.regime === "STRONG_BEAR";
  const isVol  = regime.regime === "VOLATILE";
  const hasReal = userPositions.length > 0;
  const totalWeeks = goal?.weeks ?? 12;

  const totalInvested = hasReal ? userPositions.reduce((s, p) => s + p.avgPrice * p.qty, 0) : alloc.total_capital;
  const currentValue  = hasReal ? userPositions.reduce((s, p) => s + (currentPrices[p.symbol] ?? p.avgPrice) * p.qty, 0) : alloc.total_capital;
  const pnlPct = totalInvested > 0 ? ((currentValue - totalInvested) / totalInvested) * 100 : 0;
  const goalProgress = goal && goal.targetAmount > 0 && totalInvested > 0
    ? Math.min(100, ((currentValue - totalInvested) / goal.targetAmount) * 100) : null;

  const posSymbols = hasReal
    ? userPositions.map(p => p.symbol)
    : [...alloc.breakout_picks, ...alloc.core_picks].map(p => p.symbol.replace(".NS", ""));

  const events: WeeklyEvent[] = [];

  // Week 1
  if (isBear) {
    events.push({ week: 1, label: "Week 1 — Defensive Posture", type: "review",
      description: "Bear regime active. Tighten all stop losses to −3%. Avoid new entries until ADX and RSI signal recovery. Capital protection is priority.",
      stocks: posSymbols.slice(0, 3) });
  } else if (isVol) {
    events.push({ week: 1, label: "Week 1 — Volatility Protocol", type: "review",
      description: "High VIX detected. Use limit orders only, reduce position sizes by 30%. Set hard stops at −4% and monitor daily.",
      stocks: posSymbols.slice(0, 3) });
  } else {
    events.push({ week: 1, label: hasReal ? "Week 1 — Confirm Entries" : "Week 1 — Deploy Capital", type: "entry",
      description: hasReal
        ? `${isBull ? "Bull regime supports your entries. " : ""}Confirm all ${userPositions.length} stop losses are placed. Set GTT price alerts at targets.`
        : `${isBull ? "Bull regime — " : ""}Enter ${alloc.core_picks.length} core positions at limit orders. Set stop losses immediately after fill.`,
      stocks: posSymbols.slice(0, 4) });
  }

  // Week 2
  events.push({ week: 2, label: "Week 2 — First Review", type: "review",
    description: pnlPct >= 3
      ? `Portfolio up ${pnlPct.toFixed(1)}%. Trail stops to +1% above entry on all profitable positions. Let winners run.`
      : pnlPct < -3
        ? `Portfolio down ${Math.abs(pnlPct).toFixed(1)}%. Assess each position vs stop. ${isBear ? "Consider cutting losers." : "Hold if support intact."}`
        : `Positions flat. ${isBull ? "Bull markets reward patience — hold." : "Watch for support break as exit signal."}`,
    stocks: [] });

  // Week 4
  if (goal) {
    const reqPct = totalInvested > 0 ? (goal.targetAmount / totalInvested) * 100 : 0;
    events.push({ week: 4, label: "Week 4 — Goal Checkpoint", type: "rebalance",
      description: `Target: ₹${goal.targetAmount.toLocaleString("en-IN")} (+${reqPct.toFixed(1)}% return). ${
        goalProgress !== null && goalProgress >= 33
          ? `On track at ${goalProgress.toFixed(0)}% progress. Maintain strategy.`
          : "Behind pace — consider deploying cash reserve into highest-conviction position."
      }`, stocks: [] });
  } else {
    events.push({ week: 4, label: "Week 4 — Rebalance", type: "rebalance",
      description: isBull
        ? "Reinvest freed capital into strongest momentum pick. Raise trailing stops to +2% on all profitable positions."
        : "Exit underperformers. Hold top 2-3 conviction positions only. Increase cash to 20%.",
      stocks: [] });
  }

  // Week 8
  events.push({ week: 8, label: "Week 8 — Mid-Cycle Review", type: "review",
    description: isBull
      ? "Raise all trailing stops to lock minimum 50% of current gains. Consider adding to the single strongest position if regime still bullish."
      : "Reassess every position. Exit any holding that is not up >5% by this point and redeploy.",
    stocks: posSymbols.slice(0, 3) });

  // Week 12
  if (totalWeeks >= 12) {
    events.push({ week: 12, label: goal ? "Week 12 — Final Target Review" : "Week 12 — Cycle Close", type: "exit",
      description: goal
        ? `Final checkpoint for ₹${goal.targetAmount.toLocaleString("en-IN")} goal. Book all positions at or above target. Roll remaining into next cycle with fresh analysis.`
        : "Book 60%+ of profits. Let highest-conviction position run with tight trailing stop. Prepare fresh analysis for next cycle.",
      stocks: posSymbols.slice(0, 2) });
  }

  return events;
}

// ── SVG Trajectory Chart ──────────────────────────────────────────────────────
function TrajectoryChart({
  alloc, weeks, userPositions, currentPrices, topPicks, regime,
}: {
  alloc: PortfolioAllocation; weeks: number;
  userPositions?: UserPosition[]; currentPrices?: Record<string, number>;
  topPicks?: StockPick[]; regime?: { regime: string };
}) {
  const W = 900, H = 260, PAD = { t: 20, r: 20, b: 32, l: 60 };
  const cW = W - PAD.l - PAD.r;
  const cH = H - PAD.t - PAD.b;

  const base = alloc.total_capital;
  const allPicks = [...alloc.breakout_picks, ...alloc.core_picks];
  const maxReturn = allPicks.reduce((s, p) => s + p.max_gain, 0);

  const systemPoints: number[] = Array.from({ length: weeks + 1 }, (_, w) => {
    const t = w / weeks;
    const smooth = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
    const noise = Math.sin(w * 1.7) * base * 0.004 + Math.cos(w * 2.9) * base * 0.003;
    return base + maxReturn * 0.65 * smooth + noise;
  });

  // Actual portfolio trajectory
  let actualPoints: number[] = [];
  let costBasis: number | null = null;

  if (userPositions && userPositions.length > 0 && currentPrices) {
    const invested = userPositions.reduce((s, p) => s + p.avgPrice * p.qty, 0);
    const curVal   = userPositions.reduce((s, p) => s + (currentPrices[p.symbol] ?? p.avgPrice) * p.qty, 0);

    let weightedReturn = 0, totalW = 0;
    for (const pos of userPositions) {
      const cur = currentPrices[pos.symbol] ?? pos.avgPrice;
      const val = cur * pos.qty;
      const pick = topPicks?.find(p => p.symbol.replace(".NS", "") === pos.symbol);
      let upside: number;
      if (pick && cur < pick.target) {
        upside = (pick.target - cur) / cur;
      } else {
        const map: Record<string, number> = { STRONG_BULL: 0.10, BULL: 0.07, SIDEWAYS: 0.03, BEAR: -0.03, STRONG_BEAR: -0.06, VOLATILE: 0.04 };
        upside = map[regime?.regime ?? "SIDEWAYS"] ?? 0.04;
      }
      weightedReturn += val * upside;
      totalW += val;
    }
    const avgReturn = totalW > 0 ? (weightedReturn / totalW) * 0.65 : 0.04;

    actualPoints = Array.from({ length: weeks + 1 }, (_, w) => {
      const t = w / weeks;
      const smooth = t < 0.5 ? 2*t*t : -1 + (4-2*t)*t;
      return curVal + curVal * avgReturn * smooth;
    });
    costBasis = invested;
  }

  const allVals = [...systemPoints, ...actualPoints];
  const minV = Math.min(...allVals) * 0.98;
  const maxV = Math.max(...allVals) * 1.02;

  const px = (i: number) => PAD.l + (i / weeks) * cW;
  const py = (v: number) => PAD.t + cH - ((v - minV) / (maxV - minV)) * cH;

  const sysPts  = systemPoints.map((v, i) => `${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(" ");
  const sysArea = `${px(0).toFixed(1)},${(PAD.t+cH).toFixed(1)} ${sysPts} ${px(weeks).toFixed(1)},${(PAD.t+cH).toFixed(1)}`;
  const actPts  = actualPoints.length > 0 ? actualPoints.map((v, i) => `${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(" ") : "";

  const yLabels = [minV, (minV+maxV)/2, maxV].map(v => ({ v, y: py(v), label: fmtINR(v) }));
  const xLabels = [0,3,6,9,12].filter(w => w <= weeks).map(w => ({ w, x: px(w), label: w===0?"NOW":`W${w}` }));
  const hasActual = actualPoints.length > 0;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" preserveAspectRatio="none" style={{ display: "block" }}>
      <defs>
        <linearGradient id="orange-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ff4500" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#ff4500" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="line-grad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#ff4500" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#ff4500" stopOpacity="1" />
        </linearGradient>
      </defs>

      {yLabels.map(({ v, y }) => (
        <g key={v}>
          <line x1={PAD.l} y1={y} x2={W-PAD.r} y2={y} stroke="#1e1e1e" strokeWidth="1" strokeDasharray="4,6" />
          <text x={PAD.l-8} y={y+4} textAnchor="end" fill="#444" fontSize="10" fontFamily="'JetBrains Mono', monospace">{fmtINR(v)}</text>
        </g>
      ))}

      {costBasis !== null && (
        <line x1={PAD.l} y1={py(costBasis)} x2={W-PAD.r} y2={py(costBasis)}
          stroke="#444" strokeWidth="1" strokeDasharray="6,4" />
      )}

      {/* System projection */}
      <polygon points={sysArea} fill="url(#orange-grad)" opacity={hasActual ? 0.45 : 1} />
      <polyline points={sysPts} fill="none" stroke="url(#line-grad)" strokeWidth={hasActual ? 1.5 : 2} strokeLinejoin="round" opacity={hasActual ? 0.45 : 1} />

      {/* Actual portfolio trajectory */}
      {actPts && (
        <>
          <polyline points={actPts} fill="none" stroke="#ffffff" strokeWidth="2" strokeLinejoin="round" />
          <circle cx={px(weeks)} cy={py(actualPoints[weeks])} r="5" fill="#0a0a0a" stroke="#fff" strokeWidth="2" />
          <circle cx={px(weeks)} cy={py(actualPoints[weeks])} r="2.5" fill="#fff" />
        </>
      )}

      <circle cx={px(weeks)} cy={py(systemPoints[weeks])} r={hasActual ? 3 : 5} fill="#0a0a0a" stroke="#ff4500" strokeWidth="2" />
      <circle cx={px(weeks)} cy={py(systemPoints[weeks])} r={hasActual ? 1.5 : 2.5} fill="#ff4500" />

      {xLabels.map(({ w, x, label }) => (
        <text key={w} x={x} y={H-6} textAnchor="middle" fill="#444" fontSize="10" fontFamily="'JetBrains Mono', monospace">{label}</text>
      ))}

      {hasActual && (
        <g>
          <rect x={W-PAD.r-130} y={PAD.t} width={120} height={36} fill="#111" stroke="#1e1e1e" strokeWidth="1" />
          <line x1={W-PAD.r-122} y1={PAD.t+10} x2={W-PAD.r-110} y2={PAD.t+10} stroke="#ff4500" strokeWidth="1.5" opacity="0.5" />
          <text x={W-PAD.r-106} y={PAD.t+14} fill="#555" fontSize="9" fontFamily="'JetBrains Mono', monospace">SYSTEM</text>
          <line x1={W-PAD.r-122} y1={PAD.t+24} x2={W-PAD.r-110} y2={PAD.t+24} stroke="#fff" strokeWidth="1.5" />
          <text x={W-PAD.r-106} y={PAD.t+28} fill="#888" fontSize="9" fontFamily="'JetBrains Mono', monospace">YOUR PORTFOLIO</text>
        </g>
      )}
    </svg>
  );
}

// ── Nav items ─────────────────────────────────────────────────────────────────
const NAV_ITEMS = [
  { id: "overview",    label: "OVERVIEW",     icon: "▦" },
  { id: "positions",   label: "POSITIONS",    icon: "≡" },
  { id: "breakouts",   label: "BREAKOUTS",    icon: "⚡" },
  { id: "tracker",     label: "TRACKER",      icon: "◈" },
  { id: "performance", label: "PERFORMANCE",  icon: "∿" },
  { id: "analytics",   label: "ANALYTICS",    icon: "◎" },
  { id: "system",      label: "SYSTEM SETUP", icon: "⚙" },
] as const;
type NavId = typeof NAV_ITEMS[number]["id"];

// ── Sidebar (desktop only) ────────────────────────────────────────────────────
function Sidebar({ active, setActive }: { active: NavId; setActive: (id: NavId) => void }) {
  const isMobile = useIsMobile();
  if (isMobile) return null;
  return (
    <div style={{ width: 240, background: "#0a0a0a", borderRight: "1px solid #1a1a1a", display: "flex", flexDirection: "column", height: "100dvh", flexShrink: 0 }}>
      <div style={{ padding: "28px 24px 32px", borderBottom: "1px solid #1a1a1a" }}>
        <div className="label" style={{ color: "#ff4500", marginBottom: 2, letterSpacing: "0.18em" }}>PORTF.OS</div>
        <div className="label" style={{ color: "#333", letterSpacing: "0.12em" }}>/ INTELLIGENCE</div>
      </div>
      <nav style={{ flex: 1, padding: "20px 16px", display: "flex", flexDirection: "column", gap: 4 }}>
        {NAV_ITEMS.map(item => (
          <button key={item.id} onClick={() => setActive(item.id)}
            style={{
              background: "none", cursor: "pointer", textAlign: "left", padding: "11px 16px",
              display: "flex", alignItems: "center", gap: 12,
              ...(active === item.id ? { border: "1px solid #ff4500", color: "#fff" } : { border: "1px solid transparent", color: "#444" }),
            }}
            className="label"
            onMouseEnter={e => { if (active !== item.id) (e.currentTarget as HTMLElement).style.color = "#888"; }}
            onMouseLeave={e => { if (active !== item.id) (e.currentTarget as HTMLElement).style.color = "#444"; }}
          >
            <span style={{ fontSize: "0.75rem", color: active === item.id ? "#ff4500" : "inherit" }}>{item.icon}</span>
            <span style={{ letterSpacing: "0.14em" }}>{item.label}</span>
          </button>
        ))}
      </nav>
      <div style={{ padding: "20px 24px", borderTop: "1px solid #1a1a1a" }}>
        <div className="label" style={{ color: "#2a2a2a", marginBottom: 6 }}>VERSION</div>
        <div className="mono" style={{ fontSize: "0.72rem", color: "#333" }}>v3.0 — LIVE TRACKER</div>
      </div>
    </div>
  );
}

// ── Mobile Tab Bar ────────────────────────────────────────────────────────────
function MobileTabBar({ active, setActive }: { active: NavId; setActive: (id: NavId) => void }) {
  return (
    <div style={{ position: "fixed", bottom: 0, left: 0, right: 0, background: "#0a0a0a", borderTop: "1px solid #1a1a1a", display: "flex", zIndex: 100, height: 58 }}>
      {NAV_ITEMS.map(item => (
        <button key={item.id} onClick={() => setActive(item.id)}
          style={{
            flex: 1, background: "none", border: "none", display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center", gap: 3, cursor: "pointer",
            borderTop: active === item.id ? "2px solid #ff4500" : "2px solid transparent",
            color: active === item.id ? "#ff4500" : "#444", padding: "6px 0",
          }}
        >
          <span style={{ fontSize: "0.9rem", lineHeight: 1 }}>{item.icon}</span>
          <span style={{ fontSize: "0.42rem", letterSpacing: "0.04em", fontFamily: "'JetBrains Mono', monospace", lineHeight: 1 }}>
            {item.label.split(" ")[0]}
          </span>
        </button>
      ))}
    </div>
  );
}

// ── Header bar ────────────────────────────────────────────────────────────────
function TopBar({ section, hasData, generatedAt, updateFlash }: {
  section: string; hasData: boolean; generatedAt: string | null; updateFlash: boolean;
}) {
  const isMobile = useIsMobile();
  const [ago, setAgo] = useState("");
  useEffect(() => {
    if (!generatedAt) return;
    const calc = () => {
      const diff = Math.floor((Date.now() - new Date(generatedAt).getTime()) / 60000);
      setAgo(diff < 1 ? "just now" : diff < 60 ? `${diff}m ago` : `${Math.floor(diff/60)}h ago`);
    };
    calc();
    const id = setInterval(calc, 30000);
    return () => clearInterval(id);
  }, [generatedAt]);

  if (isMobile) return (
    <div style={{ height: 44, borderBottom: "1px solid #1a1a1a", display: "flex", alignItems: "center", padding: "0 16px", flexShrink: 0, background: updateFlash ? "#0f0a00" : "#0a0a0a", transition: "background 0.6s ease" }}>
      <span className="label" style={{ color: "#fff", letterSpacing: "0.16em", fontSize: "0.7rem" }}>{section}</span>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
        {updateFlash && <span className="label" style={{ color: "#ff4500", fontSize: "0.6rem" }}>⚡ UPDATED</span>}
        <span className="label" style={{ color: hasData ? "#22c55e" : "#ff4500", fontSize: "0.65rem" }}>{hasData ? "LIVE" : "OFFLINE"}</span>
        <span className={`status-dot ${hasData ? "status-dot-green" : ""}`} />
      </div>
    </div>
  );

  return (
    <div style={{ height: 52, borderBottom: "1px solid #1a1a1a", display: "flex", alignItems: "center", padding: "0 32px", flexShrink: 0, background: updateFlash ? "#0f0a00" : "#0a0a0a", transition: "background 0.6s ease" }}>
      <span className="label" style={{ color: "#fff", letterSpacing: "0.18em", fontSize: "0.75rem" }}>{section}</span>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 28 }}>
        {generatedAt && (
          <span className="label" style={{ color: updateFlash ? "#ff4500" : "#444", transition: "color 0.6s ease" }}>
            {updateFlash ? "⚡ DATA UPDATED" : `DATA: ${ago}`}
          </span>
        )}
        <span className="label" style={{ color: "#444" }}>GLOBAL SESSION: <LiveClock /></span>
        <span className="label" style={{ color: "#444", display: "flex", alignItems: "center", gap: 6 }}>
          SYSTEM STATUS:&nbsp;
          <span style={{ color: hasData ? "#22c55e" : "#ff4500" }}>{hasData ? "LIVE" : "OFFLINE"}</span>
          <span className={`status-dot ${hasData ? "status-dot-green" : ""}`} />
        </span>
      </div>
    </div>
  );
}

// ── Stat Card ─────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, inverted = false, delta, color }: {
  label: string; value: string; sub?: string; inverted?: boolean;
  delta?: { value: string; positive: boolean }; color?: string;
}) {
  return (
    <div className={inverted ? "stat-card-inverted" : "stat-card"} style={{ flex: 1 }}>
      <div className="label" style={{ marginBottom: 10, color: inverted ? "#888" : "#555" }}>{label}</div>
      <div className="mono" style={{ fontSize: "clamp(1.1rem, 3.5vw, 2rem)", fontWeight: 600, lineHeight: 1, color: color ?? (inverted ? "#0a0a0a" : "#fff"), letterSpacing: "-0.02em" }}>
        {value}
      </div>
      {(sub || delta) && (
        <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          {delta && (
            <span style={{ background: inverted ? "#0a0a0a" : "#1e1e1e", color: delta.positive ? "#ff4500" : "#888", padding: "2px 6px", fontSize: "0.65rem", fontFamily: "'JetBrains Mono', monospace" }}>
              ↗ {delta.value}
            </span>
          )}
          {sub && <span className="label" style={{ color: inverted ? "#999" : "#444", fontSize: "0.6rem" }}>{sub}</span>}
        </div>
      )}
    </div>
  );
}

// ── Desktop table header ──────────────────────────────────────────────────────
function DesktopTableHeader() {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "32px 100px 90px 80px 80px 80px 80px 80px 60px", gap: 0, padding: "10px 24px", borderBottom: "1px solid #1a1a1a" }}>
      {["#", "SYMBOL", "PRICE", "TARGET", "STOP", "DEPLOY", "MAX GAIN", "SIGNALS", "SCORE"].map(h => (
        <div key={h} className="label" style={{ fontSize: "0.6rem" }}>{h}</div>
      ))}
    </div>
  );
}

// ── ML Confidence Badge ───────────────────────────────────────────────────────
function MlBadge({ prob }: { prob?: number }) {
  if (prob == null) return null;
  const pct   = Math.round(prob * 100);
  const color = prob >= 0.70 ? "#22c55e" : prob >= 0.55 ? "#f59e0b" : prob >= 0.45 ? "#888" : "#ef4444";
  const label = prob >= 0.70 ? "HIGH" : prob >= 0.55 ? "MED" : prob < 0.40 ? "LOW" : "";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 2 }}>
      <div style={{ width: 28, height: 3, background: "#1a1a1a", borderRadius: 1, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 1 }} />
      </div>
      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "0.58rem", color, letterSpacing: "0.05em" }}>
        {pct}%{label ? ` ${label}` : ""}
      </span>
    </div>
  );
}

// ── Position Row ──────────────────────────────────────────────────────────────
function PositionRow({ pick, rank, onExpand, expanded }: { pick: AllocatedPick; rank: number; onExpand: () => void; expanded: boolean }) {
  const isMobile = useIsMobile();
  const sym = pick.symbol.replace(".NS", "");
  const isBreak = pick.allocation_type === "breakout";
  const f = pick.fundamentals;

  if (isMobile) return (
    <>
      <div className="row-hover" onClick={onExpand} style={{ padding: "12px 16px", cursor: "pointer", borderBottom: "1px solid #111" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span className="mono" style={{ color: "#333", fontSize: "0.62rem" }}>#{rank}</span>
            {isBreak && <span style={{ color: "#ff4500", fontSize: "0.62rem" }}>⚡</span>}
            <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>{sym}</span>
          </div>
          <span className="mono" style={{ color: "#ff4500", fontSize: "0.82rem", fontWeight: 600 }}>+{pick.target_pct}%</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <div style={{ display: "flex", gap: 10 }}>
            <span className="mono" style={{ color: "#888", fontSize: "0.72rem" }}>{fmtINR(pick.price)}</span>
            <span className="mono" style={{ color: "#ef4444", fontSize: "0.72rem" }}>SL {fmtINR(pick.stop_loss)}</span>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span className="mono" style={{ color: "#22c55e", fontSize: "0.72rem" }}>+{fmtINR(pick.max_gain)}</span>
            <div>
              <span className="mono" style={{ fontSize: "0.62rem", color: pick.total_score >= 100 ? "#ff4500" : "#555" }}>{pick.total_score}/150</span>
              <MlBadge prob={pick.ml_prob} />
            </div>
          </div>
        </div>
        <div style={{ marginTop: 4 }}>
          <span className="mono" style={{ color: "#666", fontSize: "0.68rem" }}>Deploy: <span style={{ color: "#fff" }}>{fmtINR(pick.actual_invested)}</span></span>
        </div>
      </div>
      {expanded && (
        <div style={{ background: "#0d0d0d", borderBottom: "1px solid #1a1a1a", padding: "16px" }}>
          <div className="label" style={{ marginBottom: 8, color: "#555" }}>ENTRY PLAN</div>
          {[
            { l: "Shares", v: `${pick.allocated_shares} × ${fmtINR(pick.price)}` },
            { l: "Deploy", v: fmtINR(pick.actual_invested) },
            { l: "Stop", v: `${fmtINR(pick.stop_loss)} (−${pick.stop_pct.toFixed(1)}%)` },
            { l: "Target", v: `${fmtINR(pick.target)} (+${pick.target_pct}%)` },
            { l: "Max Gain", v: fmtINR(pick.max_gain) },
          ].map(r => (
            <div key={r.l} style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
              <span className="label">{r.l}</span>
              <span className="mono" style={{ fontSize: "0.75rem", color: "#ccc" }}>{r.v}</span>
            </div>
          ))}
          <div className="label" style={{ marginBottom: 8, marginTop: 12, color: "#555" }}>RATIONALE</div>
          {pick.rationale.slice(0, 3).map((r, i) => (
            <div key={i} style={{ display: "flex", gap: 6, marginBottom: 4 }}>
              <span style={{ color: "#ff4500", fontSize: "0.6rem", marginTop: 2 }}>▸</span>
              <span style={{ fontSize: "0.7rem", color: "#666", lineHeight: 1.5 }}>{r}</span>
            </div>
          ))}
        </div>
      )}
    </>
  );

  return (
    <>
      <div className="row-hover" onClick={onExpand} style={{ display: "grid", gridTemplateColumns: "32px 100px 90px 80px 80px 80px 80px 80px 60px", gap: 0, padding: "14px 24px", cursor: "pointer", borderBottom: "1px solid #111", alignItems: "center" }}>
        <div className="mono" style={{ color: "#333", fontSize: "0.72rem" }}>#{rank}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {isBreak && <span style={{ color: "#ff4500", fontSize: "0.6rem" }}>⚡</span>}
          <span style={{ fontWeight: 600, fontSize: "0.88rem" }}>{sym}</span>
        </div>
        <div className="mono" style={{ fontSize: "0.8rem", color: "#888" }}>{fmtINR(pick.price)}</div>
        <div className="mono" style={{ color: "#ff4500", fontSize: "0.8rem" }}>+{pick.target_pct}%</div>
        <div className="mono" style={{ color: "#ef4444", fontSize: "0.8rem" }}>−{pick.stop_pct.toFixed(1)}%</div>
        <div className="mono" style={{ fontSize: "0.8rem", color: "#fff" }}>{fmtINR(pick.actual_invested)}</div>
        <div className="mono" style={{ color: "#22c55e", fontSize: "0.8rem" }}>+{fmtINR(pick.max_gain)}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
          {[pick.ema_aligned, pick.macd_bullish, pick.signals.rsi_bull_div].map((ok, i) => (
            <div key={i} style={{ width: 6, height: 6, borderRadius: "50%", background: ok ? "#ff4500" : "#222" }} />
          ))}
        </div>
        <div>
          <div className="mono" style={{ fontSize: "0.72rem", color: pick.total_score >= 100 ? "#ff4500" : pick.total_score >= 80 ? "#888" : "#444" }}>
            {pick.total_score}/150
          </div>
          <MlBadge prob={pick.ml_prob} />
        </div>
      </div>
      {expanded && (
        <div style={{ background: "#0d0d0d", borderBottom: "1px solid #1a1a1a", padding: "20px 24px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 24 }}>
            <div>
              <div className="label" style={{ marginBottom: 12 }}>ENTRY PLAN</div>
              {[
                { l: "Shares", v: `${pick.allocated_shares} × ${fmtINR(pick.price)}` },
                { l: "Deploy", v: fmtINR(pick.actual_invested) },
                { l: "Stop Loss", v: `${fmtINR(pick.stop_loss)} (−${pick.stop_pct.toFixed(1)}%)` },
                { l: "Target", v: `${fmtINR(pick.target)} (+${pick.target_pct}%)` },
                { l: "Max Gain", v: fmtINR(pick.max_gain) },
                { l: "Max Loss", v: fmtINR(pick.max_loss) },
              ].map(r => (
                <div key={r.l} style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                  <span className="label">{r.l}</span>
                  <span className="mono" style={{ fontSize: "0.78rem", color: "#ccc" }}>{r.v}</span>
                </div>
              ))}
            </div>
            <div>
              <div className="label" style={{ marginBottom: 12 }}>FUNDAMENTALS</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 16px" }}>
                {[
                  { l: "ROE", v: f.roe_pct != null ? `${f.roe_pct.toFixed(1)}%` : "—" },
                  { l: "D/E", v: f.debt_to_equity != null ? f.debt_to_equity.toFixed(2) : "—" },
                  { l: "Margin", v: f.profit_margin_pct != null ? `${f.profit_margin_pct.toFixed(1)}%` : "—" },
                  { l: "Rev Grw", v: f.revenue_growth_pct != null ? `${f.revenue_growth_pct.toFixed(1)}%` : "—" },
                  { l: "FCF", v: f.fcf_margin_pct != null ? `${f.fcf_margin_pct.toFixed(1)}%` : "—" },
                  { l: "P/E", v: f.pe_ratio != null ? f.pe_ratio.toFixed(1) : "—" },
                ].map(r => (
                  <div key={r.l} style={{ display: "flex", justifyContent: "space-between" }}>
                    <span className="label">{r.l}</span>
                    <span className="mono" style={{ fontSize: "0.78rem", color: "#aaa" }}>{r.v}</span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="label" style={{ marginBottom: 12 }}>SIGNAL RATIONALE</div>
              {pick.rationale.slice(0, 5).map((r, i) => (
                <div key={i} style={{ display: "flex", gap: 8, marginBottom: 6 }}>
                  <span style={{ color: "#ff4500", fontSize: "0.6rem", marginTop: 2 }}>▸</span>
                  <span style={{ fontSize: "0.72rem", color: "#666", lineHeight: 1.5 }}>{r}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ── Live Tracker Page ─────────────────────────────────────────────────────────
function AddPositionForm({ onAdd, onCancel, isMobile, currentPrices }: {
  onAdd: (p: UserPosition) => void; onCancel: () => void; isMobile: boolean;
  currentPrices: Record<string, number>;
}) {
  const [query, setQuery]     = useState("");
  const [sym, setSym]         = useState("");   // confirmed symbol
  const [qty, setQty]         = useState("");
  const [avgPrice, setAvgPrice] = useState("");
  const [open, setOpen]       = useState(false);

  const allStocks = Object.keys(currentPrices).sort();
  const q = query.toUpperCase().trim();

  // starts-with first, then contains — max 10 items
  const filtered = q.length > 0
    ? [...allStocks.filter(s => s.startsWith(q)),
       ...allStocks.filter(s => !s.startsWith(q) && s.includes(q))].slice(0, 10)
    : [];

  const livePrice = sym ? (currentPrices[sym] ?? null) : null;
  const qtyNum    = parseInt(qty, 10);
  const avgNum    = parseFloat(avgPrice);
  const pnl       = livePrice != null && !isNaN(qtyNum) && qtyNum > 0 && !isNaN(avgNum) && avgNum > 0
    ? (livePrice - avgNum) * qtyNum : null;
  const pnlPct    = livePrice != null && !isNaN(avgNum) && avgNum > 0
    ? ((livePrice - avgNum) / avgNum) * 100 : null;
  const isValid   = !!sym && currentPrices[sym] != null && !isNaN(qtyNum) && qtyNum > 0 && !isNaN(avgNum) && avgNum > 0;

  const select = (stock: string) => { setSym(stock); setQuery(stock); setOpen(false); };

  const handleQueryChange = (val: string) => {
    const up = val.toUpperCase();
    setQuery(up);
    setOpen(true);
    // auto-confirm exact match
    if (currentPrices[up]) setSym(up); else setSym("");
  };

  const submit = () => {
    if (!isValid) return;
    onAdd({ symbol: sym, qty: qtyNum, avgPrice: avgNum });
    setSym(""); setQuery(""); setQty(""); setAvgPrice("");
  };

  const inp: React.CSSProperties = {
    width: "100%", background: "#111", border: "1px solid #2a2a2a",
    color: "#fff", fontFamily: "'JetBrains Mono', monospace",
    fontSize: "0.82rem", padding: "9px 11px", outline: "none",
  };

  const pnlColor = pnl == null ? "#888" : pnl >= 0 ? "#22c55e" : "#ef4444";

  return (
    <div style={{ background: "#0d0d0d", border: "1px solid #1a1a1a", borderTop: "none", padding: isMobile ? "14px 16px" : "16px 24px", marginBottom: 2 }}>

      {/* Row 1: input fields */}
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "2fr 72px 130px 130px", gap: 8, marginBottom: 10 }}>

        {/* Symbol autocomplete */}
        <div style={{ position: "relative" }}>
          <div className="label" style={{ marginBottom: 4 }}>SYMBOL</div>
          <input
            value={query}
            onChange={e => handleQueryChange(e.target.value)}
            onFocus={() => { if (q.length > 0) setOpen(true); }}
            onBlur={() => setTimeout(() => setOpen(false), 160)}
            placeholder="Search NSE symbol…"
            style={{ ...inp, borderColor: sym ? "#ff4500" : "#2a2a2a" }}
          />
          {open && q.length > 0 && (
            <div style={{
              position: "absolute", top: "100%", left: 0, right: 0, zIndex: 300,
              background: "#111", border: "1px solid #2a2a2a", borderTop: "none",
              maxHeight: 220, overflowY: "auto",
            }}>
              {filtered.length > 0 ? filtered.map(stock => (
                <div
                  key={stock}
                  onMouseDown={() => select(stock)}
                  style={{ padding: "8px 12px", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #1a1a1a" }}
                  onMouseEnter={e => (e.currentTarget.style.background = "#1a1a1a")}
                  onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                >
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 600, fontSize: "0.82rem" }}>{stock}</span>
                  <span className="mono" style={{ fontSize: "0.74rem", color: "#888" }}>₹{currentPrices[stock].toFixed(2)}</span>
                </div>
              )) : (
                <div style={{ padding: "10px 12px" }}>
                  <span className="label" style={{ color: "#444" }}>No matching stocks in universe</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* QTY */}
        <div>
          <div className="label" style={{ marginBottom: 4 }}>QTY</div>
          <input type="text" inputMode="numeric" value={qty}
            onChange={e => setQty(e.target.value.replace(/\D/g, ""))}
            placeholder="10" style={inp}
            onFocus={e => (e.currentTarget.style.borderColor = "#ff4500")}
            onBlur={e => (e.currentTarget.style.borderColor = "#2a2a2a")} />
        </div>

        {/* Avg buy price */}
        <div>
          <div className="label" style={{ marginBottom: 4 }}>AVG BUY PRICE</div>
          <input type="text" inputMode="decimal" value={avgPrice}
            onChange={e => setAvgPrice(e.target.value.replace(/[^0-9.]/g, ""))}
            placeholder="1600.00" style={inp}
            onFocus={e => (e.currentTarget.style.borderColor = "#ff4500")}
            onBlur={e => (e.currentTarget.style.borderColor = "#2a2a2a")} />
        </div>

        {/* Live price — readonly auto-fill */}
        <div>
          <div className="label" style={{ marginBottom: 4 }}>LIVE PRICE</div>
          <div style={{ ...inp, color: livePrice != null ? "#fff" : "#333", borderColor: "#1a1a1a", display: "flex", alignItems: "center" }}>
            {livePrice != null ? `₹${livePrice.toFixed(2)}` : "—"}
          </div>
        </div>
      </div>

      {/* Row 2: P&L preview + action buttons */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <div style={{ flex: 1, background: "#111", border: "1px solid #1a1a1a", padding: "9px 14px", display: "flex", alignItems: "center", gap: 14, minWidth: 180, minHeight: 36 }}>
          {pnl != null ? (
            <>
              <span className="mono" style={{ fontSize: "0.82rem", fontWeight: 700, color: pnlColor }}>
                {pnl >= 0 ? "+" : "−"}₹{Math.abs(pnl).toFixed(0)}
              </span>
              <span className="mono" style={{ fontSize: "0.78rem", color: pnlColor }}>
                ({pnlPct! >= 0 ? "+" : ""}{pnlPct!.toFixed(2)}%)
              </span>
              <span className="label" style={{ color: "#444", fontSize: "0.58rem" }}>ESTIMATED P&L</span>
            </>
          ) : livePrice != null ? (
            <span className="label" style={{ color: "#444" }}>enter qty & avg price to preview P&L</span>
          ) : (
            <span className="label" style={{ color: "#2a2a2a" }}>search and select a symbol above</span>
          )}
        </div>
        <button onClick={submit} disabled={!isValid}
          style={{ background: isValid ? "#ff4500" : "#161616", border: `1px solid ${isValid ? "#ff4500" : "#2a2a2a"}`, color: isValid ? "#fff" : "#444", fontFamily: "'JetBrains Mono', monospace", fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.1em", padding: "9px 20px", cursor: isValid ? "pointer" : "not-allowed", whiteSpace: "nowrap" }}>
          ADD POSITION
        </button>
        <button onClick={onCancel}
          style={{ background: "none", border: "1px solid #2a2a2a", color: "#555", fontFamily: "'JetBrains Mono', monospace", fontSize: "0.65rem", padding: "9px 14px", cursor: "pointer" }}>
          CANCEL
        </button>
      </div>
    </div>
  );
}

function TrackerPage({
  userPositions, setUserPositions, profitGoal, setProfitGoal,
  analysis, currentPrices, isMobile,
}: {
  userPositions: UserPosition[]; setUserPositions: (p: UserPosition[]) => void;
  profitGoal: ProfitGoal | null; setProfitGoal: (g: ProfitGoal | null) => void;
  analysis: Analysis; currentPrices: Record<string, number>; isMobile: boolean;
}) {
  const [showForm, setShowForm]   = useState(false);
  const [goalAmount, setGoalAmount] = useState(profitGoal?.targetAmount?.toString() ?? "");
  const [goalWeeks, setGoalWeeks]   = useState<4|12>(profitGoal?.weeks ?? 12);

  // Sync goalAmount with saved goal
  useEffect(() => { setGoalAmount(profitGoal?.targetAmount?.toString() ?? ""); }, [profitGoal]);

  const addPosition = (pos: UserPosition) => {
    const next = [...userPositions.filter(p => p.symbol !== pos.symbol), pos];
    setUserPositions(next);
    localStorage.setItem("user_positions", JSON.stringify(next));
    setShowForm(false);
  };

  const removePosition = (symbol: string) => {
    const next = userPositions.filter(p => p.symbol !== symbol);
    setUserPositions(next);
    localStorage.setItem("user_positions", JSON.stringify(next));
  };

  const saveGoal = () => {
    const amt = parseInt(goalAmount, 10);
    if (isNaN(amt) || amt <= 0) return;
    const goal: ProfitGoal = { targetAmount: amt, weeks: goalWeeks };
    setProfitGoal(goal);
    localStorage.setItem("profit_goal", JSON.stringify(goal));
  };

  const clearGoal = () => {
    setProfitGoal(null);
    setGoalAmount("");
    localStorage.removeItem("profit_goal");
  };

  // P&L calculations
  const totalInvested = userPositions.reduce((s, p) => s + p.avgPrice * p.qty, 0);
  const currentValue  = userPositions.reduce((s, p) => s + (currentPrices[p.symbol] ?? p.avgPrice) * p.qty, 0);
  const totalPnl      = currentValue - totalInvested;
  const totalPnlPct   = totalInvested > 0 ? (totalPnl / totalInvested) * 100 : 0;
  const goalProgress  = profitGoal && profitGoal.targetAmount > 0 ? Math.min(100, (totalPnl / profitGoal.targetAmount) * 100) : 0;
  const reqReturnPct  = profitGoal && totalInvested > 0 ? (profitGoal.targetAmount / totalInvested) * 100 : null;

  const advice = generateAdvice(userPositions, profitGoal, analysis, currentPrices);

  const inputStyle: React.CSSProperties = { background: "#111", border: "1px solid #2a2a2a", color: "#fff", fontFamily: "'JetBrains Mono', monospace", fontSize: "0.9rem", padding: "10px 12px", outline: "none", boxSizing: "border-box" };
  const focus = (e: React.FocusEvent<HTMLInputElement>) => { e.currentTarget.style.borderColor = "#ff4500"; };
  const blur  = (e: React.FocusEvent<HTMLInputElement>) => { e.currentTarget.style.borderColor = "#2a2a2a"; };
  const pad = isMobile ? "16px" : "28px 32px";

  return (
    <div className="fade-up">
      {/* Summary stats */}
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr 1fr" : "1fr 1fr 1fr 1fr", borderBottom: "1px solid #1a1a1a" }}>
        <div style={{ borderRight: "1px solid #1a1a1a", borderBottom: isMobile ? "1px solid #1a1a1a" : "none" }}>
          <StatCard label="INVESTED" value={totalInvested > 0 ? fmtINR(totalInvested) : "—"} sub={`${userPositions.length} positions`} />
        </div>
        <div style={{ borderBottom: isMobile ? "1px solid #1a1a1a" : "none" }}>
          <StatCard label="CURRENT VALUE" value={totalInvested > 0 ? fmtINR(currentValue) : "—"} />
        </div>
        <div style={{ borderRight: "1px solid #1a1a1a" }}>
          <StatCard
            label="UNREALISED P&L"
            value={totalInvested > 0 ? `${totalPnl >= 0 ? "+" : "−"}${fmtINR(Math.abs(totalPnl))}` : "—"}
            color={totalPnl >= 0 ? "#22c55e" : "#ef4444"}
          />
        </div>
        <div>
          <StatCard
            label="RETURN"
            value={totalInvested > 0 ? `${totalPnlPct >= 0 ? "+" : ""}${totalPnlPct.toFixed(2)}%` : "—"}
            color={totalPnlPct >= 0 ? "#22c55e" : "#ef4444"}
          />
        </div>
      </div>

      {/* Positions section */}
      <div style={{ borderBottom: "1px solid #1a1a1a" }}>
        <div style={{ padding: isMobile ? "14px 16px 10px" : "20px 32px 14px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div className="label" style={{ color: "#555" }}>MY POSITIONS</div>
          <button onClick={() => setShowForm(v => !v)}
            style={{ background: showForm ? "#111" : "#ff4500", border: `1px solid ${showForm ? "#2a2a2a" : "#ff4500"}`, color: "#fff", fontFamily: "'JetBrains Mono', monospace", fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.1em", padding: "7px 16px", cursor: "pointer" }}>
            {showForm ? "CANCEL" : "+ ADD POSITION"}
          </button>
        </div>

        {showForm && <AddPositionForm onAdd={addPosition} onCancel={() => setShowForm(false)} isMobile={isMobile} currentPrices={currentPrices} />}

        {/* Table header (desktop) */}
        {!isMobile && userPositions.length > 0 && (
          <div style={{ display: "grid", gridTemplateColumns: "120px 60px 110px 110px 110px 90px 28px", padding: "8px 24px", borderTop: "1px solid #1a1a1a", borderBottom: "1px solid #1a1a1a" }}>
            {["SYMBOL", "QTY", "AVG PRICE", "NOW", "P&L", "RETURN", ""].map(h => (
              <div key={h} className="label" style={{ fontSize: "0.6rem" }}>{h}</div>
            ))}
          </div>
        )}

        {userPositions.map(pos => {
          const cur = currentPrices[pos.symbol];
          const pnl = cur !== undefined ? (cur - pos.avgPrice) * pos.qty : null;
          const pct = cur !== undefined ? ((cur - pos.avgPrice) / pos.avgPrice) * 100 : null;
          const pick = analysis.top_picks.find(p => p.symbol.replace(".NS","") === pos.symbol);

          if (isMobile) return (
            <div key={pos.symbol} style={{ padding: "12px 16px", borderBottom: "1px solid #111", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 3 }}>
                  <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>{pos.symbol}</span>
                  {pick && <span style={{ color: "#ff4500", fontSize: "0.55rem" }} className="label">TRACKED</span>}
                </div>
                <span className="label">{pos.qty} × {fmtINR(pos.avgPrice)}</span>
              </div>
              <div style={{ textAlign: "right" }}>
                {pnl !== null ? (
                  <>
                    <div className="mono" style={{ color: pnl >= 0 ? "#22c55e" : "#ef4444", fontWeight: 600, fontSize: "0.88rem" }}>
                      {pnl >= 0 ? "+" : "−"}{fmtINR(Math.abs(pnl))}
                    </div>
                    <div className="mono" style={{ color: pnl >= 0 ? "#22c55e" : "#ef4444", fontSize: "0.7rem" }}>
                      {pct! >= 0 ? "+" : ""}{pct!.toFixed(2)}%
                    </div>
                  </>
                ) : (
                  <span className="label" style={{ color: "#444" }}>price N/A</span>
                )}
              </div>
              <button onClick={() => removePosition(pos.symbol)} style={{ background: "none", border: "none", color: "#333", cursor: "pointer", fontSize: "1.1rem", marginLeft: 10, padding: 0 }}>×</button>
            </div>
          );

          return (
            <div key={pos.symbol} className="row-hover" style={{ display: "grid", gridTemplateColumns: "120px 60px 110px 110px 110px 90px 28px", padding: "12px 24px", borderBottom: "1px solid #111", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontWeight: 600, fontSize: "0.88rem" }}>{pos.symbol}</span>
                {pick && <span style={{ color: "#ff4500", fontSize: "0.55rem" }}>⚡</span>}
              </div>
              <div className="mono" style={{ fontSize: "0.8rem", color: "#888" }}>{pos.qty}</div>
              <div className="mono" style={{ fontSize: "0.8rem", color: "#666" }}>{fmtINR(pos.avgPrice)}</div>
              <div className="mono" style={{ fontSize: "0.8rem", color: "#fff" }}>{cur !== undefined ? fmtINR(cur) : "—"}</div>
              <div className="mono" style={{ fontSize: "0.8rem", color: pnl === null ? "#444" : pnl >= 0 ? "#22c55e" : "#ef4444" }}>
                {pnl !== null ? `${pnl >= 0 ? "+" : "−"}${fmtINR(Math.abs(pnl))}` : "—"}
              </div>
              <div className="mono" style={{ fontSize: "0.8rem", color: pct === null ? "#444" : pct >= 0 ? "#22c55e" : "#ef4444" }}>
                {pct !== null ? `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%` : "—"}
              </div>
              <button onClick={() => removePosition(pos.symbol)} style={{ background: "none", border: "none", color: "#333", cursor: "pointer", fontSize: "1rem", padding: 0 }}>×</button>
            </div>
          );
        })}

        {userPositions.length === 0 && !showForm && (
          <div style={{ padding: isMobile ? "36px 16px" : "48px 32px", textAlign: "center" }}>
            <div className="label" style={{ color: "#333", marginBottom: 6 }}>NO POSITIONS ADDED</div>
            <div className="mono" style={{ color: "#222", fontSize: "0.72rem" }}>Tap "+ ADD POSITION" to start tracking your live trades</div>
          </div>
        )}
      </div>

      {/* Profit Goal */}
      <div style={{ padding: pad, borderBottom: "1px solid #1a1a1a" }}>
        <div className="label" style={{ marginBottom: 16, color: "#555" }}>PROFIT GOAL</div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 20 }}>
          <div style={{ position: "relative" }}>
            <span className="mono" style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "#555", fontSize: "0.85rem" }}>₹</span>
            <input type="text" inputMode="numeric" value={goalAmount}
              onChange={e => setGoalAmount(e.target.value.replace(/\D/g,""))}
              placeholder="Target profit"
              style={{ ...inputStyle, paddingLeft: 26, width: isMobile ? 150 : 180 }}
              onFocus={focus} onBlur={blur}
            />
          </div>
          <div style={{ display: "flex" }}>
            {([4, 12] as const).map(w => (
              <button key={w} onClick={() => setGoalWeeks(w)} className="label"
                style={{ background: goalWeeks === w ? "#ff4500" : "#111", border: "1px solid #2a2a2a", borderLeft: w === 4 ? "1px solid #2a2a2a" : "none", color: goalWeeks === w ? "#fff" : "#444", padding: "10px 16px", cursor: "pointer" }}>
                {w}W
              </button>
            ))}
          </div>
          <button onClick={saveGoal} style={{ background: "#ff4500", border: "none", color: "#fff", fontFamily: "'JetBrains Mono', monospace", fontSize: "0.7rem", fontWeight: 700, letterSpacing: "0.1em", padding: "10px 20px", cursor: "pointer" }}>
            SET GOAL
          </button>
          {profitGoal && (
            <button onClick={clearGoal} className="label" style={{ background: "none", border: "1px solid #2a2a2a", color: "#444", padding: "10px 14px", cursor: "pointer" }}>
              CLEAR
            </button>
          )}
        </div>

        {profitGoal && totalInvested > 0 && (
          <div style={{ border: "1px solid #1a1a1a", padding: isMobile ? "14px" : "20px 24px", background: "#0d0d0d" }}>
            <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 16, marginBottom: 14 }}>
              <div>
                <div className="label" style={{ color: "#555", marginBottom: 4 }}>TARGET</div>
                <div className="mono" style={{ fontSize: isMobile ? "1.1rem" : "1.4rem", fontWeight: 700, color: "#ff4500" }}>
                  +{fmtINR(profitGoal.targetAmount)} in {profitGoal.weeks}W
                </div>
              </div>
              <div>
                <div className="label" style={{ color: "#555", marginBottom: 4 }}>REQUIRED RETURN</div>
                <div className="mono" style={{ fontSize: "1.1rem", color: "#fff" }}>{reqReturnPct?.toFixed(1)}%</div>
              </div>
              <div>
                <div className="label" style={{ color: "#555", marginBottom: 4 }}>CURRENTLY AT</div>
                <div className="mono" style={{ fontSize: "1.1rem", color: totalPnlPct >= 0 ? "#22c55e" : "#ef4444" }}>
                  {totalPnlPct >= 0 ? "+" : ""}{totalPnlPct.toFixed(2)}%
                </div>
              </div>
            </div>
            <div style={{ background: "#111", height: 3, marginBottom: 8 }}>
              <div style={{ width: `${Math.max(0, Math.min(100, goalProgress))}%`, height: "100%", background: goalProgress >= 100 ? "#22c55e" : "#ff4500", transition: "width 1s ease" }} />
            </div>
            <div className="label" style={{ color: "#444" }}>
              {goalProgress >= 100
                ? "🎯 GOAL ACHIEVED"
                : `${Math.max(0, goalProgress).toFixed(0)}% of goal — ${fmtINR(Math.max(0, profitGoal.targetAmount - totalPnl))} remaining`}
            </div>
          </div>
        )}
      </div>

      {/* Advice */}
      <div style={{ padding: pad }}>
        <div className="label" style={{ marginBottom: 14, color: "#555" }}>SYSTEM ADVICE</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {advice.map((a, i) => (
            <div key={i} style={{
              display: "flex", gap: 10, alignItems: "flex-start", padding: "10px 14px",
              background: "#0d0d0d", border: "1px solid #1a1a1a",
              borderLeft: `2px solid ${a.type === "positive" ? "#22c55e" : a.type === "warning" ? "#ef4444" : a.type === "action" ? "#ff4500" : "#333"}`,
            }}>
              <span style={{ color: a.type === "positive" ? "#22c55e" : a.type === "warning" ? "#ef4444" : a.type === "action" ? "#ff4500" : "#555", fontSize: "0.65rem", marginTop: 2, flexShrink: 0 }}>
                {a.type === "positive" ? "▲" : a.type === "warning" ? "▼" : a.type === "action" ? "▸" : "—"}
              </span>
              <span style={{ fontSize: "0.78rem", color: "#888", lineHeight: 1.5 }}>{a.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── System Setup ──────────────────────────────────────────────────────────────
function SystemSetup({ capital, onChange, alloc }: { capital: number; onChange: (v: number) => void; alloc: PortfolioAllocation }) {
  const isMobile = useIsMobile();
  const [raw, setRaw] = useState(capital.toString());
  useEffect(() => { setRaw(capital.toString()); }, [capital]);
  const presets = [10000, 15000, 25000, 50000, 100000];

  const allPicks = [...alloc.breakout_picks, ...alloc.core_picks];
  const totalGain = allPicks.reduce((s, p) => s + p.max_gain, 0);
  const totalRisk = allPicks.reduce((s, p) => s + p.max_loss, 0);
  const ANNUAL_FACTOR = 4;
  const worst = -totalRisk;
  const realistic  = totalGain * 0.65 - totalRisk * 0.35;
  const optimistic = totalGain;
  const worstPct      = (worst / capital) * 100;
  const realisticPct  = (realistic / capital) * 100;
  const optimisticPct = (optimistic / capital) * 100;

  const scenarios = [
    { label: "WORST CASE",     tag: "All stops triggered, 0 targets hit", amount: worst,     pct: worstPct,      annualPct: worstPct * ANNUAL_FACTOR,     color: "#ef4444" },
    { label: "REALISTIC CASE", tag: "65% win rate — system historical avg", amount: realistic, pct: realisticPct,  annualPct: realisticPct * ANNUAL_FACTOR,  color: "#ff4500" },
    { label: "OPTIMISTIC CASE",tag: "All targets hit, zero stops triggered", amount: optimistic,pct: optimisticPct, annualPct: optimisticPct * ANNUAL_FACTOR, color: "#22c55e" },
  ];

  return (
    <div style={{ padding: isMobile ? "20px 16px" : "32px", maxWidth: isMobile ? "100%" : 680 }}>
      <div className="label" style={{ marginBottom: 8, color: "#555", letterSpacing: "0.18em" }}>SYSTEM SETUP</div>
      <div style={{ fontSize: isMobile ? "1.4rem" : "1.8rem", fontWeight: 700, marginBottom: 4 }}>Portfolio Configuration</div>
      <div className="label" style={{ color: "#ff4500", marginBottom: 28, letterSpacing: "0.12em", fontSize: isMobile ? "0.6rem" : "0.7rem" }}>
        LIVE CAPITAL DEPLOYMENT — REAL MONEY TRADING ENGINE
      </div>

      <div className="label" style={{ marginBottom: 10 }}>INVESTMENT CAPITAL</div>
      <div style={{ position: "relative", marginBottom: 14 }}>
        <span className="mono" style={{ position: "absolute", left: 16, top: "50%", transform: "translateY(-50%)", color: "#555" }}>₹</span>
        <input type="text" inputMode="numeric" pattern="[0-9]*" value={raw}
          onChange={e => {
            const d = e.target.value.replace(/\D/g, "");
            setRaw(d);
            const v = parseInt(d, 10);
            if (!isNaN(v) && v >= 1000) onChange(v);
          }}
          style={{ width: "100%", background: "#111", border: "1px solid #2a2a2a", color: "#fff", fontFamily: "'JetBrains Mono', monospace", fontSize: "1.1rem", padding: "12px 16px 12px 32px", outline: "none", boxSizing: "border-box" }}
          onFocus={e => { (e.currentTarget as HTMLInputElement).style.borderColor = "#ff4500"; }}
          onBlur={e => { (e.currentTarget as HTMLInputElement).style.borderColor = "#2a2a2a"; }}
        />
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 36 }}>
        {presets.map(p => (
          <button key={p} onClick={() => { setRaw(p.toString()); onChange(p); }} className="label mono"
            style={{ background: capital === p ? "#ff4500" : "#111", border: `1px solid ${capital === p ? "#ff4500" : "#2a2a2a"}`, color: capital === p ? "#fff" : "#555", padding: isMobile ? "7px 10px" : "8px 14px", cursor: "pointer", fontFamily: "'JetBrains Mono', monospace", fontSize: isMobile ? "0.65rem" : "0.7rem" }}>
            ₹{p.toLocaleString("en-IN")}
          </button>
        ))}
      </div>

      <div className="label" style={{ marginBottom: 14, color: "#555" }}>RETURN SCENARIOS — 3-MONTH CYCLE</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2, marginBottom: 36 }}>
        {scenarios.map(s => {
          const barW = Math.abs(optimisticPct) > 0 ? (Math.abs(s.pct) / Math.abs(optimisticPct)) * 100 : 0;
          return (
            <div key={s.label} style={{ border: "1px solid #1a1a1a", padding: isMobile ? "14px 16px" : "20px 24px", background: "#0d0d0d" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                <div>
                  <div className="label" style={{ color: s.color, marginBottom: 4, letterSpacing: "0.12em", fontSize: isMobile ? "0.62rem" : "0.7rem" }}>{s.label}</div>
                  <div className="label" style={{ color: "#444", fontSize: isMobile ? "0.58rem" : "0.62rem" }}>{s.tag}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className="mono" style={{ fontSize: isMobile ? "1.1rem" : "1.5rem", fontWeight: 700, color: s.color, lineHeight: 1 }}>
                    {s.amount >= 0 ? "+" : "−"}{fmtINR(Math.abs(s.amount))}
                  </div>
                  <div className="mono" style={{ fontSize: "0.75rem", color: "#555", marginTop: 3 }}>
                    {s.pct >= 0 ? "+" : ""}{s.pct.toFixed(1)}% this cycle
                  </div>
                </div>
              </div>
              <div style={{ background: "#111", height: 2, marginBottom: 12 }}>
                <div style={{ width: `${barW}%`, height: "100%", background: s.color, transition: "width 1s ease" }} />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span className="label" style={{ color: "#333", fontSize: isMobile ? "0.55rem" : "0.62rem" }}>ANNUALISED (4 CYCLES / YR)</span>
                <span className="mono" style={{ fontSize: "0.88rem", fontWeight: 600, color: s.annualPct >= 0 ? s.color : "#ef4444" }}>
                  {s.annualPct >= 0 ? "+" : ""}{s.annualPct.toFixed(1)}% p.a.
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="label" style={{ marginBottom: 14, color: "#555" }}>ALLOCATION STRATEGY</div>
      {[
        { l: "Core Long-Term", v: `${Math.round((1 - (alloc.breakout_budget > 0 ? alloc.breakout_budget / alloc.total_capital : 0) - alloc.reserve / alloc.total_capital) * 100)}%`, desc: "High-conviction, 2–4 month holds" },
        { l: "Breakout Reserve", v: `${Math.round((alloc.breakout_budget / alloc.total_capital) * 100)}%`, desc: "Deployed on squeeze/pattern triggers" },
        { l: "Cash Reserve", v: `${Math.round((alloc.reserve / alloc.total_capital) * 100)}%`, desc: "Emergency rebalance buffer" },
      ].map(row => (
        <div key={row.l} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 0", borderBottom: "1px solid #1a1a1a" }}>
          <div>
            <div style={{ fontSize: "0.82rem", color: "#ccc", marginBottom: 2 }}>{row.l}</div>
            <div className="label" style={{ color: "#444" }}>{row.desc}</div>
          </div>
          <div className="mono" style={{ color: "#ff4500", fontSize: "1.1rem", fontWeight: 600 }}>{row.v}</div>
        </div>
      ))}
    </div>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function Dashboard() {
  const isMobile = useIsMobile();
  const [nav, setNav]         = useState<NavId>("overview");
  const [capital, setCapital] = useState(15000);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [alloc, setAlloc]     = useState<PortfolioAllocation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [chartWeeks, setChartWeeks]   = useState(12);
  const [startDate, setStartDate]     = useState<Date | null>(null);
  const [updateFlash, setUpdateFlash] = useState(false);
  const [userPositions, setUserPositions] = useState<UserPosition[]>([]);
  const [profitGoal, setProfitGoal]       = useState<ProfitGoal | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch("/data/analysis.json?t=" + Date.now());
      if (!r.ok) throw new Error("No data");
      const d: Analysis = await r.json();
      setAnalysis(d);
      const saved = typeof window !== "undefined" ? localStorage.getItem("portfolio_capital") : null;
      const cap = saved ? parseInt(saved) : 15000;
      setCapital(cap);
      const savedGoal = typeof window !== "undefined" ? localStorage.getItem("profit_goal") : null;
      const goal: ProfitGoal | null = savedGoal ? JSON.parse(savedGoal) : null;
      const goalPct = goal && cap > 0 ? (goal.targetAmount / cap) * 100 : undefined;
      setAlloc(allocateCapital(cap, d.top_picks, goalPct));
    } catch {
      setError("Run: python main.py → python push_to_webapp.py");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const saved = localStorage.getItem("portfolio_start_date");
    if (saved) setStartDate(new Date(saved));
    const pos = localStorage.getItem("user_positions");
    if (pos) setUserPositions(JSON.parse(pos));
    const goal = localStorage.getItem("profit_goal");
    if (goal) setProfitGoal(JSON.parse(goal));
  }, []);

  // Auto-poll every 5 min
  useEffect(() => {
    if (!analysis) return;
    const poll = setInterval(async () => {
      try {
        const r = await fetch("/data/analysis.json?t=" + Date.now());
        if (!r.ok) return;
        const d: Analysis = await r.json();
        if (d.generated_at !== analysis.generated_at) {
          setAnalysis(d);
          const goalPct = profitGoal && capital > 0 ? (profitGoal.targetAmount / capital) * 100 : undefined;
          setAlloc(allocateCapital(capital, d.top_picks, goalPct));
          setUpdateFlash(true);
          setTimeout(() => setUpdateFlash(false), 4000);
        }
      } catch { }
    }, 5 * 60 * 1000);
    return () => clearInterval(poll);
  }, [analysis, capital, profitGoal]);

  const handleCapital = (v: number) => {
    setCapital(v);
    localStorage.setItem("portfolio_capital", v.toString());
    if (analysis) {
      const goalPct = profitGoal && v > 0 ? (profitGoal.targetAmount / v) * 100 : undefined;
      setAlloc(allocateCapital(v, analysis.top_picks, goalPct));
    }
  };

  const handleGoal = (goal: ProfitGoal | null) => {
    setProfitGoal(goal);
    if (goal) {
      localStorage.setItem("profit_goal", JSON.stringify(goal));
      if (analysis) {
        const goalPct = capital > 0 ? (goal.targetAmount / capital) * 100 : undefined;
        setAlloc(allocateCapital(capital, analysis.top_picks, goalPct));
      }
    } else {
      localStorage.removeItem("profit_goal");
      if (analysis) setAlloc(allocateCapital(capital, analysis.top_picks));
    }
  };

  const startCycle = () => {
    const now = new Date();
    localStorage.setItem("portfolio_start_date", now.toISOString());
    setStartDate(now);
  };
  const resetCycle = () => {
    localStorage.removeItem("portfolio_start_date");
    setStartDate(null);
  };

  const currentWeek = startDate
    ? Math.min(12, Math.floor((Date.now() - startDate.getTime()) / (7*24*60*60*1000)) + 1) : null;
  const cycleDate = (week: number) => {
    if (!startDate) return null;
    return new Date(startDate.getTime() + (week-1)*7*24*60*60*1000).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  };

  const navLabel = NAV_ITEMS.find(n => n.id === nav)?.label ?? "OVERVIEW";
  const allPicks = alloc ? [...alloc.breakout_picks, ...alloc.core_picks] : [];

  if (loading) return (
    <div style={{ height: "100dvh", display: "flex", alignItems: "center", justifyContent: "center", background: "#0a0a0a", flexDirection: "column", gap: 16 }}>
      <div style={{ width: 40, height: 40, border: "2px solid #1e1e1e", borderTopColor: "#ff4500", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
      <div className="label" style={{ color: "#444" }}>LOADING MARKET DATA</div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );

  if (error || !analysis || !alloc) return (
    <div style={{ height: "100dvh", display: "flex", alignItems: "center", justifyContent: "center", background: "#0a0a0a", flexDirection: "column", gap: 20, padding: "0 24px" }}>
      <div className="label" style={{ color: "#ff4500", fontSize: "0.9rem" }}>⚠ NO DATA FEED</div>
      <div className="mono" style={{ background: "#111", border: "1px solid #1e1e1e", padding: 20, color: "#555", fontSize: "0.78rem", lineHeight: 1.8, maxWidth: "100%" }}>
        <span style={{ color: "#ff4500" }}>$</span> python main.py<br />
        <span style={{ color: "#ff4500" }}>$</span> python push_to_webapp.py
      </div>
      <button onClick={load} className="label" style={{ background: "#ff4500", color: "#fff", border: "none", padding: "10px 24px", cursor: "pointer", letterSpacing: "0.12em" }}>RETRY</button>
    </div>
  );

  const regime    = analysis.regime;
  const fii       = analysis.market_data.fii_dii;
  const totalGain = allPicks.reduce((s, p) => s + p.max_gain, 0);
  const totalRisk = allPicks.reduce((s, p) => s + p.max_loss, 0);
  const gainPct   = ((totalGain / capital) * 100).toFixed(1);
  const rr        = (totalGain / Math.max(totalRisk, 1)).toFixed(2);

  // Current prices with top_picks fallback
  const currentPrices: Record<string, number> = { ...(analysis.current_prices ?? {}) };
  analysis.top_picks.forEach(p => {
    const sym = p.symbol.replace(".NS", "");
    if (!currentPrices[sym]) currentPrices[sym] = p.price;
  });

  // Dynamic roadmap
  const dynamicRoadmap = generateDynamicRoadmap(alloc, userPositions, currentPrices, analysis, profitGoal, currentWeek);

  return (
    <div style={{ display: "flex", height: "100dvh", background: "#0a0a0a", overflow: "hidden" }}>
      <Sidebar active={nav} setActive={setNav} />

      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>
        <TopBar section={navLabel} hasData={!!analysis} generatedAt={analysis?.generated_at ?? null} updateFlash={updateFlash} />

        <div style={{ flex: 1, overflowY: "auto", background: "#0a0a0a", paddingBottom: isMobile ? 58 : 0 }}>

          {/* ── OVERVIEW ── */}
          {nav === "overview" && (
            <div className="fade-up">
              <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr 1fr" : "1fr 1fr 1fr 1fr", borderBottom: "1px solid #1a1a1a" }}>
                <div style={{ borderRight: "1px solid #1a1a1a", borderBottom: isMobile ? "1px solid #1a1a1a" : "none" }}>
                  <StatCard label="TOTAL CAPITAL" value={fmtINR(capital)} sub={`${allPicks.length} positions`} delta={{ value: `${alloc.breakout_picks.length} breakouts`, positive: alloc.breakout_picks.length > 0 }} />
                </div>
                <div style={{ borderBottom: isMobile ? "1px solid #1a1a1a" : "none" }}>
                  <StatCard label="DEPLOYED" value={fmtINR(alloc.deployed)} sub={`${Math.round((alloc.deployed/capital)*100)}% alloc`} delta={{ value: `${fmtINR(alloc.cash)} reserve`, positive: true }} />
                </div>
                <div style={{ borderRight: "1px solid #1a1a1a" }}>
                  <StatCard label="EDGE / GAIN" value={`${gainPct}%`} sub={`R:R = ${rr}x`} inverted delta={{ value: `+${fmtINR(totalGain)}`, positive: true }} />
                </div>
                <div>
                  <StatCard label="REGIME" value={regime.regime.replace("_", " ")} sub={`${regime.confidence_pct}% conf`} delta={{ value: `ADX ${regime.adx?.toFixed(1)}`, positive: regime.regime.includes("BULL") }} />
                </div>
              </div>

              <div style={{ padding: isMobile ? "20px 16px 16px" : "36px 32px 24px", borderBottom: "1px solid #1a1a1a" }}>
                <div style={{ display: "flex", flexDirection: isMobile ? "column" : "row", justifyContent: "space-between", alignItems: "flex-start", marginBottom: isMobile ? 14 : 24, gap: isMobile ? 10 : 0 }}>
                  <div>
                    <div style={{ fontSize: isMobile ? "1.4rem" : "2.4rem", fontWeight: 700, lineHeight: 1, letterSpacing: "-0.02em" }}>
                      PORTFOLIO{" "}
                      <span className="serif" style={{ fontSize: isMobile ? "1.2rem" : "2.2rem", fontWeight: 400, color: "#888" }}>trajectory</span>
                    </div>
                    <div className="label" style={{ marginTop: 6, color: "#444", fontSize: isMobile ? "0.58rem" : "0.65rem" }}>
                      {userPositions.length > 0 ? `ACTUAL + PROJECTED — ${userPositions.length} LIVE POSITIONS` : `12-WEEK PROJECTION — ${analysis.total_analyzed} STOCKS ANALYZED`}
                    </div>
                  </div>
                  <div style={{ display: "flex" }}>
                    {[4, 8, 12].map(w => (
                      <button key={w} onClick={() => setChartWeeks(w)} className="label mono"
                        style={{ background: chartWeeks === w ? "#ff4500" : "transparent", border: "1px solid #1e1e1e", borderLeft: w === 4 ? "1px solid #1e1e1e" : "none", color: chartWeeks === w ? "#fff" : "#444", padding: isMobile ? "6px 12px" : "8px 16px", cursor: "pointer", fontFamily: "'JetBrains Mono', monospace", fontSize: isMobile ? "0.65rem" : "0.7rem" }}>
                        {w}W
                      </button>
                    ))}
                  </div>
                </div>
                <div style={{ height: isMobile ? 180 : 260 }}>
                  <TrajectoryChart alloc={alloc} weeks={chartWeeks} userPositions={userPositions} currentPrices={currentPrices} topPicks={analysis.top_picks} regime={regime} />
                </div>
              </div>

              <div style={{ display: "flex", padding: isMobile ? "12px 16px" : "16px 32px", gap: isMobile ? 20 : 40, borderBottom: "1px solid #1a1a1a", overflowX: "auto" }}>
                {[
                  { l: "NIFTY 50", v: regime.nifty_close?.toFixed(0) ?? "—", ok: true },
                  { l: "INDIA VIX", v: regime.india_vix?.toFixed(1) ?? "—", ok: (regime.india_vix ?? 99) < 20 },
                  { l: "FII FLOW", v: fii.fii_net_cr != null ? `${sign(fii.fii_net_cr)}${fmtINR(Math.abs(fii.fii_net_cr))} Cr` : "N/A", ok: (fii.fii_net_cr ?? 0) >= 0 },
                  { l: "1M RETURN", v: `${sign(regime.ret_1m_pct)}${Math.abs(regime.ret_1m_pct).toFixed(2)}%`, ok: regime.ret_1m_pct >= 0 },
                  { l: "3M RETURN", v: `${sign(regime.ret_3m_pct)}${Math.abs(regime.ret_3m_pct).toFixed(2)}%`, ok: regime.ret_3m_pct >= 0 },
                  { l: "NIFTY RSI", v: regime.rsi?.toFixed(1) ?? "—", ok: regime.rsi < 70 },
                  { l: "MACD", v: regime.macd_bullish ? "BULLISH" : "BEARISH", ok: regime.macd_bullish },
                ].map(s => (
                  <div key={s.l} style={{ flexShrink: 0 }}>
                    <div className="label" style={{ marginBottom: 3, fontSize: isMobile ? "0.58rem" : "0.65rem" }}>{s.l}</div>
                    <div className="mono" style={{ fontSize: isMobile ? "0.75rem" : "0.82rem", fontWeight: 600, color: s.ok ? "#fff" : "#666" }}>{s.v}</div>
                  </div>
                ))}
              </div>

              <div>
                {!isMobile && <DesktopTableHeader />}
                {allPicks.slice(0, 5).map((pick, i) => (
                  <PositionRow key={pick.symbol} pick={pick} rank={i+1}
                    onExpand={() => setExpandedRow(expandedRow === pick.symbol ? null : pick.symbol)}
                    expanded={expandedRow === pick.symbol} />
                ))}
              </div>
            </div>
          )}

          {/* ── POSITIONS ── */}
          {nav === "positions" && (
            <div className="fade-up">
              <div style={{ padding: isMobile ? "16px 16px 12px" : "24px 32px 16px", borderBottom: "1px solid #1a1a1a" }}>
                <div style={{ fontSize: isMobile ? "1.3rem" : "1.6rem", fontWeight: 700, marginBottom: 4 }}>
                  CORE <span className="serif" style={{ color: "#888", fontWeight: 400 }}>positions</span>
                </div>
                <div className="label" style={{ color: "#444" }}>{fmtINR(alloc.core_budget)} ALLOCATED — LONG-TERM HOLD 2–4 MONTHS</div>
              </div>
              {!isMobile && <DesktopTableHeader />}
              {alloc.core_picks.map((pick, i) => (
                <PositionRow key={pick.symbol} pick={pick} rank={i+1}
                  onExpand={() => setExpandedRow(expandedRow === pick.symbol ? null : pick.symbol)}
                  expanded={expandedRow === pick.symbol} />
              ))}
            </div>
          )}

          {/* ── BREAKOUTS ── */}
          {nav === "breakouts" && (
            <div className="fade-up">
              <div style={{ padding: isMobile ? "16px 16px 12px" : "24px 32px 16px", borderBottom: "1px solid #1a1a1a" }}>
                <div style={{ fontSize: isMobile ? "1.3rem" : "1.6rem", fontWeight: 700, marginBottom: 4 }}>
                  BREAKOUT <span className="serif" style={{ color: "#ff4500", fontWeight: 400 }}>alerts</span>
                </div>
                <div className="label" style={{ color: "#444", fontSize: isMobile ? "0.6rem" : "0.65rem" }}>
                  {alloc.breakout_picks.length > 0 ? `⚡ ${fmtINR(alloc.breakout_budget)} RESERVED — ENTER WITHIN 2 SESSIONS` : "NO ACTIVE BREAKOUT SETUPS — MARKET IN CONSOLIDATION"}
                </div>
              </div>
              {alloc.breakout_picks.length > 0 ? (
                <>
                  {!isMobile && <DesktopTableHeader />}
                  {alloc.breakout_picks.map((pick, i) => (
                    <PositionRow key={pick.symbol} pick={pick} rank={i+1}
                      onExpand={() => setExpandedRow(expandedRow === pick.symbol ? null : pick.symbol)}
                      expanded={expandedRow === pick.symbol} />
                  ))}
                </>
              ) : (
                <div style={{ padding: isMobile ? "48px 16px" : "80px 32px", textAlign: "center" }}>
                  <div className="label" style={{ color: "#333", fontSize: "0.8rem", marginBottom: 8 }}>NO BREAKOUT TRIGGERS DETECTED</div>
                  <div className="mono" style={{ color: "#222", fontSize: "0.72rem" }}>Focus capital on core long-term positions</div>
                </div>
              )}
            </div>
          )}

          {/* ── TRACKER ── */}
          {nav === "tracker" && (
            <TrackerPage
              userPositions={userPositions}
              setUserPositions={setUserPositions}
              profitGoal={profitGoal}
              setProfitGoal={handleGoal}
              analysis={analysis}
              currentPrices={currentPrices}
              isMobile={isMobile}
            />
          )}

          {/* ── PERFORMANCE ── */}
          {nav === "performance" && (
            <div className="fade-up">
              <div style={{ padding: isMobile ? "16px" : "24px 32px 20px", borderBottom: "1px solid #1a1a1a", display: "flex", flexDirection: isMobile ? "column" : "row", justifyContent: "space-between", alignItems: "flex-start", gap: isMobile ? 14 : 0 }}>
                <div>
                  <div style={{ fontSize: isMobile ? "1.3rem" : "1.6rem", fontWeight: 700, marginBottom: 4 }}>
                    PORTFOLIO <span className="serif" style={{ color: "#888", fontWeight: 400 }}>performance</span>
                  </div>
                  <div className="label" style={{ color: "#444" }}>
                    {profitGoal ? `${profitGoal.weeks}-WEEK GOAL-DRIVEN ROADMAP` : "12-WEEK LIVE EXECUTION ROADMAP"}
                    {" — "}<span style={{ color: regime.regime.includes("BULL") ? "#ff4500" : regime.regime.includes("BEAR") ? "#ef4444" : "#555" }}>{regime.regime.replace("_"," ")}</span>
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", alignItems: isMobile ? "flex-start" : "flex-end", gap: 10 }}>
                  {startDate ? (
                    <>
                      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                        <span className="label" style={{ color: "#444" }}>STARTED <span className="mono" style={{ color: "#777" }}>{startDate.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}</span></span>
                        <div style={{ background: "#ff4500", padding: "5px 12px", fontFamily: "'JetBrains Mono', monospace", fontSize: "0.72rem", fontWeight: 700, color: "#fff", letterSpacing: "0.1em" }}>
                          WEEK {currentWeek} / {profitGoal?.weeks ?? 12}
                        </div>
                      </div>
                      <button onClick={resetCycle} className="label" style={{ background: "none", border: "1px solid #2a2a2a", color: "#444", padding: "6px 14px", cursor: "pointer" }}>RESET CYCLE</button>
                    </>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", alignItems: isMobile ? "flex-start" : "flex-end", gap: 6 }}>
                      <button onClick={startCycle} style={{ background: "#ff4500", border: "none", color: "#fff", fontFamily: "'JetBrains Mono', monospace", fontSize: "0.72rem", fontWeight: 700, letterSpacing: "0.12em", padding: "12px 24px", cursor: "pointer" }}>
                        START CYCLE — TODAY
                      </button>
                      <span className="label" style={{ color: "#333" }}>Locks week numbers to real calendar dates</span>
                    </div>
                  )}
                </div>
              </div>

              <div style={{ padding: isMobile ? "20px 16px" : "32px" }}>
                {dynamicRoadmap.map((event, i) => {
                  const isPast   = currentWeek !== null && event.week < currentWeek;
                  const isActive = currentWeek !== null && event.week === currentWeek;
                  const typeColors: Record<string, string> = { entry: "#ff4500", review: "#888", exit: "#ff4500", rebalance: "#555" };
                  const baseColor  = typeColors[event.type] ?? "#888";
                  const dotBorder  = isPast ? "#2a2a2a" : isActive ? "#ff4500" : "#333";
                  const labelColor = isPast ? "#333" : isActive ? "#ff4500" : baseColor;

                  return (
                    <div key={i} style={{ display: "flex", gap: isMobile ? 14 : 24, opacity: isPast ? 0.45 : 1, transition: "opacity 0.3s" }}>
                      <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                        <div style={{ width: 28, height: 28, border: `1px solid ${dotBorder}`, background: isActive ? "#ff4500" : "transparent", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                          {isPast
                            ? <span style={{ fontSize: "0.65rem", color: "#444" }}>✓</span>
                            : <span className="mono" style={{ fontSize: "0.6rem", color: isActive ? "#fff" : dotBorder }}>W{event.week}</span>}
                        </div>
                        {i < dynamicRoadmap.length - 1 && <div style={{ width: 1, height: 48, background: "#1a1a1a" }} />}
                      </div>
                      <div style={{ paddingBottom: i < dynamicRoadmap.length-1 ? 28 : 0, flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4, flexWrap: "wrap" }}>
                          <div className="label" style={{ color: labelColor, letterSpacing: "0.12em" }}>{event.label}</div>
                          {isActive && <span style={{ background: "#ff4500", color: "#fff", fontSize: "0.55rem", fontWeight: 700, letterSpacing: "0.1em", padding: "2px 7px", fontFamily: "'JetBrains Mono', monospace" }}>NOW</span>}
                          {cycleDate(event.week) && <span className="mono" style={{ fontSize: "0.62rem", color: isPast ? "#2a2a2a" : "#444" }}>{cycleDate(event.week)}</span>}
                          {!isMobile && event.stocks?.map(s => (
                            <span key={s} className="badge mono" style={{ borderColor: isPast ? "#1a1a1a" : "#2a2a2a", color: isPast ? "#2a2a2a" : "#555", fontSize: "0.6rem" }}>{s}</span>
                          ))}
                        </div>
                        <div style={{ fontSize: "0.75rem", color: isPast ? "#2a2a2a" : "#555", lineHeight: 1.6 }}>{event.description}</div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div style={{ margin: isMobile ? "0 16px 24px" : "0 32px 32px", display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr 1fr", border: "1px solid #1a1a1a" }}>
                {[
                  { l: "BEST CASE", v: `+${fmtINR(totalGain)}`, sub: `+${gainPct}%`, color: "#ff4500" },
                  { l: "WORST CASE", v: `−${fmtINR(totalRisk)}`, sub: `-${((totalRisk/capital)*100).toFixed(1)}%`, color: "#555" },
                  { l: "REWARD : RISK", v: `${rr}×`, sub: "target 3×+", color: "#888" },
                ].map((s, i) => (
                  <div key={s.l} style={{ padding: isMobile ? "16px" : "20px 24px", borderRight: !isMobile && i < 2 ? "1px solid #1a1a1a" : "none", borderBottom: isMobile && i < 2 ? "1px solid #1a1a1a" : "none" }}>
                    <div className="label" style={{ marginBottom: 6 }}>{s.l}</div>
                    <div className="mono" style={{ fontSize: isMobile ? "1.3rem" : "1.6rem", fontWeight: 600, color: s.color }}>{s.v}</div>
                    <div className="label" style={{ marginTop: 4, color: "#333" }}>{s.sub}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── ANALYTICS ── */}
          {nav === "analytics" && (
            <div className="fade-up">
              <div style={{ padding: isMobile ? "16px 16px 12px" : "24px 32px 16px", borderBottom: "1px solid #1a1a1a" }}>
                <div style={{ fontSize: isMobile ? "1.3rem" : "1.6rem", fontWeight: 700, marginBottom: 4 }}>
                  MARKET <span className="serif" style={{ color: "#888", fontWeight: 400 }}>analytics</span>
                </div>
                <div className="label" style={{ color: "#444" }}>REGIME ANALYSIS — {analysis.total_analyzed} UNIVERSE STOCKS</div>
              </div>
              <div style={{ padding: isMobile ? "16px" : "32px", display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 16 }}>
                <div style={{ border: "1px solid #1a1a1a", padding: isMobile ? 16 : 24 }}>
                  <div className="label" style={{ marginBottom: 14 }}>REGIME SIGNALS</div>
                  {[
                    { l: "Regime", v: regime.regime.replace("_"," "), ok: regime.regime.includes("BULL") },
                    { l: "Confidence", v: `${regime.confidence_pct}%`, ok: regime.confidence_pct >= 65 },
                    { l: "ADX", v: fmtDec(regime.adx ?? 0), ok: (regime.adx ?? 0) > 25 },
                    { l: "RSI", v: fmtDec(regime.rsi ?? 0), ok: regime.rsi > 45 && regime.rsi < 70 },
                    { l: "MACD", v: regime.macd_bullish ? "BULLISH" : "BEARISH", ok: regime.macd_bullish },
                    { l: "1M Return", v: `${regime.ret_1m_pct?.toFixed(2)}%`, ok: regime.ret_1m_pct >= 0 },
                    { l: "3M Return", v: `${regime.ret_3m_pct?.toFixed(2)}%`, ok: regime.ret_3m_pct >= 0 },
                  ].map(s => (
                    <div key={s.l} style={{ display: "flex", justifyContent: "space-between", padding: "9px 0", borderBottom: "1px solid #111" }}>
                      <span className="label">{s.l}</span>
                      <span className="mono" style={{ fontSize: "0.8rem", fontWeight: 600, color: s.ok ? "#fff" : "#555" }}>{s.v}</span>
                    </div>
                  ))}
                </div>
                <div style={{ border: "1px solid #1a1a1a", padding: isMobile ? 16 : 24 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 14 }}>
                    <div className="label">TOP PICKS — SCORE DISTRIBUTION</div>
                    <div style={{ display: "flex", gap: 12 }}>
                      <span className="label" style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <span style={{ width: 10, height: 2, background: "#ff4500", display: "inline-block" }} /> RULE
                      </span>
                      <span className="label" style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <span style={{ width: 10, height: 2, background: "#22c55e", display: "inline-block" }} /> ML
                      </span>
                    </div>
                  </div>
                  {analysis.top_picks.slice(0, 10).map(p => {
                    const sym     = p.symbol.replace(".NS","");
                    const rulePct = ((p.rule_score ?? p.total_score) / 150) * 100;
                    const mlPct   = p.ml_prob != null ? p.ml_prob * 100 : null;
                    return (
                      <div key={sym} style={{ marginBottom: 12 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 3 }}>
                          <span className="mono" style={{ width: 70, fontSize: "0.72rem", color: "#888", flexShrink: 0 }}>{sym}</span>
                          <div style={{ flex: 1, background: "#111", height: 2, position: "relative" }}>
                            <div style={{ width: `${rulePct}%`, height: "100%", background: rulePct >= 70 ? "#ff4500" : "#555", transition: "width 1s ease" }} />
                          </div>
                          <span className="mono" style={{ fontSize: "0.68rem", color: "#444", width: 46, flexShrink: 0 }}>{p.total_score}/150</span>
                        </div>
                        {mlPct != null && (
                          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <span style={{ width: 70, flexShrink: 0 }} />
                            <div style={{ flex: 1, background: "#111", height: 2 }}>
                              <div style={{ width: `${mlPct}%`, height: "100%", background: mlPct >= 70 ? "#22c55e" : mlPct >= 50 ? "#f59e0b" : "#ef4444", transition: "width 1s ease" }} />
                            </div>
                            <span className="mono" style={{ fontSize: "0.68rem", color: "#444", width: 46, flexShrink: 0 }}>{Math.round(mlPct)}% ML</span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* ── SYSTEM SETUP ── */}
          {nav === "system" && (
            <div className="fade-up">
              <SystemSetup capital={capital} onChange={handleCapital} alloc={alloc} />
            </div>
          )}

        </div>
      </div>

      {isMobile && <MobileTabBar active={nav} setActive={setNav} />}
    </div>
  );
}
