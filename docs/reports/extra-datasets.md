# 外部补充数据集研究报告（2026-09-10）

> 目标：为中文主观题阅卷训练引入外部语料——客观题题干/选项、阅读理解材料、
> 考点标注、**历年高考/中考真题、初高中文科知识**。结论：**四个数据集已落地并接入
> 训练（opt-in），五个因许可/可达性暂缓**。
> 配套代码：`train/rubricspan_train/data/{import_extra,extra_processed}.py`、
> `train/tests/test_extra_import.py`；获取记录与许可见 `data/raw/extra_sources/README.md`
> （数据不入库，本报告为归档）。

## 1. 数据集清单与获取状态

| 来源 | 发布方 | 内容 | 许可 | 本机获取 | 结论 |
|---|---|---|---|---|---|
| **M3KE** | 天津大学/华为诺亚方舟 | 20477 道多学段标准化题（choice） | 无 LICENSE 文件（学术基准） | ✅ 143 文件 7.7MB | **入训练（仅 dev 355 题带答案）** |
| **InternLM-History** | 社区（2022 中考历史） | 20813 条专题分类对话（材料+问题→考点） | MIT | ✅ 156MB | **入训练** |
| **GAOKAO-Bench** | OpenLMLab | **2010–2022 高考真题**：客观题（历史/地理/政治/语文）+ **主观题（含参考答案与解析）** | Apache-2.0 | ✅ 14 文件 2.8MB | **入训练（核心新增）** |
| **AGIEval** | 微软 | **高考各科**（语文/历史/地理/英语 jsonl，带 passage 材料） | MIT | ✅ 4 文件 1.6MB | **入训练** |
| **CMMLU** | 北理工/厦门理工等 | **67 学科知识测试**（初高中+大学文科知识问答） | 无 LICENSE 文件（学术基准） | ✅ 40 CSV 859KB | **入训练（文科 20 科）** |
| **Reciter** | 社区 | **高考古诗文默写题库**（137 篇默写篇目 + 472 理解性默写） | MIT | ✅ 2 文件 308KB | **入训练（语文知识）** |
| NCR | 鹏城实验室 OpenI | 8388 文章 / 20477 中学语文阅读题（choice） | 未标注 | ⏳ Google Drive 需授权 | 适配器就绪，待数据 |
| EXAMS | 多语言考试问答 | 24 学科多选题 | CC-BY（语料） | ⏳ HF/TFDS 不可达 | 适配器就绪 |
| D175 | 数据堂 | 1.3 亿题（K12+大学职业） | 商业授权 | ⛔ OpenCSG 仓仅元数据 | **不入训练**（许可风险） |
| CEAMC | 华东师大 | 226 篇议论文论证标注+得分 | 未公开 | ⛔ 论文/仓库均无数据链接 | **需联系作者** |
| **C-Eval** | 上交 | 13948 道各学段知识题 | **CC BY-NC-SA 4.0（非商业）** | ✅ ModelScope 有镜像 | **不入训练**（与 Apache-2.0 模型许可冲突） |

## 2. 归一化体量与结构

`python -m rubricspan_train.data.import_extra` → `data/raw/extra/*/normalized.jsonl`（统一 schema：
source/subject/stage/qid/type/question/material/choices/answer_letter/answer_text/explanation/difficulty/split）。

| 来源 | 归一化条数 | 结构 |
|---|---|---|
| M3KE | 20,477（dev 355 / test 20,122） | 题干 + A–D 选项 + answer（仅 dev 带字母） |
| InternLM-History | 20,813（train 16,010 / test 4,803） | 材料+问题 → 专题/考点标注（指令前缀已剥离） |
| GAOKAO-Bench | 1,123 | 客观题 665（内联选项已解析）+ 主观题 458（含参考答案/解析/分值） |
| AGIEval | 986 | 高考各科（语文/历史/地理/英语），passage→材料 |
| CMMLU | 3,540（dev+test） | 20 个文科科目 CSV（Question,A-D,Answer） |
| Reciter | 609 | 472 理解性默写（fill）+ 137 默写篇目（open） |

合计 **47,548** 条。M3KE 学段：大学 12,576 / 其他 3,009 / 初中 2,207 / 高中 1,994 / 小学 691；
文科（Chinese 987 / History 640 / Politics 620 / Geography 411）合计 **2,658（13%）**，
与本项目主观题任务最相关的恰是文科段。GAOKAO-Bench 主观题是**文科主观题+参考答案**——
与本项目"评分点表述"形态直接同构（2010-2022 高考历史/政治/地理/语文）。

## 3. 与 SAS-Bench 去重

SAS-Bench 现有 1,018 题（归一化题干）：外部题与其**完全重合 0 条、前缀/包含重合 9 条**——
两来源几乎无泄漏，可作为互补语料而不引入重复训练样本。

## 4. 训练数据生成（extra_processed.py）

| 产物 | 条数 | 构成 | 用途 |
|---|---|---|---|
| `extra_similarity_pairs.jsonl` | 85,168（正 27,253 / 负 57,915） | M3KE dev 题干↔选项（+346/+1,047）；InternLM-History 题干↔考点正例+跨考点负例（+20,813/+41,626）；**GAOKAO-Bench 客观题↔选项（+1,044/+1,941）与主观题题干↔参考答案（+397）**；**AGIEval 题干↔选项（+937/+2,777）**；**CMMLU 题干↔选项（+3,504/+10,524）**；Reciter 默写空位↔答案（+609） | 相似度兜底"学生答错但表述沾边"拒判（BC-002 同族）；高考主观题参考答案对增强"得分点表述"语义 |
| `extra_mrc_negatives.jsonl` | 7,329（train 5,781） | InternLM-History 考点负例（6,807，train 5,259）+ **AGIEval 阅读材料负例（522，train）** | 补强 MRC has_answer 头对"材料中无答案 span"的判别 |

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
  零分带 FP 中"表述沾边"类；高考主观题"题干+材料↔参考答案"正例与判分语义同构，
  预计对兜底判分增益最直接；
- **MRC 负例**：补强 has_answer，代价是 query 与 context 无 span 关系，
  可能轻微抑制抽取召回——以 e2e 对拍为准；
- **许可边界**：C-Eval（CC BY-NC-SA）与 D175（商业）不入训练，避免模型发布许可冲突。

## 6. 后续工作

1. NCR/EXAMS：数据到位（Drive 授权下载 / 网络恢复）后直接重跑
   `import_extra` + `extra_processed`，适配器已就绪；
2. **中考真题**：GitHub 上无成规模的中考开源题库（社区仓库为 JS/HTML 内嵌、体量小）；
   建议从 OpenCSG/教育平台侧另寻，或由 InternLM-History 的 2022 中考历史 + NCR 覆盖初中段；
3. 客观题 → 选择型得分点（option_rules）语料：选择型考点标注可离线构建
   （题干+正确选项字母），无需 LLM；排期为评分引擎 option_rules 增强；
4. CEAMC：若作者公开数据，议论文论证标注可直接生成"得分点↔学生表述"高质量
   相似度正例与作文评分金标。

