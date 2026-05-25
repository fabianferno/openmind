"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

/**
 * Demo mode toggles WHO signs the on-chain anchor/settle txns:
 *   ON  → the server wallet signs (default; what the live demo has always done).
 *   OFF → the authenticated user's Privy wallet signs client-side on Arc.
 * Persisted in localStorage so a judge's choice survives reloads.
 */
const KEY = "openmind.demoMode";

type Ctx = { demoMode: boolean; setDemoMode: (v: boolean) => void };

const DemoModeContext = createContext<Ctx>({
  demoMode: true,
  setDemoMode: () => {},
});

export function DemoModeProvider({ children }: { children: React.ReactNode }) {
  const [demoMode, setDemoModeState] = useState(true);

  useEffect(() => {
    // hydrate from localStorage after mount (SSR has no window)
    const stored = window.localStorage.getItem(KEY);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (stored !== null) setDemoModeState(stored === "true");
  }, []);

  const setDemoMode = useCallback((v: boolean) => {
    setDemoModeState(v);
    window.localStorage.setItem(KEY, String(v));
  }, []);

  return (
    <DemoModeContext.Provider value={{ demoMode, setDemoMode }}>
      {children}
    </DemoModeContext.Provider>
  );
}

export function useDemoMode() {
  return useContext(DemoModeContext);
}
