export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => getJSON<HealthResp>("/api/health"),
  markets: (limit = 24) => getJSON<MarketsResp>(`/api/markets?limit=${limit}`),
  discover: () =>
    fetch(`${API_BASE}/api/discover`, { method: "POST" }).then((r) => r.json()),
  trace: (id: number) => getJSON<TraceResp>(`/api/trace/${id}`),
  decision: (id: number) => getJSON<DecisionResp>(`/api/decisions/${id}`),
  portfolio: () => getJSON<PortfolioResp>("/api/portfolio"),
  metrics: () => getJSON<MetricsResp>("/api/metrics"),
  anchors: (limit = 50) => getJSON<{ anchors: Anchor[] }>(`/api/anchors?limit=${limit}`),
  analyzeUrl: (id: string, replay = false) =>
    `${API_BASE}/api/analyze/${encodeURIComponent(id)}${replay ? "?replay=true" : ""}`,
};

import type { Anchor, GraphEdge, GraphNode, Market, Ontology } from "./types";

export type HealthResp = {
  ok: boolean;
  mode: string;
  model: string;
  arc: {
    real: boolean;
    chain_id: number;
    address: string | null;
    usdc_balance: number | null;
    explorer: string;
  };
};
export type MarketsResp = { markets: Market[]; seeds: string[] };
export type TraceResp = {
  decision_id: number;
  trace_hash: string;
  canonical_json: string;
  trace: Record<string, unknown>;
  anchors: Anchor[];
};
export type DecisionResp = {
  decision: Record<string, unknown> & { response_json?: Record<string, unknown> };
  graph: { ontology: Ontology; nodes: GraphNode[]; edges: GraphEdge[]; stats: Record<string, unknown> } | null;
  anchors: Anchor[];
  market: { id: string; question: string; category: string; last_price_yes: number } | null;
};
export type PortfolioResp = {
  positions: Position[];
  open_count: number;
  realized_pnl: number;
  bankroll: number;
};
export type Position = {
  id: number;
  market_id: string;
  question: string | null;
  venue: string | null;
  side: string;
  shares: number;
  entry_price: number;
  pnl: number | null;
  status: string;
  entry_decision_id: number | null;
  opened_at: string;
};
export type MetricsResp = {
  metrics: MetricRow[];
  llm_cost_today: number;
  anchor_count: number;
  settle_count: number;
  real_tx_count: number;
  usdc_balance: number | null;
  model: string;
};
export type MetricRow = {
  category: string;
  n_resolved: number;
  brier: number | null;
  ece: number | null;
  realized_pnl: number;
};
