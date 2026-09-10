"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import { BrandMark } from "@/components/brand-mark";
import { IconGrid, IconSliders, IconBook, IconServer, IconChevronDown, IconMenu, IconX, IconHome, IconActivity } from "@/components/icons";
import { ThemeToggle } from "@/components/theme-toggle";
import { checkHealth } from "@/lib/api";

const NAV_ITEMS = [
  { href: "/", label: "总览", icon: <IconGrid className="h-[18px] w-[18px]" />, desc: "运行统计与工程概览" },
  { href: "/projects", label: "工程项目", icon: <IconBook className="h-[18px] w-[18px]" />, desc: "创建和管理阅卷工程" },
  { href: "/config", label: "系统配置", icon: <IconServer className="h-[18px] w-[18px]" />, desc: "服务信息、模型、LLM、评分参数" },
  { href: "/settings", label: "设置", icon: <IconSliders className="h-[18px] w-[18px]" />, desc: "API 地址与界面偏好" },
];

type ServiceState = "checking" | "online" | "offline";

/** 管理后台外壳：固定侧边栏 + 顶栏。 */
export function AdminShell({ children }: { children: React.ReactNode }) {
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
    return () => { alive = false; clearInterval(timer); };
  }, []);

  const serviceUi: Record<ServiceState, { dot: string; label: string }> = {
    checking: { dot: "bg-ink-3", label: "检测中" },
    online: { dot: "bg-ok", label: "在线" },
    offline: { dot: "bg-danger", label: "离线" },
  };

  function NavItems({ onNavigate }: { onNavigate?: () => void }) {
    return (
      <nav aria-label="管理导航" className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
          return (
            <Link key={item.href} href={item.href} onClick={onNavigate}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors duration-200 ${
                active
                  ? "bg-accent-soft font-medium text-accent-strong"
                  : "text-ink-2 hover:bg-surface-2 hover:text-ink"
              }`}>
              <span className={active ? "text-accent" : "text-ink-3"}>{item.icon}</span>
              <div className="min-w-0 flex-1">
                <div className="truncate">{item.label}</div>
                <div className="truncate text-[11px] text-ink-3">{item.desc}</div>
              </div>
            </Link>
          );
        })}
      </nav>
    );
  }

  return (
    <div className="min-h-screen">
      {/* 朱批线 */}
      <div aria-hidden="true" className="h-1 w-full bg-gradient-to-r from-accent via-accent/70 to-accent/20" />

      {/* 桌面侧边栏 */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-line bg-surface shadow-sm lg:flex">
        <div className="flex items-center justify-between border-b border-line px-4 py-4">
          <BrandMark href="/" />
        </div>
        <div className="border-b border-line px-3 py-2">
          <span className="inline-flex items-center gap-1 rounded-md bg-accent-soft px-2 py-1 text-xs font-medium text-accent-strong">
            管理后台
          </span>
        </div>
        <NavItems />
        <div className="border-t border-line p-3">
          <Link href="/"
            className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink">
            <IconHome className="h-[18px] w-[18px] text-ink-3" />
            返回首页
          </Link>
        </div>
      </aside>

      {/* 移动端抽屉 */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="导航菜单">
          <div className="absolute inset-0 bg-black/40" onClick={() => setDrawerOpen(false)} />
          <div className="absolute inset-y-0 left-0 flex w-72 animate-fade-in flex-col bg-surface shadow-pop">
            <div className="flex items-center justify-between border-b border-line px-4 py-4">
              <BrandMark href="/" />
              <button type="button" aria-label="关闭导航" onClick={() => setDrawerOpen(false)}
                className="inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-ink-2 transition-colors hover:bg-surface-2">
                <IconX className="h-5 w-5" />
              </button>
            </div>
            <NavItems onNavigate={() => setDrawerOpen(false)} />
          </div>
        </div>
      )}

      {/* 主内容区 */}
      <div className="flex min-h-screen flex-col lg:pl-60">
        <header className="sticky top-0 z-20 border-b border-line bg-canvas/85 backdrop-blur">
          <div className="flex h-14 items-center gap-3 px-4 sm:px-6">
            <button type="button" aria-label="打开导航" onClick={() => setDrawerOpen(true)}
              className="inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-ink-2 transition-colors hover:bg-surface-2 lg:hidden">
              <IconMenu className="h-5 w-5" />
            </button>
            <h1 className="font-serif text-base font-semibold tracking-wide text-ink">
              {NAV_ITEMS.find((i) => pathname === i.href || (i.href !== "/" && pathname.startsWith(i.href)))?.label ?? "管理后台"}
            </h1>
            <div className="ml-auto flex items-center gap-2">
              <span title={serviceUi[service].label}
                className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-xs text-ink-2">
                <span aria-hidden="true" className={`h-2 w-2 rounded-full ${serviceUi[service].dot}`} />
                {serviceUi[service].label}
              </span>
              <ThemeToggle />
            </div>
          </div>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 px-5 py-6 lg:py-8">{children}</main>
        <footer className="border-t border-line px-6 py-4 text-center text-xs text-ink-3">
          阅微 RubricSpan · 管理后台 · AGPL-3.0
        </footer>
      </div>
    </div>
  );
}