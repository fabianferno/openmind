"use client";

import { motion } from "framer-motion";
import type { Citation } from "@/lib/types";
import { SectionLabel } from "./ui";

export function EvidenceFeed({ citations }: { citations: Citation[] }) {
  return (
    <div className="panel p-4">
      <SectionLabel index="02">Date-bounded evidence</SectionLabel>
      {citations.length === 0 ? (
        <p className="mono mt-4 text-[11px] text-faint">
          Sources are filtered by a temporal guard — nothing published after the market&apos;s
          reasoning cutoff is allowed in.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {citations.slice(0, 6).map((c, i) => (
            <motion.li
              key={c.url + i}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.06 }}
              className="group border-l border-line pl-3"
            >
              <a href={c.url} target="_blank" rel="noreferrer" className="block">
                <div className="mono mb-0.5 text-[10px] uppercase tracking-[0.1em] text-faint">
                  {c.published_date?.slice(0, 10) || "undated"}
                </div>
                <div className="text-[12px] leading-snug text-muted transition-colors group-hover:text-text">
                  {c.title || c.url}
                </div>
              </a>
            </motion.li>
          ))}
        </ul>
      )}
    </div>
  );
}
