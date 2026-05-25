"use client";

import { useEffect, useState } from "react";
import { MarketCard } from "@/components/market-card";
import Bd1Hologram from "@/components/hologram/Bd1Hologram";
import { SectionLabel, Stat } from "@/components/ui";
import { api, type MarketsResp, type MetricsResp } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { Market } from "@/lib/types";

export default function Home() {
  const gate = useRequireAuth();
  const [markets, setMarkets] = useState<Market[]>([]);
  const [metrics, setMetrics] = useState<MetricsResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [discovering, setDiscovering] = useState(false);

  const load = () =>
    api
      .markets(18)
      .then((r: MarketsResp) => setMarkets(r.markets))
      .catch(() => { }) // backend sidecar may be down — show the empty state, don't throw
      .finally(() => setLoading(false));

  useEffect(() => {
    load();
    api.metrics().then(setMetrics).catch(() => { });
  }, []);

  const discover = async () => {
    setDiscovering(true);
    await api.discover().catch(() => { });
    await load();
    setDiscovering(false);
  };

  return (
    <div className="vignette">
      {/* hero */}
      <section className="relative overflow-hidden border-b border-line">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-50" />
        <div className="relative mx-auto grid max-w-[1400px] items-center gap-10 px-5  lg:grid-cols-[1.05fr_0.95fr] lg:gap-12">
          <div>
            <div className="mono mb-6 flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-faint">
              <span className="signal-dot inline-block size-1.5 rounded-full bg-signal" />
              prediction-market trader intelligence · settled on arc
            </div>
            <h1 className="serif max-w-4xl text-6xl leading-[0.95] tracking-tight md:text-7xl">
              Reasoning <br />you can
              <span className="text-signal glow-signal"> verify.</span>
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted">
              openmind reads the news, builds a knowledge graph of who and what moves a market,
              reasons to a calibrated +EV bet — then{" "}
              <span className="text-text">anchors its entire reasoning trace on Arc</span> and
              settles in USDC. Not a black box. A glass one.
            </p>

            <div className="mt-10 grid grid-cols-2 gap-px md:grid-cols-4">
              <Stat
                label="On-chain txns"
                value={metrics?.real_tx_count ?? "—"}
                sub="real Arc testnet"
                tone="signal"
              />
              <Stat label="Traces anchored" value={metrics?.anchor_count ?? "—"} />
              <Stat label="USDC settled" value={metrics?.settle_count ?? "—"} />
              <Stat
                label="LLM cost today"
                value={metrics ? `$${metrics.llm_cost_today.toFixed(3)}` : "—"}
                sub={metrics?.model.split(".").pop()}
                tone="amber"
              />
            </div>
          </div>

          {/* BD-1 hologram — interactive WebGPU particle field (port of hologram-particles).
              Renders on a transparent canvas; the soft radial mask only feathers the
              faint dot-grid plane edges so nothing reads as a rectangle. */}
          <div
            className="relative h-full w-full sm:h-[440px] lg:h-[580px]"
            style={{
              maskImage:
                "radial-gradient(70% 70% at 50% 50%, #000 45%, transparent 88%)",
              WebkitMaskImage:
                "radial-gradient(70% 70% at 50% 50%, #000 45%, transparent 88%)",
            }}
          >
            <Bd1Hologram />
          </div>
        </div>
      </section>

      {/* market grid */}
      <section className="mx-auto max-w-[1400px] px-5 py-12">
        <div className="mb-6 flex items-center justify-between">
          <SectionLabel index="◆" className="flex-1">Live markets — pick one to analyze</SectionLabel>
          <button
            onClick={() => gate(discover)}
            disabled={discovering}
            className="mono ml-4 border border-line-bright px-3 py-1.5 text-[11px] uppercase tracking-[0.12em] text-muted transition-colors hover:border-signal/50 hover:text-signal disabled:opacity-50"
          >
            {discovering ? "discovering…" : "↻ refresh"}
          </button>
        </div>

        {loading ? (
          <div className="mono py-20 text-center text-[11px] uppercase tracking-[0.2em] text-faint">
            loading markets…
          </div>
        ) : markets.length === 0 ? (
          <div className="panel p-10 text-center">
            <p className="mono text-[12px] text-faint">
              No open markets cached. Hit refresh to discover live Manifold markets.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {markets.map((m, i) => (
              <MarketCard key={m.id} market={m} index={i} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
