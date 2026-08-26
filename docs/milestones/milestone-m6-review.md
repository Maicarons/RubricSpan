# 里程碑 M6 评审 · WASM 离线备选（2026-08-23）

> 状态：**PASS（主链路达成里程碑门：浏览器离线单题评分成功）**
> 说明：INT8 模型文件待 M2 看守脚本产出后由 `scripts/m6_wasm_build.sh` 一键换装，
> 页面已内置"优先 INT8、回落 FP32"逻辑，不阻塞本里程碑判定。

## 1. 目标与门

- 关键交付：轻量模型 WASM 构建产物 + 浏览器离线单题演示；
- 里程碑门：**无网络环境下离线评分成功**。

## 2. 交付物

| 交付物 | 位置 | 说明 |
| --- | --- | --- |
| Rust 评分核心 WASM 封装 | `backend/crates/rubricspan-wasm/` | wasm-bindgen 0.2.125；7 个单元测试通过；cdylib+rlib 双 target |
| JS 胶包 | `frontend/public/wasm/pkg/` | `--target web`，218KB .wasm |
| 浏览器推理层 | `frontend/src/lib/bert-tokenizer.ts` `local-inference.ts` | 自研 BERT 中文 WordPiece 分词（码点级偏移契约）+ onnxruntime-web 复刻在线运行时算法 |
| 离线演示页 | `frontend/src/app/offline/page.tsx`（首页有入口） | 初始化 / 示例答案 / 运行日志 / 逐点明细表 |
| 构建脚本 | `scripts/m6_wasm_build.sh` | cargo build → wasm-bindgen → ORT 资产 → 模型复制 |
| 使用说明 | `docs/guides/wasm-offline.md` | 架构、资产清单、能力边界、实测记录 |

## 3. 关键设计决策

1. **预计算推理表替代同步回调桥**：WASM 导入函数只能同步返回，浏览器推理是
   异步的。JS 先完成全部 MRC/相似度张量推理，把结果以 `{mrc:{候选:结果},
   similarity:{得分点:余弦}}` JSON 传入 `scoreAnswer`；评分编排仍完整跑在 Rust
   （`rubricspan-scoring`），与在线端逐分支一致——满足 §10.3 "两套方案结果可比"
   的硬性要求。
2. **不定长填充**：导出 ONNX 序列维为动态轴；浏览器侧按实际 token 数编码，
   结果与 Python 端 max_length 定长填充数学等价，省去 512 定长的无效计算。
3. **INT8 优先加载**：页面 HEAD 探测 `model.int8.onnx`，404 自动回落 FP32；
   M2 量化产物落位后零代码改动生效。

## 4. 验证证据（真实浏览器，Playwright 驱动）

- 初始化：`WASM 就绪：rubricspan-wasm 0.1.0`，分词器 + ONNX 会话就绪；
- 示例答案 1「这场变法发生在1898年，历史上把它称作百日维新。」→ **2/2 · excellent**：
  点 1 精确命中「发生在1898年」(conf 1.000)；点 2 精确命中「历史上把它称作百日维新」
  (conf 1.000) —— 与在线 Rust 网关 `/api/score` 输出完全一致；
- 示例答案 3「猪肉炖粉条是一道东北名菜。」→ **0/2 · fail**：两点相似度兜底未命中
  (cos 0.240 / 0.022)，与在线行为一致；
- 性能：首题含会话创建约 9s；预热后单题约 1s（5 次 MRC + 2 次相似度）；
- 截图：`docs/milestones/m6-offline-demo.png`。

## 5. 过程中发现并修复的问题

| 问题 | 修复 |
| --- | --- |
| onnxruntime-web 同一会话不允许并发 `run()`（Promise.all 双 embed 触发 "Session already started"） | `similarity()` 两次编码改为串行 await |
| crates.io 走 rsproxy 镜像曾 403 导致 wasm-bindgen 无法获取 | 本轮探测恢复可用；CLI 已有 0.2.125，crate 版本锁死一致 |

## 6. 结论

**M6 判定：PASS。** 离线演示在真实浏览器中完整走通"分词 → ONNX 推理 → Rust
WASM 评分核心"，结果与在线端一致，达成里程碑门。遗留项（不阻塞）：INT8 模型
换装（随 M2 收尾自动解锁）、可选的 Service Worker 离线缓存增强。
