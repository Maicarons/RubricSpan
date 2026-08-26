import type { Metadata, Viewport } from "next";
import { THEME_STORAGE_KEY } from "@/lib/theme";
import { ThemeProvider } from "@/lib/theme";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "阅微 RubricSpan · 主观题阅卷系统",
    template: "%s · 阅微 RubricSpan",
  },
  description:
    "本地化智能阅卷平台：录入试题 → 解析标准答案 → 批量评分 → 审阅反馈，推理全程本地完成。",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f3ed" },
    { media: "(prefers-color-scheme: dark)", color: "#11100e" },
  ],
};

/**
 * 首帧防闪烁：在 React 水合之前同步应用主题 class。
 * 与 lib/theme.tsx 的 localStorage key / class 约定保持一致。
 */
const themeInitScript = `(function(){try{var t=localStorage.getItem('${THEME_STORAGE_KEY}');var d=t?t==='dark':window.matchMedia('(prefers-color-scheme: dark)').matches;document.documentElement.classList.toggle('dark',d)}catch(e){}})()`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // 主题 class 在 hydration 前由内联脚本写入，suppressHydrationWarning 避免服务端/客户端类名不一致告警
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="min-h-screen bg-canvas text-ink antialiased">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}