"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import type { OnchainTx } from "@/lib/types";
import { truncHash } from "@/lib/utils";
import { Pill, SectionLabel } from "./ui";

function TxRow({ label, tx, sub }: { label: string; tx: OnchainTx; sub?: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center justify-between border border-line bg-bg-elev px-3 py-2.5"
    >
      <div>
        <div className="label mb-0.5 flex items-center gap-2">
          {label}
          {tx.mocked ? <Pill tone="amber">mock</Pill> : <Pill tone="signal">on-chain</Pill>}
        </div>
        <div className="mono text-[12px] text-text">
          {truncHash(tx.tx_hash, 8)}
          {sub && <span className="ml-2 text-faint">{sub}</span>}
        </div>
      </div>
      <a
        href={tx.explorer_url}
        target="_blank"
        rel="noreferrer"
        className="mono text-[10px] uppercase tracking-[0.12em] text-faint transition-colors hover:text-signal"
      >
        arcscan ↗
      </a>
    </motion.div>
  );
}

export function OnchainPanel({
  settled,
  anchored,
  decisionId,
  active,
}: {
  settled: OnchainTx | null;
  anchored: OnchainTx | null;
  decisionId?: number | null;
  active: boolean;
}) {
  return (
    <div className="panel p-4">
      <SectionLabel index="04">Settlement · Arc</SectionLabel>

      <div className="mt-4 space-y-2">
        {settled && (
          <TxRow
            label="USDC settled"
            tx={settled}
            sub={settled.usdc_amount ? `${settled.usdc_amount} USDC` : undefined}
          />
        )}
        {anchored ? (
          <TxRow label="Trace anchored" tx={anchored} />
        ) : active ? (
          <div className="flex items-center gap-2 border border-line bg-bg-elev px-3 py-2.5">
            <span className="signal-dot inline-block size-1.5 rounded-full bg-signal" />
            <span className="mono text-[11px] uppercase tracking-[0.12em] text-signal">
              anchoring reasoning trace…
            </span>
          </div>
        ) : (
          <p className="mono text-[11px] leading-relaxed text-faint">
            The full reasoning trace is hashed and anchored on Arc; a symbolic USDC stake is
            settled. Every decision becomes independently verifiable.
          </p>
        )}
      </div>

      {anchored?.trace_hash && (
        <div className="mt-3 border-t border-line pt-3">
          <div className="label mb-1">Trace hash (sha256)</div>
          <div className="mono break-all text-[11px] text-cyan">{anchored.trace_hash}</div>
          {decisionId != null && (
            <Link
              href={`/verify/${decisionId}`}
              className="mono mt-3 inline-flex items-center gap-2 border border-signal/40 bg-signal/5 px-3 py-1.5 text-[11px] uppercase tracking-[0.12em] text-signal transition-colors hover:bg-signal/10"
            >
              Verify trace →
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
