#!/usr/bin/env python
"""整理本地模型产物 → 两个自足的 **LFS 厂库**（供上传到 HF / ModelScope）。

在仓库根目录的**同级**目录生成（默认 G:\GitHub\RubricSpan-<mrc|similarity>-1.0-flash），
模型文件绝不进入 RubricSpan 的 GitHub 仓库——GitHub 侧只留 models/README.md 链接。

做了什么：
1. 复制每个模型的 onnx 三精度档 + tokenizer + model_card.json；
2. 计算各 onnx 的 sha256，写入 model_card.json 的 `files` 映射；
3. 生成 README.md（基座归属 Apache-2.0、精度档说明、文件清单、使用提示，无个人信息）；
4. 写入 .gitattributes（*.onnx 走 LFS）。

用法（仓库根目录）：
    python scripts/prepare_model_repos.py [--out-root ../..] [--user Maicarons]
之后在生成的厂库内执行：
    git init -b main && git lfs install --local && git add -A && git commit -m v2026.08.23
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODELS = REPO / "models"

SPECS = [
    ("mrc", "RubricSpan-mrc-1.0-flash", "MRC 抽取模型（mengzi-bert-base 微调）", "mrc_extraction"),
    ("similarity", "RubricSpan-similarity-1.0-flash", "语义相似度模型（text2vec 微调）", "sentence_similarity"),
]
ONNX = ["model.onnx", "model.int8.onnx", "model.fp16.onnx"]
TIERS = [
    ("model.onnx", "FP32", "对拍验收档（与金标 1e-3 一致）；GPU/CPU 通用基线"),
    ("model.int8.onnx", "INT8（动态量化）", "CPU 部署档（动态 DQL 在 CUDA 不生效，勿用于 GPU）"),
    ("model.fp16.onnx", "FP16", "GPU 最快档（~6ms/前向）；非对拍档，偏差 ~1e-3"),
]

README_TMPL = """# {repo} · {title}

> RubricSpan（主观题智能阅卷）推理模型 —— ONNX 三精度档 + 分词器。
> 本厂库供 Hugging Face / ModelScope 分发；拉取后放入本地 `models/{sub}/` 布局即可被
> `rubricspan-server --models-dir` 使用。

## 文件清单

| 文件 | 大小 | SHA-256 |
|---|---|---|
{files_table}

`tokenizer/`（tokenizer.json / tokenizer_config.json / special_tokens_map.json / vocab.txt）随仓分发，与模型同次导出。

## 精度档说明

| 档 | 说明 | 部署建议 |
|---|---|---|
{tiers_table}

> GPU 部署：FP16 最快、FP32 与验收一致；INT8 的静态 QDQ 变体曾在 ORT CUDA 验证为数值错误，故仅提供动态 INT8（CPU 档）。

## 基座与训练

- 基座：`{base_model}`（Apache-2.0）
- 任务：`{task}` · ONNX opset {opset}
- 规模：{dataset} · {samples} 样本 · seed {seed}
- 指标：EM {em} · token F1 {f1} · 得分点准确率 {point_acc}
- 导出时间：{ts} · 版本：{version}

## 校验

推理侧加载前应按 `model_card.json` 的 `files` 字段校验 SHA-256（与上表一致），不一致拒绝启动。

## 许可证

**CC BY-NC-SA 4.0**。训练数据含 CC BY-NC 4.0（CMMLU）与 CC BY-NC-SA 4.0（C-Eval）等
非商业来源，模型发布许可对齐最严格数据许可；可自由使用/分享（须署名、非商业、同协议共享），
商业使用需另行取得相关数据集商业授权。基座模型版权归原作者（{base_attr}），使用请保留基座署名。
"""


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def human(n: int) -> str:
    return f"{n / 1e6:.0f}MB" if n >= 1e6 else f"{n / 1e3:.0f}KB"


def build_repo(sub: str, repo_name: str, title: str, task: str, out_root: Path, user: str) -> None:
    src = MODELS / sub
    dst = out_root / repo_name
    dst.mkdir(parents=True, exist_ok=True)

    # 1) 复制文件
    for fn in ONNX:
        f = src / fn
        if f.exists():
            shutil.copy2(f, dst / fn)
    shutil.copytree(src / "tokenizer", dst / "tokenizer", dirs_exist_ok=True)
    card_src = src / "model_card.json"
    card = json.loads(card_src.read_text(encoding="utf-8")) if card_src.exists() else {}

    # 2) sha256 写入卡片
    files = {}
    for fn in ONNX:
        f = dst / fn
        if f.exists():
            files[fn] = {"size_bytes": f.stat().st_size, "sha256": sha256_of(f)}
    card["files"] = files
    (dst / "model_card.json").write_text(
        json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 3) README
    td = card.get("training_data", {})
    metrics = card.get("metrics", {})
    tbl = "\n".join(
        f"| {fn} | {human(files[fn]['size_bytes'])} | `{files[fn]['sha256']}` |"
        for fn in ONNX if fn in files
    )
    base_attr = "mengzi-bert-base (Langboat)" if sub == "mrc" else "text2vec-base-chinese (shibing624)"
    readme = README_TMPL.format(
        repo=repo_name,
        title=title,
        sub=sub,
        files_table=tbl,
        tiers_table="\n".join(f"| {n} | {d} |" for n, _, d in TIERS),
        base_model=card.get("base_model", ""),
        task=task,
        opset=card.get("onnx_opset", 17),
        dataset=td.get("dataset", ""),
        samples=td.get("samples", 0),
        seed=td.get("seed", ""),
        em=metrics.get("em", "—"),
        f1=metrics.get("token_f1", "—"),
        point_acc=metrics.get("point_acc", "—"),
        ts=card.get("exported_at", ""),
        version=card.get("version", ""),
        base_attr=base_attr,
        user=user,
    )
    (dst / "README.md").write_text(readme, encoding="utf-8")

    # 4) LFS attributes
    (dst / ".gitattributes").write_text("# ONNX 权重走 Git LFS\n*.onnx filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8")
    print(f"[ok] {dst}  （{sum(v['size_bytes'] for v in files.values()) / 1e6:.0f}MB）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", type=Path, default=REPO.parent,
                    help="厂库输出根（默认仓库根的同级目录，绝不在工作区内）")
    ap.add_argument("--user", default="Maicarons", help="HF/ModelScope 用户名（README/发布占位）")
    args = ap.parse_args()
    for sub, repo_name, title, task in SPECS:
        build_repo(sub, repo_name, title, task, args.out_root, args.user)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())