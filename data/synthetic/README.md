# data/synthetic/ —— M1-2 四档合成答卷

> 大模型按 **优秀 / 良好 / 及格 / 不及格** 四档扮演高中生作答，
> 用于补足训练数据量与同义表述（semantic）信号。

- 生成入口：`python -m rubricspan_train.labeling.run synth`
- 文件：`synthetic_answers.jsonl`，每行一份答卷：
  `sample_id`（`{qid}#syn-{档位}-v{变体}`）、`question_id`、`tier`、
  `variant`、`student_answer`、`model`、`created_at`
- 档位设计（见 `train/rubricspan_train/labeling/prompts.py`）：
  - excellent：全覆盖 + 至少半数得分点用同义说法；
  - good：覆盖 ~3/4，多数同义说法；
  - fair：覆盖 ~半，表述笼统、部分命中；
  - poor：0–1 点，允许出现学生典型错误联想。
- 历史题每档加做 1 份变体（`history_extra_variants`，配置于
  `train/configs/labeling.yaml`）

合成答卷与真实答卷走同一打标流水线（不自带标签）。
目录内容不入库，仅本说明入库。
