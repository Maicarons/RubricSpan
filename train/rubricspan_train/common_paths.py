# -*- coding: utf-8 -*-
"""训练 / 评估 / 导出侧共享路径常量。"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TRAIN_DIR = REPO_ROOT / "train"
DATA_DIR = REPO_ROOT / "data"
MODELS_DIR = REPO_ROOT / "models"
PROCESSED_DIR = DATA_DIR / "processed"
CONTRACTS_DIR = REPO_ROOT / "contracts"
