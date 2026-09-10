"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getApiBase, setApiBase, getAdminConfig, checkHealth, getScoringSettings, saveScoringSettings, DEFAULT_SCORING_SETTINGS, type AdminConfig, type ScoringSettings } from "@/lib/api";
import { useTheme, type Theme } from "@/lib/theme";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, PageHeader } from "@/components/ui/card";
import { Field, TextInput } from "@/components/ui/field";
import { IconCheck, IconMoon, IconRefresh, IconServer, IconSun, IconArrowRight } from "@/components/icons";

export default function AdminSettingsPage() {
  const { theme, setTheme } = useTheme();
  const [base, setBase] = useState(() => getApiBase());
  const [saved, setSaved] = useState(false);
  const [probe, setProbe] = useState<"idle" | "checking" | "ok" | "fail">("idle");
  const [serverInfo, setServerInfo] = useState<AdminConfig | null>(null);

  const [scoring, setScoring] = useState<ScoringSettings>(DEFAULT_SCORING_SETTINGS);
  const [scoringMsg, setScoringMsg] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const [scoringSaving, setScoringSaving] = useState(false);
  const [loadingInfo, setLoadingInfo] = useState(true);
  const [infoError, setInfoError] = useState<string | null>(null);

  useEffect(() => {
    getScoringSettings().then(setScoring).catch(() => {});
    setLoadingInfo(true);
    getAdminConfig()
      .then((cfg) => { setServerInfo(cfg); setInfoError(null); })
      .catch((e) => { setInfoError(String(e)); })
      .finally(() => setLoadingInfo(false));
  }, []);

  const scoringValid = scoring.similarity_high > scoring.similarity_low && scoring.similarity_low > 0 && scoring.similarity_high <= 1 && scoring.partial_credit >= 0 && scoring.partial_credit <= 1 && scoring.mrc_confidence_threshold >= 0 && scoring.mrc_confidence_threshold <= 1;

  async function handleSaveScoring() {
    setScoringSaving(true); setScoringMsg(null);
    try {
      const saved_settings = await saveScoringSettings(scoring);
      setScoring(saved_settings);
      setScoringMsg({ tone: "ok", text: "已保存并即时生效（新评分请求生效）" });
    } catch (e) { setScoringMsg({ tone: "danger", text: `保存失败：${e instanceof Error ? e.message : String(e)}` }); }
    finally { setScoringSaving(false); }
  }

  function handleResetScoring() { setScoring(DEFAULT_SCORING_SETTINGS); setScoringMsg(null); }

  async function handleSave() {
    setApiBase(base); setSaved(true); setTimeout(() => setSaved(false), 2000);
    setProbe("checking"); setServerInfo(null);
    const ok = await checkHealth();
    setProbe(ok ? "ok" : "fail");
    if (ok) { try { setServerInfo(await getAdminConfig()); } catch { /* 仅探测，信息加载失败不阻断 */ } }
  }

  function handleReset() { setApiBase(""); setBase(""); setSaved(true); setTimeout(() => setSaved(false), 2000); }

  const themeOptions: { value: Theme; label: string; icon: React.ReactNode }[] = [
    { value: "light", label: "亮色（宣纸）", icon: <IconSun className="h-4 w-4" /> },
    { value: "dark", label: "暗黑（墨底）", icon: <IconMoon className="h-4 w-4" /> },
  ];

  return (
    <>
      <PageHeader title="管理后台 · 设置" desc="服务连接地址、界面偏好与版本信息。API 地址保存在浏览器本地，改动立即生效。"
        action={<Link href="/" className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3.5 py-2 text-sm font-medium text-ink-2 transition-colors hover:border-line-strong hover:bg-surface-2 hover:text-ink"><IconArrowRight className="h-4 w-4 rotate-180" />返回总览</Link>} />

      <div className="mt-6 space-y-5">
        <Card className="p-5">
          <CardHeader title="服务设置" desc="由 Rust 后端同源托管时留空即可；如需跨域连接可在此填入完整地址。"
            action={<span className="rounded-lg bg-accent-soft p-2 text-accent"><IconServer className="h-4 w-4" /></span>} />
          <div className="mt-4 max-w-md">
            <Field label="后端 API 地址" hint="留空即使用同源地址（与当前页面同一域名/端口）。">
              <TextInput value={base} onChange={(e) => setBase(e.target.value)} placeholder="留空 = 同源" spellCheck={false} className="font-mono" />
            </Field>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Button variant="primary" onClick={handleSave} icon={<IconCheck className="h-4 w-4" />}>保存并探测</Button>
            <Button onClick={handleReset}>恢复默认</Button>
            {saved && <Badge tone="ok">已保存</Badge>}
            {probe === "checking" && <span className="inline-flex items-center gap-1.5 text-xs text-ink-3"><IconRefresh className="h-3.5 w-3.5 animate-spin" />探测中…</span>}
            {probe === "ok" && <Badge tone="ok" dot>连接正常</Badge>}
            {probe === "fail" && <Badge tone="danger" dot>连接失败，请检查地址与后端进程</Badge>}
          </div>
          {serverInfo && (
            <div className="mt-4 rounded-lg bg-surface-2 px-4 py-3 text-sm">
              <div className="text-xs font-medium uppercase tracking-wider text-ink-3">已识别服务</div>
              <p className="mt-1.5 text-ink-2">阅微 RubricSpan v{serverInfo.server_version} · 推理模型 {serverInfo.models.mrc ? "已就绪" : "未就绪"} · LLM 端点 {serverInfo.llm.endpoints.length} 个</p>
            </div>
          )}
        </Card>

        <Card className="p-5">
          <CardHeader title="评分参数" desc="相似度兜底阈值、部分命中给分比例与 MRC 置信度判定阈值。保存后在服务端 scoring_settings.json 持久化并即时生效。" />
          <div className="mt-4 grid max-w-lg gap-4 sm:grid-cols-2">
            <Field label="高阈值（语义命中）" hint="≥ 该值判语义命中，给满分">
              <TextInput type="number" step={0.05} min={0} max={1} value={scoring.similarity_high} onChange={(e) => setScoring({ ...scoring, similarity_high: Number(e.target.value) })} />
            </Field>
            <Field label="低阈值（部分命中）" hint="低于该值判未命中">
              <TextInput type="number" step={0.05} min={0} max={1} value={scoring.similarity_low} onChange={(e) => setScoring({ ...scoring, similarity_low: Number(e.target.value) })} />
            </Field>
            <Field label="部分命中给分比例" hint="得分点分值 × 该比例">
              <TextInput type="number" step={0.05} min={0} max={1} value={scoring.partial_credit} onChange={(e) => setScoring({ ...scoring, partial_credit: Number(e.target.value) })} />
            </Field>
            <Field label="MRC 置信度阈值" hint="抽取置信度 ≥ 该值才判精确命中，否则回落相似度">
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

        <Card className="p-5">
          <CardHeader title="界面偏好" desc="保存到浏览器本地，可随时切换。" />
          <div className="mt-4 flex flex-wrap gap-2">
            {themeOptions.map((opt) => {
              const active = theme === opt.value;
              return (
                <button key={opt.value} type="button" onClick={() => setTheme(opt.value)} aria-pressed={active}
                  className={`inline-flex cursor-pointer items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors ${
                    active ? "border-accent bg-accent-soft text-accent-strong" : "border-line bg-surface text-ink-2 hover:border-line-strong hover:text-ink"
                  }`}>
                  {opt.icon} {opt.label}
                </button>
              );
            })}
          </div>
        </Card>

        <Card className="p-5">
          <CardHeader title="关于" desc="部署环境与版本信息。" />
          {infoError && <p className="mt-2 text-xs text-danger">数据加载失败：{infoError}</p>}
          <dl className="mt-4 max-w-md space-y-2.5 text-sm">
            <div className="flex justify-between"><dt className="text-ink-3">后端版本</dt><dd className="font-mono text-ink-2">{loadingInfo ? "加载中…" : serverInfo ? `v${serverInfo.server_version}` : "—"}</dd></div>
            <div className="flex justify-between"><dt className="text-ink-3">推理模型</dt><dd className="text-right"><span className="font-mono text-ink-2">{loadingInfo ? "加载中…" : serverInfo ? `MRC ${serverInfo.models.mrc ? '✓' : '✗'} · 相似度 ${serverInfo.models.similarity ? '✓' : '✗'}` : "—"}</span></dd></div>
            <div className="flex justify-between"><dt className="text-ink-3">LLM 端点</dt><dd className="font-mono text-ink-2">{loadingInfo ? "加载中…" : serverInfo ? `${serverInfo.llm.endpoints.length} 个` : "—"}</dd></div>
            <div className="flex justify-between"><dt className="text-ink-3">OCR</dt><dd className="font-mono text-ink-2">{loadingInfo ? "加载中…" : serverInfo ? (serverInfo.ocr.enabled ? "已就绪" : "未加载") : "—"}</dd></div>
            <div className="flex justify-between"><dt className="text-ink-3">存储后端</dt><dd className="truncate font-mono text-xs text-ink-2">{loadingInfo ? "加载中…" : serverInfo?.store_path ? (serverInfo.store_path.includes('mysql') ? 'MySQL' : 'SQLite') : "—"}</dd></div>
            <div className="flex justify-between"><dt className="text-ink-3">数据落盘</dt><dd className="break-all text-right font-mono text-xs text-ink-2">{loadingInfo ? "加载中…" : serverInfo?.store_path ?? "—"}</dd></div>
            <div className="flex justify-between"><dt className="text-ink-3">开源协议</dt><dd className="font-mono text-ink-2">AGPL-3.0-or-later</dd></div>
          </dl>
        </Card>
      </div>
    </>
  );
}