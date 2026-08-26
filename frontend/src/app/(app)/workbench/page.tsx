"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getStandardAnswer,
  listAnswers,
  listQuestions,
  scoreAnswers,
  type Answer,
  type HitStatus,
  type PointDetail,
  type Question,
  type Rating,
  type ScoreResult,
  type ScoringConfig,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, PageHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/field";
import { IconAlert, IconDownload, IconPen } from "@/components/icons";

const HIT_CLS: Record<HitStatus, string> = {
  hit_exact: "bg-hit-exact text-hit-exact-ink",
  hit_semantic: "bg-hit-semantic text-hit-semantic-ink",
  partial: "bg-hit-partial text-hit-partial-ink",
  miss: "",
};
const HIT_LABEL: Record<HitStatus, string> = {
  hit_exact: "精确命中",
  hit_semantic: "语义命中",
  partial: "部分命中",
  miss: "未命中",
};
const HIT_TONE: Record<HitStatus, "ok" | "info" | "warn" | "neutral"> = {
  hit_exact: "ok",
  hit_semantic: "info",
  partial: "warn",
  miss: "neutral",
};
const RATING_LABEL: Record<Rating, string> = {
  excellent: "优秀",
  good: "良好",
  pass: "及格",
  fail: "不及格",
};
const RATING_TONE: Record<Rating, "ok" | "info" | "warn" | "danger"> = {
  excellent: "ok",
  good: "info",
  pass: "warn",
  fail: "danger",
};

interface Seg {
  text: string;
  cls: string;
  pointId?: number;
}

function buildSegments(text: string, details: PointDetail[]): Seg[] {
  const marks: { start: number; end: number; cls: string; pointId: number }[] = [];
  for (const d of details) {
    if (!d.extracted_span) continue;
    const span = d.extracted_span;
    let from = 0;
    while (true) {
      const idx = text.indexOf(span, from);
      if (idx < 0) break;
      marks.push({ start: idx, end: idx + span.length, cls: HIT_CLS[d.hit_status], pointId: d.point_id });
      from = idx + span.length;
    }
  }
  marks.sort((a, b) => a.start - b.start);
  const merged: typeof marks = [];
  for (const m of marks) {
    const last = merged[merged.length - 1];
    if (last && m.start < last.end) continue; // 跳过重叠
    merged.push(m);
  }
  const segs: Seg[] = [];
  let cursor = 0;
  for (const m of merged) {
    if (m.start > cursor) segs.push({ text: text.slice(cursor, m.start), cls: "" });
    segs.push({ text: text.slice(m.start, m.end), cls: m.cls, pointId: m.pointId });
    cursor = m.end;
  }
  if (cursor < text.length) segs.push({ text: text.slice(cursor), cls: "" });
  return segs;
}

function answerText(a: Answer): string {
  return a.ocr_text ?? a.answer_text ?? "";
}

export default function WorkbenchPage() {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [qid, setQid] = useState("");
  const [config, setConfig] = useState<ScoringConfig | null>(null);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [selected, setSelected] = useState<Answer | null>(null);
  const [result, setResult] = useState<ScoreResult | null>(null);
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
    setConfig(null);
    setAnswers([]);
    setSelected(null);
    setResult(null);
    getStandardAnswer(qid)
      .then(setConfig)
      .catch(() => setConfig(null));
    listAnswers(qid)
      .then((r) => setAnswers(r.items))
      .catch((e) => setErr(String(e)));
  }, [qid]);

  const segments = useMemo(
    () => (selected && result ? buildSegments(answerText(selected), result.point_details) : []),
    [selected, result],
  );

  async function handleScore() {
    if (!qid || !selected) return setErr("请选择一份答卷");
    setBusy(true);
    setErr(null);
    try {
      const r = await scoreAnswers(qid, [selected.answer_id]);
      setResult(r.results[0] ?? null);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  function exportJson() {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${result.answer_id}-score.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <PageHeader
        title="阅卷工作台"
        desc="逐点评分明细 · 答案命中高亮 · 总分解读——一次看清每分依据。"
      />

      {err && (
        <div role="alert" className="mt-5 flex items-start gap-2 rounded-lg border border-danger/40 bg-danger-soft px-3 py-2.5 text-sm text-danger">
          <IconAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{err}</span>
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
        <Button
          variant="primary"
          onClick={handleScore}
          loading={busy}
          disabled={!selected}
          icon={<IconPen className="h-4 w-4" />}
        >
          评分
        </Button>
        {result && (
          <Button onClick={exportJson} icon={<IconDownload className="h-4 w-4" />}>
            导出 JSON
          </Button>
        )}
        {!config && qid && (
          <Badge tone="warn" dot>
            该试题尚未配置评分标准（请先到「试题管理」解析并保存）
          </Badge>
        )}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-3">
        {/* 左：标准得分点 */}
        <Card className="p-4 lg:col-span-1">
          <CardHeader
            title="标准得分点"
            desc={config ? `满分 ${config.total_score} 分${config.thresholds ? ` · 相似度阈值 ${config.thresholds.similarity_high}/${config.thresholds.similarity_low}` : ""}` : "未配置"}
            action={<span className="rounded-lg bg-accent-soft p-2 text-accent"><IconPen className="h-4 w-4" /></span>}
          />
          {!config ? (
            <p className="mt-3 text-sm text-ink-3">未配置评分标准，无法评分。</p>
          ) : (
            <ul className="mt-3 space-y-2">
              {config.points.map((p) => (
                <li key={p.point_id} className="rounded-lg border border-line p-3 transition-colors hover:border-line-strong">
                  <div className="flex items-center justify-between gap-2">
                    <span className="rounded-md bg-surface-2 px-2 py-0.5 font-serif text-xs font-semibold text-ink-2">
                      得分点 {p.point_id}
                    </span>
                    <span className="font-mono text-xs text-ink-3">权重 {p.weight}</span>
                  </div>
                  <div className="mt-1.5 text-sm leading-relaxed text-ink">{p.point_text}</div>
                  {p.aliases.length > 0 && (
                    <details className="mt-1.5 text-xs text-ink-3">
                      <summary className="cursor-pointer text-ink-3">等价表述（{p.aliases.length}）</summary>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {p.aliases.map((a, i) => (
                          <span key={i} className="rounded bg-surface-2 px-1.5 py-0.5 text-ink-2">{a}</span>
                        ))}
                      </div>
                    </details>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* 中：学生答案 + 高亮 */}
        <Card className="p-4">
          <CardHeader
            title="学生答案"
            desc="命中片段按判定着色；悬停可看对应得分点。"
            action={
              <ul aria-label="命中图例" className="flex flex-wrap items-center gap-2 text-xs text-ink-2">
                {(["hit_exact", "hit_semantic", "partial", "miss"] as HitStatus[]).map((h) => (
                  <li key={h} className="flex items-center gap-1">
                    <span
                      aria-hidden="true"
                      className={`inline-block h-3 w-3 rounded border border-line ${HIT_CLS[h] || "bg-surface-2"}`}
                    />
                    {HIT_LABEL[h]}
                  </li>
                ))}
              </ul>
            }
          />
          {answers.length === 0 ? (
            <p className="mt-3 text-sm text-ink-3">该试题暂无答卷，请先到「答卷上传」录入。</p>
          ) : (
            <Select
              className="mt-3"
              aria-label="选择答卷"
              value={selected?.answer_id ?? ""}
              onChange={(e) => {
                setResult(null);
                setSelected(answers.find((a) => a.answer_id === e.target.value) ?? null);
              }}
            >
              <option value="">— 选择一份答卷 —</option>
              {answers.map((a) => (
                <option key={a.answer_id} value={a.answer_id}>
                  {a.student_id ?? a.answer_id}
                  {a.class_name ? `（${a.class_name}）` : ""}
                  {a.source === "ocr" ? " · 图片" : ""}
                </option>
              ))}
            </Select>
          )}
          {selected && (
            <div className="mt-3 whitespace-pre-wrap rounded-lg bg-surface-2 p-3.5 text-sm leading-relaxed text-ink">
              {segments.length === 0 ? (
                answerText(selected) || <span className="text-ink-3">（空）</span>
              ) : (
                segments.map((s, i) => (
                  <span key={i} className={s.cls} title={s.pointId ? `得分点 ${s.pointId}` : undefined}>
                    {s.text}
                  </span>
                ))
              )}
            </div>
          )}
          {selected?.source === "ocr" && (
            <p className="mt-2 text-xs text-ink-3">来源：试卷图片（OCR 识别）</p>
          )}
        </Card>

        {/* 右：逐点明细 + 总分 */}
        <Card className="p-4">
          <CardHeader title="评分明细" desc={result ? "本次评分结果" : "选择答卷后点击「评分」"} />
          {!result ? (
            <p className="mt-3 text-sm text-ink-3">评分结果将在此呈现。</p>
          ) : (
            <>
              <div className="mt-3 flex items-center justify-between rounded-lg bg-surface-2 p-3.5">
                <div>
                  <div className="text-xs text-ink-3">总分 / 满分</div>
                  <div className="font-serif text-3xl font-bold text-ink">
                    {result.total_score}
                    <span className="ml-1 text-base font-medium text-ink-3">/ {result.max_score}</span>
                  </div>
                </div>
                <Badge tone={RATING_TONE[result.rating]}>{RATING_LABEL[result.rating]}</Badge>
              </div>
              <ul className="mt-3 space-y-2">
                {result.point_details.map((d) => (
                  <li key={d.point_id} className="rounded-lg border border-line p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-serif text-sm font-semibold text-ink">得分点 {d.point_id}</span>
                      <Badge tone={HIT_TONE[d.hit_status]}>{HIT_LABEL[d.hit_status]}</Badge>
                    </div>
                    {d.extracted_span && (
                      <div className="mt-1.5 text-xs leading-relaxed text-ink-2">
                        命中片段：
                        <span className={`rounded px-1 ${HIT_CLS[d.hit_status]}`}>{d.extracted_span}</span>
                      </div>
                    )}
                    {d.matched_alias && <div className="mt-1 text-xs text-ink-2">匹配表述：{d.matched_alias}</div>}
                    <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-3">
                      {d.confidence != null && (
                        <span>置信度 <span className="font-mono text-ink-2">{d.confidence.toFixed(3)}</span></span>
                      )}
                      {d.similarity != null && (
                        <span>相似度 <span className="font-mono text-ink-2">{d.similarity.toFixed(3)}</span></span>
                      )}
                      <span>本点 <span className="font-mono text-ink-2">{d.point_score}</span></span>
                      <span className="ml-auto">
                        {d.source === "mrc" ? "MRC 抽取" : d.source === "option" ? "选项规则" : "相似度兜底"}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>
      </div>

      <p className="mt-4 text-xs text-ink-3">
        提示：评分依赖已加载的本地 ONNX 模型；模型未就绪时后端将返回错误。
      </p>
    </>
  );
}