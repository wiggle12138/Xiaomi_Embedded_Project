# Project：E5 环境控制 + 语音 + LLM 入口

本项目是 U2 主机上的产品化控制台，负责统一控制：

- `E2` 风扇：开关、速度 `0~100`
- `E1` 灯光：开关、颜色、亮度 `0~100`
- `E3` 窗帘：全开/全关、开度 `0~100`

并提供：

- 文本自然语言控制（LLM）
- 语音录音与回放
- 唤醒词检测（S3 + E4）

---

## 1. 快速开始

### 1.1 运行前检查

1. 确认在 U2 Linux 主机上。
2. 确认子板堆叠与供电正常（E1/E2/E3，语音场景可加 S3/E4）。
3. 确认 I2C 设备节点存在：

```bash
ls /dev/i2c-*
```

### 1.2 启动

```bash
cd /root/U2Project/Project
chmod +x scripts/run.sh scripts/stop.sh
./scripts/run.sh
```

默认访问：

- 本机：`http://127.0.0.1:8080`
- 局域网：`http://<U2_IP>:8080`

### 1.3 停止

```bash
cd /root/U2Project/Project
./scripts/stop.sh
```

---

## 2. 目录结构

```text
Project/
  backend/server.py         # HTTP 服务与路由
  backend/ai_adapter.py     # LLM 请求与结果解析
  backend/ai_schema.py      # command 白名单与参数校验
  backend/wake_worker.py    # 唤醒状态管理
  backend/wake_engine.py    # KWS 引擎（sherpa-onnx + arecord）
  frontend/index.html
  frontend/app.js
  frontend/style.css
  native/                   # e1_ctl / e2_ctl / e3_ctl
  scripts/run.sh
  scripts/stop.sh
  scripts/gen_wake_keywords.sh
  logs/                     # 启动后自动生成
```

---

## 3. 页面使用说明

### 3.1 设备控制区

- 风扇：开关、速度
- 灯光：开关、颜色预设、亮度
- 窗帘：全开、全关、开度

### 3.2 底部输入栏

- 文本模式：输入自然语言后发送
- 语音模式：按住录音、松开结束
- 右侧工具：回放最新录音、mock 文本

### 3.3 状态栏（重点）

发送文本后状态栏会显示：

- 请求文本
- 分支：`直接指令` 或 `LLM`
- 动作：例如 `light.on`
- LLM 思考时间（仅 LLM 分支）
- 最终执行结果

---

## 4. API 概览

### 4.1 设备与状态

- `GET /api/health`
- `GET /api/state`
- `POST /api/fan/power` body: `{"on": true|false}`
- `POST /api/fan/speed` body: `{"speed": 0~100}`
- `POST /api/light/power` body: `{"on": true|false}`
- `POST /api/light/rgb` body: `{"r":0~255,"g":0~255,"b":0~255,"brightness":0~100}`
- `POST /api/curtain/open`
- `POST /api/curtain/close`
- `POST /api/curtain/position` body: `{"position":0~100}`

### 4.2 AI 文本入口

- `POST /api/ai/route`：仅判断分支（direct / llm）
  - body: `{"text":"太黑了"}`
- `POST /api/ai/command`：执行文本命令
  - 自然语言：`{"text":"把窗帘开到60"}`
  - 结构化：`{"command":{"device":"curtain","action":"open","params":{}}}`

### 4.3 语音相关

- `GET /api/voice/latest`
- `GET /api/voice/status`
- `POST /api/voice/start` body: `{"max_seconds":60,"rate":16000}`
- `POST /api/voice/stop` body: `{"mock_text":"可选"}`
- `POST /api/voice/playback` body: `{"audio_file":"可选"}`
- `POST /api/voice/command` body: `{"seconds":3,"mock_text":"打开窗帘"}`
- `GET /api/wake/status`

---

## 5. LLM 设计说明（自然语言 -> 设备动作）

这部分是当前产品链路核心。

### 5.1 处理流程

1. 前端发送自然语言到 `/api/ai/command`，例如：`"现在环境好黑"`
2. 后端先做“直接指令判断”
   - 能直接识别（如“开灯”“关风扇”）则直接执行
   - 不能直接识别才进入 LLM
3. 后端给 LLM 的输入不是裸文本，而是：
   - 设备能力约束（fan/light/curtain + 可执行 action）
   - 当前设备状态（`STATE`）
   - 用户文本
4. LLM 返回结构化 JSON（command）
5. 后端用 `ai_schema` 做白名单和参数校验
6. 统一调用 `execute_action()` 执行硬件控制
7. 返回前端结果并展示在状态栏

### 5.2 为什么要“追加 prompt”

只给模型一句“现在环境好黑”时，模型不知道你的设备能力边界。  
追加 prompt 的作用是把模型约束为“设备指令解析器”，确保它输出可执行 JSON，而不是纯聊天回答。

### 5.3 示例：从自然语言到硬件动作

输入：`太黑了`  
LLM 输出（示意）：

```json
{
  "device": "light",
  "action": "on",
  "params": {},
  "need_confirm": false,
  "reason": "环境偏暗，需要照明"
}
```

后端执行：`execute_action -> do_light_power -> e1_ctl`  
设备动作：开灯。

---

## 6. `run.sh` 常用配置

`scripts/run.sh` 提供统一配置入口，常用项如下：

推荐做法（避免密钥写进脚本）：

```bash
cd /root/U2Project/Project
cp config/runtime.env.example config/runtime.env
# 编辑 config/runtime.env，填写 LLM_API_KEY 等本地配置
```

`run.sh` 启动时会自动加载 `config/runtime.env`，且该文件已加入 `.gitignore`。

- `TASK1_PORT`：服务端口（默认 `8080`）
- `RUN_FOREGROUND`：前台模式（`1` 前台，`0` 后台）
- `LLM_ENABLED`：是否启用 LLM（`1/0`）
- `LLM_API_URL`：OpenAI 兼容接口地址
- `LLM_API_KEY`：模型密钥
- `LLM_MODEL`：模型名（如 `kimi-k2.6`）
- `LLM_TIMEOUT_SECONDS`：超时秒数
- `LLM_THINKING_TYPE`：`enabled/disabled`（Kimi K2）
- `LLM_TEMPERATURE`：留空时按模型自动选择
  - Kimi K2 + thinking disabled -> `0.6`
  - Kimi K2 + thinking enabled -> `1.0`
- `LOG_WAKE_STATUS`：是否打印 wake 轮询日志
- `LOG_POST_PAYLOAD`：是否打印 POST payload
- `LOG_LLM_VERBOSE`：是否打印 LLM 详细请求/响应

> 建议：不要把真实 `LLM_API_KEY` 提交到仓库。

---

## 7. 唤醒词配置（S3 + E4）

### 7.1 配置与启动

```bash
cd /root/U2Project/Project
conda activate task3
WAKE_KEYWORD_TEXT="小龙同学" ./scripts/gen_wake_keywords.sh
./scripts/stop.sh
WAKE_KEYWORD_TEXT="小龙同学" ./scripts/run.sh
```

### 7.2 相关变量

- `WAKE_KEYWORD_TEXT`：唤醒词
- `WAKE_GREETING_TEXT`：唤醒后前端文案
- `WAKE_REPLY_WAV`：回复音频路径
- `WAKE_GREETING_SECONDS`：文案展示时长
- `WAKE_ENABLED=0`：关闭唤醒

---

## 8. 排障

### 8.1 页面能打开但硬件无反应

- 检查供电和连线
- 检查 `/dev/i2c-*`
- 看日志：`tail -n 100 /root/U2Project/Project/logs/task1.log`

### 8.2 LLM 慢或超时

- 优先关闭 thinking：`LLM_THINKING_TYPE=disabled`
- 适当增大超时：`LLM_TIMEOUT_SECONDS=45` 或更高
- 开启诊断日志：`LOG_LLM_VERBOSE=1`

### 8.3 录音自检

```bash
cd /root/U2Project/Project
chmod +x scripts/s3_audio_check.sh
./scripts/s3_audio_check.sh
```

---

## 9. 后续建议

- 增加“请求队列 + 取消机制”，避免并发文本请求堆积
- 加入设备在线检测与重试策略
- 增加对话历史与用户偏好（亮度、风扇常用档位）记忆
