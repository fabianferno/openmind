"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type HealthResp } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Terminal" },
  { href: "/auto", label: "Autonomous" },
  { href: "/portfolio", label: "Ledger" },
];

export function SiteHeader() {
  const pathname = usePathname();
  const [health, setHealth] = useState<HealthResp | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  return (
    <header className="sticky top-0 z-50 border-b border-line bg-bg/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-[1400px] items-center justify-between px-5">
        <div className="flex items-center gap-8">
          <Link href="/" className="group flex items-baseline gap-2">
            <span className="serif text-xl leading-none tracking-tight">openmind</span>
            <span className="label hidden text-faint sm:inline">/ reasoning you can verify</span>
          </Link>
          <nav className="flex items-center gap-1">
            {NAV.map((n) => {
              const active = pathname === n.href;
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  className={cn(
                    "mono px-3 py-1 text-[11px] uppercase tracking-[0.12em] transition-colors",
                    active ? "text-signal" : "text-faint hover:text-muted",
                  )}
                >
                  {n.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex items-center gap-4">
          {health && (
            <span className="mono hidden items-center gap-1.5 text-[10px] uppercase tracking-[0.12em] text-faint md:flex">
              <span className="text-muted">{health.model.split(".").pop()}</span>
            </span>
          )}
          <span className="mono flex items-center gap-2 border border-line px-2.5 py-1 text-[10px] uppercase tracking-[0.12em]">
            <span
              className={cn(
                "signal-dot inline-block size-1.5 rounded-full",
                health?.arc.real ? "bg-signal" : "bg-amber",
              )}
            />
            <span className={health?.arc.real ? "text-signal" : "text-amber"}>
              {health?.arc.real ? "ARC TESTNET" : "ARC MOCK"}
            </span>
            {health?.arc.usdc_balance != null && (
              <span className="text-faint">· {health.arc.usdc_balance.toFixed(2)} USDC</span>
            )}
          </span>
        </div>
      </div>
    </header>
  );
}
