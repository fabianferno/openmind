"use client";

import { motion } from "framer-motion";
import type { Decision } from "@/lib/types";
import { fmtPct } from "@/lib/utils";
import { SectionLabel } from "./ui";

export function DecisionCard({ decision }: { decision: Decision | null }) {
  if (!decision) {
    return (
      <div className="panel p-4">
        <SectionLabel index="03">Decision</SectionLabel>
        <p className="mono mt-4 text-[11px] text-faint">
          The agent reasons over the graph to estimate P(YES) and the edge vs. the market
          price, then sizes a position with calibrated fractional Kelly.
        </p>
      </div>
    );
  }

  const { p_yes, market_price, edge, confidence, action, rationale } = decision;
  const enter = action.startsWith("enter");
  const side = action === "enter_yes" ? "YES" : action === "enter_no" ? "NO" : null;
  const edgePos = edge >= 0;

  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between">
        <SectionLabel index="03" className="flex-1">Decision</SectionLabel>
        <motion.span
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className={`mono ml-3 border px-2 py-1 text-[11px] uppercase tracking-[0.12em] ${
            enter
              ? "border-signal/50 bg-signal/10 text-signal"
              : "border-line-bright text-muted"
          }`}
        >
          {enter ? `ENTER ${side}` : "NO TRADE"}
        </motion.span>
      </div>

      {/* probability bar: agent vs market */}
      <div className="mt-5">
        <div className="label mb-2 flex justify-between">
          <span>Agent P(YES)</span>
          <span className="text-signal">{fmtPct(p_yes)}</span>
        </div>
        <div className="relative h-2 w-full bg-line">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${p_yes * 100}%` }}
            transition={{ duration: 0.8, ease: "easeOut" }}
            className="absolute inset-y-0 left-0 bg-signal"
          />
          <div
            className="absolute inset-y-[-3px] w-0.5 bg-amber"
            style={{ left: `${market_price * 100}%` }}
            title="market price"
          />
        </div>
        <div className="label mt-1 flex justify-between">
          <span className="text-faint">market {fmtPct(market_price)}</span>
          <span className={edgePos ? "text-signal" : "text-danger"}>
            edge {edgePos ? "+" : ""}{(edge * 100).toFixed(1)}pp
          </span>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-4">
        <div>
          <div className="label">Confidence</div>
          <div className="mono mt-1 text-lg tabular-nums">{fmtPct(confidence)}</div>
        </div>
        <div>
          <div className="label">Decision ID</div>
          <div className="mono mt-1 text-lg tabular-nums text-faint">#{decision.decision_id}</div>
        </div>
      </div>

      {rationale && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="mt-4 border-l-2 border-signal/40 pl-3 text-[13px] leading-relaxed text-muted"
        >
          {rationale}
        </motion.p>
      )}
    </div>
  );
}
