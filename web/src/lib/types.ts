export type Market = {
  id: string;
  venue: string;
  question: string;
  category: string | null;
  end_date: string | null;
  last_price_yes: number | null;
  volume_24h: number | null;
  market_url?: string | null;
  seeded?: boolean;
};

export type GraphNode = {
  id: string;
  label: string;
  type: string;
  summary?: string;
  source_url?: string | null;
  published_date?: string | null;
  degree?: number;
};

export type GraphEdge = {
  source: string;
  target: string;
  type: string;
  rationale?: string;
  source_url?: string | null;
};

export type Ontology = { entity_types: string[]; relation_types: string[] };

export type Decision = {
  decision_id: number;
  p_yes: number;
  market_price: number;
  confidence: number;
  edge: number;
  action: string;
  rationale: string;
};

export type OnchainTx = {
  tx_hash: string;
  explorer_url: string;
  mocked: boolean;
  kind: string;
  trace_hash?: string;
  usdc_amount?: number;
};

export type Anchor = {
  id: number;
  decision_id: number | null;
  market_id: string | null;
  kind: string;
  trace_hash: string | null;
  tx_hash: string;
  explorer_url: string | null;
  usdc_amount: number | null;
  mocked: number;
  created_at: string;
};

// SSE event payloads
export type AnalyzeEvent =
  | { event: "market"; data: Market }
  | { event: "filter_passed"; data: { market_id: string; question: string } }
  | { event: "search_complete"; data: { n: number } }
  | { event: "ontology_generated"; data: Ontology }
  | { event: "entity_extracted"; data: { node: GraphNode } }
  | { event: "relation_extracted"; data: { edge: GraphEdge } }
  | { event: "graph_complete"; data: { stats: Record<string, unknown> } }
  | { event: "evidence"; data: { citations: Citation[] } }
  | { event: "decision"; data: Decision }
  | { event: "executed"; data: Record<string, unknown> }
  | { event: "settled"; data: OnchainTx }
  | { event: "anchored"; data: OnchainTx }
  | { event: "complete"; data: Record<string, unknown> }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: Record<string, unknown> };

export type Citation = { url: string; title: string; published_date: string | null };
