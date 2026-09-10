import type { Config } from "tailwindcss";

/**
 * 墨卷 · Ink & Vermilion 设计系统令牌（与 demo 前端一致）。
 * 语义色经 CSS 变量（globals.css）在亮/暗主题间切换，构建期映射为 Tailwind 工具类。
 */
const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "rgb(var(--canvas) / <alpha-value>)",
        "canvas-deep": "rgb(var(--canvas-deep) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        "surface-2": "rgb(var(--surface-2) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        "ink-2": "rgb(var(--ink-2) / <alpha-value>)",
        "ink-3": "rgb(var(--ink-3) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        "line-strong": "rgb(var(--line-strong) / <alpha-value>)",
        accent: {
          DEFAULT: "rgb(var(--accent) / <alpha-value>)",
          strong: "rgb(var(--accent-strong) / <alpha-value>)",
          soft: "rgb(var(--accent-soft) / <alpha-value>)",
          ink: "rgb(var(--accent-ink) / <alpha-value>)",
        },
        ok: { DEFAULT: "rgb(var(--ok) / <alpha-value>)", soft: "rgb(var(--ok-soft) / <alpha-value>)" },
        warn: { DEFAULT: "rgb(var(--warn) / <alpha-value>)", soft: "rgb(var(--warn-soft) / <alpha-value>)" },
        danger: { DEFAULT: "rgb(var(--danger) / <alpha-value>)", soft: "rgb(var(--danger-soft) / <alpha-value>)" },
        info: { DEFAULT: "rgb(var(--info) / <alpha-value>)", soft: "rgb(var(--info-soft) / <alpha-value>)" },
        "hit-exact": { DEFAULT: "rgb(var(--hit-exact) / <alpha-value>)", ink: "rgb(var(--hit-exact-ink) / <alpha-value>)" },
        "hit-semantic": { DEFAULT: "rgb(var(--hit-semantic) / <alpha-value>)", ink: "rgb(var(--hit-semantic-ink) / <alpha-value>)" },
        "hit-partial": { DEFAULT: "rgb(var(--hit-partial) / <alpha-value>)", ink: "rgb(var(--hit-partial-ink) / <alpha-value>)" },
      },
      fontFamily: {
        sans: ['"PingFang SC"', '"Microsoft YaHei"', '"Noto Sans SC"', '"Source Han Sans SC"', "system-ui", "sans-serif"],
        serif: ['"Songti SC"', '"Source Han Serif SC"', '"Noto Serif SC"', "SimSun", "Georgia", "serif"],
        kai: ['"Kaiti SC"', '"STKaiti"', '"KaiTi"', '"LXGW WenKai"', '"华文楷体"', "cursive"],
        mono: ['ui-monospace', '"SF Mono"', '"Cascadia Code"', '"JetBrains Mono"', "Consolas", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgb(80 60 30 / 0.05), 0 10px 30px -14px rgb(80 60 30 / 0.14)",
        "card-hover": "0 2px 4px rgb(80 60 30 / 0.06), 0 16px 40px -16px rgb(80 60 30 / 0.22)",
        pop: "0 12px 40px -12px rgb(15 12 8 / 0.35)",
      },
    },
  },
  plugins: [],
};

export default config;