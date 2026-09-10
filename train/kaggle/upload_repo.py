#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把训练源码上传为 Kaggle 私有数据集（rubricspan-repo）。

上传内容：train/ 下的 Python 包 + requirements.txt + pyproject.toml + contracts/。
不含 backbone、artifacts、venv、__pycache__ 等运行时产物。

用法（仓库根目录）：
    python train/kaggle/upload_repo.py --handle <KAGGLE用户名>/rubricspan-repo

认证：同 upload_dataset.py（KAGGLE_API_TOKEN 或 ~/.kaggle/kaggle.json）。
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# 需要上传的源码子目录/文件（相对于仓库根，不含 __pycache__ / .git / 模型等）
INCLUDE = [
    "train/rubricspan_train",
    "train/requirements.txt",
    "train/pyproject.toml",
    "train/configs",
    "train/README.md",
    "contracts",
    "train/tests",  # 可选，但小
]

EXCLUDE_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules"}


def collect(src: Path, dst: Path) -> None:
    for rel in INCLUDE:
        s = src / rel
        if not s.exists():
            print(f"WARN: {s} 不存在，跳过")
            continue
        d = dst / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        if s.is_file():
            shutil.copy2(s, d)
        else:
            shutil.copytree(s, d, ignore=shutil.ignore_patterns(*EXCLUDE_DIRS))
        print(f"  {rel} ({_human_size(s)})")


def _human_size(p: Path) -> str:
    if p.is_file():
        return _fmt(p.stat().st_size)
    total = sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and f.name != "__pycache__")
    return _fmt(total)


def _fmt(n: int) -> str:
    return f"{n / 1e6:.0f}MB" if n > 1e6 else f"{n / 1e3:.0f}KB"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--handle", required=True, help="Kaggle handle：<用户名>/rubricspan-repo")
    p.add_argument("--version-notes", default="")
    args = p.parse_args(argv)

    try:
        import kagglehub
    except ImportError:
        print("FAIL: pip install kagglehub", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="rubricspan-repo-") as tmp:
        staging = Path(tmp) / "repo"
        collect(REPO_ROOT, staging)
        print(f"uploading {args.handle} ...", flush=True)
        url = kagglehub.dataset_upload(
            args.handle, str(staging), version_notes=args.version_notes or None
        )
    print(f"OK: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())