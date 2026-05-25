import { cn } from "@/lib/utils";

export function SectionLabel({
  children,
  index,
  className,
}: {
  children: React.ReactNode;
  index?: string;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      {index && <span className="label text-signal">{index}</span>}
      <span className="label">{children}</span>
      <span className="h-px flex-1 bg-line" />
    </div>
  );
}

export function Pill({
  children,
  tone = "neutral",
  className,
}: {
  children: React.ReactNode;
  tone?: "neutral" | "signal" | "amber" | "cyan" | "danger";
  className?: string;
}) {
  const tones = {
    neutral: "border-line-bright text-muted",
    signal: "border-signal/40 text-signal bg-signal/5",
    amber: "border-amber/40 text-amber bg-amber/5",
    cyan: "border-cyan/40 text-cyan bg-cyan/5",
    danger: "border-danger/40 text-danger bg-danger/5",
  } as const;
  return (
    <span
      className={cn(
        "mono inline-flex items-center gap-1.5 border px-2 py-0.5 text-[10px] uppercase tracking-[0.12em]",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Dot({ tone = "signal" }: { tone?: "signal" | "amber" | "muted" }) {
  const c = { signal: "bg-signal", amber: "bg-amber", muted: "bg-faint" }[tone];
  return <span className={cn("inline-block size-1.5 rounded-full", c)} />;
}

export function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "signal" | "amber" | "default";
}) {
  const c =
    tone === "signal" ? "text-signal" : tone === "amber" ? "text-amber" : "text-text";
  return (
    <div className="panel p-4">
      <div className="label mb-2">{label}</div>
      <div className={cn("mono text-2xl font-medium tabular-nums", c)}>{value}</div>
      {sub && <div className="mono mt-1 text-[11px] text-faint">{sub}</div>}
    </div>
  );
}
