#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把训练数据子集上传为 Kaggle **私有数据集**（kagglehub）。

上传内容：data/ 下训练相关目录（raw / processed / synthetic / goldens /
labeling_cache）；store.db、scoring 等运行时数据不上传。
首次上传创建数据集，之后每次运行生成新版本（可在 Kaggle 上回滚）。

用法（仓库根目录）：
    python train/kaggle/upload_dataset.py --handle <KAGGLE用户名>/rubricspan-data

认证（任选其一，凭据不写入任何文件）：
    - 仓库根 .env 填 KAGGLE_API_TOKEN=...
    - 环境变量 KAGGLE_API_TOKEN（Settings → API → Create New Token）
    - 旧式 ~/.kaggle/kaggle.json（Settings → API → Create Legacy API Key）
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import load_repo_env  # noqa: E402

load_repo_env()

# 训练/打标需要的仓库内数据子集；不在名单中的运行时数据一律不上传
INCLUDE_DIRS = ["raw", "processed", "synthetic", "goldens", "labeling_cache"]


def stage_subset(data_dir: Path, staging: Path) -> None:
    for name in INCLUDE_DIRS:
        src = data_dir / name
        if not src.exists():
            print(f"WARN: {src} 不存在，跳过")
            continue
        print(f"staging {name}/ ...", flush=True)
        shutil.copytree(src, staging / name)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--handle", required=True, help="Kaggle 数据集 handle：<用户名>/rubricspan-data")
    p.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    p.add_argument("--version-notes", default="")
    args = p.parse_args(argv)

    try:
        import kagglehub
    except ImportError:
        print("FAIL: pip install kagglehub", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="rubricspan-kaggle-") as tmp:
        staging = Path(tmp) / "dataset"
        staging.mkdir()
        stage_subset(args.data_dir, staging)
        print(f"uploading {args.handle} (private dataset) ...", flush=True)
        url = kagglehub.dataset_upload(
            args.handle, str(staging), version_notes=args.version_notes or None
        )
    print(f"OK: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
