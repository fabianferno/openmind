"use client";

import { useCallback, useRef, useState } from "react";
import { api } from "./api";
import type {
  Citation,
  Decision,
  GraphEdge,
  GraphNode,
  Market,
  Ontology,
  OnchainTx,
} from "./types";

export type Phase =
  | "idle"
  | "connecting"
  | "filtering"
  | "searching"
  | "ontology"
  | "extracting"
  | "reasoning"
  | "settling"
  | "anchoring"
  | "done"
  | "error";

export type StreamState = {
  phase: Phase;
  market: Market | null;
  searchCount: number | null;
  ontology: Ontology | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
  evidence: Citation[];
  decision: Decision | null;
  executed: Record<string, unknown> | null;
  settled: OnchainTx | null;
  anchored: OnchainTx | null;
  error: string | null;
};

const EMPTY: StreamState = {
  phase: "idle",
  market: null,
  searchCount: null,
  ontology: null,
  nodes: [],
  edges: [],
  evidence: [],
  decision: null,
  executed: null,
  settled: null,
  anchored: null,
  error: null,
};

export function useAnalyzeStream(marketId: string) {
  const [state, setState] = useState<StreamState>(EMPTY);
  const esRef = useRef<EventSource | null>(null);

  const reset = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    setState(EMPTY);
  }, []);

  const start = useCallback(
    (replay = false) => {
      esRef.current?.close();
      setState({ ...EMPTY, phase: "connecting" });
      const es = new EventSource(api.analyzeUrl(marketId, replay));
      esRef.current = es;

      const on = (name: string, fn: (d: unknown) => void) =>
        es.addEventListener(name, (e) => fn(JSON.parse((e as MessageEvent).data)));

      on("market", (d) =>
        setState((s) => ({ ...s, market: d as Market, phase: "filtering" })),
      );
      on("filter_passed", () => setState((s) => ({ ...s, phase: "searching" })));
      on("search_complete", (d) =>
        setState((s) => ({
          ...s,
          searchCount: (d as { n: number }).n,
          phase: "ontology",
        })),
      );
      on("ontology_generated", (d) =>
        setState((s) => ({ ...s, ontology: d as Ontology, phase: "extracting" })),
      );
      on("entity_extracted", (d) =>
        setState((s) => ({
          ...s,
          nodes: [...s.nodes, (d as { node: GraphNode }).node],
        })),
      );
      on("relation_extracted", (d) =>
        setState((s) => ({
          ...s,
          edges: [...s.edges, (d as { edge: GraphEdge }).edge],
        })),
      );
      on("graph_complete", () => setState((s) => ({ ...s, phase: "reasoning" })));
      on("evidence", (d) =>
        setState((s) => ({
          ...s,
          evidence: (d as { citations: Citation[] }).citations,
        })),
      );
      on("decision", (d) =>
        setState((s) => ({ ...s, decision: d as Decision, phase: "settling" })),
      );
      on("executed", (d) =>
        setState((s) => ({ ...s, executed: d as Record<string, unknown> })),
      );
      on("settled", (d) =>
        setState((s) => ({ ...s, settled: d as OnchainTx, phase: "anchoring" })),
      );
      on("anchored", (d) =>
        setState((s) => ({ ...s, anchored: d as OnchainTx, phase: "anchoring" })),
      );
      on("complete", () => setState((s) => ({ ...s, phase: "done" })));
      on("error", (d) =>
        setState((s) => ({
          ...s,
          error: (d as { message: string }).message,
          phase: "error",
        })),
      );
      on("done", () => {
        setState((s) => (s.phase === "error" ? s : { ...s, phase: "done" }));
        es.close();
      });
      es.onerror = () => {
        setState((s) =>
          s.phase === "done" || s.phase === "error"
            ? s
            : { ...s, phase: "error", error: "stream disconnected" },
        );
        es.close();
      };
    },
    [marketId],
  );

  const running =
    state.phase !== "idle" && state.phase !== "done" && state.phase !== "error";

  return { state, start, reset, running };
}
