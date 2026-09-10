"use client";

import { useCallback, useEffect, useState } from "react";
import { getAdminConfig, getScoringSettings, saveScoringSettings, DEFAULT_SCORING_SETTINGS, type AdminConfig, type ScoringSettings } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, PageHeader } from "@/components/ui/card";
import { Field, TextInput } from "@/components/ui/field";
import { IconServer, IconCpu, IconDatabase, IconActivity, IconPen, IconCheck, IconRefresh } from "@/components/icons";

export default function AdminConfigPage() {
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const [scoring, setScoring] = useState<ScoringSettings>(DEFAULT_SCORING_SETTINGS);
  const [scoringMsg, setScoringMsg] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const [scoringSaving, setScoringSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setErr(null);
    try {
      const [c, s] = await Promise.all([getAdminConfig(), getScoringSettings()]);
      setConfig(c); setScoring(s);
    } catch (e) { setErr(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const scoringValid = scoring.similarity_high > scoring.similarity_low && scoring.similarity_low > 0 && scoring.similarity_high <= 1 && scoring.partial_credit >= 0 && scoring.partial_credit <= 1 && scoring.mrc_confidence_threshold >= 0 && scoring.mrc_confidence_threshold <= 1;

  async function handleSaveScoring() {
    setScoringSaving(true); setScoringMsg(null);
    try {
      const saved = await saveScoringSettings(scoring);
      setScoring(saved);
      setScoringMsg({ tone: "ok", text: "已保存并即时生效" });
    } catch (e) { setScoringMsg({ tone: "danger", text: `保存失败：${e instanceof Error ? e.message : String(e)}` }); }
    finally { setScoringSaving(false); }
  }

  function handleResetScoring() { setScoring(DEFAULT_SCORING_SETTINGS); setScoringMsg(null); }

  return (
    <>
      <PageHeader title="管理后台 · 配置" desc="服务端运行信息、模型状态、LLM 端点、OCR 状态及评分参数。所有配置为只读，评分参数除外。"
        action={<Button onClick={() => void load()} loading={loading} icon={<IconRefresh className="h-4 w-4" />}>刷新</Button>} />

      {err && !loading && (
        <div role="alert" className="mt-4 rounded-lg border border-danger/40 bg-danger-soft px-3.5 py-3 text-sm leading-relaxed text-danger">
          {err}
        </div>
      )}

      {loading ? (
        <div className="mt-6 space-y-4" aria-hidden="true">
          <div className="h-48 animate-pulse rounded-xl border border-line bg-surface" />
          <div className="h-48 animate-pulse rounded-xl border border-line bg-surface" />
        </div>
      ) : config ? (
        <div className="mt-6 space-y-5">
          {/* 服务器信息 */}
          <Card className="p-5">
            <CardHeader title="服务器信息" desc="服务端版本与数据存储路径"
              action={<span className="rounded-lg bg-accent-soft p-2 text-accent"><IconServer className="h-4 w-4" /></span>} />
            <dl className="mt-4 space-y-3.5 text-sm">
              <div className="flex items-start justify-between gap-3 border-b border-line pb-2.5">
                <dt className="flex items-center gap-1.5 text-ink-3"><IconCpu className="h-4 w-4" />服务版本</dt>
                <dd className="font-mono text-ink">v{config.server_version}</dd>
              </div>
              <div className="flex items-start justify-between gap-3 border-b border-line pb-2.5">
                <dt className="flex items-center gap-1.5 text-ink-3"><IconDatabase className="h-4 w-4" />数据落盘路径</dt>
                <dd className="break-all text-right font-mono text-xs text-ink-2">{config.store_path}</dd>
              </div>
            </dl>
          </Card>

          {/* 模型状态 */}
          <Card className="p-5">
            <CardHeader title="模型状态" desc="推理引擎运行状态"
              action={<span className="rounded-lg bg-accent-soft p-2 text-accent"><IconActivity className="h-4 w-4" /></span>} />
            <dl className="mt-4 space-y-3.5 text-sm">
              <div className="flex items-start justify-between gap-3 border-b border-line pb-2.5">
                <dt className="flex items-center gap-1.5 text-ink-3"><IconActivity className="h-4 w-4" />MRC 模型</dt>
                <dd><Badge tone={config.models.mrc ? "ok" : "danger"} dot>{config.models.mrc ? "已就绪" : "未就绪"}</Badge></dd>
              </div>
              <div className="flex items-start justify-between gap-3 border-b border-line pb-2.5">
                <dt className="flex items-center gap-1.5 text-ink-3"><IconActivity className="h-4 w-4" />相似度模型</dt>
                <dd><Badge tone={config.models.similarity ? "ok" : "danger"} dot>{config.models.similarity ? "已就绪" : "未就绪"}</Badge></dd>
              </div>
            </dl>
          </Card>

          {/* LLM 端点 */}
          <Card className="p-5">
            <CardHeader title="LLM 端点" desc="已配置的大语言模型推理端点"
              action={<span className="rounded-lg bg-accent-soft p-2 text-accent"><IconServer className="h-4 w-4" /></span>} />
            {config.llm.endpoints.length === 0 ? (
              <div className="mt-4">
                <Badge tone="warn">未配置 LLM 端点</Badge>
                <p className="mt-2 text-xs text-ink-3">部分评分功能（如语义分析）可能不可用。</p>
              </div>
            ) : (
              <div className="mt-4 space-y-2.5">
                {config.llm.endpoints.map((ep) => (
                  <div key={ep.name} className="rounded-lg border border-line bg-surface-2 px-4 py-3 text-sm">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-ink">{ep.name}</span>
                      <Badge tone="neutral">{ep.model}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-3">
              <span className="text-xs text-ink-3">LLM 配置状态：</span>
              <Badge tone={config.llm.configured ? "ok" : "warn"} dot>{config.llm.configured ? "已配置" : "未配置"}</Badge>
            </div>
          </Card>

          {/* OCR 状态 */}
          <Card className="p-5">
            <CardHeader title="OCR 状态" desc="光学字符识别（图片转文字）"
              action={<span className="rounded-lg bg-accent-soft p-2 text-accent"><IconPen className="h-4 w-4" /></span>} />
            <div className="mt-4">
              <Badge tone={config.ocr.enabled ? "ok" : "neutral"} dot>{config.ocr.enabled ? "可用" : "暂停"}</Badge>
              {config.ocr.note && <p className="mt-2 text-sm text-ink-3">{config.ocr.note}</p>}
            </div>
          </Card>

          {/* 评分参数（可编辑） */}
          <Card className="p-5">
            <CardHeader title="评分参数" desc="相似度兜底阈值、部分命中给分比例与 MRC 置信度阈值。保存后在服务端持久化并即时生效。" />
            <div className="mt-4 grid max-w-lg gap-4 sm:grid-cols-2">
              <Field label="高阈值（语义命中）" hint=">= 该值判语义命中，给满分">
                <TextInput type="number" step={0.05} min={0} max={1} value={scoring.similarity_high} onChange={(e) => setScoring({ ...scoring, similarity_high: Number(e.target.value) })} />
              </Field>
              <Field label="低阈值（部分命中）" hint="低于该值判未命中">
                <TextInput type="number" step={0.05} min={0} max={1} value={scoring.similarity_low} onChange={(e) => setScoring({ ...scoring, similarity_low: Number(e.target.value) })} />
              </Field>
              <Field label="部分命中给分比例" hint="得分点分值 x 该比例">
                <TextInput type="number" step={0.05} min={0} max={1} value={scoring.partial_credit} onChange={(e) => setScoring({ ...scoring, partial_credit: Number(e.target.value) })} />
              </Field>
              <Field label="MRC 置信度阈值" hint="抽取置信度 >= 该值才判精确命中">
                <TextInput type="number" step={0.05} min={0} max={1} value={scoring.mrc_confidence_threshold} onChange={(e) => setScoring({ ...scoring, mrc_confidence_threshold: Number(e.target.value) })} />
              </Field>
            </div>
            {!scoringValid && <p className="mt-3 text-xs text-danger">参数非法：需满足 0 &lt; 低阈值 &lt; 高阈值 ≤ 1，且给分比例、MRC 置信度阈值在 0–1 之间。</p>}
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Button variant="primary" onClick={handleSaveScoring} disabled={!scoringValid || scoringSaving} icon={<IconCheck className="h-4 w-4" />}>{scoringSaving ? "保存中…" : "保存评分参数"}</Button>
              <Button onClick={handleResetScoring}>恢复默认</Button>
              {scoringMsg && <Badge tone={scoringMsg.tone === "ok" ? "ok" : "danger"}>{scoringMsg.text}</Badge>}
            </div>
          </Card>
        </div>
      ) : null}
    </>
  );
}