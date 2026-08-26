"use client";

import { useEffect, useState } from "react";
import {
  createQuestion,
  getStandardAnswer,
  listQuestions,
  parseStandardAnswer,
  saveStandardAnswer,
  type Question,
  type ScoringConfig,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, PageHeader } from "@/components/ui/card";
import { Field, Select, TextArea, TextInput } from "@/components/ui/field";
import { IconAlert, IconBook, IconCheck, IconPen } from "@/components/icons";

/** 把一行等价表述文本按逗号切分为列表，统一识别中文/英文逗号并去空。 */
function parseAliases(raw: string): string[] {
  return raw
    .split(/[，,]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * 等价表述编辑框：以逗号（统一为中文逗号）分隔。
 * 输入过程中保留草稿，避免结尾分隔符被即时切分吞掉；失焦时归格为中文逗号拼接。
 */
function AliasEditor({
  aliases,
  onChange,
  className = "",
}: {
  aliases: string[];
  onChange: (aliases: string[]) => void;
  className?: string;
}) {
  const [draft, setDraft] = useState(aliases.join("，"));

  // 仅当 aliases 与当前草稿解析结果不一致（外部变更，如重新解析）时同步草稿，
  // 避免输入分隔符时被父级 join 回填覆盖而使逗号消失。
  useEffect(() => {
    if (parseAliases(draft).join("，") !== aliases.join("，")) {
      setDraft(aliases.join("，"));
    }
  }, [aliases]);

  return (
    <Field label="等价表述（中文逗号分隔）" className={className}>
      <TextInput
        value={draft}
        onChange={(e) => {
          const normalized = e.target.value.replace(/,/g, "，");
          setDraft(normalized);
          onChange(parseAliases(normalized));
        }}
        onBlur={() => setDraft(aliases.join("，"))}
      />
    </Field>
  );
}

const STATUS: Record<string, { label: string; tone: "neutral" | "warn" | "ok" }> = {
  none: { label: "未配置", tone: "neutral" },
  pending_review: { label: "待复核", tone: "warn" },
  confirmed: { label: "已确认", tone: "ok" },
};

const SUBJECT_PRESETS = ["语文", "数学", "英语", "政治", "历史", "地理", "物理", "化学", "生物"];

export default function QuestionsPage() {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(true);

  // 新建表单
  const [qid, setQid] = useState("");
  const [content, setContent] = useState("");
  const [subject, setSubject] = useState("历史");
  const [totalScore, setTotalScore] = useState(5);
  const [stdText, setStdText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  // 解析 + 编辑态
  const [currentQ, setCurrentQ] = useState<Question | null>(null);
  const [rawAnswer, setRawAnswer] = useState("");
  const [editing, setEditing] = useState<ScoringConfig | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const r = await listQuestions();
      setQuestions(r.items);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, []);

  async function handleCreate() {
    setErr(null);
    setInfo(null);
    if (!content.trim()) return setErr("请填写题目内容");
    setBusy(true);
    try {
      const q = await createQuestion({
        question_id: qid.trim() || undefined,
        content: content.trim(),
        subject: subject.trim(),
        total_score: totalScore,
        standard_answer_text: stdText.trim() || undefined,
      });
      setInfo(`已创建试题 ${q.question_id}`);
      setCurrentQ(q);
      setRawAnswer(stdText.trim());
      setQid("");
      setContent("");
      setStdText("");
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleParse() {
    if (!currentQ) return;
    setErr(null);
    setBusy(true);
    try {
      const r = await parseStandardAnswer(currentQ.question_id, rawAnswer, currentQ.content);
      setEditing(r.scoring_config);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleSave() {
    if (!editing) return;
    setBusy(true);
    try {
      await saveStandardAnswer(editing);
      setInfo(`评分配置已保存并确认：${editing.question_id}`);
      setEditing(null);
      setCurrentQ(null);
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleOpen(q: Question) {
    setErr(null);
    setCurrentQ(q);
    setRawAnswer(q.standard_answer_text ?? "");
    setEditing(null);
    try {
      const cfg = await getStandardAnswer(q.question_id);
      setEditing(cfg);
    } catch {
      // 尚未保存配置，等待解析
    }
  }

  function updatePoint(i: number, patch: Partial<ScoringConfig["points"][number]>) {
    if (!editing) return;
    const points = editing.points.map((p, idx) => (idx === i ? { ...p, ...patch } : p));
    setEditing({ ...editing, points });
  }

  return (
    <>
      <PageHeader
        title="试题管理"
        desc="录入题目与自然语言标准答案；由模型解析为标准得分点配置，确认后即可用于评分。"
      />

      {err && (
        <div role="alert" className="mt-5 flex items-start gap-2 rounded-lg border border-danger/40 bg-danger-soft px-3 py-2.5 text-sm text-danger">
          <IconAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{err}</span>
        </div>
      )}
      {info && (
        <div role="status" aria-live="polite" className="mt-5 flex items-start gap-2 rounded-lg border border-ok/40 bg-ok-soft px-3 py-2.5 text-sm text-ok">
          <IconCheck className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{info}</span>
        </div>
      )}

      <div className="mt-6 space-y-6">
        {/* 新建试题 */}
        <Card className="p-5">
          <CardHeader
            title="新建试题"
            desc="题号可留空自动生成；学科支持常用科目快捷选择。"
            action={<span className="rounded-lg bg-accent-soft p-2 text-accent"><IconBook className="h-4 w-4" /></span>}
          />
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="题号（可选）">
              <TextInput value={qid} onChange={(e) => setQid(e.target.value)} placeholder="Q001" />
            </Field>
            <Field label="学科">
              <Select value={subject} onChange={(e) => setSubject(e.target.value)} aria-label="学科">
                {SUBJECT_PRESETS.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </Select>
            </Field>
            <Field label="满分">
              <TextInput
                type="number"
                step="0.5"
                min={0}
                value={totalScore}
                onChange={(e) => setTotalScore(Number(e.target.value))}
              />
            </Field>
          </div>
          <div className="mt-4">
            <Field label="题目内容">
              <TextArea rows={3} value={content} onChange={(e) => setContent(e.target.value)} placeholder="例如：简述戊戌变法的主要影响。" />
            </Field>
          </div>
          <div className="mt-4">
            <Field label="自然语言标准答案" hint="可留空，创建后进入「解析」步骤再粘贴。">
              <TextArea rows={3} value={stdText} onChange={(e) => setStdText(e.target.value)} />
            </Field>
          </div>
          <div className="mt-4 flex justify-end">
            <Button variant="primary" onClick={handleCreate} loading={busy} icon={<IconBook className="h-4 w-4" />}>
              创建试题
            </Button>
          </div>
        </Card>

        {/* 解析与编辑 */}
        {currentQ && (
          <Card className="p-5">
            <CardHeader
              title={`标准答案解析 · ${currentQ.question_id}`}
              desc="模型按学科解析得分点与等价表述，请复核后保存确认。"
            />
            <div className="mt-4">
              <Field label="标准答案文本（自然语言）">
                <TextArea rows={4} value={rawAnswer} onChange={(e) => setRawAnswer(e.target.value)} />
              </Field>
            </div>
            <div className="mt-4 flex gap-2">
              <Button variant="primary" onClick={handleParse} loading={busy} disabled={!rawAnswer.trim()} icon={<IconPen className="h-4 w-4" />}>
                解析为标准得分点
              </Button>
              <Button variant="ghost" onClick={() => setCurrentQ(null)} disabled={busy}>
                关闭
              </Button>
            </div>
          </Card>
        )}

        {/* 编辑得分点 */}
        {editing && (
          <Card className="p-5">
            <CardHeader
              title={`编辑评分配置 · ${editing.question_id}`}
              desc={`满分 ${editing.total_score} 分 · ${editing.points.length} 个得分点`}
              action={
                <Button variant="primary" onClick={handleSave} loading={busy} icon={<IconCheck className="h-4 w-4" />}>
                  保存并确认
                </Button>
              }
            />
            <div className="mt-4 space-y-3">
              {editing.points.map((p, i) => (
                <div key={p.point_id} className="rounded-lg border border-line p-3.5 transition-colors hover:border-line-strong">
                  <div className="flex items-center gap-2">
                    <span className="rounded-md bg-surface-2 px-2 py-0.5 font-serif text-sm font-semibold text-ink-2">
                      得分点 {p.point_id}
                    </span>
                    <label className="ml-auto flex items-center gap-1.5 text-xs text-ink-2">
                      权重
                      <input
                        type="number"
                        step="0.5"
                        min={0}
                        aria-label={`得分点 ${p.point_id} 权重`}
                        className="w-16 rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink"
                        value={p.weight}
                        onChange={(e) => updatePoint(i, { weight: Number(e.target.value) })}
                      />
                    </label>
                  </div>
                  <TextInput
                    className="mt-2"
                    aria-label={`得分点 ${p.point_id} 标准表述`}
                    value={p.point_text}
                    onChange={(e) => updatePoint(i, { point_text: e.target.value })}
                  />
                  <AliasEditor
                    className="mt-2"
                    aliases={p.aliases}
                    onChange={(aliases) => updatePoint(i, { aliases })}
                  />
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* 列表 */}
        <section>
          <div className="flex items-center justify-between">
            <h2 className="font-serif text-base font-semibold tracking-wide text-ink">已有试题</h2>
            <span className="text-xs text-ink-3">共 {questions.length} 题</span>
          </div>
          {loading ? (
            <div className="mt-3 space-y-2" aria-hidden="true">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-14 animate-pulse rounded-lg border border-line bg-surface" />
              ))}
            </div>
          ) : questions.length === 0 ? (
            <p className="mt-3 rounded-lg border border-dashed border-line-strong px-4 py-8 text-center text-sm text-ink-3">
              暂无试题，从上方「新建试题」开始。
            </p>
          ) : (
            <ul className="mt-3 divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface shadow-card">
              {questions.map((q) => {
                const st = STATUS[q.config_status] ?? STATUS.none;
                return (
                  <li key={q.question_id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3.5 transition-colors hover:bg-surface-2/60">
                    <span className="font-mono text-sm font-medium text-accent">{q.question_id}</span>
                    <Badge tone="neutral">{q.subject}</Badge>
                    <span className="min-w-0 flex-1 truncate text-sm text-ink">{q.content}</span>
                    <span className="text-xs text-ink-3">满分 {q.total_score}</span>
                    <Badge tone={st.tone} dot>{st.label}</Badge>
                    <Button size="sm" variant="secondary" onClick={() => handleOpen(q)}>
                      配置
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}