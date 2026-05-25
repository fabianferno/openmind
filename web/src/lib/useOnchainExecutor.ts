"use client";

import { useSendTransaction } from "@privy-io/react-auth";
import { useCallback } from "react";
import { encodeFunctionData, parseUnits, type Hex } from "viem";
import { api } from "./api";
import { HAS_PRIVY, useAuth } from "./auth";
import type { AnchorRequest, OnchainTx, SettleRequest } from "./types";

const ERC20_TRANSFER_ABI = [
  {
    name: "transfer",
    type: "function",
    stateMutability: "nonpayable",
    inputs: [
      { name: "to", type: "address" },
      { name: "amount", type: "uint256" },
    ],
    outputs: [{ name: "", type: "bool" }],
  },
] as const;

export type OnchainExecutor = {
  /** Sign the trace-hash anchor with the user's wallet, then persist it. */
  anchor: (req: AnchorRequest) => Promise<OnchainTx>;
  /** Sign the symbolic USDC settle with the user's wallet, then persist it. */
  settle: (req: SettleRequest) => Promise<OnchainTx>;
};

/**
 * Personal-mode signer: the server never holds the user's key, so the browser
 * signs the Arc anchor + settle txns via the Privy embedded wallet and reports
 * the resulting hashes back to be recorded in the ledger.
 */
export function useOnchainExecutor(): OnchainExecutor {
  // sendTransaction requires PrivyProvider; only call the hook when Privy is
  // configured (HAS_PRIVY is a stable build-time constant — safe to branch on).
  if (!HAS_PRIVY) {
    // No hooks in this branch — keeps the hook-call order stable (HAS_PRIVY is
    // a build-time constant, so exactly one branch runs for the app's lifetime).
    const disabled = async (): Promise<never> => {
      throw new Error("Privy not configured — personal mode unavailable.");
    };
    return { anchor: disabled, settle: disabled };
  }
  /* eslint-disable react-hooks/rules-of-hooks */
  const { sendTransaction } = useSendTransaction();
  // signer address — recorded as from_address so the ledger can attribute these
  // txns (and their positions) to this user in personal mode.
  const { address } = useAuth();

  const anchor = useCallback(
    async (req: AnchorRequest): Promise<OnchainTx> => {
      const data = (req.trace_hash.startsWith("0x")
        ? req.trace_hash
        : `0x${req.trace_hash}`) as Hex;
      const { hash } = await sendTransaction({
        to: req.to,
        data,
        value: 0,
        chainId: req.chain_id,
      });
      return api.recordAnchor({
        decision_id: req.decision_id,
        market_id: req.market_id,
        kind: "anchor",
        tx_hash: hash,
        trace_hash: req.trace_hash,
        from_address: address,
      });
    },
    [sendTransaction, address],
  );

  const settle = useCallback(
    async (req: SettleRequest): Promise<OnchainTx> => {
      const data = encodeFunctionData({
        abi: ERC20_TRANSFER_ABI,
        functionName: "transfer",
        args: [
          req.treasury as Hex,
          parseUnits(String(req.amount_usdc), req.decimals),
        ],
      });
      const { hash } = await sendTransaction({
        to: req.usdc_address,
        data,
        value: 0,
        chainId: req.chain_id,
      });
      return api.recordAnchor({
        decision_id: req.decision_id,
        market_id: req.market_id,
        kind: "settle",
        tx_hash: hash,
        usdc_amount: req.amount_usdc,
        to_address: req.treasury,
        from_address: address,
      });
    },
    [sendTransaction, address],
  );
  /* eslint-enable react-hooks/rules-of-hooks */

  return { anchor, settle };
}
