import Link from "next/link";

/** 功能模块入口 —— 与技术方案 §11.2 功能模块表对应 */
const modules = [
  { href: "/questions", title: "试题管理", desc: "录入题目与自然语言标准答案" },
  { href: "/answers", title: "答卷上传", desc: "文本录入 / 批量导入 / 试卷图片（OCR）" },
  { href: "/workbench", title: "阅卷工作台", desc: "逐点评分明细、命中高亮、总分解读" },
  { href: "/results", title: "结果与统计", desc: "导出 / 分数分布 / 得分点命中率" },
];

export default function HomePage() {
  return (
    <main className="mx-auto max-w-4xl px-6 py-12">
      <h1 className="text-3xl font-bold">主观题阅卷教师模型</h1>
      <p className="mt-3 text-gray-600">
        本地化智能阅卷系统 · 当前为脚手架骨架，各模块将在 M5 阶段逐步实现。
      </p>
      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {modules.map((m) => (
          <Link
            key={m.href}
            href={m.href}
            className="rounded-lg border p-5 transition hover:border-gray-400 hover:shadow-sm"
          >
            <div className="font-semibold">{m.title}</div>
            <div className="mt-1 text-sm text-gray-500">{m.desc}</div>
          </Link>
        ))}
      </div>
    </main>
  );
}
