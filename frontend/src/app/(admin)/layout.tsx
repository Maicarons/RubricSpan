import type { Metadata } from "next";
import { AdminShell } from "@/components/admin-shell";

export const metadata: Metadata = {
  title: "管理后台",
  description:
    "阅微 RubricSpan 管理后台：运行统计、系统状态与服务设置（聚合数据来自 /api/admin/stats 与 /api/admin/config）。",
};

/** 后台（admin）壳：管理后台专属布局。 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <AdminShell>{children}</AdminShell>;
}