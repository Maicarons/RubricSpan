# -*- coding: utf-8 -*-
"""M1 打标流水线编排入口。

用法（在仓库根目录，使用系统 Python）::

    python -m rubricspan_train.labeling.run parse-points [--limit N] [--with-reserve]
    python -m rubricspan_train.labeling.run synth       [--limit N]
    python -m rubricspan_train.labeling.run label       [--limit N] [--origins full,fragment,synthetic]
    python -m rubricspan_train.labeling.run selfcheck   [--limit N]
    python -m rubricspan_train.labeling.run quality
    python -m rubricspan_train.labeling.run stats

产物（均不入库，见 .gitignore）：

- ``data/scoring_configs/{qid}.json``   —— 唯一题评分配置（scoring-config 契约）
- ``data/synthetic/synthetic_answers.jsonl`` —— 四档合成答卷
- ``data/labeling_cache/labels_raw.jsonl``    —— 首轮打标（信封格式，内嵌契约对象）
- ``data/labeling_cache/labels_voted.jsonl``  —— 自一致性投票后
- ``data/labeling_cache/labels_final.jsonl``  —— 对齐 + 质检后（训练数据构建输入）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import jsonschema

from ..align.aligner import align_batch  # noqa: F401  (re-export convenience)
from .client import LabelCallError, LLMClient
from .common import (
    DATA_DIR,
    DIR_LABELING_CACHE,
    DIR_SCORING_CONFIGS,
    DIR_SYNTHETIC,
    TRAIN_DIR,
    append_jsonl,
    load_json_schema,
    load_labeling_config,
    load_jsonl,
)
from .prompts import build_label_messages, build_parse_points_messages, build_synth_messages
from .quality import run_quality
from .seeds import SeedQuestion, SeedSample, load_sas_bench, sample_fragments

LABELS_RAW = DIR_LABELING_CACHE / "labels_raw.jsonl"
LABELS_VOTED = DIR_LABELING_CACHE / "labels_voted.jsonl"
LABELS_FINAL = DIR_LABELING_CACHE / "labels_final.jsonl"
SYNTH_FILE = DIR_SYNTHETIC / "synthetic_answers.jsonl"


# ---------------------------------------------------------------------------
# 种子与评分配置
# ---------------------------------------------------------------------------


def build_seed_pool(cfg: dict[str, Any], with_reserve: bool) -> tuple[list[SeedQuestion], list[SeedSample]]:
    subjects = list(cfg["pipeline"]["subjects"])
    if with_reserve:
        subjects += list(cfg["pipeline"].get("reserve_subjects", []))
    return load_sas_bench(DATA_DIR / "raw", subjects)


def load_scoring_configs() -> dict[str, dict]:
    configs = {}
    if DIR_SCORING_CONFIGS.exists():
        for p in sorted(DIR_SCORING_CONFIGS.glob("SAS-*.json")):
            try:
                configs[p.stem] = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                print(f"WARN: skip broken config {p.name}")
    return configs


def _fix_weights(points: list[dict], total: float) -> list[dict]:
    """权重和 ≠ 总分时按比例缩放（保序），保证契约约束 sum(weight)=total_score。"""
    s = sum(p["weight"] for p in points)
    if s <= 0 or abs(s - total) < 0.011:
        return points
    factor = total / s
    for p in points:
        p["weight"] = round(p["weight"] * factor, 2)
    drift = round(total - sum(p["weight"] for p in points), 2)
    if abs(drift) >= 0.01:
        points[-1]["weight"] = round(points[-1]["weight"] + drift, 2)
    return points


def _model_of(out: Any, client: LLMClient) -> str:
    """元数据用模型名：优先取实际产出该条结果的端点模型（fallback 后可能不同）。"""
    return getattr(out, "source_model", "") or client.model


def _normalize_parse_output(raw: dict, q: SeedQuestion, model: str) -> dict:
    """解析输出 → 严格符合 scoring-config 契约的对象；无法修复的字段直接抛错。"""
    points = []
    for p in sorted(raw.get("points", []), key=lambda x: x.get("point_id", 0)):
        text = str(p.get("point_text", "")).strip()
        if not text:
            continue
        aliases = [str(a).strip() for a in (p.get("aliases") or []) if str(a).strip()]
        aliases = list(dict.fromkeys(aliases))  # 去重保序
        try:
            weight = float(p.get("weight", 1))
        except (TypeError, ValueError):
            weight = 1.0
        points.append(
            {
                "point_id": len(points) + 1,
                "point_text": text,
                "weight": max(weight, 0.5),
                "aliases": aliases,
            }
        )
    if not points:
        raise ValueError("no valid points")
    points = _fix_weights(points, float(q.total))
    return {
        "question_id": q.question_id,
        "total_score": float(q.total),
        "subject": q.subject,
        "points": points,
        "meta": {
            "parsed_by": model,
            "parsed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "confirmed_by_teacher": False,
        },
    }


def cmd_parse_points(client: LLMClient, cfg: dict[str, Any], args: argparse.Namespace) -> None:
    questions, _ = build_seed_pool(cfg, args.with_reserve)
    existing = load_scoring_configs()
    todo = [q for q in questions if q.question_id not in existing]
    if args.limit:
        todo = todo[: args.limit]
    print(f"parse-points: {len(todo)} questions to parse ({len(existing)} cached)")
    max_points = int(cfg.get("parse_points", {}).get("max_points", 10))
    schema = load_json_schema("scoring-config.schema.json")
    ok = fail = 0
    results = client.map_json(
        todo,
        lambda q: (
            build_parse_points_messages(q.question_text, q.reference, q.total, q.question_id, max_points),
            {"temperature": 0.1},
        ),
        progress_every=25,
        progress_label="parse",
    )
    for q, out in results:
        if isinstance(out, LabelCallError):
            print(f"  FAIL(call) {q.question_id}: {out}")
            fail += 1
            continue
        try:
            config = _normalize_parse_output(out, q, _model_of(out, client))
            jsonschema.validate(config, schema)
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL(parse) {q.question_id}: {e}")
            fail += 1
            continue
        path = DIR_SCORING_CONFIGS / f"{q.question_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        ok += 1
    print(f"parse-points done: ok={ok} fail={fail} | {client.meter.summary()}")


# ---------------------------------------------------------------------------
# M1-2 合成答卷
# ---------------------------------------------------------------------------


def cmd_synth(client: LLMClient, cfg: dict[str, Any], args: argparse.Namespace) -> None:
    questions, _ = build_seed_pool(cfg, args.with_reserve)
    configs = load_scoring_configs()
    existing = {rec["sample_id"] for rec in load_jsonl(SYNTH_FILE)}
    scfg = cfg.get("synth", {})
    tiers: list[str] = scfg.get("tiers", ["excellent", "good", "fair", "poor"])
    vpt = int(scfg.get("variants_per_tier", 1))
    hist_extra = int(scfg.get("history_extra_variants", 0))

    jobs: list[dict[str, Any]] = []
    for q in questions:
        config = configs.get(q.question_id)
        if not config:
            continue
        variants = vpt + (hist_extra if q.question_id.startswith("SAS-HIST") else 0)
        for tier in tiers:
            for v in range(variants):
                sid = f"{q.question_id}#syn-{tier}-v{v}"
                if sid not in existing:
                    jobs.append(
                        {"sample_id": sid, "question_id": q.question_id, "tier": tier,
                         "variant": v, "question": q.question_text, "points": config["points"]}
                    )
    if args.limit:
        jobs = jobs[: args.limit]
    print(f"synth: {len(jobs)} answers to generate ({len(existing)} cached)")
    tcfg = cfg.get("client", {})
    temp = float(tcfg.get("synth_temperature", 0.9))
    results = client.map_json(
        jobs,
        lambda j: (
            build_synth_messages(j["question"], j["points"], j["tier"], j["variant"]),
            {"temperature": temp + 0.1 * j["variant"], "max_tokens": 4096},
        ),
        progress_every=50,
        progress_label="synth",
    )
    ok = fail = 0
    batch: list[dict] = []
    for job, out in results:
        if isinstance(out, LabelCallError):
            fail += 1
            continue
        answer = str(out.get("answer", "")).strip()
        if len(answer) < 10:
            fail += 1
            continue
        batch.append(
            {
                "sample_id": job["sample_id"],
                "question_id": job["question_id"],
                "origin": "synthetic",
                "tier": job["tier"],
                "variant": job["variant"],
                "student_answer": answer,
                "model": _model_of(out, client),
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
        ok += 1
    if batch:
        append_jsonl(SYNTH_FILE, batch)
    print(f"synth done: ok={ok} fail={fail} | {client.meter.summary()}")


# ---------------------------------------------------------------------------
# M1-3 批量打标
# ---------------------------------------------------------------------------


def _collect_label_samples(
    cfg: dict[str, Any], origins: set[str], with_reserve: bool = False
) -> list[SeedSample]:
    questions, samples = build_seed_pool(cfg, with_reserve=with_reserve)
    picked: list[SeedSample] = []
    if "full" in origins:
        picked += [s for s in samples if s.origin == "full"]
    if "fragment" in origins:
        lcfg = cfg.get("label", {})
        picked += sample_fragments(
            samples,
            total=int(lcfg.get("fragment_samples", 900)),
            miss_ratio=float(lcfg.get("fragment_miss_ratio", 0.25)),
            seed=int(cfg["pipeline"].get("random_seed", 42)),
        )
    if "synthetic" in origins:
        for rec in load_jsonl(SYNTH_FILE):
            picked.append(
                SeedSample(
                    sample_id=rec["sample_id"],
                    question_id=rec["question_id"],
                    student_answer=rec["student_answer"],
                    origin="synthetic",
                    expert_total=None,
                )
            )
    return picked


def _normalize_label_output(
    raw: dict, sample: SeedSample, config: dict, model: str, temperature: float
) -> dict:
    """模型输出 + 流水线回填 → 严格符合 labeling 契约的记录（信封格式）。"""
    valid_ids = {p["point_id"] for p in config["points"]}
    by_id: dict[int, dict] = {}
    for pl in raw.get("point_labels", []):
        try:
            pid = int(pl.get("point_id"))
        except (TypeError, ValueError):
            continue
        if pid not in valid_ids or pid in by_id:
            continue
        hit_type = pl.get("hit_type")
        if hit_type not in ("exact", "semantic", "miss"):
            continue
        hit = bool(pl.get("hit", hit_type != "miss"))
        span = str(pl.get("extracted_span") or "").strip()
        if hit_type == "miss" or not hit:
            hit, hit_type, span = False, "miss", ""
        elif not span:
            hit, hit_type = False, "miss"
        try:
            conf = float(pl.get("confidence", 1.0))
        except (TypeError, ValueError):
            conf = 1.0
        conf = min(max(conf, 0.0), 1.0)
        point = {
            "point_id": pid,
            "hit": hit,
            "hit_type": hit_type,
            "extracted_span": span,
            "confidence": round(conf, 3),
        }
        if hit_type == "semantic":
            try:
                pc = float(pl.get("partial_credit", 1.0))
            except (TypeError, ValueError):
                pc = 1.0
            point["partial_credit"] = min(max(pc, 0.5), 1.0)
        elif hit_type == "exact":
            point["partial_credit"] = 1.0
        rationale = str(pl.get("rationale") or "").strip()
        if rationale:
            point["rationale"] = rationale[:80]
        by_id[pid] = point
    # 缺失的点补 miss（模型漏标视作未命中）
    labels = [by_id.get(pid, {"point_id": pid, "hit": False, "hit_type": "miss",
                               "extracted_span": "", "confidence": 0.5})
              for pid in sorted(valid_ids)]
    labels = sorted(labels, key=lambda x: x["point_id"])
    labels_obj = {
        "question_id": sample.question_id,
        "student_answer": sample.student_answer,
        "point_labels": labels,
        "labeling_meta": {
            "model": model,
            "temperature": temperature,
            "self_consistency_votes": 1,
            "labeled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    }
    return {
        "sample_id": sample.sample_id,
        "origin": sample.origin,
        "expert_total": sample.expert_total,
        "expert_step_label": sample.expert_step_label,
        "labels": labels_obj,
    }


def cmd_label(client: LLMClient, cfg: dict[str, Any], args: argparse.Namespace) -> None:
    origins = {o.strip() for o in args.origins.split(",") if o.strip()}
    samples = _collect_label_samples(cfg, origins, with_reserve=args.with_reserve)
    configs = load_scoring_configs()
    existing = {rec["sample_id"] for rec in load_jsonl(LABELS_RAW)}
    todo = [s for s in samples if s.sample_id not in existing and s.question_id in configs]
    skipped = sum(1 for s in samples if s.sample_id not in existing and s.question_id not in configs)
    if args.limit:
        todo = todo[: args.limit]
    print(f"label: {len(todo)} samples to label ({len(existing)} cached, {skipped} skipped: no config)")
    qmap = {q.question_id: q for q in build_seed_pool(cfg, args.with_reserve)[0]}
    schema = load_json_schema("labeling-schema.json")
    temp = float(cfg.get("client", {}).get("temperature_default", 0.1))

    def make_call(s: SeedSample):
        config = configs[s.question_id]
        messages = build_label_messages(
            qmap[s.question_id].question_text, config["points"], s.student_answer, s.question_id
        )
        return messages, {"temperature": temp}

    # 增量落盘：每 25 条刷盘一次，中断不丢已完成样本
    pend: list[dict] = []
    ok = fail = 0

    def flush() -> None:
        nonlocal pend
        if pend:
            append_jsonl(LABELS_RAW, pend)
            pend = []

    def on_result(sample: SeedSample, out: Any) -> None:
        nonlocal ok, fail, pend
        if isinstance(out, LabelCallError):
            fail += 1
        else:
            try:
                rec = _normalize_label_output(
                    out, sample, configs[sample.question_id], _model_of(out, client), temp
                )
                jsonschema.validate(rec["labels"], schema)
                pend.append(rec)
                ok += 1
            except Exception as e:  # noqa: BLE001
                print(f"  FAIL(normalize) {sample.sample_id}: {e}", flush=True)
                fail += 1
        if len(pend) >= 25:
            flush()

    client.map_json(todo, make_call, progress_every=100, progress_label="label", on_result=on_result)
    flush()
    print(f"label done: ok={ok} fail={fail} | {client.meter.summary()}")


# ---------------------------------------------------------------------------
# M1-4 自一致性校验
# ---------------------------------------------------------------------------


def _vote_point_key(pl: dict) -> tuple:
    return (pl["hit"], pl["hit_type"])


def cmd_selfcheck(client: LLMClient, cfg: dict[str, Any], args: argparse.Namespace) -> None:
    scfg = cfg.get("selfcheck", {})
    votes_total = int(scfg.get("votes", 3))
    extra_temps: list[float] = list(scfg.get("temperatures", [0.7, 1.1]))[: votes_total - 1]
    low_conf = float(scfg.get("low_confidence", 0.75))
    max_samples = int(scfg.get("max_samples", 400))

    records = load_jsonl(LABELS_RAW)
    configs = load_scoring_configs()
    questions, _ = build_seed_pool(cfg, with_reserve=True)
    qmap = {q.question_id: q for q in questions}
    done = {rec["sample_id"] for rec in load_jsonl(LABELS_VOTED)}

    # 高价值样本：含 semantic 命中，或存在低置信点
    def high_value(rec: dict) -> bool:
        pls = rec["labels"]["point_labels"]
        return any(p["hit_type"] == "semantic" for p in pls) or any(
            p["confidence"] < low_conf for p in pls
        )

    candidates = [r for r in records if r["sample_id"] not in done and high_value(r)]
    # 票数有限 → 优先给最不确定的样本（min 点置信度升序）
    candidates.sort(key=lambda r: min(p["confidence"] for p in r["labels"]["point_labels"]))
    candidates = candidates[:max_samples]
    if args.limit:
        candidates = candidates[: args.limit]
    print(f"selfcheck: {len(candidates)} high-value samples x {len(extra_temps)} extra votes")

    jobs = [
        {"rec": rec, "temperature": t}
        for rec in candidates
        for t in extra_temps
    ]

    def make_call(job: dict):
        rec = job["rec"]
        labels = rec["labels"]
        config = configs[rec["labels"]["question_id"]]
        messages = build_label_messages(
            qmap[rec["labels"]["question_id"]].question_text,
            config["points"],
            labels["student_answer"],
            labels["question_id"],
        )
        return messages, {"temperature": job["temperature"]}

    vote_results = client.map_json(jobs, make_call, progress_every=100, progress_label="vote")
    extra_votes: dict[str, list[dict]] = {}
    for job, out in vote_results:
        if isinstance(out, LabelCallError):
            continue
        rec = job["rec"]
        config = configs[rec["labels"]["question_id"]]
        sample = SeedSample(
            sample_id=rec["sample_id"],
            question_id=rec["labels"]["question_id"],
            student_answer=rec["labels"]["student_answer"],
            origin=rec["origin"],
        )
        try:
            voted = _normalize_label_output(
                out, sample, config, _model_of(out, client), job["temperature"]
            )
        except Exception:  # noqa: BLE001
            continue
        extra_votes.setdefault(rec["sample_id"], []).append(voted["labels"]["point_labels"])

    schema = load_json_schema("labeling-schema.json")
    batch: list[dict] = []
    flipped_points = 0
    agree_sum = 0.0
    agree_n = 0
    for rec in candidates:
        rounds = [rec["labels"]["point_labels"]] + extra_votes.get(rec["sample_id"], [])
        final_points, flips, agreement = _majority_vote(rec["labels"]["point_labels"], rounds)
        flipped_points += flips
        agree_sum += agreement
        agree_n += 1
        labels_obj = dict(rec["labels"])
        labels_obj["point_labels"] = final_points
        labels_obj["labeling_meta"] = {
            **rec["labels"].get("labeling_meta", {}),
            "self_consistency_votes": len(rounds),
        }
        jsonschema.validate(labels_obj, schema)
        batch.append({**rec, "labels": labels_obj})
    if batch:
        append_jsonl(LABELS_VOTED, batch)
    # 非高价值样本直接透传
    passthrough = [
        r for r in records if r["sample_id"] not in {b["sample_id"] for b in batch}
        and r["sample_id"] not in done
    ]
    if passthrough:
        append_jsonl(LABELS_VOTED, passthrough)
    consistency = agree_sum / agree_n if agree_n else 1.0
    report = {
        "checked_samples": len(candidates),
        "votes_per_sample": votes_total,
        "point_flips": flipped_points,
        "mean_point_agreement": round(consistency, 4),
        "model": client.describe(),
        "usage": {"prompt_tokens": client.meter.prompt_tokens,
                  "completion_tokens": client.meter.completion_tokens},
    }
    (DIR_LABELING_CACHE / "selfcheck_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"selfcheck done: flips={flipped_points} agreement={consistency:.3f} | {client.meter.summary()}")


def _majority_vote(first_round: list[dict], rounds: list[list[dict]]) -> tuple[list[dict], int, float]:
    """逐点多数投票；平票回退首轮。返回 (最终点标注, 翻转点数, 平均一致率)。"""
    final: list[dict] = []
    flips = 0
    agree_ratios: list[float] = []
    for base in first_round:
        pid = base["point_id"]
        keys = Counter()
        spans: list[dict] = []
        for rnd in rounds:
            pl = next((p for p in rnd if p["point_id"] == pid), None)
            if pl is None:
                continue
            keys[_vote_point_key(pl)] += 1
            spans.append(pl)
        if not keys:
            final.append(base)
            continue
        winner_key, winner_n = keys.most_common(1)[0]
        # 平票回退首轮判断
        if winner_n <= len(rounds) / 2:
            winner_key = _vote_point_key(base)
        agree_ratios.append(winner_n / len(rounds))
        chosen = None
        for pl in spans:  # 与胜出判断一致中置信度最高者的 span
            if _vote_point_key(pl) == winner_key and (chosen is None or pl["confidence"] > chosen["confidence"]):
                chosen = pl
        merged = dict(base)
        if chosen is not None:
            merged.update(
                {
                    "hit": chosen["hit"],
                    "hit_type": chosen["hit_type"],
                    "extracted_span": chosen["extracted_span"],
                    "confidence": round(
                        sum(p["confidence"] for p in spans) / len(spans), 3
                    ),
                }
            )
            if chosen["hit_type"] == "semantic":
                merged["partial_credit"] = chosen.get("partial_credit", 1.0)
            else:
                merged.pop("partial_credit", None)
                if chosen["hit_type"] == "exact":
                    merged["partial_credit"] = 1.0
            merged.pop("rationale", None)
        if _vote_point_key(merged) != _vote_point_key(base):
            flips += 1
        final.append(merged)
    return final, flips, (sum(agree_ratios) / len(agree_ratios) if agree_ratios else 1.0)


# ---------------------------------------------------------------------------
# quality / stats
# ---------------------------------------------------------------------------


def cmd_quality(cfg: dict[str, Any]) -> None:
    run_quality(cfg)


def cmd_stats(_cfg: dict[str, Any]) -> None:
    configs = load_scoring_configs()
    raw = load_jsonl(LABELS_RAW)
    voted = load_jsonl(LABELS_VOTED)
    final = load_jsonl(LABELS_FINAL)
    synth = load_jsonl(SYNTH_FILE)
    print(f"scoring_configs: {len(configs)}")
    print(f"synthetic answers: {len(synth)}")
    print(f"labels_raw: {len(raw)}")
    print(f"labels_voted: {len(voted)}")
    print(f"labels_final: {len(final)}")
    for name, recs in (("raw", raw), ("voted", voted), ("final", final)):
        if not recs:
            continue
        hits = sum(1 for r in recs for p in r["labels"]["point_labels"] if p["hit"])
        sem = sum(1 for r in recs for p in r["labels"]["point_labels"] if p["hit_type"] == "semantic")
        ex = sum(1 for r in recs for p in r["labels"]["point_labels"] if p["hit_type"] == "exact")
        total_points = sum(len(r["labels"]["point_labels"]) for r in recs)
        print(
            f"  [{name}] point_labels={total_points} hits={hits} "
            f"(exact={ex}, semantic={sem}, semantic/hits={sem / hits:.1%})" if hits else f"  [{name}] no hits"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RubricSpan M1 labeling pipeline")
    sub = parser.add_subparsers(dest="stage", required=True)
    for name in ("parse-points", "synth", "label", "selfcheck"):
        p = sub.add_parser(name)
        p.add_argument("--limit", type=int, default=0, help="only process first N items (0=all)")
        p.add_argument("--with-reserve", action="store_true", help="include reserve subjects")
        if name == "label":
            p.add_argument("--origins", default="full,fragment,synthetic")
    sub.add_parser("quality")
    sub.add_parser("stats")

    args = parser.parse_args(argv)
    cfg = load_labeling_config()
    if args.stage == "quality":
        cmd_quality(cfg)
        return 0
    if args.stage == "stats":
        cmd_stats(cfg)
        return 0

    t0 = time.time()
    client = LLMClient.from_env(TRAIN_DIR.parent / ".env", cfg)
    print(f"endpoints (fallback order): {client.describe()}")
    {"parse-points": cmd_parse_points, "synth": cmd_synth,
     "label": cmd_label, "selfcheck": cmd_selfcheck}[args.stage](client, cfg, args)
    print(f"stage '{args.stage}' wall time: {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
