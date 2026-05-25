"use client";

import { useCallback, useRef, useState } from "react";
import { API_BASE } from "./api";
import type { Decision, OnchainTx } from "./types";

export type AutoItem = {
  index: number;
  market: {
    id: string;
    question: string;
    category: string | null;
    price_yes: number | null;
    market_url?: string | null;
  };
  entityTypes: string[];
  nodeCount: number;
  edgeCount: number;
  decision: Decision | null;
  settled: OnchainTx | null;
  anchored: OnchainTx | null;
  phase: string;
  error?: string;
};

export function useAutoStream() {
  const [items, setItems] = useState<AutoItem[]>([]);
  const [status, setStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const esRef = useRef<EventSource | null>(null);

  const patch = (index: number, fn: (it: AutoItem) => AutoItem) =>
    setItems((arr) => arr.map((it) => (it.index === index ? fn(it) : it)));

  const start = useCallback((n = 4) => {
    esRef.current?.close();
    setItems([]);
    setStatus("running");
    const es = new EventSource(`${API_BASE}/api/auto?n=${n}`);
    esRef.current = es;

    es.addEventListener("auto_pick", (e) => {
      const { index, market } = JSON.parse((e as MessageEvent).data);
      setItems((arr) => [
        ...arr,
        {
          index,
          market,
          entityTypes: [],
          nodeCount: 0,
          edgeCount: 0,
          decision: null,
          settled: null,
          anchored: null,
          phase: "analyzing",
        },
      ]);
    });

    es.addEventListener("auto_event", (e) => {
      const { index, ev, data } = JSON.parse((e as MessageEvent).data);
      patch(index, (it) => {
        switch (ev) {
          case "ontology_generated":
            return { ...it, entityTypes: data.entity_types ?? [], phase: "graph" };
          case "entity_extracted":
            return { ...it, nodeCount: it.nodeCount + 1 };
          case "relation_extracted":
            return { ...it, edgeCount: it.edgeCount + 1 };
          case "graph_complete":
            return { ...it, phase: "reasoning" };
          case "decision":
            return { ...it, decision: data as Decision, phase: "settling" };
          case "settled":
            return { ...it, settled: data as OnchainTx };
          case "anchored":
            return { ...it, anchored: data as OnchainTx, phase: "anchored" };
          case "complete":
            return { ...it, phase: "done" };
          default:
            return it;
        }
      });
    });

    es.addEventListener("auto_error", (e) => {
      const { index, message } = JSON.parse((e as MessageEvent).data);
      if (index >= 0) patch(index, (it) => ({ ...it, error: message, phase: "error" }));
    });

    es.addEventListener("auto_done", () => {
      setStatus("done");
      es.close();
    });
    es.onerror = () => {
      setStatus((s) => (s === "done" ? s : "error"));
      es.close();
    };
  }, []);

  return { items, status, start };
}
