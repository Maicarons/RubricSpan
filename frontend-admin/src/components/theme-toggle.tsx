"use client";

import { useTheme } from "@/lib/theme";
import { IconMoon, IconSun } from "@/components/icons";

export function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const dark = theme === "dark";
  return (
    <button type="button" onClick={toggleTheme} aria-label={dark ? "切换到亮色模式" : "切换到暗黑模式"} title={dark ? "亮色模式" : "暗黑模式"}
      className={`inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-ink-2 transition-colors duration-200 hover:bg-surface-2 hover:text-ink ${className}`}>
      <span className="transition-transform duration-300" style={{ transform: dark ? "rotate(0deg)" : "rotate(90deg)" }}>
        {dark ? <IconMoon /> : <IconSun />}
      </span>
    </button>
  );
}