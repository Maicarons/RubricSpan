"use client";

/**
 * 离线单题评分演示（M6 · 技术方案 §10.2 方案 B）。
 *
 * 全流程本地推理，不依赖任何服务端：
 * 1. 加载 rubricspan-wasm（Rust 混合评分核心）；
 * 2. onnxruntime-web + 本站分词器完成 MRC / 相似度张量推理；
 * 3. 预计算推理表交回 WASM 评分核心，得到与在线端一致的 ScoreOutcome。
 *
 * 标准答案解析在离线场景降级为手动编辑评分配置 JSON（§10.3）。
 */

import { useCallback, useRef, useState } from "react";

import type { MrcResult } from "@/lib/local-inference";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, PageHeader } from "@/components/ui/card";
import { TextArea } from "@/components/ui/field";
import { IconCloudOff, IconPen } from "@/components/icons";

interface PointDetail {
  point_id: number;
  hit_status: string;
  matched_alias: string | null;
  extracted_span: string | null;
  confidence: number | null;
  similarity: number | null;
  point_score: number;
  source: string;
}

interface ScoreOutcome {
  question_id: string;
  total_score: number;
  max_score: number;
  rating: string;
  point_details: PointDetail[];
}

interface ScoringPointCfg {
  point_id: number;
  point_text: string;
  weight: number;
  aliases: string[];
}

interface ScoringConfigLite {
  question_id: string;
  total_score: number;
  points: ScoringPointCfg[];
}

const PRESET_CONFIG = JSON.stringify(
  {
    question_id: "Q_OFFLINE_DEMO",
    total_score: 2,
    subject: "history",
    points: [
      { point_id: 1, point_text: "发生在1898年", weight: 1, aliases: ["1898年"] },
      { point_id: 2, point_text: "又称百日维新", weight: 1, aliases: ["百日维新", "维新运动"] },
    ],
    thresholds: { similarity_high: 0.85, similarity_low: 0.6 },
    meta: { note: "M6 离线演示预设：戊戌变法两得分点" },
  },
  null,
  2,
);

const PRESET_ANSWERS = [
  "这场变法发生在1898年，历史上把它称作百日维新。",
  "戊戌变法是一次资产阶级改良运动，也叫维新运动。",
  "猪肉炖粉条是一道东北名菜。",
];

type WasmModule = {
  default: () => Promise<void>;
  scoreAnswer: (configJson: string, answer: string, inferenceJson: string) => string;
  version: () => string;
};

const HIT_LABEL: Record<string, string> = {
  hit_exact: "精确命中",
  hit_semantic: "语义命中",
  partial: "部分命中",
  miss: "未命中",
};

export default function OfflinePage() {
  const [configText, setConfigText] = useState(PRESET_CONFIG);
  const [answer, setAnswer] = useState(PRESET_ANSWERS[0]);
  const [log, setLog] = useState<string[]>([]);
  const [outcome, setOutcome] = useState<ScoreOutcome | null>(null);
  const [busy, setBusy] = useState(false);
  const wasmRef = useRef<WasmModule | null>(null);
  const inferenceRef = useRef<{
    mrcExtract: (c: string, a: string) => Promise<MrcResult>;
    similarity: (p: string, a: string) => Promise<number>;
  } | null>(null);
  const logRef = useRef<HTMLPreElement>(null);

  const say = useCallback((msg: string) => {
    setLog((prev) => [...prev.slice(-40), `[${new Date().toLocaleTimeString()}] ${msg}`]);
    requestAnimationFrame(() => logRef.current?.scrollTo(0, logRef.current.scrollHeight));
  }, []);

  const init = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    try {
      say("加载 rubricspan-wasm …");
      // public/ 下的构建产物（wasm-bindgen 生成），运行时加载、不参与打包；
      // webpackIgnore 使 Next.js 原样保留该绝对路径请求。
      // @ts-expect-error 该模块由 wasm-bindgen 在 M6 构建期产出，不在 src 类型图内
      const mod = (await import(/* webpackIgnore: true */ "/wasm/pkg/rubricspan_wasm.js")) as unknown as WasmModule;
      await mod.default();
      wasmRef.current = mod;
      say(`WASM 就绪：${mod.version()}`);

      say("加载分词器与 ONNX 模型（首次约数百 MB，请耐心等待）…");
      const { LocalInference } = await import("@/lib/local-inference");
      const li = await LocalInference.create("/wasm/models");
      inferenceRef.current = li;
      say("本地推理引擎就绪（onnxruntime-web · wasm EP）。可以点击「离线评分」。");
    } catch (e) {
      say(`初始化失败：${String(e)}`);
    } finally {
      setBusy(false);
    }
  }, [busy, say]);

  const score = useCallback(async () => {
    const wasm = wasmRef.current;
    const li = inferenceRef.current;
    if (!wasm || !li) {
      say("尚未初始化，请先点击「初始化本地引擎」。");
      return;
    }
    let cfg: ScoringConfigLite;
    try {
      cfg = JSON.parse(configText) as ScoringConfigLite;
    } catch (e) {
      say(`评分配置不是合法 JSON：${String(e)}`);
      return;
    }
    setBusy(true);
    setOutcome(null);
    try {
      // ---- 第一步：JS 侧预计算全部模型推理（异步）----
      const candidates = new Set<string>();
      for (const p of cfg.points ?? []) {
        candidates.add(p.point_text);
        for (const a of p.aliases ?? []) candidates.add(a);
      }
      const list = [...candidates];
      const mrc: Record<string, MrcResult> = {};
      for (let i = 0; i < list.length; i++) {
        say(`MRC 推理 ${i + 1}/${list.length}：「${list[i]}」…`);
        mrc[list[i]] = await li.mrcExtract(list[i], answer);
      }
      const similarity: Record<string, { cosine: number }> = {};
      const pointTexts = [...new Set((cfg.points ?? []).map((p) => p.point_text))];
      for (let i = 0; i < pointTexts.length; i++) {
        say(`相似度推理 ${i + 1}/${pointTexts.length}：「${pointTexts[i]}」↔ 全文`);
        similarity[pointTexts[i]] = { cosine: await li.similarity(pointTexts[i], answer) };
      }

      // ---- 第二步：WASM 评分核心编排（同步，与在线端同一套 Rust 逻辑）----
      say("调用 WASM 评分核心 …");
      const raw = wasm.scoreAnswer(configText, answer, JSON.stringify({ mrc, similarity }));
      const result = JSON.parse(raw) as ScoreOutcome;
      setOutcome(result);
      say(`评分完成：${result.total_score}/${result.max_score}（${result.rating}）`);
    } catch (e) {
      say(`评分失败：${String(e)}`);
    } finally {
      setBusy(false);
    }
  }, [answer, busy, configText, say]);

  return (
    <>
      <PageHeader
        title="离线单题评分演示"
        desc="无网络环境下浏览器本地推理：onnxruntime-web 运行模型张量计算，Rust/WASM 评分核心执行与在线端一致的混合评分。首次初始化需从本站下载模型文件。"
        action={
          <span className="rounded-lg bg-accent-soft p-2 text-accent">
            <IconCloudOff className="h-4 w-4" />
          </span>
        }
      />

      {/* 控制条 */}
      <div className="mt-5 flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={init} loading={busy} icon={<IconCloudOff className="h-4 w-4" />}>
          初始化本地引擎
        </Button>
        <Button onClick={score} disabled={busy} icon={<IconPen className="h-4 w-4" />}>
          离线评分
        </Button>
        <span aria-hidden="true" className="mx-1 hidden h-5 w-px bg-line-strong sm:block" />
        {PRESET_ANSWERS.map((a, i) => (
          <Button key={i} size="sm" onClick={() => setAnswer(a)} disabled={busy}>
            示例答案 {i + 1}
          </Button>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* 配置 JSON */}
        <Card className="p-4">
          <CardHeader title="评分配置 JSON" desc="离线降级为手动编辑（需与 scoring-config schema 一致）" />
          <TextArea
            className="mt-3 font-mono text-xs leading-relaxed"
            aria-label="评分配置 JSON"
            rows={18}
            value={configText}
            onChange={(e) => setConfigText(e.target.value)}
            spellCheck={false}
          />
        </Card>

        <div className="space-y-5">
          {/* 学生答案 */}
          <Card className="p-4">
            <CardHeader title="学生答案" desc="支持预设与自由编辑" />
            <TextArea
              className="mt-3"
              aria-label="学生答案"
              rows={4}
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
            />
          </Card>

          {/* 运行日志（终端样式，两主题下保持一致） */}
          <Card className="overflow-hidden p-0">
            <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
              <span aria-hidden="true" className="flex gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-danger/70" />
                <span className="h-2.5 w-2.5 rounded-full bg-warn/70" />
                <span className="h-2.5 w-2.5 rounded-full bg-ok/70" />
              </span>
              <span className="text-xs font-medium text-ink-2">运行日志</span>
            </div>
            <pre
              ref={logRef}
              aria-label="运行日志"
              className="h-56 overflow-auto whitespace-pre-wrap bg-[#0d1117] p-3 font-mono text-xs leading-relaxed text-[#7ee787]"
            >
              {log.join("\n") || "（等待操作）"}
            </pre>
          </Card>
        </div>
      </div>

      {outcome && (
        <Card className="mt-6 p-5">
          <CardHeader
            title={`总分 ${outcome.total_score} / ${outcome.max_score}`}
            desc="逐点判定明细（与在线端同一评分核心）"
            action={<Badge tone="ok" dot>评级 {outcome.rating}</Badge>}
          />
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-surface-2 text-left text-xs uppercase tracking-wider text-ink-3">
                <tr>
                  <th className="px-4 py-2.5 font-medium">点</th>
                  <th className="px-4 py-2.5 font-medium">判定</th>
                  <th className="px-4 py-2.5 font-medium">来源</th>
                  <th className="px-4 py-2.5 font-medium">命中片段 / 相似度</th>
                  <th className="px-4 py-2.5 font-medium">置信</th>
                  <th className="px-4 py-2.5 text-right font-medium">得分</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {outcome.point_details.map((d) => (
                  <tr key={d.point_id}>
                    <td className="px-4 py-2.5 font-mono text-ink">{d.point_id}</td>
                    <td className="px-4 py-2.5">
                      <Badge tone={d.hit_status === "hit_exact" ? "ok" : d.hit_status === "hit_semantic" ? "info" : d.hit_status === "partial" ? "warn" : "neutral"}>
                        {HIT_LABEL[d.hit_status] ?? d.hit_status}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5 text-ink-2">{d.source === "mrc" ? "MRC 抽取" : "相似度兜底"}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-ink-2">
                      {d.extracted_span ? `“${d.extracted_span}”` : d.similarity?.toFixed(4)}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-ink-3">{d.confidence?.toFixed(3) ?? "-"}</td>
                    <td className="px-4 py-2.5 text-right font-mono font-medium text-ink">{d.point_score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}