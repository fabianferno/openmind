"use client";

import { useCallback, useEffect, useState } from "react";
import { createPublicClient, formatEther, http } from "viem";
import { arcTestnet } from "./chains";

const client = createPublicClient({ chain: arcTestnet, transport: http() });

export type ArcBalance = {
  /** Native balance in wei (USDC is the gas token on Arc), or null until/if it loads. */
  wei: bigint | null;
  /** Human-readable USDC, e.g. "12.5000". */
  formatted: string | null;
  /** True only once a balance has loaded AND it is exactly zero. */
  isZero: boolean;
  refetch: () => void;
};

/**
 * Reads the connected wallet's native (USDC) balance on Arc — the gas it needs
 * to sign personal-mode txns. Polls gently and re-reads on demand (e.g. after a
 * faucet drip). Returns null on RPC failure so we never nag on a transient error.
 */
export function useArcBalance(address: string | null): ArcBalance {
  const [wei, setWei] = useState<bigint | null>(null);

  const refetch = useCallback(() => {
    if (!address) {
      setWei(null);
      return;
    }
    client
      .getBalance({ address: address as `0x${string}` })
      .then(setWei)
      .catch(() => setWei(null));
  }, [address]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refetch();
    if (!address) return;
    const t = setInterval(refetch, 20_000);
    return () => clearInterval(t);
  }, [address, refetch]);

  return {
    wei,
    formatted: wei == null ? null : Number(formatEther(wei)).toFixed(4),
    isZero: wei === BigInt(0),
    refetch,
  };
}
