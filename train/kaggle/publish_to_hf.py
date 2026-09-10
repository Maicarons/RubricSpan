#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 prepare_model_repos.py 生成的厂库目录发布到 Hugging Face。

替代手动 git-lfs 推送：upload_folder 一次性上传整个目录，大文件自动走
Hub 的 LFS/Xet 存储，无需本地 git lfs。ModelScope 侧仍走原 git 流程。

用法（仓库根目录，两库一起发）：
    python train/kaggle/publish_to_hf.py --user <HF用户名>

只发其中一个：
    python train/kaggle/publish_to_hf.py --user <HF用户名> --only mrc

认证（任选其一，凭据不写入本仓库）：
    - 仓库根 .env 填 HF_TOKEN=...
    - 环境变量 HF_TOKEN（https://huggingface.co/settings/tokens，需 write 权限）
    - 本机已 `hf auth login` 缓存的 token
可选加速：pip install hf_transfer 且环境变量 HF_HUB_ENABLE_HF_TRANSFER=1（新版 Xet 后端默认即快）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import load_repo_env  # noqa: E402

load_repo_env()
REPOS = {"mrc": "RubricSpan-mrc-1.0-flash", "similarity": "RubricSpan-similarity-1.0-flash"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--user", required=True, help="HF 用户名")
    p.add_argument("--only", choices=sorted(REPOS), help="只发布其中一个模型")
    p.add_argument("--repo-root", type=Path, default=REPO_ROOT.parent,
                   help="厂库目录所在父目录（默认 RubricSpan 仓库同级）")
    p.add_argument("--private", action="store_true", help="以 private 仓库发布")
    p.add_argument("--message", default="update model artifacts")
    args = p.parse_args(argv)

    try:
        from huggingface_hub import create_repo, upload_folder
    except ImportError:
        print("FAIL: pip install huggingface_hub", file=sys.stderr)
        return 1

    names = [args.only] if args.only else sorted(REPOS)
    for name in names:
        repo_id = f"{args.user}/{REPOS[name]}"
        local = args.repo_root / REPOS[name]
        if not local.exists():
            print(f"WARN: {local} 不存在（先跑 scripts/prepare_model_repos.py），跳过")
            continue
        create_repo(repo_id, repo_type="model", private=args.private, exist_ok=True)
        print(f"uploading {local} -> {repo_id} ...", flush=True)
        upload_folder(
            folder_path=str(local), repo_id=repo_id, repo_type="model",
            commit_message=args.message,
        )
        print(f"OK: https://huggingface.co/{repo_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
