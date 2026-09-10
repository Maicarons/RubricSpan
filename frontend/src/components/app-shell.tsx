"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandMark } from "@/components/brand-mark";
import {
  IconBook,
  IconChart,
  IconChevronDown,
  IconCloudOff,
  IconMenu,
  IconPen,
  IconSparkle,
  IconUpload,
  IconX,
} from "@/components/icons";
import { ThemeToggle } from "@/components/theme-toggle";
import { getApiBase, checkHealth } from "@/lib/api";

const PAGES: { href: string; label: string; icon: React.ReactNode; group: string; tag?: string }[] = [
  { href: "/questions", label: "试题管理", icon: <IconBook className="h-[18px] w-[18px]" />, group: "阅卷工作" },
  { href: "/answers", label: "答卷上传", icon: <IconUpload className="h-[18px] w-[18px]" />, group: "阅卷工作" },
  { href: "/workbench", label: "阅卷工作台", icon: <IconPen className="h-[18px] w-[18px]" />, group: "阅卷工作" },
  { href: "/results", label: "结果与统计", icon: <IconChart className="h-[18px] w-[18px]" />, group: "阅卷工作" },
  { href: "/offline", label: "离线演示", icon: <IconCloudOff className="h-[18px] w-[18px]" />, group: "模式", tag: "试验" },
];

const GROUP_ORDER = ["阅卷工作", "模式"];
const GROUPS = Object.fromEntries(GROUP_ORDER.map((g) => [g, PAGES.filter((p) => p.group === g)]));

function currentTitle(pathname: string): string {
  const hit = PAGES.find((p) => (p.href === "/" ? pathname === "/" : pathname.startsWith(p.href)));
  return hit?.label ?? "阅微";
}

function NavItems({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  return (
    <nav aria-label="工作台导航" className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
      {GROUP_ORDER.map((g) => (
        <div key={g}>
          <p className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-ink-3">
            {g}
          </p>
          <ul className="space-y-0.5">
            {GROUPS[g].map((p) => {
              const active = pathname.startsWith(p.href);
              return (
                <li key={p.href}>
                  <Link
                    href={p.href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors duration-200 ${
                      active
                        ? "bg-accent-soft font-medium text-accent-strong"
                        : "text-ink-2 hover:bg-surface-2 hover:text-ink"
                    }`}
                  >
                    <span className={active ? "text-accent" : "text-ink-3"}>{p.icon}</span>
                    {p.label}
                    {p.tag && (
                      <span className="ml-auto rounded-full bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-3">
                        {p.tag}
                      </span>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function SidebarFooter() {
  return (
    <div className="border-t border-line p-3">
      <Link
        href="/"
        className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
      >
        <IconChevronDown className="h-3.5 w-3.5 rotate-90 text-ink-3" />
        返回门户
      </Link>
    </div>
  );
}

type ServiceState = "checking" | "online" | "offline";

/** 中台外壳：桌面侧边栏 + 移动抽屉 + 顶栏（页面标题/服务状态/亮暗切换）。 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [service, setService] = useState<ServiceState>("checking");

  useEffect(() => {
    let alive = true;
    const probe = async () => {
      const ok = await checkHealth();
      if (alive) setService(ok ? "online" : "offline");
    };
    void probe();
    const timer = setInterval(probe, 30_000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  const serviceUi: Record<ServiceState, { dot: string; label: string; hint: string }> = {
    checking: { dot: "bg-ink-3", label: "检测中", hint: "正在探测后端服务…" },
    online: { dot: "bg-ok", label: "在线", hint: `服务就绪 · ${getApiBase()}` },
    offline: { dot: "bg-danger", label: "离线", hint: `未连上 ${getApiBase()}` },
  };

  return (
    <div className="min-h-screen">
      {/* 桌面侧边栏 */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-line bg-surface lg:flex">
        <div className="border-b border-line px-4 py-4">
          <BrandMark href="/" />
        </div>
        <NavItems pathname={pathname} />
        <SidebarFooter />
      </aside>

      {/* 移动抽屉 */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="导航菜单">
          <div className="absolute inset-0 bg-black/40" onClick={() => setDrawerOpen(false)} />
          <div className="absolute inset-y-0 left-0 flex w-72 animate-fade-in flex-col bg-surface shadow-pop">
            <div className="flex items-center justify-between border-b border-line px-4 py-4">
              <BrandMark href="/" />
              <button
                type="button"
                aria-label="关闭导航"
                onClick={() => setDrawerOpen(false)}
                className="inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-ink-2 transition-colors hover:bg-surface-2"
              >
                <IconX className="h-5 w-5" />
              </button>
            </div>
            <NavItems pathname={pathname} onNavigate={() => setDrawerOpen(false)} />
            <SidebarFooter />
          </div>
        </div>
      )}

      {/* 主内容区 */}
      <div className="flex min-h-screen flex-col lg:pl-60">
        <header className="sticky top-0 z-20 border-b border-line bg-canvas/85 backdrop-blur">
          <div className="flex h-14 items-center gap-3 px-4 sm:px-6">
            <button
              type="button"
              aria-label="打开导航"
              onClick={() => setDrawerOpen(true)}
              className="inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-ink-2 transition-colors hover:bg-surface-2 lg:hidden"
            >
              <IconMenu className="h-5 w-5" />
            </button>
            <h1 className="font-serif text-base font-semibold tracking-wide text-ink">
              {currentTitle(pathname)}
            </h1>
            <div className="ml-auto flex items-center gap-1.5">
              <span
                title={serviceUi[service].hint}
                className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-xs text-ink-2"
              >
                <span aria-hidden="true" className={`h-2 w-2 rounded-full ${serviceUi[service].dot}`} />
                {serviceUi[service].label}
              </span>
              <span className="hidden items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-medium text-accent-strong sm:inline-flex">
                <IconSparkle className="h-3 w-3" /> 演示
              </span>
              <ThemeToggle />
            </div>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {children}
        </main>
        <footer className="border-t border-line px-6 py-4 text-center text-xs text-ink-3">
          阅微 RubricSpan · 本地推理阅卷平台 · AGPL-3.0
        </footer>
      </div>
    </div>
  );
}