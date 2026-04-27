export interface ScoreBreakdown {
  technical: number;
  signals: number;
  chart_patterns?: number;
  fundamental: number;
  rel_strength: number;
  stability: number;
  entry_quality: number;
  momentum: number;
  regime_bonus: number;
  market_boost: number;
}

export interface Signals {
  rsi_bull_div: boolean;
  rsi_bear_div: boolean;
  macd_bull_div: boolean;
  macd_bear_div: boolean;
  squeeze_active: boolean;
  squeeze_fired: boolean;
  momentum_up: boolean;
  breakout: boolean;
  breakout_type?: "CONSOLIDATION" | "52W_HIGH" | "RESISTANCE" | "EMA_CROSS" | "VCP" | null;
  vol_surge: boolean;
  consol_range_pct: number;
  candle_pattern: string | null;
  candle_bullish: boolean | null;
  sr: { resistance: number[]; support: number[] };
  patterns?: {
    bullish_patterns: string[];
    bearish_patterns: string[];
    neutral_patterns: string[];
    pattern_score: number;
    pattern_bias: string;
    trend_structure: {
      structure: string;
      bias: string;
      confidence: number;
    };
  };
}

export interface Fundamentals {
  roe_pct: number | null;
  debt_to_equity: number | null;
  profit_margin_pct: number | null;
  revenue_growth_pct: number | null;
  earnings_growth_pct: number | null;
  pe_ratio: number | null;
  fcf_margin_pct: number | null;
  interest_coverage: number | null;
  current_ratio: number | null;
}

export interface SectorRS {
  sector: string;
  rs_score: number;
  sector_rank: number | null;
  sector_peers: number | null;
  own_ret_50d_pct: number | null;
  sector_avg_50d_pct: number | null;
}

export interface StockPick {
  symbol: string;
  price: number;
  shares: number;
  invested: number;
  stop_loss: number;
  stop_pct: number;
  target: number;
  target_pct: number;
  max_loss: number;
  max_gain: number;
  total_score: number;
  rule_score?: number;
  ml_prob?: number;
  position_size_pct: number;
  score_breakdown: ScoreBreakdown;
  signals: Signals;
  fundamentals: Fundamentals;
  sector_rs: SectorRS | null;
  market_context: string;
  manip_resistance: { manip_resistance_score: number; avg_daily_turnover_cr: number };
  stats_52w: { high52: number; low52: number; pct_from_high: number; pct_from_low: number };
  rsi: number;
  adx: number;
  ema_aligned: boolean;
  macd_bullish: boolean;
  rationale: string[];
}

export interface Regime {
  regime: "STRONG_BULL" | "BULL" | "SIDEWAYS" | "BEAR" | "STRONG_BEAR" | "VOLATILE";
  description: string;
  confidence_pct: number;
  nifty_close: number;
  adx: number;
  rsi: number;
  macd_bullish: boolean;
  ret_1m_pct: number;
  ret_3m_pct: number;
  india_vix: number;
}

export interface MarketData {
  fii_dii: { fii_net_cr: number | null; dii_net_cr: number | null };
  nifty_1d_pct: number;
  global_factors: Record<string, number>;
}

export interface Analysis {
  generated_at: string;
  regime: Regime;
  market_data: MarketData;
  top_picks: StockPick[];
  total_analyzed: number;
  investment_budget: number;
  current_prices?: Record<string, number>;
}

export interface UserPosition {
  symbol: string;
  qty: number;
  avgPrice: number;
}

export interface ProfitGoal {
  targetAmount: number;
  weeks: 4 | 12;
}

// ── Portfolio allocation types ────────────────────────────────────────────────

export interface AllocatedPick extends StockPick {
  allocated_amount: number;
  allocated_shares: number;
  actual_invested: number;
  allocation_type: "core" | "breakout";
  allocation_pct: number;
  weekly_target_pct: number;
  urgency: "high" | "medium" | "low";
}

export interface PortfolioAllocation {
  total_capital: number;
  core_budget: number;
  breakout_budget: number;
  reserve: number;
  core_picks: AllocatedPick[];
  breakout_picks: AllocatedPick[];
  weekly_plan: WeeklyEvent[];
  deployed: number;
  cash: number;
}

export interface WeeklyEvent {
  week: number;
  label: string;
  type: "entry" | "review" | "exit" | "rebalance";
  description: string;
  stocks?: string[];
}
