"use client";

import { useState } from "react";
import { ARC_FAUCET_URL } from "@/lib/chains";
import { useAuth } from "@/lib/auth";
import { useDemoMode } from "@/lib/demo-mode";
import { useArcBalance } from "@/lib/useArcBalance";

/**
 * Personal mode signs on-chain with the user's own wallet, which needs Arc-testnet
 * USDC for gas. When that balance is zero, surface a clear prompt + faucet link
 * rather than letting the signing fail with a cryptic "insufficient funds".
 */
export function FaucetPrompt() {
  const { authenticated, address, hasPrivy } = useAuth();
  const { demoMode } = useDemoMode();
  const { isZero, refetch } = useArcBalance(authenticated ? address : null);
  const [copied, setCopied] = useState(false);

  // Only nag when it actually matters: logged in, personal mode, confirmed 0.
  if (!hasPrivy || !authenticated || demoMode || !isZero) return null;

  const copy = () => {
    if (!address) return;
    navigator.clipboard?.writeText(address).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div className="border-b border-amber/30 bg-amber/10">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-4 gap-y-2 px-5 py-2.5">
        <span className="signal-dot inline-block size-1.5 shrink-0 rounded-full bg-amber" />
        <span className="mono text-[11px] uppercase tracking-[0.1em] text-amber">
          Insufficient balance
        </span>
        <span className="text-[12px] text-muted">
          Your wallet has{" "}
          <span className="text-amber">0 USDC</span> on Arc — personal mode needs
          USDC to pay gas. Fund it from the faucet, then re-check.
        </span>

        <div className="ml-auto flex items-center gap-2">
          {address && (
            <button
              onClick={copy}
              title="Copy your wallet address"
              className="mono border border-line px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-faint transition-colors hover:border-line-bright hover:text-text"
            >
              {copied ? "copied ✓" : `${address.slice(0, 6)}…${address.slice(-4)} · copy`}
            </button>
          )}
          <a
            href={ARC_FAUCET_URL}
            target="_blank"
            rel="noreferrer"
            className="mono border border-amber/50 bg-amber/10 px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-amber transition-colors hover:bg-amber/20"
          >
            get testnet USDC ↗
          </a>
          <button
            onClick={refetch}
            className="mono border border-line px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-muted transition-colors hover:border-line-bright hover:text-text"
          >
            ↻ recheck
          </button>
        </div>
      </div>
    </div>
  );
}
