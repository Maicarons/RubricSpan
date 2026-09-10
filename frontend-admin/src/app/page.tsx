"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { getAdminConfig, getAdminStats, getApiBase, listProjects, type AdminConfig, type AdminStats, type Project } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, PageHeader } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { StatCard } from "@/components/ui/stat";
import { IconActivity, IconBook, IconCpu, IconDatabase, IconPen, IconRefresh, IconServer, IconUsers, IconArrowRight } from "@/components/icons";

const RATING_LABEL: Record<string, string> = { excellent: "优秀", good: "良好", pass: "及格", fail: "不及格" };
const RATING_FILL: Record<string, string> = { excellent: "bg-ok", good: "bg-info", pass: "bg-warn", fail: "bg-danger" };

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true); else setRefreshing(true);
    setErr(null);
    try {
      const [s, c, p] = await Promise.all([getAdminStats(), getAdminConfig(), listProjects()]);
      setStats(s); setConfig(c); setProjects(p.items);
    } catch (e) { setErr(String(e)); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const byQuestion = new Map<string, { point_id: number; hit: number; total: number }[]>();
  for (const ph of stats?.point_hits ?? []) {
    const arr = byQuestion.get(ph.question_id) ?? [];
    arr.push(ph); byQuestion.set(ph.question_id, arr);
  }

  return (
    <>
      <PageHeader title="管理后台 · 总览" desc="运行统计与工程概览——聚合数据由后端提供。"
        action={<Button onClick={() => void load(true)} loading={refreshing} icon={<IconRefresh className="h-4 w-4" />}>刷新</Button>} />

      <div className="mt-5 flex flex-wrap items-center gap-2">
        {config ? (<><Badge tone="ok" dot>服务在线</Badge><span className="text-xs text-ink-3">API 地址：<span className="font-mono text-ink-2">{getApiBase() || "同源（默认）"}</span> · 服务版本 v{config.server_version}</span></>)
          : err ? (<><Badge tone="danger" dot>服务离线</Badge><span className="text-xs text-ink-3">API 地址：<span className="font-mono text-ink-2">{getApiBase() || "同源"}</span></span></>)
          : <Badge tone="neutral" dot>检测中</Badge>}
      </div>

      {err && !loading && (
        <div role="alert" className="mt-4 rounded-lg border border-danger/40 bg-danger-soft px-3.5 py-3 text-sm leading-relaxed text-danger">
          无法读取服务数据：{err}
          <p className="mt-1 text-xs">请确认后端服务已启动，或到「设置」修改 API 地址。</p>
        </div>
      )}

      {loading ? (
        <div className="mt-6 space-y-4" aria-hidden="true">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{[0,1,2,3].map(i => <div key={i} className="h-24 animate-pulse rounded-xl border border-line bg-surface" />)}</div>
          <div className="h-64 animate-pulse rounded-xl border border-line bg-surface" />
          <div className="h-64 animate-pulse rounded-xl border border-line bg-surface" />
        </div>
      ) : stats ? (
        <div className="mt-6 space-y-5">
          {/* Stats cards */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="工程项目" value={projects.length}
              sub="全部工程" icon={<IconBook className="h-5 w-5" />} tone="accent" />
            <StatCard label="试题数" value={stats.questions.total}
              sub={Object.entries(stats.questions.by_config_status).map(([k, v]) => `${k}: ${v}`).join(" · ")}
              icon={<IconBook className="h-5 w-5" />} tone="accent" />
            <StatCard label="已录答卷" value={stats.answers.total} sub="全库合计" icon={<IconUsers className="h-5 w-5" />} tone="info" />
            <StatCard label="已评分记录" value={stats.scores.total} sub={`评级含 ${Object.keys(stats.scores.by_rating).length} 档`} icon={<IconPen className="h-5 w-5" />} tone="ok" />
          </div>

          {/* Recent projects */}
          <Card className="p-5">
            <CardHeader title="最近工程" desc="最新的工程项目，点击进入详情"
              action={<Link href="/projects" className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:border-line-strong hover:text-ink"><IconArrowRight className="h-3.5 w-3.5" />查看全部</Link>} />
            {projects.length === 0 ? (
              <p className="mt-4 text-sm text-ink-3">暂无工程项目，前往「工程项目」创建。</p>
            ) : (
              <div className="mt-4 space-y-2.5">
                {projects.slice(0, 5).map((p) => (
                  <Link key={p.project_id} href={`/projects?id=${encodeURIComponent(p.project_id)}`}
                    className="flex items-center justify-between gap-3 rounded-lg border border-line bg-surface-2 p-3.5 transition-colors hover:border-accent/40 hover:bg-accent-soft/30">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-ink">{p.name}</span>
                        <Badge tone={p.status === "active" ? "ok" : "neutral"}>{p.status === "active" ? "进行中" : p.status}</Badge>
                      </div>
                      {p.description && <p className="mt-1 text-xs text-ink-3 truncate">{p.description}</p>}
                      <div className="mt-1 flex items-center gap-3 text-xs text-ink-3">
                        {p.subject && <span>科目：{p.subject}</span>}
                        <span>创建于：{new Date(p.created_at).toLocaleDateString("zh-CN")}</span>
                      </div>
                    </div>
                    <IconArrowRight className="h-4 w-4 shrink-0 text-ink-3" />
                  </Link>
                ))}
              </div>
            )}
          </Card>

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <Card className="p-5">
              <CardHeader title="评级分布" desc="excellent / good / pass / fail" />
              {stats.scores.total === 0 ? <p className="mt-4 text-sm text-ink-3">暂无评分数据。</p> : (
                <ul className="mt-4 space-y-2.5">
                  {(["excellent", "good", "pass", "fail"] as const).map(rt => {
                    const cnt = stats.scores.by_rating[rt] ?? 0;
                    const pct = (cnt / stats.scores.total) * 100;
                    return (
                      <li key={rt}>
                        <div className="flex justify-between text-sm"><span className="text-ink-2">{RATING_LABEL[rt]}</span><span className="font-mono text-xs text-ink-3">{cnt}（{pct.toFixed(0)}%）</span></div>
                        <Progress className="mt-1.5" value={pct} tone={rt === "excellent" ? "ok" : rt === "good" ? "info" : rt === "pass" ? "warn" : "danger"} />
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>

            <Card className="p-5">
              <CardHeader title="得分占比分布" desc="按得分/满分比例分桶，20% 一档" />
              {stats.scores.total === 0 ? <p className="mt-4 text-sm text-ink-3">暂无评分数据。</p> : (
                <div className="mt-4 flex h-44 items-end justify-around gap-3 border-b border-line">
                  {stats.scores.distribution.map((b, i) => {
                    const h = stats.scores.total ? Math.max(4, (b.count / stats.scores.total) * 100) : 0;
                    return (
                      <div key={b.label} className="flex flex-1 flex-col items-center gap-1">
                        <span className="font-mono text-xs text-ink-2">{b.count}</span>
                        <div className={`w-full max-w-12 rounded-t-md ${i === 4 ? "bg-accent" : "bg-accent/60"}`} style={{ height: `${h * 1.4}px`, minHeight: 4 }} />
                        <span className="pt-1 text-[10px] text-ink-3">{b.label}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </Card>
          </div>

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <Card className="p-5">
              <CardHeader title="得分点命中率" desc="按试题聚合，未命中不计入" />
              {stats.point_hits.length === 0 ? <p className="mt-4 text-sm text-ink-3">暂无命中明细。</p> : (
                <div className="mt-4 space-y-4">
                  {[...byQuestion.entries()].map(([qid, points]) => (
                    <div key={qid}>
                      <p className="font-mono text-xs font-medium text-accent">{qid}</p>
                      <ul className="mt-2 space-y-2">
                        {points.map(p => {
                          const rate = p.total ? (p.hit / p.total) * 100 : 0;
                          return (
                            <li key={p.point_id}>
                              <div className="flex justify-between text-xs"><span className="text-ink-2">得分点 {p.point_id}</span><span className="font-mono text-ink-3">{p.hit}/{p.total} · {rate.toFixed(0)}%</span></div>
                              <Progress className="mt-1" value={rate} tone={rate >= 60 ? "ok" : rate >= 30 ? "warn" : "danger"} />
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card className="p-5">
              <CardHeader title="系统状态" desc="服务端只读运行信息" action={<IconServer className="h-4 w-4 text-accent" />} />
              {config && (
                <dl className="mt-4 space-y-3.5 text-sm">
                  <div className="flex items-start justify-between gap-3"><dt className="flex items-center gap-1.5 text-ink-3"><IconCpu className="h-4 w-4" /> 服务版本</dt><dd className="font-mono text-ink">v{config.server_version}</dd></div>
                  <div className="flex items-start justify-between gap-3"><dt className="flex items-center gap-1.5 text-ink-3"><IconDatabase className="h-4 w-4" /> 数据落盘</dt><dd className="break-all text-right font-mono text-xs text-ink-2">{config.store_path}</dd></div>
                  <div className="flex items-start justify-between gap-3"><dt className="flex items-center gap-1.5 text-ink-3"><IconActivity className="h-4 w-4" /> 推理模型</dt><dd className="flex gap-1.5"><Badge tone={config.models.mrc ? "ok" : "danger"} dot>MRC</Badge><Badge tone={config.models.similarity ? "ok" : "danger"} dot>相似度</Badge></dd></div>
                  <div className="flex items-start justify-between gap-3"><dt className="flex items-center gap-1.5 text-ink-3"><IconServer className="h-4 w-4" /> LLM 端点</dt><dd className="text-right">{config.llm.endpoints.length === 0 ? <Badge tone="warn">未配置</Badge> : <span className="flex flex-wrap justify-end gap-1.5">{config.llm.endpoints.map(e => <Badge key={e.name} tone="neutral">{e.name} / {e.model}</Badge>)}</span>}</dd></div>
                  <div className="flex items-start justify-between gap-3"><dt className="flex items-center gap-1.5 text-ink-3"><IconPen className="h-4 w-4" /> OCR</dt><dd className="text-right">{config.ocr.enabled ? <Badge tone="ok">可用</Badge> : <Badge tone="neutral" dot>暂停</Badge>}</dd></div>
                  {config.ocr.note && <p className="text-xs leading-relaxed text-ink-3">{config.ocr.note}</p>}
                </dl>
              )}
            </Card>
          </div>
        </div>
      ) : null}
    </>
  );
}