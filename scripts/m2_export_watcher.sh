#!/usr/bin/env bash
# M2 导出看守脚本：相似度训练（PID 4384）结束后自动跑 export -> verify -> quantize。
# 背景 bash 的 PATH 极简，故此处显式设置完整 PATH：
#   核心工具(/usr/bin 等) + python + torch/lib，并剔除系统 CUDA 目录的 cuDNN
#   （避免与 torch 自带 cuDNN 冲突导致 WinError 127）。
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
TRAIN_PID=4384
LOG=/tmp/m2_export_watcher.log
SIM_PT_DIR="$REPO/models/artifacts/similarity/pytorch"
# Python 解释器（按需通过环境变量 PY 覆盖；TORCH_LIB 可显式指定 torch/lib 目录）
PY="${PY:-python}"
TORCH_LIB="${TORCH_LIB:-}"

export PATH="./:$TORCH_LIB:/usr/bin:/bin:/mingw64/bin:/c/Windows/System32:/c/Windows/System32/WindowsPowerShell/v1.0:/c/Windows"

echo "$(date -u) watcher started (train_pid=$TRAIN_PID)" >> "$LOG"
while true; do
  if tasklist.exe //FI "PID eq $TRAIN_PID" 2>/dev/null | grep -q "$TRAIN_PID"; then
    echo "$(date -u) training still alive, waiting 60s..." >> "$LOG"
    sleep 60
    continue
  fi
  # 训练已结束
  ckpt=$(ls "$SIM_PT_DIR"/*.safetensors "$SIM_PT_DIR"/pytorch_model.bin 2>/dev/null | head -n1)
  if [ -n "$ckpt" ]; then
    echo "$(date -u) training ended + checkpoint ($ckpt) -> run export chain" >> "$LOG"
    cd "$REPO/train"
    "$PY" -m rubricspan_train.export.onnx export   >> "$LOG" 2>&1; echo "$(date -u) export exit=$?" >> "$LOG"
    "$PY" -m rubricspan_train.export.onnx verify   >> "$LOG" 2>&1; echo "$(date -u) verify exit=$?" >> "$LOG"
    "$PY" -m rubricspan_train.export.onnx quantize >> "$LOG" 2>&1; echo "$(date -u) quantize exit=$?" >> "$LOG"
  else
    echo "$(date -u) training ended but NO checkpoint in $SIM_PT_DIR -> abort" >> "$LOG"
  fi
  break
done
echo "$(date -u) watcher done" >> "$LOG"
