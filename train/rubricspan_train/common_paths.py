# -*- coding: utf-8 -*-
"""训练 / 评估 / 导出侧共享路径常量。

数据与模型产物根目录可用环境变量覆盖（默认保持仓库布局），
供云上环境（如 Kaggle：数据挂载在 /kaggle/input、可写区在 /kaggle/working）复用。
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TRAIN_DIR = REPO_ROOT / "train"
DATA_DIR = Path(os.environ.get("RUBRICSPAN_DATA_DIR") or REPO_ROOT / "data")
MODELS_DIR = Path(os.environ.get("RUBRICSPAN_MODELS_DIR") or REPO_ROOT / "models")
PROCESSED_DIR = DATA_DIR / "processed"
CONTRACTS_DIR = REPO_ROOT / "contracts"
