import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RubricSpan 阅微 · 主观题阅卷系统",
  description: "本地化智能阅卷：上传试卷 → 作答识别 → 自动评分 → 审阅反馈",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
