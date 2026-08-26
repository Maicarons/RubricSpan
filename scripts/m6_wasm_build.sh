#!/usr/bin/env bash
# M6 · WASM 离线产物构建：Rust 评分核心 -> wasm-bindgen JS 胶包 + 运行时资产。
# 依赖：rustup target wasm32-unknown-unknown；本机 wasm-bindgen-cli（版本须与
# backend/crates/rubricspan-wasm/Cargo.toml 中 wasm-bindgen 完全一致）。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND="$ROOT/frontend"
PKG_DIR="$FRONTEND/public/wasm/pkg"
ORT_DIR="$FRONTEND/public/wasm/ort"
MODEL_DIR="$FRONTEND/public/wasm/models"

echo "== [1/4] cargo build (wasm32 release) =="
cargo build --manifest-path "$ROOT/backend/Cargo.toml" \
  -p rubricspan-wasm --target wasm32-unknown-unknown --release

echo "== [2/4] wasm-bindgen 生成 JS 胶包 =="
wasm-bindgen "$ROOT/backend/target/wasm32-unknown-unknown/release/rubricspan_wasm.wasm" \
  --out-dir "$PKG_DIR" --target web

echo "== [3/4] 复制 onnxruntime-web WASM 运行时（本地分发，保证离线） =="
mkdir -p "$ORT_DIR"
cp "$FRONTEND"/node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded*.wasm "$ORT_DIR/"
cp "$FRONTEND"/node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded*.mjs "$ORT_DIR/"

echo "== [4/4] 复制分词器与模型（FP32 现有版；INT8 产出后同名覆盖 model.int8.onnx） =="
mkdir -p "$MODEL_DIR/mrc" "$MODEL_DIR/sim"
cp "$ROOT/models/mrc/tokenizer/vocab.txt" "$MODEL_DIR/vocab.txt"
[ -f "$ROOT/models/mrc/model.onnx" ] && cp "$ROOT/models/mrc/model.onnx" "$MODEL_DIR/mrc/model.onnx"
[ -f "$ROOT/models/similarity/model.onnx" ] && cp "$ROOT/models/similarity/model.onnx" "$MODEL_DIR/sim/model.onnx"
[ -f "$ROOT/models/mrc/model.int8.onnx" ] && cp "$ROOT/models/mrc/model.int8.onnx" "$MODEL_DIR/mrc/model.int8.onnx"
[ -f "$ROOT/models/similarity/model.int8.onnx" ] && cp "$ROOT/models/similarity/model.int8.onnx" "$MODEL_DIR/sim/model.int8.onnx"

echo "完成。启动前端后访问 /offline。"
