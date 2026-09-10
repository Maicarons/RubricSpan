import type { ReactNode } from "react";

type Tone = "accent" | "ok" | "warn" | "danger" | "info" | "neutral";
const TONES: Record<Tone, string> = {
  accent: "text-accent bg-accent-soft",
  ok: "text-ok bg-ok-soft",
  warn: "text-warn bg-warn-soft",
  danger: "text-danger bg-danger-soft",
  info: "text-info bg-info-soft",
  neutral: "text-ink-2 bg-surface-2",
};

export interface StatCardProps { label: string; value: ReactNode; sub?: ReactNode; icon?: ReactNode; tone?: Tone; }

export function StatCard({ label, value, sub, icon, tone = "accent" }: StatCardProps) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-xl border border-line bg-surface p-4 shadow-card">
      <div className="min-w-0">
        <div className="text-xs font-medium uppercase tracking-wider text-ink-3">{label}</div>
        <div className="mt-1.5 font-serif text-2xl font-bold tracking-tight text-ink">{value}</div>
        {sub && <div className="mt-1 text-xs text-ink-2">{sub}</div>}
      </div>
      {icon && <span aria-hidden="true" className={`rounded-lg p-2.5 ${TONES[tone]}`}>{icon}</span>}
    </div>
  );
}