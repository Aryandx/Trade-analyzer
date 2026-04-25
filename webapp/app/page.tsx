"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { Analysis, AllocatedPick, PortfolioAllocation } from "@/lib/types";
import { allocateCapital } from "@/lib/allocator";

// ── Formatters ────────────────────────────────────────────────────────────────
const fmtINR = (n: number) =>
  "₹" + new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(Math.abs(n));
const fmtDec = (n: number) =>
  new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(n);
const sign = (n: number) => (n >= 0 ? "+" : "−");

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

// ── SVG Trajectory Chart ──────────────────────────────────────────────────────
function TrajectoryChart({
  alloc, weeks,
}: { alloc: PortfolioAllocation; weeks: number }) {
  const W = 900, H = 260, PAD = { t: 20, r: 20, b: 32, l: 60 };
  const cW = W - PAD.l - PAD.r;
  const cH = H - PAD.t - PAD.b;

  // Build weekly projected values — S-curve toward blended target
  const base = alloc.total_capital;
  const allPicks = [...alloc.breakout_picks, ...alloc.core_picks];
  const maxReturn = allPicks.reduce((s, p) => s + p.max_gain, 0);
  const conservativeReturn = maxReturn * 0.65; // realistic 65% of targets hit

  const points: number[] = Array.from({ length: weeks + 1 }, (_, w) => {
    const t = w / weeks;
    const smooth = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
    const noise = Math.sin(w * 1.7) * base * 0.004 + Math.cos(w * 2.9) * base * 0.003;
    return base + conservativeReturn * smooth + noise;
  });

  const minV = Math.min(...points) * 0.99;
  const maxV = Math.max(...points) * 1.01;

  const px = (i: number) => PAD.l + (i / weeks) * cW;
  const py = (v: number) => PAD.t + cH - ((v - minV) / (maxV - minV)) * cH;

  const linePts = points.map((v, i) => `${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(" ");
  const areaPts = `${px(0).toFixed(1)},${(PAD.t + cH).toFixed(1)} ${linePts} ${px(weeks).toFixed(1)},${(PAD.t + cH).toFixed(1)}`;

  const yLabels = [minV, (minV + maxV) / 2, maxV].map(v => ({
    v, y: py(v), label: fmtINR(v),
  }));

  const xLabels = [0, 3, 6, 9, 12].filter(w => w <= weeks).map(w => ({
    w, x: px(w), label: w === 0 ? "NOW" : `W${w}`,
  }));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" preserveAspectRatio="none" style={{ display: "block" }}>
      <defs>
        <linearGradient id="orange-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ff4500" stopOpacity="0.35" />
          <stop offset="60%" stopColor="#ff4500" stopOpacity="0.08" />
          <stop offset="100%" stopColor="#ff4500" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="line-grad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#ff4500" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#ff4500" stopOpacity="1" />
        </linearGradient>
      </defs>

      {/* Grid lines */}
      {yLabels.map(({ v, y }) => (
        <g key={v}>
          <line x1={PAD.l} y1={y} x2={W - PAD.r} y2={y}
            stroke="#1e1e1e" strokeWidth="1" strokeDasharray="4,6" />
          <text x={PAD.l - 8} y={y + 4} textAnchor="end"
            fill="#444" fontSize="10" fontFamily="'JetBrains Mono', monospace">
            {fmtINR(v)}
          </text>
        </g>
      ))}

      {/* Area fill */}
      <polygon points={areaPts} fill="url(#orange-grad)" />

      {/* Line */}
      <polyline points={linePts} fill="none"
        stroke="url(#line-grad)" strokeWidth="2" strokeLinejoin="round" />

      {/* End dot */}
      <circle cx={px(weeks)} cy={py(points[weeks])} r="5"
        fill="#0a0a0a" stroke="#ff4500" strokeWidth="2" />
      <circle cx={px(weeks)} cy={py(points[weeks])} r="2.5" fill="#ff4500" />

      {/* X axis labels */}
      {xLabels.map(({ w, x, label }) => (
        <text key={w} x={x} y={H - 6} textAnchor="middle"
          fill="#444" fontSize="10" fontFamily="'JetBrains Mono', monospace">
          {label}
        </text>
      ))}
    </svg>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────
const NAV_ITEMS = [
  { id: "overview",    label: "OVERVIEW",     icon: "▦" },
  { id: "positions",   label: "POSITIONS",    icon: "≡" },
  { id: "breakouts",   label: "BREAKOUTS",    icon: "⚡" },
  { id: "performance", label: "PERFORMANCE",  icon: "∿" },
  { id: "analytics",   label: "ANALYTICS",    icon: "◎" },
  { id: "system",      label: "SYSTEM SETUP", icon: "⚙" },
] as const;
type NavId = typeof NAV_ITEMS[number]["id"];

function Sidebar({
  active, setActive,
}: { active: NavId; setActive: (id: NavId) => void }) {
  return (
    <div style={{
      width: 240, background: "#0a0a0a",
      borderRight: "1px solid #1a1a1a",
      display: "flex", flexDirection: "column",
      height: "100vh", flexShrink: 0,
    }}>
      {/* Logo */}
      <div style={{ padding: "28px 24px 32px", borderBottom: "1px solid #1a1a1a" }}>
        <div className="label" style={{ color: "#ff4500", marginBottom: 2, letterSpacing: "0.18em" }}>
          PORTF.OS
        </div>
        <div className="label" style={{ color: "#333", letterSpacing: "0.12em" }}>
          / INTELLIGENCE
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: "20px 16px", display: "flex", flexDirection: "column", gap: 4 }}>
        {NAV_ITEMS.map(item => (
          <button key={item.id} onClick={() => setActive(item.id)}
            style={{
              background: "none", cursor: "pointer",
              textAlign: "left", padding: "11px 16px",
              display: "flex", alignItems: "center", gap: 12,
              ...(active === item.id
                ? { border: "1px solid #ff4500", color: "#fff" }
                : { border: "1px solid transparent", color: "#444" }),
            }}
            className="label"
            onMouseEnter={e => { if (active !== item.id) (e.currentTarget as HTMLElement).style.color = "#888"; }}
            onMouseLeave={e => { if (active !== item.id) (e.currentTarget as HTMLElement).style.color = "#444"; }}
          >
            <span style={{ fontSize: "0.75rem", color: active === item.id ? "#ff4500" : "inherit" }}>
              {item.icon}
            </span>
            <span style={{ letterSpacing: "0.14em" }}>{item.label}</span>
          </button>
        ))}
      </nav>

      {/* Bottom */}
      <div style={{ padding: "20px 24px", borderTop: "1px solid #1a1a1a" }}>
        <div className="label" style={{ color: "#2a2a2a", marginBottom: 6 }}>VERSION</div>
        <div className="mono" style={{ fontSize: "0.72rem", color: "#333" }}>v2.1 — NSE FEED</div>
      </div>
    </div>
  );
}

// ── Header bar ────────────────────────────────────────────────────────────────
function TopBar({
  section, hasData, generatedAt, updateFlash,
}: {
  section: string; hasData: boolean;
  generatedAt: string | null; updateFlash: boolean;
}) {
  const [ago, setAgo] = useState("");

  useEffect(() => {
    if (!generatedAt) return;
    const calc = () => {
      const diff = Math.floor((Date.now() - new Date(generatedAt).getTime()) / 60000);
      setAgo(diff < 1 ? "just now" : diff < 60 ? `${diff}m ago` : `${Math.floor(diff / 60)}h ago`);
    };
    calc();
    const id = setInterval(calc, 30000);
    return () => clearInterval(id);
  }, [generatedAt]);

  return (
    <div style={{
      height: 52, borderBottom: "1px solid #1a1a1a",
      display: "flex", alignItems: "center",
      padding: "0 32px", flexShrink: 0,
      background: updateFlash ? "#0f0a00" : "#0a0a0a",
      transition: "background 0.6s ease",
    }}>
      <span className="label" style={{ color: "#fff", letterSpacing: "0.18em", fontSize: "0.75rem" }}>
        {section}
      </span>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 28 }}>
        {generatedAt && (
          <span className="label" style={{
            color: updateFlash ? "#ff4500" : "#444",
            transition: "color 0.6s ease",
          }}>
            {updateFlash ? "⚡ DATA UPDATED" : `DATA: ${ago}`}
          </span>
        )}
        <span className="label" style={{ color: "#444" }}>
          GLOBAL SESSION: <LiveClock />
        </span>
        <span className="label" style={{ color: "#444", display: "flex", alignItems: "center", gap: 6 }}>
          SYSTEM STATUS:&nbsp;
          <span style={{ color: hasData ? "#22c55e" : "#ff4500" }}>
            {hasData ? "LIVE" : "OFFLINE"}
          </span>
          <span className={`status-dot ${hasData ? "status-dot-green" : ""}`} />
        </span>
      </div>
    </div>
  );
}

// ── Stat Card ─────────────────────────────────────────────────────────────────
function StatCard({
  label, value, sub, inverted = false, delta,
}: {
  label: string; value: string; sub?: string;
  inverted?: boolean; delta?: { value: string; positive: boolean };
}) {
  return (
    <div className={inverted ? "stat-card-inverted" : "stat-card"} style={{ flex: 1 }}>
      <div className="label" style={{ marginBottom: 12, color: inverted ? "#888" : "#555" }}>
        {label}
      </div>
      <div className="mono" style={{
        fontSize: "2.1rem", fontWeight: 600, lineHeight: 1,
        color: inverted ? "#0a0a0a" : "#fff",
        letterSpacing: "-0.02em",
      }}>
        {value}
      </div>
      {(sub || delta) && (
        <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 8 }}>
          {delta && (
            <span style={{
              background: inverted ? "#0a0a0a" : "#1e1e1e",
              color: delta.positive ? "#ff4500" : "#888",
              padding: "2px 8px", fontSize: "0.7rem",
              fontFamily: "'JetBrains Mono', monospace", fontWeight: 500,
            }}>
              ↗ {delta.value}
            </span>
          )}
          {sub && <span className="label" style={{ color: inverted ? "#999" : "#444" }}>{sub}</span>}
        </div>
      )}
    </div>
  );
}

// ── Position Row ──────────────────────────────────────────────────────────────
function PositionRow({ pick, rank, onExpand, expanded }:
  { pick: AllocatedPick; rank: number; onExpand: () => void; expanded: boolean }) {
  const sym = pick.symbol.replace(".NS", "");
  const isBreak = pick.allocation_type === "breakout";
  const f = pick.fundamentals;

  return (
    <>
      <div className="row-hover" onClick={onExpand} style={{
        display: "grid",
        gridTemplateColumns: "32px 100px 90px 80px 80px 80px 80px 80px 60px",
        gap: 0, padding: "14px 24px", cursor: "pointer",
        borderBottom: "1px solid #111",
        alignItems: "center",
      }}>
        <div className="mono" style={{ color: "#333", fontSize: "0.72rem" }}>#{rank}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {isBreak && <span style={{ color: "#ff4500", fontSize: "0.6rem" }}>⚡</span>}
          <span style={{ fontWeight: 600, fontSize: "0.88rem" }}>{sym}</span>
        </div>
        <div className="mono" style={{ fontSize: "0.8rem", color: "#888" }}>
          {fmtINR(pick.price)}
        </div>
        <div className="mono" style={{ color: "#ff4500", fontSize: "0.8rem" }}>
          +{pick.target_pct}%
        </div>
        <div className="mono" style={{ color: "#ef4444", fontSize: "0.8rem" }}>
          −{pick.stop_pct.toFixed(1)}%
        </div>
        <div className="mono" style={{ fontSize: "0.8rem", color: "#fff" }}>
          {fmtINR(pick.actual_invested)}
        </div>
        <div className="mono" style={{ color: "#22c55e", fontSize: "0.8rem" }}>
          +{fmtINR(pick.max_gain)}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
          {[pick.ema_aligned, pick.macd_bullish, pick.signals.rsi_bull_div].map((ok, i) => (
            <div key={i} style={{
              width: 6, height: 6, borderRadius: "50%",
              background: ok ? "#ff4500" : "#222",
            }} />
          ))}
        </div>
        <div className="mono" style={{
          fontSize: "0.72rem",
          color: pick.total_score >= 100 ? "#ff4500" : pick.total_score >= 80 ? "#888" : "#444",
        }}>
          {pick.total_score}/150
        </div>
      </div>

      {/* Expanded row */}
      {expanded && (
        <div style={{
          background: "#0d0d0d", borderBottom: "1px solid #1a1a1a",
          padding: "20px 24px",
        }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 24 }}>
            {/* Entry plan */}
            <div>
              <div className="label" style={{ marginBottom: 12 }}>ENTRY PLAN</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {[
                  { l: "Shares", v: `${pick.allocated_shares} × ${fmtINR(pick.price)}` },
                  { l: "Deploy", v: fmtINR(pick.actual_invested) },
                  { l: "Stop Loss", v: `${fmtINR(pick.stop_loss)} (−${pick.stop_pct.toFixed(1)}%)` },
                  { l: "Target", v: `${fmtINR(pick.target)} (+${pick.target_pct}%)` },
                  { l: "Max Gain", v: fmtINR(pick.max_gain) },
                  { l: "Max Loss", v: fmtINR(pick.max_loss) },
                ].map(r => (
                  <div key={r.l} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span className="label">{r.l}</span>
                    <span className="mono" style={{ fontSize: "0.78rem", color: "#ccc" }}>{r.v}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Fundamentals */}
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

            {/* Rationale */}
            <div>
              <div className="label" style={{ marginBottom: 12 }}>SIGNAL RATIONALE</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {pick.rationale.slice(0, 5).map((r, i) => (
                  <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                    <span style={{ color: "#ff4500", fontSize: "0.6rem", marginTop: 2 }}>▸</span>
                    <span style={{ fontSize: "0.72rem", color: "#666", lineHeight: 1.5 }}>{r}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ── System Setup (capital input) ──────────────────────────────────────────────
function SystemSetup({
  capital, onChange, alloc,
}: { capital: number; onChange: (v: number) => void; alloc: PortfolioAllocation }) {
  const [raw, setRaw] = useState(capital.toString());
  const presets = [10000, 15000, 25000, 50000, 100000];

  const allPicks = [...alloc.breakout_picks, ...alloc.core_picks];
  const totalGain = allPicks.reduce((s, p) => s + p.max_gain, 0);
  const totalRisk = allPicks.reduce((s, p) => s + p.max_loss, 0);

  // 3-month hold → annualise ×4
  const ANNUAL_FACTOR = 4;
  const worst     = -totalRisk;
  const realistic = totalGain * 0.65 - totalRisk * 0.35;
  const optimistic = totalGain;

  const worstPct      = (worst / capital) * 100;
  const realisticPct  = (realistic / capital) * 100;
  const optimisticPct = (optimistic / capital) * 100;

  const scenarios = [
    {
      label: "WORST CASE",
      tag: "All stops triggered, 0 targets hit",
      amount: worst,
      pct: worstPct,
      annualPct: worstPct * ANNUAL_FACTOR,
      color: "#ef4444",
      barColor: "#ef4444",
    },
    {
      label: "REALISTIC CASE",
      tag: "65% win rate — system historical avg",
      amount: realistic,
      pct: realisticPct,
      annualPct: realisticPct * ANNUAL_FACTOR,
      color: "#ff4500",
      barColor: "#ff4500",
    },
    {
      label: "OPTIMISTIC CASE",
      tag: "All targets hit, zero stops triggered",
      amount: optimistic,
      pct: optimisticPct,
      annualPct: optimisticPct * ANNUAL_FACTOR,
      color: "#22c55e",
      barColor: "#22c55e",
    },
  ];

  return (
    <div style={{ padding: "32px", maxWidth: 680 }}>
      <div className="label" style={{ marginBottom: 8, color: "#555", letterSpacing: "0.18em" }}>
        SYSTEM SETUP
      </div>
      <div style={{ fontSize: "1.8rem", fontWeight: 700, marginBottom: 4 }}>
        Portfolio Configuration
      </div>
      <div className="label" style={{ color: "#ff4500", marginBottom: 32, letterSpacing: "0.12em" }}>
        LIVE CAPITAL DEPLOYMENT — REAL MONEY TRADING ENGINE
      </div>

      <div className="label" style={{ marginBottom: 10 }}>INVESTMENT CAPITAL</div>
      <div style={{ position: "relative", marginBottom: 16 }}>
        <span className="mono" style={{
          position: "absolute", left: 16, top: "50%", transform: "translateY(-50%)", color: "#555",
        }}>₹</span>
        <input type="number" value={raw}
          onChange={e => {
            setRaw(e.target.value);
            const v = parseInt(e.target.value);
            if (!isNaN(v) && v >= 1000) onChange(v);
          }}
          style={{
            width: "100%", background: "#111", border: "1px solid #2a2a2a",
            color: "#fff", fontFamily: "'JetBrains Mono', monospace",
            fontSize: "1.2rem", padding: "14px 16px 14px 32px",
            outline: "none",
          }}
          onFocus={e => { (e.currentTarget as HTMLInputElement).style.borderColor = "#ff4500"; }}
          onBlur={e => { (e.currentTarget as HTMLInputElement).style.borderColor = "#2a2a2a"; }}
        />
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 40 }}>
        {presets.map(p => (
          <button key={p} onClick={() => { setRaw(p.toString()); onChange(p); }}
            className="label mono"
            style={{
              background: capital === p ? "#ff4500" : "#111",
              border: `1px solid ${capital === p ? "#ff4500" : "#2a2a2a"}`,
              color: capital === p ? "#fff" : "#555",
              padding: "8px 14px", cursor: "pointer",
              fontFamily: "'JetBrains Mono', monospace",
            }}>
            ₹{p.toLocaleString("en-IN")}
          </button>
        ))}
      </div>

      {/* Return scenarios */}
      <div className="label" style={{ marginBottom: 16, color: "#555" }}>RETURN SCENARIOS — 3-MONTH CYCLE</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2, marginBottom: 40 }}>
        {scenarios.map(s => {
          const absPct = Math.abs(s.pct);
          const maxPct = Math.abs(optimisticPct);
          const barW = maxPct > 0 ? (absPct / maxPct) * 100 : 0;
          return (
            <div key={s.label} style={{
              border: "1px solid #1a1a1a", padding: "20px 24px",
              background: "#0d0d0d",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
                <div>
                  <div className="label" style={{ color: s.color, marginBottom: 4, letterSpacing: "0.14em" }}>
                    {s.label}
                  </div>
                  <div className="label" style={{ color: "#444" }}>{s.tag}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className="mono" style={{ fontSize: "1.5rem", fontWeight: 700, color: s.color, lineHeight: 1 }}>
                    {s.amount >= 0 ? "+" : "−"}{fmtINR(Math.abs(s.amount))}
                  </div>
                  <div className="mono" style={{ fontSize: "0.8rem", color: "#555", marginTop: 4 }}>
                    {s.pct >= 0 ? "+" : ""}{s.pct.toFixed(1)}% this cycle
                  </div>
                </div>
              </div>

              {/* Bar */}
              <div style={{ background: "#111", height: 2, marginBottom: 14 }}>
                <div style={{
                  width: `${barW}%`, height: "100%",
                  background: s.barColor, transition: "width 1s ease",
                }} />
              </div>

              {/* Annual row */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="label" style={{ color: "#333" }}>ANNUALISED RETURN (4 CYCLES / YR)</span>
                <span className="mono" style={{
                  fontSize: "0.9rem", fontWeight: 600,
                  color: s.annualPct >= 0 ? s.color : "#ef4444",
                }}>
                  {s.annualPct >= 0 ? "+" : ""}{s.annualPct.toFixed(1)}% p.a.
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Allocation strategy */}
      <div className="label" style={{ marginBottom: 16, color: "#555" }}>ALLOCATION STRATEGY</div>
      {[
        { l: "Core Long-Term", v: "60%", desc: "High-conviction, 2–4 month holds" },
        { l: "Breakout Reserve", v: "30%", desc: "Deployed on squeeze/pattern triggers" },
        { l: "Cash Reserve", v: "10%", desc: "Emergency rebalance buffer" },
      ].map(row => (
        <div key={row.l} style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "12px 0", borderBottom: "1px solid #1a1a1a",
        }}>
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

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const [nav, setNav]           = useState<NavId>("overview");
  const [capital, setCapital]   = useState(15000);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [alloc, setAlloc]       = useState<PortfolioAllocation | null>(null);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [chartWeeks, setChartWeeks]   = useState(12);
  const [startDate, setStartDate]     = useState<Date | null>(null);
  const [updateFlash, setUpdateFlash] = useState(false);

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
      setAlloc(allocateCapital(cap, d.top_picks));
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
  }, []);

  // Auto-poll for new analysis data every 5 minutes
  useEffect(() => {
    if (!analysis) return;
    const poll = setInterval(async () => {
      try {
        const r = await fetch("/data/analysis.json?t=" + Date.now());
        if (!r.ok) return;
        const d: Analysis = await r.json();
        if (d.generated_at !== analysis.generated_at) {
          setAnalysis(d);
          setAlloc(prev => allocateCapital(prev?.total_capital ?? capital, d.top_picks));
          setUpdateFlash(true);
          setTimeout(() => setUpdateFlash(false), 4000);
        }
      } catch { /* silent — no connection change */ }
    }, 5 * 60 * 1000);
    return () => clearInterval(poll);
  }, [analysis, capital]);

  const handleCapital = (v: number) => {
    setCapital(v);
    localStorage.setItem("portfolio_capital", v.toString());
    if (analysis) setAlloc(allocateCapital(v, analysis.top_picks));
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
    ? Math.min(12, Math.floor((Date.now() - startDate.getTime()) / (7 * 24 * 60 * 60 * 1000)) + 1)
    : null;

  const cycleDate = (week: number) => {
    if (!startDate) return null;
    const d = new Date(startDate.getTime() + (week - 1) * 7 * 24 * 60 * 60 * 1000);
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  };

  const navLabel = NAV_ITEMS.find(n => n.id === nav)?.label ?? "OVERVIEW";
  const allPicks = alloc ? [...alloc.breakout_picks, ...alloc.core_picks] : [];

  // ── Loading ────────────────────────────────────────────────────────────────
  if (loading) return (
    <div style={{
      height: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "#0a0a0a", flexDirection: "column", gap: 16,
    }}>
      <div style={{
        width: 40, height: 40, border: "2px solid #1e1e1e",
        borderTopColor: "#ff4500", borderRadius: "50%",
        animation: "spin 0.8s linear infinite",
      }} />
      <div className="label" style={{ color: "#444" }}>LOADING MARKET DATA</div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );

  // ── No data ────────────────────────────────────────────────────────────────
  if (error || !analysis || !alloc) return (
    <div style={{
      height: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "#0a0a0a", flexDirection: "column", gap: 20,
    }}>
      <div className="label" style={{ color: "#ff4500", fontSize: "0.9rem" }}>⚠ NO DATA FEED</div>
      <div className="mono" style={{
        background: "#111", border: "1px solid #1e1e1e", padding: 20,
        color: "#555", fontSize: "0.78rem", lineHeight: 1.8,
      }}>
        <span style={{ color: "#ff4500" }}>$</span> python main.py<br />
        <span style={{ color: "#ff4500" }}>$</span> python push_to_webapp.py
      </div>
      <button onClick={load} className="label" style={{
        background: "#ff4500", color: "#fff", border: "none",
        padding: "10px 24px", cursor: "pointer", letterSpacing: "0.12em",
      }}>RETRY</button>
    </div>
  );

  const regime = analysis.regime;
  const fii    = analysis.market_data.fii_dii;
  const totalGain = allPicks.reduce((s, p) => s + p.max_gain, 0);
  const totalRisk = allPicks.reduce((s, p) => s + p.max_loss, 0);
  const gainPct   = ((totalGain / capital) * 100).toFixed(1);
  const rr        = (totalGain / Math.max(totalRisk, 1)).toFixed(2);

  return (
    <div style={{ display: "flex", height: "100vh", background: "#0a0a0a", overflow: "hidden" }}>
      <Sidebar active={nav} setActive={setNav} />

      {/* Main */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <TopBar section={navLabel} hasData={!!analysis} generatedAt={analysis?.generated_at ?? null} updateFlash={updateFlash} />

        <div style={{ flex: 1, overflowY: "auto", background: "#0a0a0a" }}>

          {/* ── OVERVIEW ── */}
          {nav === "overview" && (
            <div className="fade-up">
              {/* Stats row */}
              <div style={{ display: "flex", borderBottom: "1px solid #1a1a1a" }}>
                <StatCard
                  label="TOTAL CAPITAL"
                  value={fmtINR(capital)}
                  sub={`${allPicks.length} positions`}
                  delta={{ value: `${alloc.breakout_picks.length} breakouts`, positive: alloc.breakout_picks.length > 0 }}
                />
                <div style={{ width: 1, background: "#1a1a1a" }} />
                <StatCard
                  label="DEPLOYED"
                  value={fmtINR(alloc.deployed)}
                  sub={`${Math.round((alloc.deployed / capital) * 100)}% allocated`}
                  delta={{ value: `${fmtINR(alloc.cash)} reserve`, positive: true }}
                />
                <div style={{ width: 1, background: "#1a1a1a" }} />
                <StatCard
                  label="GAIN POTENTIAL / EDGE"
                  value={`${gainPct}%`}
                  sub={`R:R = ${rr}x`}
                  inverted
                  delta={{ value: `+${fmtINR(totalGain)}`, positive: true }}
                />
                <div style={{ width: 1, background: "#1a1a1a" }} />
                <StatCard
                  label="MARKET REGIME"
                  value={regime.regime.replace("_", " ")}
                  sub={`${regime.confidence_pct}% confidence`}
                  delta={{ value: `ADX ${regime.adx?.toFixed(1)}`, positive: regime.regime.includes("BULL") }}
                />
              </div>

              {/* Chart section */}
              <div style={{ padding: "36px 32px 24px", borderBottom: "1px solid #1a1a1a" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 28 }}>
                  <div>
                    <div style={{ fontSize: "2.4rem", fontWeight: 700, lineHeight: 1, letterSpacing: "-0.02em" }}>
                      PORTFOLIO{" "}
                      <span className="serif" style={{ fontSize: "2.2rem", fontWeight: 400, color: "#888" }}>
                        trajectory
                      </span>
                    </div>
                    <div className="label" style={{ marginTop: 8, color: "#444" }}>
                      12-WEEK CUMULATIVE CAPITAL PROJECTION — {analysis.total_analyzed} STOCKS ANALYZED
                    </div>
                  </div>

                  {/* Time selector */}
                  <div style={{ display: "flex", gap: 0 }}>
                    {[4, 8, 12].map(w => (
                      <button key={w} onClick={() => setChartWeeks(w)}
                        className="label mono"
                        style={{
                          background: chartWeeks === w ? "#ff4500" : "transparent",
                          border: "1px solid #1e1e1e",
                          borderLeft: w === 4 ? "1px solid #1e1e1e" : "none",
                          color: chartWeeks === w ? "#fff" : "#444",
                          padding: "8px 16px", cursor: "pointer",
                          fontFamily: "'JetBrains Mono', monospace",
                        }}>
                        {w}W
                      </button>
                    ))}
                  </div>
                </div>

                {/* Chart */}
                <div style={{ height: 260 }}>
                  <TrajectoryChart alloc={alloc} weeks={chartWeeks} />
                </div>
              </div>

              {/* FII / Regime strip */}
              <div style={{ display: "flex", padding: "16px 32px", gap: 40, borderBottom: "1px solid #1a1a1a" }}>
                {[
                  { l: "NIFTY 50", v: regime.nifty_close?.toFixed(0) ?? "—", ok: true },
                  { l: "INDIA VIX", v: regime.india_vix?.toFixed(1) ?? "—", ok: (regime.india_vix ?? 99) < 20 },
                  { l: "FII FLOW", v: fii.fii_net_cr != null ? `${sign(fii.fii_net_cr)}${fmtINR(Math.abs(fii.fii_net_cr))} Cr` : "N/A", ok: (fii.fii_net_cr ?? 0) >= 0 },
                  { l: "1M RETURN", v: `${sign(regime.ret_1m_pct)}${Math.abs(regime.ret_1m_pct).toFixed(2)}%`, ok: regime.ret_1m_pct >= 0 },
                  { l: "3M RETURN", v: `${sign(regime.ret_3m_pct)}${Math.abs(regime.ret_3m_pct).toFixed(2)}%`, ok: regime.ret_3m_pct >= 0 },
                  { l: "NIFTY RSI", v: regime.rsi?.toFixed(1) ?? "—", ok: regime.rsi < 70 },
                  { l: "MACD", v: regime.macd_bullish ? "BULLISH" : "BEARISH", ok: regime.macd_bullish },
                ].map(s => (
                  <div key={s.l}>
                    <div className="label" style={{ marginBottom: 4 }}>{s.l}</div>
                    <div className="mono" style={{
                      fontSize: "0.82rem", fontWeight: 600,
                      color: s.ok ? "#fff" : "#666",
                    }}>{s.v}</div>
                  </div>
                ))}
              </div>

              {/* Positions preview table */}
              <div>
                <div style={{
                  display: "grid",
                  gridTemplateColumns: "32px 100px 90px 80px 80px 80px 80px 80px 60px",
                  gap: 0, padding: "10px 24px",
                  borderBottom: "1px solid #1a1a1a",
                }}>
                  {["#", "SYMBOL", "PRICE", "TARGET", "STOP", "DEPLOY", "MAX GAIN", "SIGNALS", "SCORE"].map(h => (
                    <div key={h} className="label" style={{ fontSize: "0.6rem" }}>{h}</div>
                  ))}
                </div>
                {allPicks.slice(0, 5).map((pick, i) => (
                  <PositionRow key={pick.symbol} pick={pick} rank={i + 1}
                    onExpand={() => setExpandedRow(expandedRow === pick.symbol ? null : pick.symbol)}
                    expanded={expandedRow === pick.symbol} />
                ))}
              </div>
            </div>
          )}

          {/* ── POSITIONS ── */}
          {nav === "positions" && (
            <div className="fade-up">
              <div style={{ padding: "24px 32px 16px", borderBottom: "1px solid #1a1a1a" }}>
                <div style={{ fontSize: "1.6rem", fontWeight: 700, marginBottom: 4 }}>
                  CORE{" "}
                  <span className="serif" style={{ color: "#888", fontWeight: 400 }}>positions</span>
                </div>
                <div className="label" style={{ color: "#444" }}>
                  {fmtINR(alloc.core_budget)} ALLOCATED — LONG-TERM HOLD 2–4 MONTHS
                </div>
              </div>
              <div style={{
                display: "grid",
                gridTemplateColumns: "32px 100px 90px 80px 80px 80px 80px 80px 60px",
                gap: 0, padding: "10px 24px", borderBottom: "1px solid #1a1a1a",
              }}>
                {["#", "SYMBOL", "PRICE", "TARGET", "STOP", "DEPLOY", "MAX GAIN", "SIGNALS", "SCORE"].map(h => (
                  <div key={h} className="label" style={{ fontSize: "0.6rem" }}>{h}</div>
                ))}
              </div>
              {alloc.core_picks.map((pick, i) => (
                <PositionRow key={pick.symbol} pick={pick} rank={i + 1}
                  onExpand={() => setExpandedRow(expandedRow === pick.symbol ? null : pick.symbol)}
                  expanded={expandedRow === pick.symbol} />
              ))}
            </div>
          )}

          {/* ── BREAKOUTS ── */}
          {nav === "breakouts" && (
            <div className="fade-up">
              <div style={{ padding: "24px 32px 16px", borderBottom: "1px solid #1a1a1a" }}>
                <div style={{ fontSize: "1.6rem", fontWeight: 700, marginBottom: 4 }}>
                  BREAKOUT{" "}
                  <span className="serif" style={{ color: "#ff4500", fontWeight: 400 }}>alerts</span>
                </div>
                <div className="label" style={{ color: "#444" }}>
                  {alloc.breakout_picks.length > 0
                    ? `⚡ ${fmtINR(alloc.breakout_budget)} RESERVED — TIME-SENSITIVE, ENTER WITHIN 2 SESSIONS`
                    : "NO ACTIVE BREAKOUT SETUPS — MARKET IN CONSOLIDATION"}
                </div>
              </div>

              {alloc.breakout_picks.length > 0 ? (
                <>
                  <div style={{
                    display: "grid",
                    gridTemplateColumns: "32px 100px 90px 80px 80px 80px 80px 80px 60px",
                    gap: 0, padding: "10px 24px", borderBottom: "1px solid #1a1a1a",
                  }}>
                    {["#", "SYMBOL", "PRICE", "TARGET", "STOP", "DEPLOY", "MAX GAIN", "SIGNALS", "SCORE"].map(h => (
                      <div key={h} className="label" style={{ fontSize: "0.6rem" }}>{h}</div>
                    ))}
                  </div>
                  {alloc.breakout_picks.map((pick, i) => (
                    <PositionRow key={pick.symbol} pick={pick} rank={i + 1}
                      onExpand={() => setExpandedRow(expandedRow === pick.symbol ? null : pick.symbol)}
                      expanded={expandedRow === pick.symbol} />
                  ))}
                </>
              ) : (
                <div style={{ padding: "80px 32px", textAlign: "center" }}>
                  <div className="label" style={{ color: "#333", fontSize: "0.8rem", marginBottom: 8 }}>
                    NO BREAKOUT TRIGGERS DETECTED
                  </div>
                  <div className="mono" style={{ color: "#222", fontSize: "0.72rem" }}>
                    Focus capital on core long-term positions
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── PERFORMANCE ── */}
          {nav === "performance" && (
            <div className="fade-up">
              {/* Header */}
              <div style={{ padding: "24px 32px 20px", borderBottom: "1px solid #1a1a1a", display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ fontSize: "1.6rem", fontWeight: 700, marginBottom: 4 }}>
                    PORTFOLIO{" "}
                    <span className="serif" style={{ color: "#888", fontWeight: 400 }}>performance</span>
                  </div>
                  <div className="label" style={{ color: "#444" }}>12-WEEK LIVE EXECUTION ROADMAP</div>
                </div>

                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 10 }}>
                  {startDate ? (
                    <>
                      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <span className="label" style={{ color: "#444" }}>
                          STARTED{" "}
                          <span className="mono" style={{ color: "#777" }}>
                            {startDate.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
                          </span>
                        </span>
                        <div style={{
                          background: "#ff4500", padding: "5px 14px",
                          fontFamily: "'JetBrains Mono', monospace",
                          fontSize: "0.72rem", fontWeight: 700, color: "#fff", letterSpacing: "0.1em",
                        }}>
                          WEEK {currentWeek} / 12
                        </div>
                      </div>
                      <button onClick={resetCycle} className="label" style={{
                        background: "none", border: "1px solid #2a2a2a",
                        color: "#444", padding: "6px 14px", cursor: "pointer",
                      }}>
                        RESET CYCLE
                      </button>
                    </>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
                      <button onClick={startCycle} style={{
                        background: "#ff4500", border: "none", color: "#fff",
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: "0.72rem", fontWeight: 700,
                        letterSpacing: "0.12em", padding: "12px 24px", cursor: "pointer",
                      }}>
                        START CYCLE — TODAY
                      </button>
                      <span className="label" style={{ color: "#333" }}>Locks in week numbers to real calendar dates</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Timeline */}
              <div style={{ padding: "32px" }}>
                {alloc.weekly_plan.map((event, i) => {
                  const isPast   = currentWeek !== null && event.week < currentWeek;
                  const isActive = currentWeek !== null && event.week === currentWeek;
                  const typeColors: Record<string, string> = { entry: "#ff4500", review: "#888", exit: "#ff4500", rebalance: "#555" };
                  const baseColor = typeColors[event.type] ?? "#888";
                  const dotBorder = isPast ? "#2a2a2a" : isActive ? "#ff4500" : "#333";
                  const labelColor = isPast ? "#333" : isActive ? "#ff4500" : baseColor;
                  const date = cycleDate(event.week);

                  return (
                    <div key={i} style={{ display: "flex", gap: 24, opacity: isPast ? 0.45 : 1, transition: "opacity 0.3s" }}>
                      <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                        <div style={{
                          width: 30, height: 30,
                          border: `1px solid ${dotBorder}`,
                          background: isActive ? "#ff4500" : "transparent",
                          display: "flex", alignItems: "center", justifyContent: "center",
                          flexShrink: 0,
                        }}>
                          {isPast
                            ? <span style={{ fontSize: "0.65rem", color: "#444" }}>✓</span>
                            : <span className="mono" style={{ fontSize: "0.6rem", color: isActive ? "#fff" : dotBorder }}>W{event.week}</span>
                          }
                        </div>
                        {i < alloc.weekly_plan.length - 1 && (
                          <div style={{ width: 1, height: 52, background: "#1a1a1a" }} />
                        )}
                      </div>

                      <div style={{ paddingBottom: i < alloc.weekly_plan.length - 1 ? 32 : 0, flex: 1 }}>
                        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 6, flexWrap: "wrap" }}>
                          <div className="label" style={{ color: labelColor, letterSpacing: "0.14em" }}>
                            {event.label}
                          </div>
                          {isActive && (
                            <span style={{
                              background: "#ff4500", color: "#fff",
                              fontSize: "0.55rem", fontWeight: 700, letterSpacing: "0.1em",
                              padding: "2px 7px", fontFamily: "'JetBrains Mono', monospace",
                            }}>NOW</span>
                          )}
                          {date && (
                            <span className="mono" style={{ fontSize: "0.65rem", color: isPast ? "#2a2a2a" : "#444" }}>
                              {date}
                            </span>
                          )}
                          {event.stocks?.map(s => (
                            <span key={s} className="badge mono" style={{
                              borderColor: isPast ? "#1a1a1a" : "#2a2a2a",
                              color: isPast ? "#2a2a2a" : "#555",
                              fontSize: "0.6rem",
                            }}>{s}</span>
                          ))}
                        </div>
                        <div style={{ fontSize: "0.78rem", color: isPast ? "#2a2a2a" : "#555", lineHeight: 1.6, maxWidth: 560 }}>
                          {event.description}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* R:R summary */}
              <div style={{
                margin: "0 32px 32px", display: "grid", gridTemplateColumns: "1fr 1fr 1fr",
                border: "1px solid #1a1a1a",
              }}>
                {[
                  { l: "BEST CASE", v: `+${fmtINR(totalGain)}`, sub: `+${gainPct}%`, color: "#ff4500" },
                  { l: "WORST CASE", v: `−${fmtINR(totalRisk)}`, sub: `-${((totalRisk/capital)*100).toFixed(1)}%`, color: "#555" },
                  { l: "REWARD : RISK", v: `${rr}×`, sub: "target 3×+", color: "#888" },
                ].map((s, i) => (
                  <div key={s.l} style={{ padding: "20px 24px", borderRight: i < 2 ? "1px solid #1a1a1a" : "none" }}>
                    <div className="label" style={{ marginBottom: 8 }}>{s.l}</div>
                    <div className="mono" style={{ fontSize: "1.6rem", fontWeight: 600, color: s.color }}>{s.v}</div>
                    <div className="label" style={{ marginTop: 4, color: "#333" }}>{s.sub}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── ANALYTICS ── */}
          {nav === "analytics" && (
            <div className="fade-up">
              <div style={{ padding: "24px 32px 16px", borderBottom: "1px solid #1a1a1a" }}>
                <div style={{ fontSize: "1.6rem", fontWeight: 700, marginBottom: 4 }}>
                  MARKET{" "}
                  <span className="serif" style={{ color: "#888", fontWeight: 400 }}>analytics</span>
                </div>
                <div className="label" style={{ color: "#444" }}>
                  REGIME ANALYSIS — {analysis.total_analyzed} UNIVERSE STOCKS
                </div>
              </div>
              <div style={{ padding: "32px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
                {/* Regime */}
                <div style={{ border: "1px solid #1a1a1a", padding: 24 }}>
                  <div className="label" style={{ marginBottom: 16 }}>REGIME SIGNALS</div>
                  {[
                    { l: "Regime", v: regime.regime.replace("_", " "), ok: regime.regime.includes("BULL") },
                    { l: "Confidence", v: `${regime.confidence_pct}%`, ok: regime.confidence_pct >= 65 },
                    { l: "ADX", v: fmtDec(regime.adx ?? 0), ok: (regime.adx ?? 0) > 25 },
                    { l: "RSI", v: fmtDec(regime.rsi ?? 0), ok: regime.rsi > 45 && regime.rsi < 70 },
                    { l: "MACD", v: regime.macd_bullish ? "BULLISH" : "BEARISH", ok: regime.macd_bullish },
                    { l: "1M Return", v: `${regime.ret_1m_pct?.toFixed(2)}%`, ok: regime.ret_1m_pct >= 0 },
                    { l: "3M Return", v: `${regime.ret_3m_pct?.toFixed(2)}%`, ok: regime.ret_3m_pct >= 0 },
                  ].map(s => (
                    <div key={s.l} style={{
                      display: "flex", justifyContent: "space-between",
                      padding: "10px 0", borderBottom: "1px solid #111",
                    }}>
                      <span className="label">{s.l}</span>
                      <span className="mono" style={{
                        fontSize: "0.8rem", fontWeight: 600,
                        color: s.ok ? "#fff" : "#555",
                      }}>{s.v}</span>
                    </div>
                  ))}
                </div>

                {/* Score distribution */}
                <div style={{ border: "1px solid #1a1a1a", padding: 24 }}>
                  <div className="label" style={{ marginBottom: 16 }}>TOP PICKS — SCORE DISTRIBUTION</div>
                  {analysis.top_picks.slice(0, 10).map(p => {
                    const sym = p.symbol.replace(".NS", "");
                    const pct = (p.total_score / 150) * 100;
                    return (
                      <div key={sym} style={{
                        display: "flex", alignItems: "center", gap: 12,
                        marginBottom: 10,
                      }}>
                        <span className="mono" style={{ width: 80, fontSize: "0.72rem", color: "#888" }}>{sym}</span>
                        <div style={{ flex: 1, background: "#111", height: 2 }}>
                          <div style={{
                            width: `${pct}%`, height: "100%",
                            background: pct >= 70 ? "#ff4500" : pct >= 55 ? "#555" : "#2a2a2a",
                            transition: "width 1s ease",
                          }} />
                        </div>
                        <span className="mono" style={{ fontSize: "0.72rem", color: "#444", width: 50 }}>
                          {p.total_score}/150
                        </span>
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
    </div>
  );
}
