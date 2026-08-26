import { defineConfig } from 'vitepress'

// VitePress 文档站配置（源码位于本 docs/ 目录）。
// 部署：.github/workflows/docs.yml 通过 GitHub Pages 自动发布。
export default defineConfig({
  title: 'RubricSpan · 阅微',
  description: '中文主观题智能阅卷系统 · 项目文档',
  lang: 'zh-CN',
  cleanUrls: true,
  head: [['link', { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' }]],
  themeConfig: {
    nav: [
      { text: '入门', link: '/guides/getting-started' },
      { text: '技术方案', link: '/project/plan' },
      { text: '执行计划', link: '/project/execution-plan' },
      { text: '里程碑', link: '/milestones/milestone-m7-review' },
    ],
    sidebar: [
      {
        text: '项目',
        items: [
          { text: '技术方案（计划书）', link: '/project/plan' },
          { text: '执行计划', link: '/project/execution-plan' },
        ],
      },
      {
        text: '上手',
        items: [
          { text: '入门教程 · 快速开始', link: '/guides/getting-started' },
        ],
      },
      {
        text: '组件指南',
        items: [
          { text: '后端 · Rust Workspace', link: '/guides/guide-backend' },
          { text: '前端 · Next.js 15', link: '/guides/guide-frontend' },
          { text: '训练 · Python 流水线', link: '/guides/guide-training' },
          { text: 'WASM 离线演示', link: '/guides/wasm-offline' },
          { text: '部署与运行手册', link: '/guides/deployment' },
        ],
      },
      {
        text: '里程碑评审',
        items: [
          { text: 'M0 环境与数据就绪', link: '/milestones/milestone-m0-review' },
          { text: 'M1 大模型打标', link: '/milestones/milestone-m1-review' },
          { text: 'M2 模型训练与导出', link: '/milestones/milestone-m2-review' },
          { text: 'M3 模型运行时与推理集成', link: '/milestones/milestone-m3-review' },
          { text: 'M4+M5 在线后端与前端', link: '/milestones/milestone-m4-m5-review' },
          { text: 'M6 WASM 离线备选', link: '/milestones/milestone-m6-review' },
          { text: 'M7 联调评估与交付', link: '/milestones/milestone-m7-review' },
        ],
      },
      {
        text: '评估与产物报告',
        items: [
          { text: '全链路评估报告', link: '/reports/m7-eval-report' },
          { text: '仲裁清单（BC-002）', link: '/reports/arbitration-sheet' },
          { text: 'ONNX 一致性校验', link: '/reports/m2-onnx-consistency' },
          { text: 'INT8 量化对比', link: '/reports/m2-int8-quantization' },
        ],
      },
      {
        text: '质量与合规',
        items: [
          { text: 'Bad Case 登记', link: '/quality/bad-cases' },
          { text: '契约变更记录', link: '/quality/changelog-contracts' },
          { text: '许可证与合规', link: '/quality/licenses' },
        ],
      },
    ],
    socialLinks: [
      { icon: 'github', link: 'https://github.com/Maicarons/RubricSpan' },
    ],
    search: { provider: 'local' },
    footer: {
      message: 'RubricSpan · 阅微 —— 中文主观题智能阅卷系统',
      copyright: 'AGPL-3.0',
    },
  },
})
