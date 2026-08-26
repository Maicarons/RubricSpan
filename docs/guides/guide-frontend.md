# 前端指南 · Next.js 15

> 技术方案 §11 · 阅卷平台前端（M5 实现，M6 增补离线入口，M8 平台化重构：前中后台 + 暗黑模式）。
> 组件根目录：[`frontend/`](https://github.com/Maicarons/RubricSpan/tree/main/frontend)

## 开发

```bash
cd frontend
npm install
npm run dev        # 开发模式（默认 3000 端口）
npm run build      # 生产构建
npm run typecheck  # tsc --noEmit
```

环境变量：`NEXT_PUBLIC_API_BASE`（后端地址，默认 `http://127.0.0.1:8080`；
可在 admin「设置」页运行时覆盖，存于 localStorage `rubricspan.apiBase`）。

## 页面结构（路由组三段式）

```
src/
├── app/
│   ├── layout.tsx                # 根布局：主题 Provider + 防闪烁脚本 + 全局样式
│   ├── (portal)/                 # 前台门户：落地页（hero/功能/工作流/技术特性）
│   │   └── page.tsx
│   ├── (app)/                    # 中台（工作台）：侧边栏壳 `app-shell`，URL 不带前缀
│   │   ├── layout.tsx            # AppShell：侧边栏导航 + 顶栏（服务状态/亮暗切换）
│   │   ├── questions/            # 试题管理 + 标准答案录入 / LLM 解析确认
│   │   ├── answers/              # 答卷上传：文本批量录入 + 图片识别（RapidOCR · M8.1 恢复）
│   │   ├── workbench/            # 阅卷工作台：逐点明细、命中片段高亮、总分评级
│   │   ├── results/              # 结果查询 + 统计看板（分布图 / 命中率 / 导出）
│   │   └── offline/              # 离线单题评分演示（WASM，见 [WASM 离线](/guides/wasm-offline)）
│   └── (admin)/                  # 后台：管理后台壳 `admin-shell`（朱批顶线 + 标签导航）
│       ├── admin/page.tsx        # /admin 总览：聚合统计 + 系统状态（/api/admin/*）
│       └── admin/settings/       # /admin/settings 设置：API 地址 / 主题偏好 / 关于
├── components/
│   ├── app-shell.tsx             # 中台壳（侧边栏 + 抽屉 + 服务状态轮询）
│   ├── admin-shell.tsx           # 后台壳
│   ├── portal-nav.tsx            # 前台导航
│   ├── brand-mark.tsx            # 品牌标识（朱砂印章「阅」）
│   ├── icons.tsx                 # 全站图标集（Lucide 风格内联 SVG，零依赖）
│   ├── theme-toggle.tsx          # 亮暗切换
│   └── ui/                       # 薄组件层：button / card / badge / field / stat / progress
└── lib/
    ├── api.ts                    # 在线 API 客户端（动态 API 地址；admin 聚合接口）
    ├── theme.tsx                 # 主题 Provider（localStorage + 跟随系统）
    ├── bert-tokenizer.ts         # BERT 中文分词器（离线用，码点级偏移契约）
    └── local-inference.ts        # onnxruntime-web 推理层（复刻在线运行时算法）
```

## 设计系统：墨卷 · Ink & Vermilion

- 语义色令牌经 CSS 变量（`app/globals.css`）在亮（宣纸）/暗（墨底）主题间切换，
  `tailwind.config.ts` 映射为工具类（`bg-surface` / `text-ink` / `border-line` / `bg-accent` 等）；
- 主色为**朱砂**（`--accent`），呼应批注/印章传统；字体栈：sans 界面正文、
  serif 卷宗标题、kai 印章批注（全本机字体，离线可用）；
- 暗黑模式：class 策略（`dark` 挂在 `<html>`），`lib/theme.tsx` 持久化到
  `localStorage["rubricspan.theme"]`，首帧防闪烁由根布局内联脚本完成；
- 组件层无状态、零运行时依赖，接口语义（variant/size/tone）便于未来整体替换 shadcn/ui。

## 技术栈与双模式

- Next.js 15（App Router）+ React 19 + TypeScript strict；Radix UI + Tailwind CSS；
- **在线模式**：连接 Rust 后端（`lib/api.ts` 的 `checkHealth` 探测，顶栏状态点轮询）；
- **离线模式**：`/offline` 页加载 WASM 构建产物本地推理，
  架构与能力边界见 [WASM 离线](/guides/wasm-offline)。