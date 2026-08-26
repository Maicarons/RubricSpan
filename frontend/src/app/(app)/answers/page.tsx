"use client";

import { useEffect, useRef, useState } from "react";
import {
  listQuestions,
  ocrImage,
  submitAnswers,
  type OcrResult,
  type Question,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, PageHeader } from "@/components/ui/card";
import { Field, Select, TextArea, TextInput } from "@/components/ui/field";
import {
  IconAlert,
  IconCheck,
  IconImage,
  IconInfo,
  IconPlus,
  IconTrash,
  IconUpload,
} from "@/components/icons";

interface Row {
  id: number;
  student_id: string;
  class_name: string;
  text: string;
}

let rowSeq = 1;

function newRow(): Row {
  return { id: rowSeq++, student_id: "", class_name: "", text: "" };
}

export default function AnswersPage() {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [qid, setQid] = useState("");
  const [rows, setRows] = useState<Row[]>([newRow()]);
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [accepted, setAccepted] = useState<string[]>([]);

  // 图片识别（RapidOCR · Rust 侧推理，M8.1 恢复）
  const [ocrBusy, setOcrBusy] = useState(false);
  const [ocrResult, setOcrResult] = useState<OcrResult | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listQuestions()
      .then((r) => {
        setQuestions(r.items);
        if (r.items.length) setQid(r.items[0].question_id);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  function updateRow(id: number, patch: Partial<Row>) {
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }

  function addRow() {
    setRows((rs) => [...rs, newRow()]);
  }

  function removeRow(id: number) {
    setRows((rs) => (rs.length > 1 ? rs.filter((r) => r.id !== id) : rs));
  }

  async function handleSubmit() {
    if (!qid) return setErr("请先选择试题");
    setErr(null);
    setAccepted([]);
    setBusy(true);
    try {
      const submissions = rows
        .filter((r) => r.text.trim())
        .map((r) => ({
          student_id: r.student_id || undefined,
          class_name: r.class_name || undefined,
          answer_text: r.text.trim(),
        }));
      if (submissions.length === 0) {
        setErr("请至少填写一份作答文本");
        return;
      }
      const res = await submitAnswers({ question_id: qid, submissions });
      setAccepted(res.answer_ids);
      setRows([newRow()]);
      setInfo(`已接收 ${res.accepted} 份答卷`);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  /** 图片识别：上传 → /api/ocr → 把识别文本填入首个空作答行（可编辑后提交）。 */
  async function handleOcrFile(file: File) {
    if (!qid) {
      setErr("请先选择试题");
      return;
    }
    setErr(null);
    setOcrResult(null);
    setOcrBusy(true);
    try {
      const r = await ocrImage(qid, file);
      setOcrResult(r);
      if (r.answer_text.trim()) {
        setRows((rs) => {
          const emptyIdx = rs.findIndex((row) => !row.text.trim());
          if (emptyIdx >= 0) {
            return rs.map((row, i) => (i === emptyIdx ? { ...row, text: r.answer_text } : row));
          }
          const row = newRow();
          row.text = r.answer_text;
          return [...rs, row];
        });
      }
    } catch (e) {
      setErr(String(e));
    } finally {
      setOcrBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="答卷上传"
        desc="录入学生作答文本；提交后可在「阅卷工作台」逐份评分。"
      />

      <div className="mt-5 flex items-start gap-2 rounded-lg border border-info/40 bg-info-soft px-3.5 py-2.5 text-xs leading-relaxed text-info">
        <IconInfo className="mt-0.5 h-4 w-4 shrink-0" />
        <span>
          支持图片识别（RapidOCR · Rust 侧推理）与直接文本录入；识别结果先填入作答框，可编辑后提交。离线 WASM 演示无 OCR。
        </span>
      </div>

      {err && (
        <div role="alert" className="mt-4 flex items-start gap-2 rounded-lg border border-danger/40 bg-danger-soft px-3 py-2.5 text-sm text-danger">
          <IconAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{err}</span>
        </div>
      )}
      {info && (
        <div role="status" aria-live="polite" className="mt-4 flex items-start gap-2 rounded-lg border border-ok/40 bg-ok-soft px-3 py-2.5 text-sm text-ok">
          <IconCheck className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{info}</span>
        </div>
      )}

      <Card className="mt-6 p-5">
        <CardHeader
          title="批量录入"
          desc="学号、班级可留空；作答文本必填。"
          action={<span className="rounded-lg bg-accent-soft p-2 text-accent"><IconUpload className="h-4 w-4" /></span>}
        />
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_auto]">
          <div className="max-w-md">
            <Field label="选择试题">
              <Select id="question-select" value={qid} onChange={(e) => setQid(e.target.value)}>
                <option value="">— 请选择 —</option>
                {questions.map((q) => (
                  <option key={q.question_id} value={q.question_id}>
                    {q.question_id} · {q.subject} · {q.content.slice(0, 18)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          {/* 图片识别入口 */}
          <div className="lg:pt-1">
            <span className="mb-1.5 block text-sm font-medium text-ink">试卷图片识别</span>
            <div className="flex items-center gap-2">
              <input
                ref={fileRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                aria-label="选择试卷图片"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void handleOcrFile(f);
                  e.target.value = "";
                }}
              />
              <Button
                variant="primary"
                onClick={() => fileRef.current?.click()}
                loading={ocrBusy}
                disabled={!qid}
                icon={<IconImage className="h-4 w-4" />}
              >
                {ocrBusy ? "识别中…" : "识别图片"}
              </Button>
              {ocrResult && (
                <Badge tone={ocrResult.low_confidence ? "warn" : "ok"} dot>
                  置信 {(ocrResult.confidence * 100).toFixed(0)}%{ocrResult.low_confidence ? " · 存疑" : ""}
                </Badge>
              )}
            </div>
            {ocrResult && (
              <div className="mt-2 max-w-sm rounded-lg border border-line bg-surface-2 px-3 py-2 text-xs leading-relaxed text-ink-2">
                {ocrResult.answer_text.split("\n").slice(0, 4).map((l, i) => (
                  <div key={i}>{l}</div>
                ))}
                {ocrResult.low_confidence && (
                  <p className="mt-1 text-warn">识别存在存疑片段，请人工核对后提交。</p>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="mt-5 space-y-4">
          {rows.map((r, i) => (
            <div key={r.id} className="rounded-xl border border-line p-4 transition-colors hover:border-line-strong">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-md bg-surface-2 px-2 py-0.5 font-serif text-xs font-semibold text-ink-2">
                  第 {i + 1} 份
                </span>
                <TextInput
                  aria-label={`第 ${i + 1} 份答卷学号`}
                  className="w-28"
                  placeholder="学号（可选）"
                  value={r.student_id}
                  onChange={(e) => updateRow(r.id, { student_id: e.target.value })}
                />
                <TextInput
                  aria-label={`第 ${i + 1} 份答卷班级`}
                  className="w-28"
                  placeholder="班级（可选）"
                  value={r.class_name}
                  onChange={(e) => updateRow(r.id, { class_name: e.target.value })}
                />
                {rows.length > 1 && (
                  <button
                    type="button"
                    aria-label={`删除第 ${i + 1} 份答卷`}
                    className="ml-auto inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-danger-soft hover:text-danger"
                    onClick={() => removeRow(r.id)}
                  >
                    <IconTrash className="h-4 w-4" />
                  </button>
                )}
              </div>
              <TextArea
                className="mt-3"
                aria-label={`第 ${i + 1} 份答卷作答文本`}
                rows={3}
                placeholder="作答文本…"
                value={r.text}
                onChange={(e) => updateRow(r.id, { text: e.target.value })}
              />
            </div>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button onClick={addRow} icon={<IconPlus className="h-4 w-4" />}>
            添加一份
          </Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            loading={busy}
            disabled={!qid}
            icon={<IconUpload className="h-4 w-4" />}
          >
            提交答卷
          </Button>
          <span className="ml-auto text-xs text-ink-3">
            已填写 {rows.filter((r) => r.text.trim()).length} / {rows.length} 份
          </span>
        </div>
      </Card>

      {accepted.length > 0 && (
        <Card className="mt-6 p-5">
          <CardHeader title="本次提交" desc={`已接收 ${accepted.length} 份答卷`} />
          <ul className="mt-3 flex flex-wrap gap-2">
            {accepted.map((a) => (
              <li key={a} className="rounded-md border border-line bg-surface-2 px-2 py-1 font-mono text-xs text-ink-2">
                {a}
              </li>
            ))}
          </ul>
          <p className="mt-3 text-sm leading-relaxed text-ink-2">
            前往「
            <a
              href="/workbench"
              className="font-medium text-accent underline decoration-accent/40 underline-offset-2 hover:text-accent-strong"
            >
              阅卷工作台
            </a>
            」选择该题进行逐点评分。
          </p>
        </Card>
      )}
    </>
  );
}