# frontend/ —— Next.js 15 前端

技术方案第 11 章：阅卷工作台与全部功能模块（M5 阶段实现）。

## 开发

```bash
npm install
npm run dev        # 开发模式（默认 3000 端口）
npm run build      # 生产构建
npm run typecheck  # 类型检查
```

环境变量：`NEXT_PUBLIC_API_BASE`（后端服务地址，默认 `http://127.0.0.1:8080`）。

## 结构

```
src/
├── app/
│   ├── layout.tsx / page.tsx   # 根布局与首页（模块入口）
│   ├── questions/              # 试题管理 + 标准答案录入/解析（M5）
│   ├── answers/                # 答卷上传 + OCR 预览（M5）
│   ├── workbench/              # 阅卷工作台（核心页，M5）
│   └── results/                # 结果导出 + 统计看板（M5）
└── lib/
    └── api.ts                  # API 客户端（基于 contracts/openapi.yaml 封装）
```

## 技术栈

- Next.js 15（App Router）+ React 19 + TypeScript（strict）
- Radix UI（组件原语）+ Tailwind CSS（原子样式；命中高亮色见 `tailwind.config.ts`）
- TanStack Query（服务端数据缓存）—— M5 接入

## 双模式

在线模式连接 Rust 后端（`lib/api.ts` 的 `checkHealth` 探测）；
离线模式加载 `wasm/` 构建产物，见 `../wasm/README.md`（M6）。
