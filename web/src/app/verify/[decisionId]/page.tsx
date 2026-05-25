"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { Pill, SectionLabel } from "@/components/ui";
import { api, type TraceResp } from "@/lib/api";
import { truncHash } from "@/lib/utils";

async function sha256hex(str: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str));
  return "0x" + [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export default function VerifyPage({
  params,
}: {
  params: Promise<{ decisionId: string }>;
}) {
  const { decisionId } = use(params);
  const id = Number(decisionId);
  const [trace, setTrace] = useState<TraceResp | null>(null);
  const [recomputed, setRecomputed] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [showJson, setShowJson] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.trace(id).then(setTrace).catch((e) => setErr(String(e)));
  }, [id]);

  const verify = useCallback(async () => {
    if (!trace) return;
    setVerifying(true);
    const h = await sha256hex(trace.canonical_json);
    setRecomputed(h);
    setVerifying(false);
  }, [trace]);

  useEffect(() => {
    if (trace) verify();
  }, [trace, verify]);

  const match = recomputed && trace && recomputed === trace.trace_hash;
  const anchorTx = trace?.anchors.find((a) => a.kind === "anchor");

  return (
    <div className="mx-auto max-w-4xl px-5 py-10">
      <Link
        href="/"
        className="mono mb-4 inline-block text-[11px] uppercase tracking-[0.12em] text-faint hover:text-signal"
      >
        ← terminal
      </Link>
      <h1 className="serif text-4xl">Trace verification</h1>
      <p className="mt-2 max-w-2xl text-muted">
        The reasoning trace is canonicalised and hashed. We re-hash the exact bytes in your
        browser and compare against the hash anchored on Arc — proving the on-chain record
        matches the reasoning, untampered.
      </p>

      {err && <div className="panel mt-6 border-danger/40 p-4 mono text-danger">{err}</div>}

      {trace && (
        <>
          {/* verdict */}
          <div
            className={`panel mt-8 flex items-center justify-between p-6 ${
              match ? "border-signal/50" : "border-amber/40"
            }`}
          >
            <div>
              <div className="label mb-2">Verification status</div>
              <div
                className={`serif text-3xl ${match ? "text-signal glow-signal" : "text-amber"}`}
              >
                {verifying ? "verifying…" : match ? "✓ Verified" : "recomputed hash differs"}
              </div>
            </div>
            <div className="text-right">
              <div className="label mb-1">Decision</div>
              <div className="mono text-2xl text-faint">#{id}</div>
            </div>
          </div>

          {/* hash comparison */}
          <div className="mt-4 grid gap-px md:grid-cols-2">
            <div className="panel p-4">
              <div className="label mb-2">Anchored hash (on Arc)</div>
              <div className="mono break-all text-[12px] text-cyan">{trace.trace_hash}</div>
            </div>
            <div className="panel p-4">
              <div className="label mb-2">Recomputed in browser</div>
              <div className={`mono break-all text-[12px] ${match ? "text-signal" : "text-amber"}`}>
                {recomputed ?? "…"}
              </div>
            </div>
          </div>

          {/* on-chain records */}
          <div className="mt-8">
            <SectionLabel index="◆">On-chain records</SectionLabel>
            <div className="mt-3 space-y-2">
              {trace.anchors.map((a) => (
                <div
                  key={a.id}
                  className="panel flex items-center justify-between p-3"
                >
                  <div className="flex items-center gap-3">
                    {a.mocked ? <Pill tone="amber">mock</Pill> : <Pill tone="signal">on-chain</Pill>}
                    <span className="mono text-[11px] uppercase tracking-[0.12em] text-faint">
                      {a.kind}
                    </span>
                    <span className="mono text-[12px]">{truncHash(a.tx_hash, 10)}</span>
                    {a.usdc_amount != null && (
                      <span className="mono text-[11px] text-faint">{a.usdc_amount} USDC</span>
                    )}
                  </div>
                  {a.explorer_url && (
                    <a
                      href={a.explorer_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mono text-[10px] uppercase tracking-[0.12em] text-faint hover:text-signal"
                    >
                      arcscan ↗
                    </a>
                  )}
                </div>
              ))}
              {trace.anchors.length === 0 && (
                <p className="mono text-[11px] text-faint">no anchors recorded</p>
              )}
            </div>
            {anchorTx && (
              <div className="mono mt-3 text-[11px] text-faint">
                anchored in calldata of tx {truncHash(anchorTx.tx_hash, 10)} ·{" "}
                {anchorTx.created_at?.slice(0, 19).replace("T", " ")} UTC
              </div>
            )}
          </div>

          {/* canonical bytes */}
          <div className="mt-8">
            <button
              onClick={() => setShowJson((v) => !v)}
              className="mono border border-line-bright px-3 py-1.5 text-[11px] uppercase tracking-[0.12em] text-muted hover:border-signal/50 hover:text-signal"
            >
              {showJson ? "− hide" : "+ show"} canonical trace ({trace.canonical_json.length} bytes)
            </button>
            {showJson && (
              <pre className="panel mt-3 max-h-96 overflow-auto p-4 mono text-[11px] leading-relaxed text-muted">
                {JSON.stringify(JSON.parse(trace.canonical_json), null, 2)}
              </pre>
            )}
          </div>
        </>
      )}
    </div>
  );
}
