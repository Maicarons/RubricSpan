"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandMark } from "@/components/brand-mark";
import { IconSparkle } from "@/components/icons";
import { ThemeToggle } from "@/components/theme-toggle";

const anchorLinks = [
  { href: "#features", label: "功能" },
  { href: "#workflow", label: "工作流" },
  { href: "#tech", label: "技术特性" },
];

/** 前台门户顶栏：浮动式设计，磨砂玻璃效果，与内容区拉开层次。 */
export function PortalNav() {
  const pathname = usePathname();
  const active = (href: string) => (href.startsWith("/") ? pathname.startsWith(href) : false);

  return (
    <header className="fixed left-1/2 top-4 z-50 mx-auto w-[calc(100%-2rem)] max-w-6xl -translate-x-1/2 rounded-2xl border border-line bg-canvas/85 shadow-sm backdrop-blur-lg transition-shadow duration-200 hover:shadow-md">
      <div className="flex h-14 items-center gap-4 px-5">
        <BrandMark />
        <span className="hidden items-center gap-1 rounded-full bg-accent-soft px-2.5 py-0.5 text-[11px] font-medium text-accent-strong sm:inline-flex">
          <IconSparkle className="h-3 w-3" /> 演示版
        </span>
        <nav aria-label="主导航" className="ml-4 hidden items-center gap-1 md:flex">
          {anchorLinks.map((l) => (
            <a key={l.href} href={l.href}
              className="rounded-md px-3 py-1.5 text-sm text-ink-2 transition-colors duration-200 hover:bg-surface-2 hover:text-ink">
              {l.label}
            </a>
          ))}
          <Link href="/offline" aria-current={active("/offline") ? "page" : undefined}
            className={`rounded-md px-3 py-1.5 text-sm transition-colors duration-200 ${active("/offline") ? "bg-accent-soft text-accent-strong" : "text-ink-2 hover:bg-surface-2 hover:text-ink"}`}>
            离线演示
          </Link>
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <ThemeToggle />
          <Link href="/questions"
            className="hidden items-center gap-1.5 rounded-lg bg-accent px-3.5 py-2 text-sm font-medium text-accent-ink shadow-sm transition-all duration-200 hover:bg-accent-strong hover:shadow-md active:scale-[0.97] sm:inline-flex">
            进入工作台
          </Link>
          <Link href="/questions"
            className="inline-flex items-center rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-ink shadow-sm transition-all duration-200 hover:bg-accent-strong active:scale-[0.97] sm:hidden">
            进入
          </Link>
        </div>
      </div>
    </header>
  );
}