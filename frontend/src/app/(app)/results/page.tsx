"use client";

import { useEffect, useMemo, useState } from "react";
import { listQuestions, listResults, type Question, type ScoreRecord } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, PageHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/field";
import { Progress } from "@/components/ui/progress";
import { StatCard } from "@/components/ui/stat";
import { IconChart, IconDownload, IconRefresh, IconUsers } from "@/components/icons";

const RATING_LABEL: Record<string, string> = {
  excellent: "优秀",
  good: "良好",
  pass: "及格",
  fail: "不及格",
};
const RATING_COLOR: Record<string, string> = {
  excellent: "bg-ok",
  good: "bg-info",
  pass: "bg-warn",
  fail: "bg-danger",
};

export default function ResultsPage() {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [qid, setQid] = useState("");
  const [records, setRecords] = useState<ScoreRecord[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listQuestions()
      .then((r) => {
        setQuestions(r.items);
        if (r.items.length) setQid(r.items[0].question_id);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => {
    if (!qid) return;
    setBusy(true);
    listResults(qid)
      .then((r) => setRecords(r.items))
      .catch((e) => setErr(String(e)))
      .finally(() => setBusy(false));
  }, [qid]);

  const stats = useMemo(() => {
    if (records.length === 0) return null;
    const total = records.reduce((s, r) => s + r.total_score, 0);
    const avg = total / records.length;
    const scores = records.map((r) => r.total_score);
    const max = Math.max(...scores);
    const min = Math.min(...scores);
    const passCnt = records.filter((r) => r.rating !== "fail").length;
    const dist: Record<string, number> = {};
    for (const r of records) dist[r.rating] = (dist[r.rating] ?? 0) + 1;
    const ratings = ["excellent", "good", "pass", "fail"];
    // 得分占比分桶（0-20 / 20-40 / 40-60 / 60-80 / 80-100）
    const buckets = [0, 0, 0, 0, 0];
    for (const r of records) {
      const ratio = r.max_score > 0 ? (r.total_score / r.max_score) * 100 : 0;
      buckets[Math.min(99, Math.floor(ratio)) / 20 | 0] += 1;
    }
    const bucketLabels = ["0–20%", "20–40%", "40–60%", "60–80%", "80–100%"];
    // 得分点命中率
    const pointHits: Record<number, { hit: number; total: number }> = {};
    for (const r of records) {
      for (const p of r.point_details) {
        const e = (pointHits[p.point_id] ??= { hit: 0, total: 0 });
        e.total += 1;
        if (p.hit_status !== "miss") e.hit += 1;
      }
    }
    const maxScore = records[0]?.max_score ?? 0;
    return { avg, max, min, passRate: (passCnt / records.length) * 100, dist, ratings, pointHits, buckets, bucketLabels, maxScore };
  }, [records]);

  function exportCsv() {
    if (records.length === 0) return;
    const header = ["answer_id", "student_id", "class_name", "total_score", "max_score", "rating"];
    const lines = [header.join(",")];
    for (const r of records) {
      lines.push([r.answer_id, r.student_id ?? "", r.class_name ?? "", r.total_score, r.max_score, r.rating].join(","));
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${qid}-results.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function exportJson() {
    const blob = new Blob([JSON.stringify(records, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${qid}-results.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <PageHeader
        title="结果与统计"
        desc="评分结果汇总、分数分布、得分点命中率与数据导出。"
      />

      {err && (
        <div role="alert" className="mt-5 rounded-lg border border-danger/40 bg-danger-soft px-3 py-2.5 text-sm text-danger">
          {err}
        </div>
      )}

      {/* 工具栏 */}
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <div className="w-full max-w-xs sm:w-64">
          <Select aria-label="选择试题" value={qid} onChange={(e) => setQid(e.target.value)}>
            <option value="">— 选择试题 —</option>
            {questions.map((q) => (
              <option key={q.question_id} value={q.question_id}>
                {q.question_id} · {q.subject}
              </option>
            ))}
          </Select>
        </div>
        <Button onClick={exportCsv} disabled={records.length === 0} icon={<IconDownload className="h-4 w-4" />}>
          导出 CSV
        </Button>
        <Button onClick={exportJson} disabled={records.length === 0} icon={<IconDownload className="h-4 w-4" />}>
          导出 JSON
        </Button>
        {busy && (
          <span className="inline-flex items-center gap-1.5 text-xs text-ink-3">
            <IconRefresh className="h-3.5 w-3.5 animate-spin" />
            加载中…
          </span>
        )}
      </div>

      {stats && (
        <div className="mt-6 space-y-5">
          {/* 概览统计卡 */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="样本数"
              value={records.length}
              sub={`满分均值 ${stats.maxScore}`}
              icon={<IconUsers className="h-5 w-5" />}
              tone="info"
            />
            <StatCard
              label="平均分"
              value={stats.avg.toFixed(2)}
              sub={`最高 ${stats.max} / 最低 ${stats.min}`}
              icon={<IconChart className="h-5 w-5" />}
              tone="accent"
            />
            <StatCard
              label="及格率"
              value={`${stats.passRate.toFixed(0)}%`}
              sub="非不及格评级占比"
              icon={<IconChart className="h-5 w-5" />}
              tone="ok"
            />
            <div className="rounded-xl border border-line bg-surface p-4 shadow-card">
              <div className="text-xs font-medium uppercase tracking-wider text-ink-3">评级分布</div>
              <ul className="mt-2 space-y-1.5">
                {stats.ratings.map((rt) => {
                  const cnt = stats.dist[rt] ?? 0;
                  const pct = records.length ? (cnt / records.length) * 100 : 0;
                  return (
                    <li key={rt} className="flex items-center gap-2 text-xs">
                      <span className="w-8 text-ink-2">{RATING_LABEL[rt] ?? rt}</span>
                      <span aria-hidden="true" className={`h-2 rounded-full ${RATING_COLOR[rt]} ${cnt ? "" : "opacity-20"}`} style={{ width: `${Math.max(4, pct)}%` }} />
                      <span className="ml-auto font-mono text-ink-3">{cnt}</span>
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            {/* 分数分布 */}
            <Card className="p-5">
              <CardHeader title="分数分布" desc="按得分占比（得分/满分）分桶" />
              <div className="mt-4 flex h-40 items-end justify-around gap-3 border-b border-line pb-0">
                {stats.bucketLabels.map((label, i) => {
                  const cnt = stats.buckets[i];
                  const h = records.length ? Math.max(4, (cnt / records.length) * 100) : 0;
                  return (
                    <div key={label} className="flex flex-1 flex-col items-center gap-1">
                      <span className="text-xs font-mono text-ink-2">{cnt}</span>
                      <div
                        className={`w-full max-w-12 rounded-t-md ${i === 4 ? "bg-accent" : "bg-accent/60"}`}
                        style={{ height: `${h * 1.4}px`, minHeight: 4 }}
                      />
                      <span className="pt-1 text-[10px] text-ink-3">{label}</span>
                    </div>
                  );
                })}
              </div>
            </Card>

            {/* 得分点命中率 */}
            <Card className="p-5">
              <CardHeader title="得分点命中率" desc="所有评分记录聚合，未命中不计入命中" />
              {Object.keys(stats.pointHits).length === 0 ? (
                <p className="mt-4 text-sm text-ink-3">暂无得分点明细。</p>
              ) : (
                <ul className="mt-4 space-y-3">
                  {Object.entries(stats.pointHits)
                    .sort((a, b) => Number(a[0]) - Number(b[0]))
                    .map(([pid, v]) => {
                      const rate = v.total ? (v.hit / v.total) * 100 : 0;
                      return (
                        <li key={pid}>
                          <div className="flex items-center justify-between text-sm">
                            <span className="text-ink">得分点 {pid}</span>
                            <span className="font-mono text-xs text-ink-3">
                              {v.hit}/{v.total} · {rate.toFixed(0)}%
                            </span>
                          </div>
                          <Progress className="mt-1.5" value={rate} tone={rate >= 60 ? "ok" : rate >= 30 ? "warn" : "danger"} />
                        </li>
                      );
                    })}
                </ul>
              )}
            </Card>
          </div>

          {/* 明细表 */}
          <Card>
            <CardHeader title="评分明细" desc={`共 ${records.length} 条记录`} className="px-5 pt-5" />
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-surface-2 text-left text-xs uppercase tracking-wider text-ink-3">
                  <tr>
                    <th className="px-5 py-2.5 font-medium">答卷</th>
                    <th className="px-3 py-2.5 font-medium">学号</th>
                    <th className="px-3 py-2.5 font-medium">班级</th>
                    <th className="px-3 py-2.5 font-medium">总分</th>
                    <th className="px-5 py-2.5 text-right font-medium">评级</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {records.map((r) => (
                    <tr key={r.answer_id} className="transition-colors hover:bg-surface-2/60">
                      <td className="px-5 py-2.5 font-mono text-xs text-ink-2">{r.answer_id}</td>
                      <td className="px-3 py-2.5 text-ink-2">{r.student_id ?? "—"}</td>
                      <td className="px-3 py-2.5 text-ink-2">{r.class_name ?? "—"}</td>
                      <td className="px-3 py-2.5 font-mono text-ink">
                        {r.total_score} <span className="text-ink-3">/ {r.max_score}</span>
                      </td>
                      <td className="px-5 py-2.5 text-right">
                        <Badge tone={r.rating === "excellent" ? "ok" : r.rating === "good" ? "info" : r.rating === "pass" ? "warn" : "danger"}>
                          {RATING_LABEL[r.rating] ?? r.rating}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {!busy && !stats && qid && (
        <p className="mt-8 rounded-lg border border-dashed border-line-strong px-4 py-10 text-center text-sm text-ink-3">
          该试题暂无评分结果，请先到「阅卷工作台」完成评分。
        </p>
      )}
    </>
  );
}