# 外部补充数据集研究报告（2026-09-10）

> 目标：为中文主观题阅卷训练引入外部语料——客观题题干/选项、阅读理解材料、
> 考点标注。结论：**两个数据集已落地并接入训练（opt-in），四个因许可/可达性暂缓**。
> 配套代码：`train/rubricspan_train/data/{import_extra,extra_processed}.py`、
> `train/tests/test_extra_import.py`；获取记录与许可见 `data/raw/extra_sources/README.md`
> （数据不入库，本报告为归档）。

## 1. 数据集清单与获取状态

| 来源 | 发布方 | 内容 | 许可 | 本机获取 | 结论 |
|---|---|---|---|---|---|
| **M3KE** | 天津大学/华为诺亚方舟 | 20477 道多学段标准化题（choice） | 无 LICENSE 文件（学术基准） | ✅ 143 文件 7.7MB | **入训练（仅 dev 355 题带答案）** |
| **InternLM-History** | 社区（2022 中考历史） | 20813 条专题分类对话（材料+问题→考点） | MIT | ✅ 156MB | **入训练** |
| NCR | 鹏城实验室 OpenI | 8388 文章 / 20477 中学语文阅读题（choice） | 未标注 | ⏳ Google Drive 需授权 | 适配器就绪，待数据 |
| EXAMS | 多语言考试问答 | 24 学科多选题 | CC-BY（语料） | ⏳ HF/TFDS 不可达 | 适配器就绪 |
| D175 | 数据堂 | 1.3 亿题（K12+大学职业） | 商业授权 | ⛔ OpenCSG 仓仅元数据 | **不入训练**（许可风险） |
| CEAMC | 华东师大 | 226 篇议论文论证标注+得分 | 未公开 | ⛔ 论文/仓库均无数据链接 | **需联系作者** |

## 2. 归一化体量与结构

`python -m rubricspan_train.data.import_extra` → `data/raw/extra/*/normalized.jsonl`（统一 schema：
source/subject/stage/qid/type/question/material/choices/answer_letter/answer_text/explanation/difficulty/split）。

| 来源 | 归一化条数 | 结构 |
|---|---|---|
| M3KE | 20,477（dev 355 / test 20,122） | 题干 + A–D 选项 + answer（仅 dev 带字母） |
| InternLM-History | 20,813（train 16,010 / test 4,803） | 材料+问题 → 专题/考点标注（指令前缀已剥离） |

M3KE 学段：大学 12,576 / 其他 3,009 / 初中 2,207 / 高中 1,994 / 小学 691；
文科（Chinese 987 / History 640 / Politics 620 / Geography 411）合计 **2,658（13%）**，
与本项目主观题任务最相关的恰是文科段。

## 3. 与 SAS-Bench 去重

SAS-Bench 现有 1,018 题（归一化题干）：外部题与其**完全重合 0 条、前缀/包含重合 9 条**——
两来源几乎无泄漏，可作为互补语料而不引入重复训练样本。

## 4. 训练数据生成（extra_processed.py）

| 产物 | 条数 | 构成 | 用途 |
|---|---|---|---|
| `extra_similarity_pairs.jsonl` | 63,832（正 21,159 / 负 42,673） | M3KE dev：题干↔正确选项（+346）/错误选项 hard 负例（+1,047）；InternLM-History：题干↔考点正例（+20,813）/跨考点抽样 hard 负例（+41,626） | 相似度兜底"学生答错但表述沾边"拒判（BC-002 同族） |
| `extra_mrc_negatives.jsonl` | 6,807（train 5,259） | InternLM-History：context=题干材料、query=考点标注的 is_impossible 负例（考点名不以 span 出现，守卫剔除含考点名的假负例） | 补强 MRC has_answer 头对"材料中无答案 span"的判别 |

设计原则：**不扰动主 build**（data/build.py 的固定种子与 question_id 划分保持原样），
另立文件 + 训练入口显式 opt-in。

## 5. 训练接入（opt-in，默认关闭）

```bash
cd train
# 相似度：并入额外句子对（仅 train split）
python -m rubricspan_train.training.train_similarity --extra-pairs ../data/processed/extra_similarity_pairs.jsonl
# MRC：并入外部 is_impossible 负例（仅 train split）
python -m rubricspan_train.training.train_mrc --stage main --strip-stems \
    --extra-negatives ../data/processed/extra_mrc_negatives.jsonl
```

预期收益与风险：
- **相似度 hard 负例**：正负比约 1:2，强化"相关但错误"选项的拒判——直接对治
  零分带 FP 中"表述沾边"类；风险：InternLM-History 题干↔考点对是分类语义，
  与"学生答案↔得分点"分布有差异，需对拍验证（val Pearson 与 36 卷 e2e）；
- **MRC 负例**：补强 has_answer，代价是 query 与 context 无 span 关系，
  可能轻微抑制抽取召回——同样以 e2e 对拍为准。

## 6. 后续工作

1. NCR/EXAMS：数据到位（Drive 授权下载 / 网络恢复）后直接重跑
   `import_extra` + `extra_processed`，适配器已就绪；
2. 客观题 → 选择型得分点（option_rules）语料：选择型考点标注可离线构建
   （题干+正确选项字母），无需 LLM；排期为评分引擎 option_rules 增强；
3. CEAMC：若作者公开数据，议论文论证标注可直接生成"得分点↔学生表述"高质量
   相似度正例与作文评分金标。
