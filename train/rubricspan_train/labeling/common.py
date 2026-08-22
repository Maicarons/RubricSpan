# -*- coding: utf-8 -*-
"""M1 流水线公共工具：路径、配置加载、JSONL 读写。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
TRAIN_DIR = REPO_ROOT / "train"
DATA_DIR = REPO_ROOT / "data"
CONTRACTS_DIR = REPO_ROOT / "contracts"

DIR_SCORING_CONFIGS = DATA_DIR / "scoring_configs"
DIR_SYNTHETIC = DATA_DIR / "synthetic"
DIR_LABELING_CACHE = DATA_DIR / "labeling_cache"
DIR_PROCESSED = DATA_DIR / "processed"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_labeling_config() -> dict[str, Any]:
    return load_yaml(TRAIN_DIR / "configs" / "labeling.yaml")


def read_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_jsonl(path: Path) -> list[dict]:
    return list(read_jsonl(path))


def append_jsonl(path: Path, records: list[dict] | dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(records, dict):
        records = [records]
    with path.open("a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_json_schema(name: str) -> dict:
    return json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))
