---
layout: home

hero:
  name: RubricSpan · 阅微
  text: 中文主观题智能阅卷系统
  tagline: 本地化、可解释、双后端（Rust + GPU 在线 / WASM 离线）的文科主观题评分教师模型
  actions:
    - theme: brand
      text: 技术方案
      link: /project/plan
    - theme: alt
      text: 执行计划
      link: /project/execution-plan

features:
  - title: 可解释评分
    details: 给出分数的同时，逐点标注学生答案中命中每个得分点的原文片段，便于教师复核。
  - title: 同义答案识别
    details: 等价表述扩展（aliases）+ 语义相似度兜底，正确处理「戊戌变法 / 百日维新 / 维新运动」类答案。
  - title: 自然语言标准答案
    details: 教师粘贴自然语言评分说明，由 LLM 自动解析为结构化评分配置（得分点 + 权重 + 等价表述）。
  - title: 双后端模式
    details: Rust + GPU 在线服务（生产首选）与 WASM 浏览器离线演示（备选），评分链路全程本地推理。
---

## 里程碑状态

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 环境与数据就绪 | ✅ 已完成（tag `m0-env`） |
| M1 | 大模型离线打标 | ✅ 已完成（tag `m1-labeling`） |
| M2 | 模型训练与 ONNX 导出 | ✅ 已完成（FP32+INT8 双模型交付；相似度按最优快照交付，[评审](/milestones/milestone-m2-review)） |
| M3 | OCR 与模型运行时集成 | ✅ 已完成（运行时+网关端到端验证，[评审](/milestones/milestone-m3-review)） |
| M4 | Rust 在线后端 | ✅ 已编译/测试通过，修复启动崩溃（[M3 评审 §3](/milestones/milestone-m3-review)） |
| M5 | 前端开发 | ✅ 已构建通过 |
| M6 | WASM 离线备选 | ✅ 已完成（浏览器离线单题评分验证通过，[评审](/milestones/milestone-m6-review)） |
| M7 | 联调 / 评估 / 交付 | ✅ 已完成（系统级 ScoreCorr **0.959** / 等价给分率 **97.4%** 达标，[评审](/milestones/milestone-m7-review)、[评估报告](/reports/m7-eval-report)；两项调优类指标经评审裁剪至迭代闭环） |
| M8 | 推理栈去 Python 化 | ✅ 已完成（ort + tokenizers 原生推理并入 Rust 网关，删除 `backend/runtime/`；金标对拍 53 MRC + 180 相似度逐位一致，e2e 指标零回退；OCR 随运行时移除暂停，`/api/ocr` 返回 501） |

详见 [执行计划](/project/execution-plan)、各里程碑评审与 [评估报告](/reports/m7-eval-report)。
