#!/usr/bin/env python3
"""零分带残余误差审计：金标错位 vs 合成泄漏的自动归类清单。

背景（docs/reports/deploy-improvement.md §3）：题干剥离 + 参数从严后，
零分卷被给分率 63.6% → 18.0%，残余 18% 集中在 3 份答卷，归两类：
1. **金标错位**：答卷包含对得分点的实质性讨论（语义等价、措辞不同），
   但专家判零分——治理在打标口径侧；
2. **合成泄漏**：采集时混入与参考答案几乎一致的语句，片段非题干，剥离触及不到——
   治理在合成/采集侧。

本工具不重新跑网关（复用 e2e_eval_strip_strict.json 的逐点记录），只做两类检测：

A. **零分带清单**：gold=0 且 pred>0 的记录 → 逐 FP 点归因：
   - `verbatim-leak`：抽取片段与参考表述（query/aliases）有 ≥8 字归一化原句重合
     （合成泄漏特征，治理在数据侧）；
   - `semantic-discussion`：无原句重合但被判中（金标错位特征，治理在打标口径侧）。
B. **全量泄漏扫描**：mrc_test.jsonl 中 is_impossible=True 的行，答案文本含与参考
   表述 ≥8 字归一化原句重合且**非题干来源**的片段（未被网关评分的潜在泄漏）。

用法：python scripts/audit_zero_band.py [--strict paper/artifacts/e2e_eval_strip_strict.json]
产出：paper/artifacts/zero_band_audit.md（随论文材料存档，不入库）+ 控制台摘要。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from m7_e2e_eval import MRC_TEST, SAS_RAW, build_stems  # noqa: E402

MIN_MATCH_CHARS = 8
STRICT_JSON = ROOT / "paper" / "artifacts" / "e2e_eval_strip_strict.json"
OUT_MD = ROOT / "paper" / "artifacts" / "zero_band_audit.md"

# 与 rubricspan-scoring::preprocess 同构的归一化：忽略空白/标点/数字/注释上标，拉丁小写。
_IGNORABLE = set("0123456789，。；：、！？（）【】《》「」『』“”‘’…—·～．﹒＊＃＋－／＝０１２３４５６７８９") | {
    chr(c) for c in range(ord("①"), ord("⑳") + 1)
} | {chr(c) for c in range(ord("⑴"), ord("⑽") + 1)} | {chr(c) for c in range(ord("㈠"), ord("㈩") + 1)}


def norm(text: str) -> str:
    """与 rubricspan-scoring::preprocess 同构的归一化（宽松版）：
    忽略空白/标点/数字/注释上标，ASCII 字母折叠小写，其余（主要为汉字）保留。
    """
    out: list[str] = []
    for c in text:
        if c in _IGNORABLE or c.isspace():
            continue
        if c.isascii():
            if c.isalnum():
                out.append(c.lower())
            continue
        out.append(c)
    return "".join(out)


def longest_common_substring(a: str, b: str) -> str:
    """两归一化串的最长公共子串（LCS 动态规划，长度 ≤ 数十字，开销可忽略）。"""
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    best = 0
    end_a = 0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
                if dp[i][j] > best:
                    best = dp[i][j]
                    end_a = i
    return a[end_a - best:end_a]


def in_stem(hit: str, stem_norm: str) -> bool:
    """命中片段是否出自题干（含参考自身措辞的边缘 1–2 字容错）。

    例：题干引文言「苟可以利民，不循其礼」，参考表述带"翻译正确"后缀，
    命中片段「苟可以利民不循其礼翻译」去掉尾部 2 字即入题干 → 判为题干污染。
    """
    if not stem_norm:
        return False
    if hit in stem_norm:
        return True
    for drop in (1, 2):
        if len(hit) > MIN_MATCH_CHARS + drop and hit[:-drop] in stem_norm:
            return True
        if len(hit) > MIN_MATCH_CHARS + drop and hit[drop:] in stem_norm:
            return True
    return False


def classify_span(extracted: str, refs: list[str]) -> tuple[str, str]:
    """返回 (类别, 命中片段)。参考表述任一 ≥8 字原句重合 → verbatim-leak，否则 semantic-discussion。"""
    a = norm(extracted)
    for ref in refs:
        r = norm(ref)
        if not a or not r:
            continue
        hit = longest_common_substring(a, r)
        if len(hit) >= MIN_MATCH_CHARS:
            return "verbatim-leak", hit
    return "semantic-discussion", ""


def load_mrc_rows() -> list[dict]:
    with open(MRC_TEST, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", type=Path, default=STRICT_JSON)
    args = ap.parse_args()

    strict = json.loads(args.strict.read_text(encoding="utf-8"))
    rows = load_mrc_rows()
    # 金标-答案上下文索引：(question_id, context) -> mrc_test 行（origin=full 为主）
    ctx_by_q: dict[str, dict[str, list[dict]]] = {}
    for r in rows:
        ctx_by_q.setdefault(r["question_id"], {}).setdefault(r["context"], []).append(r)

    zero_band = [r for r in strict["records"] if r["gold"] == 0 and r["pred"] > 0]
    leaks_total = 0
    md: list[str] = [
        "# 零分带残余误差审计（自动归类清单）",
        "",
        f"> {args.strict.name} · 生成时间 {__import__('datetime').datetime.now():%Y-%m-%d %H:%M} · "
        "脚本 scripts/audit_zero_band.py",
        "",
        f"零分带记录（gold=0 且 pred>0）：**{len(zero_band)}** 卷。",
        "",
        "> 答卷原文按 question_id 取 mrc_test 中首份 `origin=full` 上下文；同题多份答卷时",
        "> 请按 qid 核对具体实例。`semantic-discussion` 为模型判中但无参考原句重合的点——",
        "> 需人工仲裁细分为「金标错位」（答卷确实质性讨论得分点）与「观点相反误报」",
        "> （学生答错/答反但表述沾边，BC-002 同类）。",
        "",
        "## A. 零分带逐卷明细",
        "",
    ]
    for rec in sorted(zero_band, key=lambda x: x["question_id"]):
        qid = rec["question_id"]
        fp = [d for d in rec["details"] if d["point_score"] > 0]
        # 取该题下上下文包含抽取片段的 origin=full 行作为答卷原文（同卷多份时取首份）
        contexts = ctx_by_q.get(qid, {})
        answer_text = ""
        for ctx, rws in contexts.items():
            full = [r for r in rws if r.get("origin") == "full"]
            if full:
                answer_text = ctx
                break
        md.append(f"### {qid} · pred {rec['pred']:.1f} / gold {rec['gold']} / max {rec['max']}")
        md.append("")
        md.append("```")
        md.append(answer_text[:400])
        md.append("```")
        md.append("")
        md.append("| 点 | 判定 | 抽取片段 | 参考表述（query/aliases） | 置信 | 归因 |")
        md.append("|---|---|---|---|---|---|")
        for d in fp:
            refs = [d.get("matched_alias") or ""] + _refs_for(qid, d["point_id"], rows)
            cat, hit = classify_span(d.get("extracted_span") or "", refs)
            if cat == "verbatim-leak":
                leaks_total += 1
            md.append(
                f"| {d['point_id']} | {d['hit_status']} | {d.get('extracted_span','')[:40]} | "
                f"{refs[0][:40]} | {d.get('confidence', 0):.3f} | {cat}" + (f"（`{hit}`）" if hit else "") + " |"
            )
        md.append("")

    md += [
        "## B. 全量泄漏扫描（mrc_test is_impossible 行）",
        "",
        "答案文本含与参考表述 ≥8 字归一化原句重合、且非题干来源的片段——",
        "即使本次未进入评测样本，也是合成侧泄漏的存量证据：",
        "",
    ]
    stems = build_stems()
    leaked_rows: list[tuple[dict, str, str]] = []
    for r in rows:
        if not r.get("is_impossible") or r.get("origin") != "full":
            continue
        ctx_norm = norm(r["context"])
        if len(ctx_norm) < MIN_MATCH_CHARS:
            continue
        refs = [r["query"]] + list(r.get("query_aliases") or [])
        stem = stems.get(r["question_id"], "")
        stem_norm = norm(stem)
        for ref in refs:
            ref_norm = norm(ref)
            hit = longest_common_substring(ctx_norm, ref_norm)
            if len(hit) < MIN_MATCH_CHARS:
                continue
            # 重合片段同样出现在题干里 → 属题干污染（运行时剥离已处理），不算泄漏
            if in_stem(hit, stem_norm):
                continue
            leaked_rows.append((r, ref, hit))
            break
    if leaked_rows:
        md.append(f"共 **{len(leaked_rows)}** 行命中（去重后），下表列前 20：")
        md.append("")
        md.append("| qid | 参考表述（截断） | 泄漏片段 | 答案文本（截断） |")
        md.append("|---|---|---|---|")
        for r, ref, hit in leaked_rows[:20]:
            md.append(
                f"| {r['id']} | {ref[:40]} | `{hit[:30]}` | {r['context'][:50]} |"
            )
        md.append("")
    else:
        md.append("无命中。")
        md.append("")

    summary = {
        "n_zero_band": len(zero_band),
        "n_verbatim_leak_fp": leaks_total,
        "n_semantic_discussion_fp": sum(
            len([d for d in r["details"] if d["point_score"] > 0]) for r in zero_band
        ) - leaks_total,
        "n_leaked_mrc_rows": len(leaked_rows),
    }
    md.append("## C. 摘要")
    md.append("")
    md.append("```json")
    md.append(json.dumps(summary, ensure_ascii=False, indent=2))
    md.append("```")
    md.append("")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"报告已写入 {OUT_MD}")
    return 0


def _refs_for(qid: str, point_id: int, rows: list[dict]) -> list[str]:
    """该题该得分点的参考表述全集（query + query_aliases），供抽取片段比对。"""
    for r in rows:
        if r["question_id"] == qid and r.get("point_id") == point_id:
            return [r["query"]] + list(r.get("query_aliases") or [])
    return []


if __name__ == "__main__":
    sys.exit(main())
