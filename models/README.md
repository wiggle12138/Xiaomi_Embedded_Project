# KWS 模型目录

本目录存放 **sherpa-onnx 中文关键词检测** 模型，体积约十几 MB，**不提交到 git**。

## 推荐模型

- [sherpa-onnx 预训练 KWS 模型列表](https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html)
- 优先：中英文 zipformer **3M** 系列（如 `sherpa-onnx-kws-zipformer-zh-en-3M-*`）

## 部署步骤

1. 下载并解压到 `models/<模型目录>/`（需含 `tokens.txt`、`encoder*.onnx` 等）。
2. 生成唤醒词文件：
   ```bash
   conda activate task3
   ./scripts/gen_keywords.sh
   ```
   默认关键词「你好小爱」，可设 `WAKE_KEYWORD_TEXT=你好小爱`。  
   首次会自动安装 `pypinyin`、`sentencepiece`（仅生成用，运行时 KWS 不需要 click）。
3. 重启服务：`./scripts/stop.sh && ./scripts/run.sh`

## 环境变量（可选）

| 变量 | 说明 |
|------|------|
| `WAKE_MODEL_DIR` | 模型根目录，默认 `task3/models/<模型名>/` |

## 注意

- 首次下载需网络；板子离线时可从 PC 拷贝整个解压目录。
- 调参重点：`keywords_threshold`、chunk 大小（延迟 vs 准确率）。
