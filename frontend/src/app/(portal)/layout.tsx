import type { Metadata } from "next";
import { PortalNav } from "@/components/portal-nav";
import { BrandMark } from "@/components/brand-mark";

export const metadata: Metadata = {
  title: "阅微 RubricSpan",
  description:
    "本地化智能阅卷平台：录入试题 → 解析标准答案 → 批量评分 → 审阅反馈，推理全程本地完成。",
};

/** 前台门户壳：顶栏导航 + 页脚。 */
export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <PortalNav />
      {children}
      <footer className="mt-16 border-t border-line bg-canvas-deep/60">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-6 py-8 text-center sm:flex-row sm:text-left">
          <div className="flex flex-col items-center gap-2 sm:items-start">
            <BrandMark />
            <p className="text-xs leading-relaxed text-ink-3">
              主观题阅卷教师模型 · 本地推理优先，数据不出本机
            </p>
          </div>
          <div className="flex items-center gap-4 text-xs text-ink-3">
            <span>AGPL-3.0</span>
            <span aria-hidden="true" className="h-3 w-px bg-line-strong" />
            <span>Rust 引擎 · Next.js 前端</span>
            <span aria-hidden="true" className="h-3 w-px bg-line-strong" />
            <a href="/admin" className="text-ink-2 transition-colors hover:text-accent">
              管理后台
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}