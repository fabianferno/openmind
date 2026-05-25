import { defineChain } from "viem";

/**
 * Arc testnet — EVM-compatible, gas paid in USDC (the native balance).
 * Mirrors agent/config.py (arc_chain_id / arc_rpc_url / arc_explorer_base).
 * Used as Privy's default + supported chain so the embedded wallet signs here.
 */
export const ARC_CHAIN_ID = 5042002;

export const arcTestnet = defineChain({
  id: ARC_CHAIN_ID,
  name: "Arc Testnet",
  network: "arc-testnet",
  nativeCurrency: { name: "USD Coin", symbol: "USDC", decimals: 18 },
  rpcUrls: {
    default: { http: ["https://rpc.testnet.arc.network"] },
  },
  blockExplorers: {
    default: { name: "Arcscan", url: "https://testnet.arcscan.app" },
  },
  testnet: true,
});

/** ERC-20 USDC token on Arc testnet (agent/config.py::arc_usdc_address). */
export const ARC_USDC_ADDRESS =
  "0x3600000000000000000000000000000000000000" as const;

/** Circle testnet faucet — choose Arc Testnet → USDC (gas is paid in USDC on Arc). */
export const ARC_FAUCET_URL = "https://faucet.circle.com";
