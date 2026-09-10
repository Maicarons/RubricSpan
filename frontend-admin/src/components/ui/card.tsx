import type { HTMLAttributes, ReactNode } from "react";

export function Card({ className = "", ...rest }: HTMLAttributes<HTMLElement>) {
  return <section className={`rounded-xl border border-line bg-surface shadow-card ${className}`} {...rest} />;
}

export function CardHeader({ title, desc, action, className = "" }: { title: ReactNode; desc?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={`flex flex-wrap items-start justify-between gap-3 ${className}`}>
      <div>
        <h2 className="font-serif text-base font-semibold tracking-wide text-ink">{title}</h2>
        {desc && <p className="mt-1 text-sm text-ink-2">{desc}</p>}
      </div>
      {action}
    </div>
  );
}

export function PageHeader({ title, desc, action }: { title: ReactNode; desc?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="font-serif text-2xl font-bold tracking-wide text-ink">{title}</h1>
        {desc && <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-ink-2">{desc}</p>}
      </div>
      {action && <div className="flex items-center gap-2">{action}</div>}
    </div>
  );
}