type Tone = "accent" | "ok" | "warn" | "danger" | "info";

const FILLS: Record<Tone, string> = {
  accent: "bg-accent",
  ok: "bg-ok",
  warn: "bg-warn",
  danger: "bg-danger",
  info: "bg-info",
};

/** 迷你进度条：value 为 0-100 百分比。 */
export function Progress({
  value,
  tone = "accent",
  className = "",
}: {
  value: number;
  tone?: Tone;
  className?: string;
}) {
  const v = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(v)}
      aria-valuemin={0}
      aria-valuemax={100}
      className={`h-2 w-full overflow-hidden rounded-full bg-surface-2 ${className}`}
    >
      <div
        className={`h-full rounded-full transition-[width] duration-300 ease-out ${FILLS[tone]}`}
        style={{ width: `${v}%` }}
      />
    </div>
  );
}