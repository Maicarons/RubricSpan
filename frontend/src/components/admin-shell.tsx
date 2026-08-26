"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandMark } from "@/components/brand-mark";
import { IconChevronDown, IconGrid, IconSliders } from "@/components/icons";
import { ThemeToggle } from "@/components/theme-toggle";

const TABS = [
  { href: "/admin", label: "总览", icon: <IconGrid className="h-4 w-4" /> },
  { href: "/admin/settings", label: "设置", icon: <IconSliders className="h-4 w-4" /> },
];

/** 管理后台壳：朱批顶线 + 顶部标签导航，与工作台视觉区隔。 */
export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="min-h-screen">
      {/* 朱批线：管理后台标识色 */}
      <div aria-hidden="true" className="h-1 w-full bg-gradient-to-r from-accent via-accent/70 to-accent/20" />
      <header className="sticky top-0 z-30 border-b border-line bg-canvas/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-4 px-5">
          <BrandMark href="/" compact />
          <span className="hidden items-center gap-1 rounded-md bg-accent-soft px-2 py-1 text-xs font-medium text-accent-strong sm:inline-flex">
            管理后台
          </span>
          <nav aria-label="管理后台导航" className="ml-2 flex items-center gap-1">
            {TABS.map((t) => {
              const active = pathname === t.href || (t.href !== "/admin" && pathname.startsWith(t.href));
              return (
                <Link
                  key={t.href}
                  href={t.href}
                  aria-current={active ? "page" : undefined}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition-colors ${
                    active
                      ? "bg-accent-soft font-medium text-accent-strong"
                      : "text-ink-2 hover:bg-surface-2 hover:text-ink"
                  }`}
                >
                  {t.icon}
                  {t.label}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <Link
              href="/questions"
              className="hidden items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink sm:inline-flex"
            >
              进入工作台
            </Link>
            <Link
              href="/"
              aria-label="返回门户"
              title="返回门户"
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
            >
              <IconChevronDown className="h-4 w-4 rotate-90" />
            </Link>
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl px-5 py-8">{children}</main>
    </div>
  );
}