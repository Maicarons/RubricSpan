# 模型厂库发布指引（HF / ModelScope 双平台）

> 本地两个厂库仓库已整理并 commit（`v2026.08.23` 快照，含 model.onnx /
> model.int8.onnx / model.fp16.onnx / tokenizer / model_card.json，*.onnx 走 Git LFS），
> **尚未推送**——需持有各平台写权限 token，由你手动执行。
> 两仓库在 `G:\GitHub\` 下、工作区外，0 remote 防误推 GitHub。

- MRC 抽取：`G:\GitHub\rubricspan-mrc-onnx`
- 语义相似度：`G:\GitHub\rubricspan-similarity-onnx`

## 0. 前置检查（可选）

```bash
git -C /g/GitHub/rubricspan-mrc-onnx status --short   # 应为空
git -C /g/GitHub/rubricspan-mrc-onnx lfs ls-files     # *.onnx 应在 LFS 列表
```

## 1. Hugging Face

1. 网页 https://huggingface.co/new 建同名空模型仓：
   `rubricspan-mrc-onnx`、`rubricspan-similarity-onnx`，**License = CC BY-NC-SA 4.0**；
2. 生成写权限 token（Settings → Access Tokens，Role = Write）；
3. 推送（token 仅作 remote 凭据，不进仓库）：

```bash
cd /g/GitHub/rubricspan-mrc-onnx
git remote add hf "https://user:${HF_TOKEN}@huggingface.co/USER/rubricspan-mrc-onnx"
git push -u hf main
git push hf v2026.08.23          # 可选：打 tag 版本
```

similarity 仓库同理（`git remote add hf .../rubricspan-similarity-onnx`）。
推错后可 `git remote remove hf` 重来；模型仓不要开 pull request。

## 2. ModelScope

1. 网页 https://www.modelscope.cn/models/create 建同名模型仓（类型=模型，License=CC BY-NC-SA 4.0）；
2. 获取 token（网页 → 头像 → 访问令牌，需开启「模型创建/管理」权限）；
3. 推送（ModelScope 使用 `oauth2` 用户 + token 作为口令）：

```bash
cd /g/GitHub/rubricspan-mrc-onnx
git remote add ms "https://oauth2:${MS_TOKEN}@www.modelscope.cn/USER/rubricspan-mrc-onnx.git"
git push -u ms main
git push ms v2026.08.23
```

## 3. 发布后

- 把 [models/README.md](README.md) 中的 `{{USER}}` 替换为你的用户名并确认链接可访问；
- 首次下载体验：删除本地 `models/mrc/` 后启动后端，确认自动拉取路径（现阶段下载脚本
  按本索引布局落盘；缺失时回退本地厂库手动拷贝）。

## 安全约定

- token 只用于 `git remote add` 的 URL 凭据，**不要**写进任何提交/脚本/环境变量文件；
- 推送后本地 `git remote -v` 仍会显示含 token 的 URL，可改为
  `git remote set-url hf https://huggingface.co/USER/rubricspan-mrc-onnx` 消除明文。
