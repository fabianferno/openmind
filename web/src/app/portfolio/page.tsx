"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { SectionLabel, Stat } from "@/components/ui";
import { Pill } from "@/components/ui";
import {
  api,
  type MetricsResp,
  type PortfolioResp,
} from "@/lib/api";
import type { Anchor } from "@/lib/types";
import { fmtUsd, truncHash } from "@/lib/utils";

export default function PortfolioPage() {
  const [pf, setPf] = useState<PortfolioResp | null>(null);
  const [metrics, setMetrics] = useState<MetricsResp | null>(null);
  const [anchors, setAnchors] = useState<Anchor[]>([]);

  useEffect(() => {
    api.portfolio().then(setPf).catch(() => {});
    api.metrics().then(setMetrics).catch(() => {});
    api.anchors(30).then((r) => setAnchors(r.anchors)).catch(() => {});
  }, []);

  return (
    <div className="mx-auto max-w-[1400px] px-5 py-10">
      <h1 className="serif text-4xl">Ledger</h1>
      <p className="mt-2 text-muted">Positions, calibration, and the on-chain settlement record.</p>

      <div className="mt-8 grid grid-cols-2 gap-px md:grid-cols-4">
        <Stat label="Open positions" value={pf?.open_count ?? "—"} tone="signal" />
        <Stat label="Realized PnL" value={pf ? fmtUsd(pf.realized_pnl) : "—"} />
        <Stat
          label="On-chain txns"
          value={metrics?.real_tx_count ?? "—"}
          sub="real Arc testnet"
          tone="signal"
        />
        <Stat
          label="Treasury USDC"
          value={metrics?.usdc_balance != null ? metrics.usdc_balance.toFixed(2) : "—"}
          tone="amber"
        />
      </div>

      <div className="mt-10 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* positions */}
        <div>
          <SectionLabel index="01">Positions</SectionLabel>
          <div className="panel mt-3 divide-y divide-line">
            {(pf?.positions ?? []).slice(0, 14).map((p) => (
              <Link
                key={p.id}
                href={`/analyze/${encodeURIComponent(p.market_id)}`}
                className="group flex items-center justify-between gap-3 px-4 py-3 transition-colors hover:bg-bg-elev"
              >
                <div className="min-w-0">
                  <div className="text-[13px] leading-tight text-text transition-colors group-hover:text-signal truncate">
                    {p.question || p.market_id}
                  </div>
                  <div className="mono mt-0.5 text-[10px] uppercase tracking-[0.12em] text-faint">
                    {p.side} · {p.shares.toFixed(2)} sh @ {(p.entry_price * 100).toFixed(0)}¢
                    {p.entry_decision_id != null && <> · #{p.entry_decision_id}</>}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  {p.pnl != null && (
                    <span
                      className={`mono text-[12px] tabular-nums ${
                        p.pnl >= 0 ? "text-signal" : "text-danger"
                      }`}
                    >
                      {p.pnl >= 0 ? "+" : ""}
                      {p.pnl.toFixed(2)}
                    </span>
                  )}
                  <Pill tone={p.status === "open" ? "cyan" : "neutral"}>{p.status}</Pill>
                  <span className="mono text-faint transition-colors group-hover:text-signal">→</span>
                </div>
              </Link>
            ))}
            {(!pf || pf.positions.length === 0) && (
              <div className="mono p-6 text-center text-[11px] text-faint">no positions yet</div>
            )}
          </div>
        </div>

        {/* on-chain ledger */}
        <div>
          <SectionLabel index="02">On-chain settlement log</SectionLabel>
          <div className="panel mt-3 divide-y divide-line">
            {anchors.map((a) => (
              <div key={a.id} className="flex items-center justify-between px-4 py-3">
                <div className="flex items-center gap-3">
                  {a.mocked ? <Pill tone="amber">mock</Pill> : <Pill tone="signal">live</Pill>}
                  <span className="mono text-[10px] uppercase tracking-[0.12em] text-faint">
                    {a.kind}
                  </span>
                  {a.decision_id != null && (
                    <Link
                      href={`/verify/${a.decision_id}`}
                      className="mono text-[11px] text-cyan hover:text-signal"
                    >
                      #{a.decision_id}
                    </Link>
                  )}
                </div>
                {a.explorer_url ? (
                  <a
                    href={a.explorer_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mono text-[11px] text-faint hover:text-signal"
                  >
                    {truncHash(a.tx_hash, 8)} ↗
                  </a>
                ) : (
                  <span className="mono text-[11px] text-faint">{truncHash(a.tx_hash, 8)}</span>
                )}
              </div>
            ))}
            {anchors.length === 0 && (
              <div className="mono p-6 text-center text-[11px] text-faint">no settlements yet</div>
            )}
          </div>
        </div>
      </div>

      {/* calibration */}
      {metrics && metrics.metrics.length > 0 && (
        <div className="mt-10">
          <SectionLabel index="03">Calibration by category</SectionLabel>
          <div className="panel mt-3 overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="label border-b border-line">
                  <th className="px-4 py-2 font-normal">Category</th>
                  <th className="px-4 py-2 font-normal">Resolved</th>
                  <th className="px-4 py-2 font-normal">Brier</th>
                  <th className="px-4 py-2 font-normal">ECE</th>
                  <th className="px-4 py-2 font-normal">PnL</th>
                </tr>
              </thead>
              <tbody className="mono text-[12px]">
                {metrics.metrics.map((m) => (
                  <tr key={m.category} className="border-b border-line/50">
                    <td className="px-4 py-2 text-text">{m.category}</td>
                    <td className="px-4 py-2 text-muted">{m.n_resolved}</td>
                    <td className="px-4 py-2 text-muted">{m.brier?.toFixed(3) ?? "—"}</td>
                    <td className="px-4 py-2 text-muted">{m.ece?.toFixed(3) ?? "—"}</td>
                    <td className="px-4 py-2 text-muted">{fmtUsd(m.realized_pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
