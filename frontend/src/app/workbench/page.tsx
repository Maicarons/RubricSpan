/**
 * 阅卷工作台（核心页面，M5 实现）—— 技术方案 §11.3。
 *
 * 布局规划：
 * - 左侧：题目信息 + 标准得分点列表（权重、aliases 折叠展示）
 * - 中部：学生答案文本，命中片段高亮（hit-exact / hit-semantic / hit-partial），
 *   悬停查看对应得分点与置信度；图片来源时展示原图缩略与识别文本折叠区
 * - 右侧：逐点评分明细卡片 + 总分汇总与评级
 * - 顶部：重新评分 / 开始阅卷 / 导出 / 在线离线切换
 */
export default function WorkbenchPage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="text-2xl font-bold">阅卷工作台</h1>
      <p className="mt-2 text-gray-500">
        骨架占位：三栏布局与评分明细将在 M5 阶段实现（执行计划 §4.6）。
      </p>
    </main>
  );
}
