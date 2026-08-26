import Link from "next/link";

/**
 * 品牌标识：朱砂印章「阅」字 + 阅微字号。
 * 印章呼应朱批（朱砂批注）传统，作为全站识别点。
 */
export function BrandMark({
  href = "/",
  compact = false,
}: {
  href?: string;
  compact?: boolean;
}) {
  return (
    <Link href={href} className="group flex shrink-0 items-center gap-2.5" aria-label="阅微 RubricSpan 首页">
      <span
        aria-hidden="true"
        className="flex h-9 w-9 select-none items-center justify-center rounded-lg bg-accent font-kai text-lg font-bold text-accent-ink shadow-sm transition-transform duration-200 group-hover:scale-105"
      >
        阅
      </span>
      {!compact && (
        <span className="flex flex-col leading-none">
          <span className="font-serif text-base font-bold tracking-[0.18em] text-ink">阅微</span>
          <span className="mt-1 text-[10px] font-medium tracking-[0.22em] text-ink-3">
            RUBRICSPAN
          </span>
        </span>
      )}
    </Link>
  );
}