"use client";

import { PrivyProvider } from "@privy-io/react-auth";
import { DemoModeProvider } from "@/lib/demo-mode";
import { arcTestnet } from "@/lib/chains";

const APP_ID = process.env.NEXT_PUBLIC_PRIVY_APP_ID;

export function Providers({ children }: { children: React.ReactNode }) {
  // Without an app id Privy can't initialise — render the app ungated rather
  // than crashing, so a missing key never blocks the demo locally.
  if (!APP_ID) {
    if (typeof window !== "undefined") {
      console.warn("NEXT_PUBLIC_PRIVY_APP_ID not set — auth disabled.");
    }
    return <DemoModeProvider>{children}</DemoModeProvider>;
  }

  return (
    <PrivyProvider
      appId={APP_ID}
      config={{
        appearance: { theme: "dark", accentColor: "#2bd576" },
        embeddedWallets: { ethereum: { createOnLogin: "users-without-wallets" } },
        defaultChain: arcTestnet,
        supportedChains: [arcTestnet],
      }}
    >
      <DemoModeProvider>{children}</DemoModeProvider>
    </PrivyProvider>
  );
}
