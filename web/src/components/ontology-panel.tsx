"use client";

import { motion } from "framer-motion";
import type { Ontology } from "@/lib/types";
import { typeColor } from "@/lib/utils";
import { SectionLabel } from "./ui";

export function OntologyPanel({
  ontology,
  nodeCount,
  edgeCount,
}: {
  ontology: Ontology | null;
  nodeCount: number;
  edgeCount: number;
}) {
  return (
    <div className="panel flex h-full flex-col p-4">
      <SectionLabel index="01">Ontology</SectionLabel>

      {!ontology ? (
        <p className="mono mt-4 text-[11px] leading-relaxed text-faint">
          The agent designs a schema of entity and relationship types tailored to this
          market before reading the evidence.
        </p>
      ) : (
        <div className="mt-4 space-y-5">
          <div>
            <div className="label mb-2 text-faint">Entity types</div>
            <div className="flex flex-wrap gap-1.5">
              {ontology.entity_types.map((t, i) => (
                <motion.span
                  key={t}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="mono inline-flex items-center gap-1.5 border px-2 py-1 text-[11px]"
                  style={{ borderColor: `${typeColor(t)}55`, color: typeColor(t) }}
                >
                  <span className="size-1.5 rounded-full" style={{ background: typeColor(t) }} />
                  {t}
                </motion.span>
              ))}
            </div>
          </div>

          <div>
            <div className="label mb-2 text-faint">Relation types</div>
            <div className="flex flex-wrap gap-1.5">
              {ontology.relation_types.map((t, i) => (
                <motion.span
                  key={t}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.2 + i * 0.04 }}
                  className="mono border border-line-bright px-2 py-1 text-[10px] uppercase tracking-[0.08em] text-muted"
                >
                  {t}
                </motion.span>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="mt-auto grid grid-cols-2 gap-px border-t border-line pt-4">
        <div>
          <div className="mono text-2xl tabular-nums text-signal">{nodeCount}</div>
          <div className="label mt-0.5">Entities</div>
        </div>
        <div>
          <div className="mono text-2xl tabular-nums text-cyan">{edgeCount}</div>
          <div className="label mt-0.5">Relations</div>
        </div>
      </div>
    </div>
  );
}
