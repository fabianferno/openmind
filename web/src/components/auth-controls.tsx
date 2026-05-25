"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { useDemoMode } from "@/lib/demo-mode";

function shortAddr(a: string | null) {
  return a ? `${a.slice(0, 6)}…${a.slice(-4)}` : "wallet";
}

export function AuthControls() {
  const { ready, authenticated, address, login, logout, hasPrivy } = useAuth();
  const { demoMode, setDemoMode } = useDemoMode();
  const [copied, setCopied] = useState(false);

  const copyAddress = () => {
    if (!address) return;
    navigator.clipboard?.writeText(address).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  if (!hasPrivy) return null;

  if (!ready) {
    return (
      <span className="mono text-[10px] uppercase tracking-[0.12em] text-faint">
        …
      </span>
    );
  }

  if (!authenticated) {
    return (
      <button
        onClick={login}
        className="mono border border-signal/50 bg-signal/10 px-3 py-1 text-[10px] uppercase tracking-[0.12em] text-signal transition-colors hover:bg-signal/20"
      >
        Log in
      </button>
    );
  }

  return (
    <div className="flex items-center gap-3">
      {/* demo-mode toggle: ON = server wallet signs, OFF = your wallet signs */}
      <div
        role="switch"
        aria-checked={!demoMode}
        aria-label="Signing mode: demo (server wallet) or personal (your wallet)"
        title={
          demoMode
            ? "Demo mode: the server wallet signs on-chain. Click to sign with your own wallet."
            : "Personal mode: your wallet signs on-chain (needs Arc testnet USDC for gas). Click to use the server wallet."
        }
        className="mono relative flex select-none items-center border border-line text-[10px] uppercase tracking-[0.12em]"
      >
        {/* sliding indicator */}
        <span
          aria-hidden
          className={cn(
            "absolute inset-y-0 w-1/2 border transition-[left,border-color,background-color] duration-200 ease-out",
            demoMode
              ? "left-0 border-amber/50 bg-amber/10"
              : "left-1/2 border-signal/50 bg-signal/10",
          )}
        />
        <button
          type="button"
          onClick={() => setDemoMode(true)}
          className={cn(
            "relative z-10 px-2.5 py-1 transition-colors",
            demoMode ? "text-amber" : "text-faint hover:text-muted",
          )}
        >
          demo
        </button>
        <button
          type="button"
          onClick={() => setDemoMode(false)}
          className={cn(
            "relative z-10 px-2.5 py-1 transition-colors",
            demoMode ? "text-faint hover:text-muted" : "text-signal",
          )}
        >
          personal
        </button>
      </div>

      <div className="mono flex items-center border border-line text-[10px] uppercase tracking-[0.12em]">
        <span
          className="px-2.5 py-1 text-muted"
          title={address ?? undefined}
        >
          {shortAddr(address)}
        </span>
        <button
          type="button"
          onClick={copyAddress}
          title={copied ? "Copied" : "Copy wallet address"}
          aria-label={copied ? "Copied wallet address" : "Copy wallet address"}
          className="cursor-pointer border-l border-line px-2 py-1 text-faint transition-colors hover:text-text"
        >
          {copied ? (
            <Check className="size-3 text-signal" aria-hidden />
          ) : (
            <Copy className="size-3" aria-hidden />
          )}
        </button>
        <button
          type="button"
          onClick={logout}
          className="border-l border-line px-2.5 py-1 text-muted transition-colors hover:text-text"
        >
          out
        </button>
      </div>
    </div>
  );
}
