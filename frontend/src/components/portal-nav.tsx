"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandMark } from "@/components/brand-mark";
import { IconShield } from "@/components/icons";
import { ThemeToggle } from "@/components/theme-toggle";

const anchorLinks = [
  { href: "#features", label: "功能" },
  { href: "#workflow", label: "工作流" },
  { href: "#tech", label: "技术特性" },
];

/** 前台门户顶栏：锚点导航 + 亮暗切换 + 进入工作台 CTA。 */
export function PortalNav() {
  const pathname = usePathname();
  const active = (href: string) => (href.startsWith("/") ? pathname.startsWith(href) : false);

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas/85 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-6">
        <BrandMark />
        <nav aria-label="主导航" className="ml-4 hidden items-center gap-1 md:flex">
          {anchorLinks.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="rounded-md px-3 py-1.5 text-sm text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
            >
              {l.label}
            </a>
          ))}
          <Link
            href="/offline"
            aria-current={active("/offline") ? "page" : undefined}
            className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
              active("/offline")
                ? "bg-accent-soft text-accent-strong"
                : "text-ink-2 hover:bg-surface-2 hover:text-ink"
            }`}
          >
            离线演示
          </Link>
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <Link
            href="/admin"
            aria-current={active("/admin") ? "page" : undefined}
            className="hidden items-center gap-1.5 rounded-md px-3 py-1.5 text-sm text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink sm:inline-flex"
          >
            <IconShield className="h-4 w-4" />
            管理后台
          </Link>
          <ThemeToggle />
          <Link
            href="/questions"
            className="hidden items-center gap-1.5 rounded-lg bg-accent px-3.5 py-2 text-sm font-medium text-accent-ink shadow-sm transition-colors hover:bg-accent-strong sm:inline-flex"
          >
            进入工作台
          </Link>
          <Link
            href="/questions"
            className="inline-flex items-center rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-ink shadow-sm transition-colors hover:bg-accent-strong sm:hidden"
          >
            进入
          </Link>
        </div>
      </div>
    </header>
  );
}