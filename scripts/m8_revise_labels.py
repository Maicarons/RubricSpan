# -*- coding: utf-8 -*-
"""M8 仲裁修订工具 —— 修订金标（labels_final.jsonl）并输出修订日志。

M8 调优闭环 Phase A2：对 M7 全链路评估遗留的 34 条高置信分歧与 5 组矛盾标签
执行仲裁修订（判定依据为逐条人工阅读学生答案原文，见 data/m8_arbitration_working.md）：

- 34 条分歧中判「金标漏标」的条目 → 对应点强制修订为正例（hit=True + span + align 回填）；
  定位按「locate（系统原命中片段/卷特征文本）出现在学生答案全文」锁定目标卷，
  span 为修订使用的正例片段。已命中（hit+align）的点跳过（旧 mrc build 未同步，
  重建数据集即可消除分歧）。
- 5 组矛盾标签（SAS-POL-033 / SAS-GEO-012 / SAS-HIST-071）→ 全卷同点统一为「命中」。

注意：labels_final 当前状态与 mrc_test.jsonl（旧 build 产物）可能不同步；
本脚本只改 labels_final，随后必须重跑 `python -m rubricspan_train.data.build` 重建数据集。

用法::

    python scripts/m8_revise_labels.py            # dry-run：打印待修订计划
    python scripts/m8_revise_labels.py --apply    # 写盘（先备份 labels_final.pre-m8.bak）+ 修订日志

产物: data/labeling_cache/labels_final.pre-m8.bak、data/m8_revise_log.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "train"))  # 复用 rubricspan_train.align.aligner

from rubricspan_train.align.aligner import align_span  # noqa: E402

LABELS_PATH = REPO / "data" / "labeling_cache" / "labels_final.jsonl"
BACKUP_PATH = REPO / "data" / "labeling_cache" / "labels_final.pre-m8.bak"
LOG_PATH = REPO / "data" / "m8_revise_log.csv"
CONFIGS_DIR = REPO / "data" / "scoring_configs"

# ---------------------------------------------------------------------------
# 仲裁判定表（人工阅读原文后的结论）
#   locate: 目标卷的指纹文本（系统原命中片段或其所在卷的特征句，须唯一出现于目标卷）
#   span:   修订为命中时使用的正例片段（须出现在目标卷学生答案正文中）
# ---------------------------------------------------------------------------
ARBITRATION: list[dict] = [
    # [1] SAS-CHN-075 学生③回应"毕业后不一定能适应社会需要"，金标漏标
    {"qid": "SAS-CHN-075",
     "point_text": "不是有了兴趣和好成绩毕业后也就一定能很好地适应社会需要",
     "locate": "毕业后也就一定能很好地适应社会需要",
     "span": "并不是所有工科生都能找到合适的工作"},
    # [5] SAS-POL-049 mrc 卷（"加强国际联防联控"句），学生①③表达
    {"qid": "SAS-POL-049",
     "point_text": "只有秉持人类命运共同体理念，加强团结合作，才能打赢全球疫情防控阻击战",
     "locate": "加强国际联防联控",
     "span": "只有坚持人类命运共同体理念，加强国际宏观经济政策协调，支持国际组织发挥作用，才能有效应对疫情给全球经济和各国发展带来的挑战"},
    # [7][17] SAS-CHN-016 选择B项：学生（1）B
    {"qid": "SAS-CHN-016", "point_text": "选择B项", "locate": "（1）B", "span": "B"},
    # [10] SAS-CHN-056 断句正确项为B：学生 10.B（卷含"该拿那些商朝的士人和百姓怎么办"）
    {"qid": "SAS-CHN-056", "point_text": "断句正确项为B",
     "locate": "该拿那些商朝的士人和百姓怎么办", "span": "B"},
    # [12] SAS-CHN-056 "论而供秩"：学生（2）"评定之后安置他们"
    {"qid": "SAS-CHN-056", "point_text": "“论而供秩”译为“评定（之后）安置/供给待遇”",
     "locate": "评定之后安置他们", "span": "评定之后安置他们"},
    # [13] SAS-CHN-016 表达诗人…：学生（2）②直述
    {"qid": "SAS-CHN-016",
     "point_text": "表达诗人虽感叹不遇于时，但不甘沉沦的乐观、自勉之情",
     "locate": "虽有时不我遇之叹", "span": "虽有时不我遇之叹，却始终保持着不甘沉寂、奋发向上的积极心态"},
    # [14] SAS-CHN-061 祖先…：学生①"祖先们便开始利用铜资源，制作铜器"
    {"qid": "SAS-CHN-061", "point_text": "祖先就开始采掘铜矿、铸造铜器",
     "locate": "祖先们便开始利用铜资源", "span": "远古时期，祖先们便开始利用铜资源，制作铜器"},
    # [15][29] SAS-CHN-061 这却没有…：学生②"尚未得到考古发掘的证实"
    {"qid": "SAS-CHN-061", "point_text": "这却一直没有得到考古发掘的证实",
     "locate": "尚未得到考古发掘的证实", "span": "这一说法尚未得到考古发掘的证实"},
    # [16] SAS-POL-016：学生（3）①"在保护村落原始风貌的前提下提升居民生活质量"
    {"qid": "SAS-POL-016",
     "point_text": "在保持原有村落形态的基础上改善居民生活条件",
     "locate": "在保护村落原始风貌的前提下", "span": "在保护村落原始风貌的前提下提升居民生活质量"},
    # [18] SAS-CHN-061 最迟…：学生③原句
    {"qid": "SAS-CHN-061", "point_text": "我国最迟在夏晚期就已经开始使用铜器了",
     "locate": "我国最迟在夏晚期就已经开始使用铜器了", "span": "我国最迟在夏晚期就已经开始使用铜器了"},
    # [20] SAS-CHN-137：学生（2）②直述（系统误抽选项字母 A）
    {"qid": "SAS-CHN-137", "point_text": "独立思考，学术创新，不蹈袭前人",
     "locate": "注重独立思考", "span": "注重独立思考，注重学术创新，从不蹈袭前人"},
    # [27] SAS-POL-049 宗旨：学生②"维护世界和平、促进共同发展是我国外交政策的宗旨"
    {"qid": "SAS-POL-049",
     "point_text": "符合我国外交政策的宗旨和目标（维护国家主权、安全和发展利益，促进世界和平与发展）",
     "locate": "维护世界和平、促进共同发展是我国外交政策的宗旨",
     "span": "维护世界和平、促进共同发展是我国外交政策的宗旨"},
    # [33] SAS-POL-049 只有…（similarity 卷）：学生③"只有坚持…加强国际合作…"
    {"qid": "SAS-POL-049",
     "point_text": "只有秉持人类命运共同体理念，加强团结合作，才能打赢全球疫情防控阻击战",
     "locate": "加强国际合作，才能有效应对疫情",
     "span": "只有坚持人类命运共同体理念，加强国际合作，才能有效应对疫情给全球经济和各国发展带来的挑战"},
    # [34] SAS-POL-049 宗旨（similarity 卷）：同 [27]
    {"qid": "SAS-POL-049",
     "point_text": "符合我国外交政策的宗旨和目标（维护国家主权、安全和发展利益，促进世界和平与发展）",
     "locate": "维护世界和平、促进共同发展是我国外交政策的宗旨",
     "span": "维护世界和平、促进共同发展是我国外交政策的宗旨"},
]

# 矛盾标签组：统一为「命中」（逐组阅读原文后均认定学生表达了得分点）
CONFLICT_QIDS: list[str] = ["SAS-POL-033", "SAS-GEO-012", "SAS-HIST-071"]


def load_configs() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in CONFIGS_DIR.glob("SAS-*.json"):
        out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    return out


def point_text_of(config: dict, point_id: int) -> str | None:
    for pt in config.get("points", []):
        if pt["point_id"] == point_id:
            return pt["point_text"]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="写盘；缺省仅 dry-run 打印计划")
    args = ap.parse_args()

    records = [json.loads(l) for l in LABELS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    configs = load_configs()
    log_rows: list[dict] = []
    errors: list[str] = []
    warnings: list[str] = []
    planned: list[str] = []

    # ---- 1) 仲裁漏标点：强制修订为正例 ----
    for item in ARBITRATION:
        qid, pt, locate, span = item["qid"], item["point_text"], item["locate"], item["span"]
        cfg = configs.get(qid)
        if not cfg:
            errors.append(f"无配置: {qid}")
            continue
        if not any(p["point_text"] == pt for p in cfg["points"]):
            errors.append(f"point_text 不匹配 config: {qid} | {pt[:24]}…")
            continue
        located = False
        for rec in records:
            labs = rec.get("labels", {})
            if labs.get("question_id") != qid:
                continue
            ctx = labs.get("student_answer") or ""
            if locate not in ctx:
                continue
            located = True
            pl = next((p for p in labs.get("point_labels", [])
                       if point_text_of(cfg, p["point_id"]) == pt), None)
            if pl is None:
                continue
            if pl.get("hit") and pl.get("align"):
                continue  # 已命中：只需 rebuild 同步
            res = align_span(ctx, span)
            if res is None:
                warnings.append(f"对齐失败(该卷无此句，保持 impossible): {rec['sample_id']} | {pt[:20]}…")
                continue
            pl["hit"] = True
            pl["hit_type"] = "semantic"
            pl["extracted_span"] = span
            pl["confidence"] = 1.0
            pl["partial_credit"] = 1.0
            pl["align"] = {"start": res.start, "end": res.end, "strategy": res.strategy}
            log_rows.append({
                "kind": "arbitration", "sample_id": rec["sample_id"], "question_id": qid,
                "point_id": pl["point_id"], "point_text": pt, "action": "->hit",
                "old_hit": False, "new_hit": True, "span": span, "align": res.strategy,
            })
            planned.append(f"  {qid} | {rec['sample_id']} p{pl['point_id']} | {pt[:22]}… | align={res.strategy}")
        if not located:
            errors.append(f"未定位仲裁条目(locate 不在任何卷): {qid} | {pt[:20]}… | locate={locate[:18]}…")

    # ---- 2) 矛盾组：同 (ctx, point) 全卷统一为命中 ----
    for qid in CONFLICT_QIDS:
        cfg = configs.get(qid)
        if not cfg:
            errors.append(f"无配置: {qid}")
            continue
        by_ctx: dict[tuple[str, str], list[tuple[int, dict]]] = {}
        for i, rec in enumerate(records):
            labs = rec.get("labels", {})
            if labs.get("question_id") != qid:
                continue
            ctx = labs.get("student_answer") or ""
            for pl in labs.get("point_labels", []):
                key = (ctx, point_text_of(cfg, pl["point_id"]) or "")
                by_ctx.setdefault(key, []).append((i, pl))
        for (ctx, pt), items in by_ctx.items():
            pos_items = [(i, pl) for i, pl in items if pl.get("hit") and pl.get("align")]
            if not pos_items:
                continue  # 无命中侧：整组一致（无冲突可解）
            src_pl = pos_items[0][1]
            for i, pl in items:
                if pl.get("hit") and pl.get("align"):
                    continue
                pl["hit"] = True
                pl["hit_type"] = src_pl.get("hit_type", "semantic")
                pl["extracted_span"] = src_pl.get("extracted_span", "")
                pl["confidence"] = src_pl.get("confidence", 1.0)
                pl["partial_credit"] = src_pl.get("partial_credit", 1.0)
                pl["align"] = dict(src_pl["align"])
                log_rows.append({
                    "kind": "conflict", "sample_id": records[i]["sample_id"],
                    "question_id": qid, "point_id": pl["point_id"],
                    "point_text": pt or "", "action": "unify->hit",
                    "old_hit": False, "new_hit": True,
                    "span": pl.get("extracted_span", ""),
                    "align": f'{src_pl["align"].get("start")}-{src_pl["align"].get("end")}',
                })
                planned.append(f"  {qid} | {records[i]['sample_id']} p{pl['point_id']} | 矛盾统一为命中")

    # ---- 汇总 ----
    print(f"修订计划（{len(planned)} 条）:")
    for line in planned:
        print(line)
    print(f"\n警告（不阻断）: {len(warnings)}")
    for w in warnings:
        print("  [WARN]", w)
    print(f"待确认错误: {len(errors)}")
    for e in errors:
        print("  [ERROR]", e)

    if args.apply:
        if errors:
            print("存在错误，中止写盘")
            return 1
        shutil.copy2(LABELS_PATH, BACKUP_PATH)
        with LABELS_PATH.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        with LOG_PATH.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(log_rows[0].keys()))
            w.writeheader()
            w.writerows(log_rows)
        print(f"已写盘：{LABELS_PATH.name}（备份 {BACKUP_PATH.name}）；日志 {LOG_PATH.name}（{len(log_rows)} 条）")
    else:
        print("dry-run 完成（未写盘）；加 --apply 生效")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())