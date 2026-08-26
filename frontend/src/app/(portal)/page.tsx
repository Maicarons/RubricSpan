import Link from "next/link";
import {
  IconArrowRight,
  IconBook,
  IconChart,
  IconCloudOff,
  IconCpu,
  IconFileText,
  IconGauge,
  IconPen,
  IconServer,
  IconUpload,
} from "@/components/icons";
import { Badge } from "@/components/ui/badge";

/**
 * 前台门户落地页：功能模块入口、工作流、技术特性（与 docs/index.md 数据一致）。
 * 纯服务端组件：无交互逻辑，入场动画走 CSS 类。
 */

const stats = [
  { value: "0.959", label: "系统级评分相关性", note: "M7 达标基准" },
  { value: "97.4%", label: "等价给分率", note: "M7 评审达标" },
  { value: "100%", label: "推理在本机完成", note: "ONNX Runtime · Rust 引擎" },
];

const modules = [
  {
    href: "/questions",
    title: "试题管理",
    desc: "录入题目与自然语言标准答案，解析为标准得分点配置，状态全程可跟踪。",
    icon: <IconBook className="h-5 w-5" />,
  },
  {
    href: "/answers",
    title: "答卷上传",
    desc: "学生作答文本批量录入，学号/班级可选，支持逐份校验与补录。",
    icon: <IconUpload className="h-5 w-5" />,
  },
  {
    href: "/workbench",
    title: "阅卷工作台",
    desc: "逐点评分明细、答案命中高亮、总分解读，一次看清给分依据。",
    icon: <IconPen className="h-5 w-5" />,
  },
  {
    href: "/results",
    title: "结果与统计",
    desc: "分数分布、评级分布、得分点命中率，CSV / JSON 一键导出。",
    icon: <IconChart className="h-5 w-5" />,
  },
  {
    href: "/offline",
    title: "离线单题演示",
    desc: "无网络环境浏览器本地 WASM 推理评分（M6 备选模式）。",
    icon: <IconCloudOff className="h-5 w-5" />,
  },
];

const workflow = [
  { step: "壹", title: "录入试题", desc: "填写题干、学科与满分，可附带自然语言标准答案。" },
  { step: "贰", title: "解析标准答案", desc: "大模型把标准答案解析为得分点与等价表述，人工复核后确认。" },
  { step: "叁", title: "批量录入答卷", desc: "逐份或批量录入学生作答文本，按试题归档。" },
  { step: "肆", title: "评分与复盘", desc: "逐点评分并高亮命中片段，汇总分布与命中率，导出结果。" },
];

const techPoints = [
  {
    icon: <IconCpu className="h-5 w-5" />,
    title: "Rust 评分引擎",
    desc: "推理、编排、存储同进程，混合评分链路与 WASM 共享同一份核心逻辑。",
  },
  {
    icon: <IconGauge className="h-5 w-5" />,
    title: "ONNX 本地推理",
    desc: "MRC 抽取 + 语义相似度双通道，模型与分词器全程本机运行。",
  },
  {
    icon: <IconServer className="h-5 w-5" />,
    title: "多端点解析",
    desc: "标准答案解析走 OpenAI 兼容端点，多端点自动 fallback，密钥不出服务端。",
  },
  {
    icon: <IconFileText className="h-5 w-5" />,
    title: "冻结契约",
    desc: "前后端以 OpenAPI 契约为唯一依据，变更需登记 CC 记录并全方确认。",
  },
];

/** 朱批演示卡：hero 右侧静态示例（纯装饰）。 */
function HeroPaper() {
  return (
    <div className="relative mx-auto w-full max-w-md animate-scale-in lg:mx-0">
      <div className="relative z-10 rotate-1 rounded-2xl border border-line bg-surface p-6 shadow-card-hover">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="font-mono text-xs text-ink-3">Q001 · 历史 · 满分 5 分</div>
            <p className="mt-2 text-sm leading-relaxed text-ink">简述戊戌变法的主要影响。</p>
          </div>
          <span
            aria-hidden="true"
            className="shrink-0 rounded-lg border-2 border-accent/70 px-2 py-1 font-kai text-2xl font-bold leading-none text-accent"
          >
            优
          </span>
        </div>
        <div className="mt-4 rounded-lg bg-surface-2 p-3 text-sm leading-relaxed">
          <span className="text-ink-3">学生答：</span>
          <span className="text-ink">戊戌变法发生在</span>
          <mark className="rounded bg-hit-exact px-1 text-hit-exact-ink">1898 年</mark>
          <span className="text-ink">，又称</span>
          <mark className="rounded bg-hit-partial px-1 text-hit-partial-ink">百日维新</mark>
          <span className="text-ink">，推动了思想启蒙。</span>
        </div>
        <div className="mt-4 flex items-center justify-between border-t border-line pt-3">
          <Badge tone="ok" dot>
            评级 · 优秀
          </Badge>
          <div className="font-serif text-2xl font-bold text-ink">
            5<span className="ml-0.5 text-sm font-medium text-ink-3">/ 5</span>
          </div>
        </div>
      </div>
      <div className="absolute -bottom-5 -left-4 -rotate-3 rounded-xl border border-line bg-surface px-4 py-3 shadow-pop">
        <div className="text-xs font-medium text-ink-2">得分点 1 · 精确命中</div>
        <div className="mt-0.5 font-mono text-xs text-ok">MRC 置信度 0.982</div>
      </div>
    </div>
  );
}

export default function PortalHomePage() {
  return (
    <main>
      {/* ------------------------------------------------ hero */}
      <section className="relative overflow-hidden border-b border-line bg-canvas-deep/60">
        {/* 氛围：朱砂淡晕 + 细密点阵 */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgb(var(--accent)/0.10),transparent_42%),radial-gradient(circle_at_85%_75%,rgb(var(--accent)/0.08),transparent_45%)]"
        />
        <div className="relative mx-auto grid max-w-6xl grid-cols-1 items-center gap-12 px-6 py-16 lg:grid-cols-[1.1fr_0.9fr] lg:py-24">
          <div>
            <Badge tone="accent" className="animate-fade-up">
              主观题智能阅卷平台
            </Badge>
            <h1
              className="mt-5 animate-fade-up font-serif text-4xl font-bold leading-[1.25] tracking-wide text-ink sm:text-5xl"
              style={{ animationDelay: "60ms" }}
            >
              让每一次阅卷，
              <br />
              都有据可依
              <span aria-hidden="true" className="ml-2 inline-block h-[0.4em] w-2 rounded-full bg-accent align-baseline" />
            </h1>
            <p
              className="mt-5 max-w-xl animate-fade-up text-base leading-relaxed text-ink-2"
              style={{ animationDelay: "120ms" }}
            >
              从录入试题、解析标准答案，到逐点评分与结果复盘——全流程本地推理，
              数据不出本机。教师掌握给分依据，学生看到命中与缺漏。
            </p>
            <div className="mt-8 flex animate-fade-up flex-wrap items-center gap-3" style={{ animationDelay: "180ms" }}>
              <Link
                href="/questions"
                className="inline-flex items-center gap-2 rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink shadow-sm transition-colors hover:bg-accent-strong"
              >
                进入工作台
                <IconArrowRight className="h-4 w-4" />
              </Link>
              <Link
                href="/offline"
                className="inline-flex items-center gap-2 rounded-lg border border-line-strong bg-surface px-5 py-2.5 text-sm font-medium text-ink transition-colors hover:border-accent hover:text-accent"
              >
                离线演示
              </Link>
            </div>
            <dl className="mt-10 grid animate-fade-up grid-cols-3 gap-4 border-t border-line pt-6" style={{ animationDelay: "240ms" }}>
              {stats.map((s) => (
                <div key={s.label}>
                  <dd className="font-serif text-2xl font-bold text-ink sm:text-3xl">{s.value}</dd>
                  <dt className="mt-1 text-xs text-ink-2">{s.label}</dt>
                  <dt className="text-[10px] text-ink-3">{s.note}</dt>
                </div>
              ))}
            </dl>
          </div>
          <div className="pb-6 lg:pb-0">
            <HeroPaper />
          </div>
        </div>
      </section>

      {/* ------------------------------------------------ 功能模块 */}
      <section id="features" className="mx-auto max-w-6xl scroll-mt-20 px-6 py-16">
        <div className="animate-fade-up">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">功能模块</p>
          <h2 className="mt-2 font-serif text-2xl font-bold tracking-wide text-ink sm:text-3xl">
            一条完整的阅卷流水线
          </h2>
        </div>
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {modules.map((m, i) => (
            <Link
              key={m.href}
              href={m.href}
              className="group animate-fade-up rounded-xl border border-line bg-surface p-5 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/60 hover:shadow-card-hover"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <div className="flex items-center gap-3">
                <span className="rounded-lg bg-accent-soft p-2.5 text-accent transition-colors group-hover:bg-accent group-hover:text-accent-ink">
                  {m.icon}
                </span>
                <span className="font-serif text-lg font-semibold text-ink">{m.title}</span>
                <IconArrowRight className="ml-auto h-4 w-4 text-ink-3 transition-all duration-200 group-hover:translate-x-0.5 group-hover:text-accent" />
              </div>
              <p className="mt-3 text-sm leading-relaxed text-ink-2">{m.desc}</p>
            </Link>
          ))}
          <Link
            href="/admin"
            className="group flex animate-fade-up flex-col justify-between rounded-xl border border-dashed border-line-strong p-5 transition-colors duration-200 hover:border-accent/60 hover:bg-surface"
            style={{ animationDelay: `${modules.length * 60}ms` }}
          >
            <div className="flex items-center gap-3">
              <span className="rounded-lg bg-surface-2 p-2.5 text-ink-2 transition-colors group-hover:text-accent">
                <IconGauge className="h-5 w-5" />
              </span>
              <span className="font-serif text-lg font-semibold text-ink">管理后台</span>
              <IconArrowRight className="ml-auto h-4 w-4 text-ink-3 transition-all duration-200 group-hover:translate-x-0.5 group-hover:text-accent" />
            </div>
            <p className="mt-3 text-sm leading-relaxed text-ink-2">
              运行统计、系统状态与服务设置——服务级运行视图。
            </p>
          </Link>
        </div>
      </section>

      {/* ------------------------------------------------ 工作流 */}
      <section id="workflow" className="scroll-mt-20 border-y border-line bg-canvas-deep/50">
        <div className="mx-auto max-w-6xl px-6 py-16">
          <div className="animate-fade-up text-center">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">工作流</p>
            <h2 className="mt-2 font-serif text-2xl font-bold tracking-wide text-ink sm:text-3xl">
              四步完成一场阅卷
            </h2>
          </div>
          <ol className="mt-10 grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-4">
            {workflow.map((w, i) => (
              <li key={w.title} className="relative animate-fade-up" style={{ animationDelay: `${i * 80}ms` }}>
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-accent/60 bg-accent-soft font-kai text-lg font-bold text-accent">
                    {w.step}
                  </span>
                  <h3 className="font-serif text-base font-semibold text-ink">{w.title}</h3>
                </div>
                <p className="mt-3 pl-1 text-sm leading-relaxed text-ink-2">{w.desc}</p>
                {i < workflow.length - 1 && (
                  <IconArrowRight
                    aria-hidden="true"
                    className="absolute -bottom-5 left-12 hidden h-4 w-4 rotate-90 text-line-strong lg:block"
                  />
                )}
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ------------------------------------------------ 技术特性 */}
      <section id="tech" className="mx-auto max-w-6xl scroll-mt-20 px-6 py-16">
        <div className="animate-fade-up">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">技术特性</p>
          <h2 className="mt-2 font-serif text-2xl font-bold tracking-wide text-ink sm:text-3xl">
            为"本地优先"而设计
          </h2>
        </div>
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {techPoints.map((t, i) => (
            <div
              key={t.title}
              className="animate-fade-up rounded-xl border border-line bg-surface p-5 shadow-card"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <span className="inline-flex rounded-lg bg-surface-2 p-2.5 text-accent">{t.icon}</span>
              <h3 className="mt-3 font-serif text-base font-semibold text-ink">{t.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{t.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ------------------------------------------------ CTA */}
      <section className="mx-auto max-w-6xl px-6 pb-4">
        <div className="animate-fade-up overflow-hidden rounded-2xl border border-accent/30 bg-gradient-to-br from-accent-soft via-surface to-surface p-8 text-center sm:p-12">
          <h2 className="font-serif text-2xl font-bold tracking-wide text-ink sm:text-3xl">
            从第一道试题开始
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-ink-2">
            录入题目与标准答案，几分钟内即可完成解析、配置并开始逐点评分。
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/questions"
              className="inline-flex items-center gap-2 rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink shadow-sm transition-colors hover:bg-accent-strong"
            >
              新建试题
              <IconArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/admin"
              className="inline-flex items-center gap-2 rounded-lg border border-line-strong bg-surface px-5 py-2.5 text-sm font-medium text-ink transition-colors hover:border-accent hover:text-accent"
            >
              查看管理后台
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}