"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { Pill, SectionLabel } from "@/components/ui";
import { useRequireAuth } from "@/lib/auth";
import { fmtPct, truncHash } from "@/lib/utils";
import { type AutoItem, useAutoStream } from "@/lib/useAutoStream";

function AutoCard({ it }: { it: AutoItem }) {
  const d = it.decision;
  const enter = d?.action.startsWith("enter");
  const side = d?.action === "enter_yes" ? "YES" : d?.action === "enter_no" ? "NO" : null;
  const running = !["done", "error"].includes(it.phase);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="panel p-4"
    >
      <div className="mb-3 flex items-center justify-between">
        <span className="mono text-[10px] uppercase tracking-[0.12em] text-faint">
          {it.market.category || "—"}
        </span>
        <Pill tone={it.phase === "error" ? "danger" : running ? "cyan" : "signal"}>
          {running && <span className="signal-dot inline-block size-1.5 rounded-full bg-current" />}
          {it.phase}
        </Pill>
      </div>

      <h3 className="serif text-lg leading-tight">{it.market.question}</h3>

      <div className="mono mt-3 flex items-center gap-4 text-[11px] text-faint">
        <span>
          <span className="text-signal">{it.nodeCount}</span> entities
        </span>
        <span>
          <span className="text-cyan">{it.edgeCount}</span> relations
        </span>
        {it.entityTypes.length > 0 && (
          <span className="truncate">{it.entityTypes.slice(0, 3).join(" · ")}</span>
        )}
      </div>

      {d && (
        <div className="mt-3 flex items-center justify-between border-t border-line pt-3">
          <div className="mono text-[12px]">
            <span className="text-faint">P(YES)</span>{" "}
            <span className="text-signal">{fmtPct(d.p_yes)}</span>
            <span className="ml-2 text-faint">edge</span>{" "}
            <span className={d.edge >= 0 ? "text-signal" : "text-danger"}>
              {d.edge >= 0 ? "+" : ""}
              {(d.edge * 100).toFixed(1)}pp
            </span>
          </div>
          <span
            className={`mono border px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] ${
              enter ? "border-signal/50 text-signal" : "border-line-bright text-muted"
            }`}
          >
            {enter ? `ENTER ${side}` : "NO TRADE"}
          </span>
        </div>
      )}

      <div className="mt-3 flex items-center justify-between">
        {it.anchored ? (
          <a
            href={it.anchored.explorer_url}
            target="_blank"
            rel="noreferrer"
            className="mono text-[10px] uppercase tracking-[0.12em] text-faint hover:text-signal"
          >
            {it.anchored.mocked ? "mock" : "⛓ anchored"} {truncHash(it.anchored.tx_hash, 6)} ↗
          </a>
        ) : (
          <span className="mono text-[10px] uppercase tracking-[0.12em] text-faint">
            {running ? "working…" : "—"}
          </span>
        )}
        <div className="flex items-center gap-3">
          {it.market.market_url && (
            <a
              href={it.market.market_url}
              target="_blank"
              rel="noreferrer"
              className="mono text-[10px] uppercase tracking-[0.12em] text-faint hover:text-cyan"
            >
              market ↗
            </a>
          )}
          {it.decision && (
            <Link
              href={`/verify/${it.decision.decision_id}`}
              className="mono text-[10px] uppercase tracking-[0.12em] text-cyan hover:text-signal"
            >
              verify →
            </Link>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export default function AutoPage() {
  const { items, status, start } = useAutoStream();
  const gate = useRequireAuth();
  const running = status === "running";
  const traded = items.filter((i) => i.decision?.action.startsWith("enter")).length;
  const anchored = items.filter((i) => i.anchored).length;

  return (
    <div className="mx-auto max-w-[1400px] px-5 py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mono mb-3 flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-faint">
            <span className="signal-dot inline-block size-1.5 rounded-full bg-signal" />
            full autonomy · no human in the loop
          </div>
          <h1 className="serif text-4xl">Autonomous run</h1>
          <p className="mt-2 max-w-2xl text-muted">
            The agent selects markets from its own universe, builds a knowledge graph for each,
            decides, and settles + anchors on Arc — you just watch.
          </p>
        </div>
        <button
          onClick={() => gate(() => start(4))}
          disabled={running}
          className="mono border border-signal/50 bg-signal/10 px-5 py-2 text-[11px] uppercase tracking-[0.12em] text-signal transition-colors hover:bg-signal/20 disabled:opacity-40"
        >
          {running ? "agent running…" : "▶ run autonomously"}
        </button>
      </div>

      {items.length > 0 && (
        <div className="mt-6 flex gap-6">
          <SectionLabel index="◆" className="flex-1">
            {status === "done" ? "Run complete" : "Decision feed"} · {anchored} anchored · {traded} traded
          </SectionLabel>
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {items.map((it) => (
          <AutoCard key={it.index} it={it} />
        ))}
      </div>

      {items.length === 0 && (
        <div className="mono mt-16 text-center text-[11px] uppercase tracking-[0.18em] text-faint">
          press <span className="text-signal">run autonomously</span> to let the agent trade on its own
        </div>
      )}
    </div>
  );
}
