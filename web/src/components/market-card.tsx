"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import type { Market } from "@/lib/types";
import { fmtPct, fmtUsd } from "@/lib/utils";
import { Pill } from "./ui";

export function MarketCard({ market, index }: { market: Market; index: number }) {
  const price = market.last_price_yes ?? 0.5;
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
    >
      <Link
        href={`/analyze/${encodeURIComponent(market.id)}`}
        className="group panel relative block p-5 transition-colors hover:border-line-bright"
      >
        <div className="mb-3 flex items-center justify-between">
          <span className="mono text-[10px] uppercase tracking-[0.12em] text-faint">
            {market.venue} · {market.category || "—"}
          </span>
          {market.seeded && <Pill tone="signal">seeded</Pill>}
        </div>

        <h3 className="serif text-xl leading-tight text-text transition-colors group-hover:text-signal">
          {market.question}
        </h3>

        <div className="mt-5 flex items-end justify-between">
          <div>
            <div className="label mb-1">YES price</div>
            <div className="mono text-2xl tabular-nums">{fmtPct(price)}</div>
          </div>
          <div className="text-right">
            <div className="label mb-1">24h vol</div>
            <div className="mono text-sm tabular-nums text-muted">{fmtUsd(market.volume_24h)}</div>
          </div>
        </div>

        {/* price meter */}
        <div className="mt-4 h-1 w-full bg-line">
          <div className="h-full bg-signal/60" style={{ width: `${price * 100}%` }} />
        </div>

        <div className="mono mt-4 flex items-center gap-2 text-[11px] uppercase tracking-[0.12em] text-faint transition-colors group-hover:text-signal">
          Build reasoning graph →
        </div>
      </Link>
    </motion.div>
  );
}
