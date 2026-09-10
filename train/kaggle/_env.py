# -*- coding: utf-8 -*-
"""把仓库根 ``.env`` 合并进 ``os.environ``（已设置的环境变量优先，空值忽略）。

kagglehub / huggingface_hub 只认进程环境变量，不读 .env 文件；
本目录的脚本入口先调 :func:`load_repo_env`，让 ``.env`` 里填的
KAGGLE_API_TOKEN / HF_TOKEN 等直接生效。
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_repo_env() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v
