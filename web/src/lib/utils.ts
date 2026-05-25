import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const truncHash = (h?: string | null, n = 6) =>
  !h ? "—" : `${h.slice(0, n + 2)}…${h.slice(-4)}`;

export const fmtPct = (v?: number | null) =>
  v == null ? "—" : `${(v * 100).toFixed(1)}%`;

export const fmtUsd = (v?: number | null) =>
  v == null ? "—" : `$${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

// deterministic colour per entity type — drawn from a curated terminal palette
const PALETTE = [
  "#c6f24a", "#62d2e6", "#f2b441", "#e07be0", "#7ce0a3",
  "#f2603c", "#9a8cf2", "#e6d262", "#62e6b0", "#e6628a",
];
export function typeColor(type: string) {
  let h = 0;
  for (let i = 0; i < type.length; i++) h = (h * 31 + type.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

export const explorerTx = (base: string, tx: string) => `${base}/tx/${tx}`;
