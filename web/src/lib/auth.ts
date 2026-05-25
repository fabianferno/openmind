"use client";

import { useCallback } from "react";
import { usePrivy, useWallets } from "@privy-io/react-auth";

/**
 * Build-time constant: whether Privy is configured. Because it's inlined at
 * build and never changes between renders, branching on it before the Privy
 * hooks keeps the rules-of-hooks invariant (the branch is stable for the app's
 * whole life) while letting the app run ungated if the key is missing.
 */
export const HAS_PRIVY = Boolean(process.env.NEXT_PUBLIC_PRIVY_APP_ID);

export type Auth = {
  ready: boolean;
  authenticated: boolean;
  hasPrivy: boolean;
  address: string | null;
  login: () => void;
  logout: () => void;
};

export function useAuth(): Auth {
  if (!HAS_PRIVY) {
    return {
      ready: true,
      authenticated: false,
      hasPrivy: false,
      address: null,
      login: () => {},
      logout: () => {},
    };
  }
  /* eslint-disable react-hooks/rules-of-hooks */
  const { ready, authenticated, user, login, logout } = usePrivy();
  const { wallets } = useWallets();
  /* eslint-enable react-hooks/rules-of-hooks */
  const embedded =
    wallets.find((w) => w.walletClientType === "privy") ?? wallets[0];
  const address = embedded?.address ?? user?.wallet?.address ?? null;
  return { ready, authenticated, hasPrivy: true, address, login, logout };
}

/**
 * Returns a wrapper that runs `fn` only when the user is logged in, otherwise
 * opening the Privy login modal. Used to gate action buttons (discover, run).
 */
export function useRequireAuth() {
  const { authenticated, login, hasPrivy } = useAuth();
  return useCallback(
    (fn: () => void) => {
      if (hasPrivy && !authenticated) {
        login();
        return;
      }
      fn();
    },
    [authenticated, login, hasPrivy],
  );
}
