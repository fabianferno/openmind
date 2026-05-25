"use client";

import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type Simulation,
} from "d3-force";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import type { GraphEdge, GraphNode } from "@/lib/types";
import { typeColor } from "@/lib/utils";

type SimNode = GraphNode & { x: number; y: number };
type SimLink = { source: SimNode | string; target: SimNode | string; type: string };

export function GraphCanvas({
  nodes,
  edges,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 760, h: 540 });
  const simRef = useRef<Simulation<SimNode, undefined> | null>(null);
  const nodesRef = useRef<SimNode[]>([]);
  const linksRef = useRef<SimLink[]>([]);
  const [, setTick] = useState(0);
  const [hover, setHover] = useState<SimNode | null>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      if (r.width && r.height) setSize({ w: r.width, h: r.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const { w, h } = size;
    const existing = new Map(nodesRef.current.map((n) => [n.id, n]));
    const simNodes: SimNode[] = nodes.map((n) => {
      const prev = existing.get(n.id);
      return prev
        ? Object.assign(prev, n)
        : { ...n, x: w / 2 + (Math.random() - 0.5) * 80, y: h / 2 + (Math.random() - 0.5) * 80 };
    });
    nodesRef.current = simNodes;
    const ids = new Set(simNodes.map((n) => n.id));
    const simLinks: SimLink[] = edges
      .filter((e) => ids.has(e.source) && ids.has(e.target))
      .map((e) => ({ source: e.source, target: e.target, type: e.type }));
    linksRef.current = simLinks;

    if (!simRef.current) {
      simRef.current = forceSimulation<SimNode>(simNodes)
        .force("charge", forceManyBody().strength(-280))
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        .force("link", forceLink<SimNode, SimLink>(simLinks).id((d: any) => d.id).distance(96).strength(0.45))
        .force("center", forceCenter(w / 2, h / 2))
        .force("collide", forceCollide(36))
        .on("tick", () => setTick((t) => t + 1));
    } else {
      const sim = simRef.current;
      sim.nodes(simNodes);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (sim.force("link") as any).links(simLinks);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (sim.force("center") as any).x(w / 2).y(h / 2);
      sim.alpha(0.9).restart();
    }
  }, [nodes, edges, size]);

  useEffect(() => {
    return () => {
      simRef.current?.stop();
    };
  }, []);

  const simNodes = nodesRef.current;
  const simLinks = linksRef.current;
  const radius = (n: GraphNode) => 8 + Math.min(n.degree ?? 0, 6) * 2.2;

  return (
    <div ref={wrapRef} className="relative h-full w-full overflow-hidden">
      <div className="grid-bg pointer-events-none absolute inset-0" />
      {simNodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="mono text-[11px] uppercase tracking-[0.2em] text-faint">
            awaiting entity extraction
          </span>
        </div>
      )}
      <svg width={size.w} height={size.h} className="relative">
        <defs>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3.5" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {simLinks.map((l, i) => {
          const s = l.source as SimNode;
          const t = l.target as SimNode;
          if (!s.x || !t.x) return null;
          const active = hover && (s.id === hover.id || t.id === hover.id);
          return (
            <motion.line
              key={`${s.id}-${t.id}-${i}`}
              initial={{ opacity: 0 }}
              animate={{ opacity: active ? 0.9 : 0.28 }}
              x1={s.x}
              y1={s.y}
              x2={t.x}
              y2={t.y}
              stroke={active ? "#c6f24a" : "#3a4047"}
              strokeWidth={active ? 1.5 : 1}
            />
          );
        })}

        <AnimatePresence>
          {simNodes.map((n) => {
            const c = typeColor(n.type);
            const r = radius(n);
            const dim = hover && hover.id !== n.id &&
              !simLinks.some(
                (l) =>
                  ((l.source as SimNode).id === hover.id && (l.target as SimNode).id === n.id) ||
                  ((l.target as SimNode).id === hover.id && (l.source as SimNode).id === n.id),
              );
            return (
              <g
                key={n.id}
                transform={`translate(${n.x},${n.y})`}
                onMouseEnter={() => setHover(n)}
                onMouseLeave={() => setHover(null)}
                style={{ cursor: "pointer", opacity: dim ? 0.25 : 1, transition: "opacity 0.2s" }}
              >
                <motion.circle
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: "spring", stiffness: 240, damping: 16 }}
                  r={r}
                  fill={c}
                  fillOpacity={0.12}
                  stroke={c}
                  strokeWidth={1.4}
                  filter="url(#glow)"
                />
                <motion.circle
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: "spring", stiffness: 300, damping: 18, delay: 0.05 }}
                  r={2.5}
                  fill={c}
                />
                <text
                  x={r + 6}
                  y={4}
                  className="mono"
                  fontSize={11}
                  fill="#e9e7df"
                  style={{ pointerEvents: "none" }}
                >
                  {n.label.length > 22 ? n.label.slice(0, 21) + "…" : n.label}
                </text>
              </g>
            );
          })}
        </AnimatePresence>
      </svg>

      {hover && (
        <div className="panel pointer-events-none absolute bottom-3 left-3 max-w-xs p-3">
          <div className="mb-1 flex items-center gap-2">
            <span
              className="size-2 rounded-full"
              style={{ background: typeColor(hover.type) }}
            />
            <span className="mono text-[10px] uppercase tracking-[0.12em]" style={{ color: typeColor(hover.type) }}>
              {hover.type}
            </span>
          </div>
          <div className="serif text-base leading-tight">{hover.label}</div>
          {hover.summary && (
            <div className="mt-1 text-[12px] leading-snug text-muted">{hover.summary}</div>
          )}
        </div>
      )}
    </div>
  );
}
