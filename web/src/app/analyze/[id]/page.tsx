"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";
import { DecisionCard } from "@/components/decision-card";
import { EvidenceFeed } from "@/components/evidence-feed";
import { GraphCanvas } from "@/components/graph-canvas";
import { OnchainPanel } from "@/components/onchain-panel";
import { OntologyPanel } from "@/components/ontology-panel";
import { Pill } from "@/components/ui";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { Market } from "@/lib/types";
import { cn } from "@/lib/utils";
import { type Phase, useAnalyzeStream } from "@/lib/useAnalyzeStream";

const STEPS: { key: string; label: string; phases: Phase[] }[] = [
  { key: "search", label: "Search", phases: ["filtering", "searching"] },
  { key: "onto", label: "Ontology", phases: ["ontology"] },
  { key: "graph", label: "Graph", phases: ["extracting"] },
  { key: "reason", label: "Reason", phases: ["reasoning"] },
  { key: "settle", label: "Settle", phases: ["settling"] },
  { key: "anchor", label: "Anchor", phases: ["anchoring"] },
];

function phaseRank(p: Phase): number {
  const order: Phase[] = [
    "idle", "connecting", "filtering", "searching", "ontology",
    "extracting", "reasoning", "settling", "anchoring", "done",
  ];
  return order.indexOf(p);
}

export default function AnalyzePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const marketId = decodeURIComponent(id);
  const { state, start, running } = useAnalyzeStream(marketId);
  const gate = useRequireAuth();
  const [seedAvailable, setSeedAvailable] = useState(false);
  const [premarket, setPremarket] = useState<Market | null>(null);

  useEffect(() => {
    api.markets(60).then((r) => {
      setSeedAvailable(r.seeds.some((s) => s.startsWith(marketId.replace(/:/g, "_"))));
      setPremarket(r.markets.find((m) => m.id === marketId) ?? null);
    }).catch(() => {});
  }, [marketId]);

  const market = state.market ?? premarket;
  const rank = phaseRank(state.phase);
  const started = state.phase !== "idle";

  const statusTone = useMemo(() => {
    if (state.phase === "error") return "danger" as const;
    if (state.phase === "done") return "signal" as const;
    return running ? "cyan" as const : "neutral" as const;
  }, [state.phase, running]);

  return (
    <div className="mx-auto max-w-[1500px] px-5 py-6">
      {/* header */}
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <Link
            href="/"
            className="mono mb-2 inline-block text-[11px] uppercase tracking-[0.12em] text-faint hover:text-signal"
          >
            ← terminal
          </Link>
          <h1 className="serif max-w-3xl text-3xl leading-tight">
            {market?.question ?? marketId}
          </h1>
          <div className="mono mt-2 flex items-center gap-3 text-[11px] uppercase tracking-[0.12em] text-faint">
            <span>{market?.venue ?? "—"}</span>
            <span>·</span>
            <span>{market?.category ?? "—"}</span>
            {market?.last_price_yes != null && (
              <>
                <span>·</span>
                <span className="text-muted">YES {(market.last_price_yes * 100).toFixed(0)}%</span>
              </>
            )}
            {market?.market_url && (
              <>
                <span>·</span>
                <a
                  href={market.market_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-cyan transition-colors hover:text-signal"
                >
                  view on {market.venue} ↗
                </a>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Pill tone={statusTone}>
            {running && <span className="signal-dot inline-block size-1.5 rounded-full bg-current" />}
            {state.phase}
          </Pill>
          {seedAvailable && (
            <button
              onClick={() => start(true)}
              disabled={running}
              className="mono border border-line-bright px-3 py-1.5 text-[11px] uppercase tracking-[0.12em] text-muted transition-colors hover:border-cyan/50 hover:text-cyan disabled:opacity-40"
            >
              ▶ replay
            </button>
          )}
          <button
            onClick={() => gate(() => start(false))}
            disabled={running}
            className="mono border border-signal/50 bg-signal/10 px-4 py-1.5 text-[11px] uppercase tracking-[0.12em] text-signal transition-colors hover:bg-signal/20 disabled:opacity-40"
          >
            {running ? "running…" : started ? "↻ run again" : "▶ run live"}
          </button>
        </div>
      </div>

      {/* stepper */}
      <div className="panel mb-4 flex items-center gap-1 overflow-x-auto p-1">
        {STEPS.map((step) => {
          const minRank = Math.min(...step.phases.map(phaseRank));
          const done = rank > Math.max(...step.phases.map(phaseRank));
          const active = step.phases.includes(state.phase);
          return (
            <div
              key={step.key}
              className={cn(
                "mono flex-1 whitespace-nowrap border-b-2 px-3 py-2 text-center text-[10px] uppercase tracking-[0.14em] transition-colors",
                active
                  ? "border-signal text-signal"
                  : done
                  ? "border-line-bright text-muted"
                  : "border-transparent text-faint",
                rank >= minRank ? "" : "opacity-50",
              )}
            >
              {step.label}
            </div>
          );
        })}
      </div>

      {/* three-column dossier */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[320px_1fr_370px]">
        <div className="flex flex-col gap-4">
          <OntologyPanel
            ontology={state.ontology}
            nodeCount={state.nodes.length}
            edgeCount={state.edges.length}
          />
          <EvidenceFeed citations={state.evidence} />
        </div>

        <div className="panel relative min-h-[560px] overflow-hidden">
          <div className="absolute left-4 top-3 z-10 mono text-[10px] uppercase tracking-[0.18em] text-faint">
            knowledge graph · graphRAG
          </div>
          <GraphCanvas nodes={state.nodes} edges={state.edges} />
        </div>

        <div className="flex flex-col gap-4">
          <DecisionCard decision={state.decision} />
          {state.executed && (
            <div className="panel flex items-center justify-between p-3">
              <div className="mono text-[11px] uppercase tracking-[0.12em] text-faint">
                bet{" "}
                <span className={state.executed.status === "filled" ? "text-signal" : "text-amber"}>
                  {String(state.executed.status)}
                </span>{" "}
                · {String(state.executed.side ?? "")} ${String(state.executed.usd_size ?? "")}
              </div>
              {typeof state.executed.market_url === "string" && (
                <a
                  href={state.executed.market_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mono text-[10px] uppercase tracking-[0.12em] text-cyan hover:text-signal"
                >
                  view on {String(state.executed.venue ?? "venue")} ↗
                </a>
              )}
            </div>
          )}
          <OnchainPanel
            settled={state.settled}
            anchored={state.anchored}
            decisionId={state.decision?.decision_id}
            active={state.phase === "anchoring" || state.phase === "settling"}
          />
        </div>
      </div>

      {state.error && (
        <div className="panel mt-4 border-danger/40 p-4">
          <span className="mono text-[12px] text-danger">error · {state.error}</span>
        </div>
      )}

      {!started && (
        <div className="mono mt-8 text-center text-[11px] uppercase tracking-[0.18em] text-faint">
          press <span className="text-signal">run live</span> to build the reasoning graph and anchor it on arc
        </div>
      )}
    </div>
  );
}
