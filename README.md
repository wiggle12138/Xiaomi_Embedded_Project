# Project - E5 页面控制 + AI/语音入口（P1）

本项目实现了一个最小可行控制台：

- E2 风扇：开关、速度(0~100)
- E1 灯：开关、预设颜色、亮度(0~100)
- E3 窗帘：全开/全关、开度(0~100)

页面在 E5 屏幕（Linux 图形环境）中打开即可操作。

---

## 1. 目录结构

```text
Project/
  backend/server.py       # Python HTTP 服务
  frontend/index.html     # 前端页面（底部固定文字/语音输入栏）
  frontend/app.js
  frontend/style.css
  native/Makefile         # 编译 e1_ctl/e2_ctl/e3_ctl
  native/e1_ctl.cpp
  native/e2_ctl.cpp
  native/e3_ctl.cpp
  scripts/run.sh          # 启动脚本
  scripts/stop.sh         # 停止脚本
  logs/                   # 运行日志目录(启动时自动创建)
```

---

## 2. 运行前准备

1. 确认你在 U2 Linux 主机上。
2. 确认硬件已正确堆叠并供电：E1、E2、E3。
3. 确认系统存在 I2C 设备节点，例如：

```bash
ls /dev/i2c-*
```

---

## 3. 启动项目

在 `Project` 目录执行：

```bash
cd /root/U2Project/Project
chmod +x scripts/run.sh scripts/stop.sh
./scripts/run.sh
```

脚本会自动完成：

1. 编译本地控制程序（`e1_ctl/e2_ctl/e3_ctl`）
2. 启动 Python 服务（默认端口 `8080`）
3. 输出访问地址与日志位置

默认访问地址：

- 本机访问：`http://127.0.0.1:8080`
- 局域网访问：`http://<U2_IP>:8080`

---

## 4. 停止项目

```bash
cd /root/U2Project/Project
./scripts/stop.sh
```

---

## 5. 页面操作说明

### E2 风扇

- `开启风扇`：按当前速度开启，若无历史速度默认 30
- `关闭风扇`：停止
- `设置速度`：按滑条值设置 0~100

### E1 灯光

- `开灯/关灯`
- 颜色按钮：红/绿/蓝/白/橙
- 亮度滑条：0~100（变化后自动下发）

### E3 窗帘

- `全开`：100%
- `全关`：0%
- `设置开度`：按滑条值设置 0~100

### 底部输入栏（文字 / 语音）

- 固定在页面底部；左侧按钮在「语音」「键盘」图标间切换模式。
- **文字模式**：输入框 +「发送」；Enter 或点击发送，调用 `/api/ai/command`。
- **语音模式**：「按住 说话」；松开结束并上传录音。
- 右侧小图标：**回放**最新录音；**M** 展开 mock 识别文本（留空则只录音不执行）。

---

## 6. 接口清单（含语音入口）

- `GET /api/health`
- `GET /api/state`
- `POST /api/fan/power`，body: `{"on": true|false}`
- `POST /api/fan/speed`，body: `{"speed": 0~100}`
- `POST /api/light/power`，body: `{"on": true|false}`
- `POST /api/light/rgb`，body: `{"r":0~255,"g":0~255,"b":0~255,"brightness":0~100}`
- `POST /api/curtain/open`，body: `{}`
- `POST /api/curtain/close`，body: `{}`
- `POST /api/curtain/position`，body: `{"position":0~100}`
- `POST /api/ai/command`，支持两种输入：
  - 自然语言：`{"text":"打开窗帘"}`
  - 结构化：`{"command":{"device":"curtain","action":"open","params":{}}}`
- `GET /api/voice/latest`，返回最近录音文件
- `GET /api/voice/status`，返回按住说话会话状态
- `POST /api/voice/start`，body: `{"max_seconds":60,"rate":16000}`（按下开始）
- `POST /api/voice/stop`，body: `{"mock_text":"可选，留空仅录音"}`（松开停止）
- `POST /api/voice/playback`，body: `{"audio_file":"可选，不传则播最近录音"}`
- `POST /api/voice/command`，body: `{"seconds":3,"mock_text":"打开窗帘"}`（兼容旧方式）
- `GET /api/wake/status`，流式唤醒状态（常开 KWS「小爱同学」）

### 流式语音唤醒（S3 + E4）

- 常开 KWS，识别 **「小爱同学」** 后：
  - 页面横幅显示 **「你好呀」**（占位，约 5s）
  - E4 扬声器播放 **`assets/speech/reply.wav`**（自行录制，16kHz mono 推荐）
- 首次配置（复用 task3 的 KWS 模型即可）：

```bash
cd /root/U2Project/Project
conda activate task3
./scripts/gen_wake_keywords.sh    # 写入 Project/models/keywords.txt
# 将自录 reply.wav 放到 assets/speech/
./scripts/stop.sh && ./scripts/run.sh
```

- 关闭唤醒：`WAKE_ENABLED=0 ./scripts/run.sh`
- 环境变量：`WAKE_REPLY_WAV`（回复音频）、`WAKE_GREETING_SECONDS`（前端展示秒数）

示例（自然语言）：

```bash
curl -X POST http://127.0.0.1:8080/api/ai/command \
  -H "Content-Type: application/json" \
  -d '{"text":"把窗帘开到60"}'
```

示例（结构化）：

```bash
curl -X POST http://127.0.0.1:8080/api/ai/command \
  -H "Content-Type: application/json" \
  -d '{"command":{"device":"fan","action":"set_speed","params":{"speed":45}}}'
```

---

## 7. 常见问题

### 1) 页面能打开，但控制无反应

- 检查子板堆叠与供电
- 检查 `/dev/i2c-*` 是否存在
- 查看日志：

```bash
tail -n 100 /root/U2Project/Project/logs/task1.log
```

### 2) 看到 `Remote I/O error`

这是 I2C 探测阶段可能出现的总线写失败提示，若关键地址设备能探测到并且元件有动作，可先按正常现象处理。

### 3) 改端口启动

```bash
cd /root/U2Project/Project
TASK1_PORT=8090 ./scripts/run.sh
```

### 4) S3 麦克风子板录音自检

```bash
cd /root/U2Project/Project
chmod +x scripts/s3_audio_check.sh
./scripts/s3_audio_check.sh
```

可选参数（秒）：

```bash
./scripts/s3_audio_check.sh 6
```

说明：

- 脚本会优先使用 `tinycap`（与 S3 demo 一致），若不存在则回退 `arecord`。
- 若已接入 E4，推荐使用 `tinyplay -D 0 -d 1 -r 16000 <wav>` 回放（与 E4 demo 一致）。
- `/api/voice/command` 当前使用 `mock_text` 代替 ASR 结果，后续可直接替换为火山流式识别输出。

### 5) E4 `tinyplay` 报错 `failed to open` 的常见原因

你之前执行的是：

```bash
tinyplay -D 0 -d 1 -r 16000 /logs/audio-check/s3_xxx.wav
```

这里的路径 `/logs/...` 不存在。应使用项目真实路径，例如：

```bash
tinyplay -D 0 -d 1 -r 16000 /root/U2Project/Project/logs/audio-check/s3_20260522_161035.wav
```

或先 `cd /root/U2Project/Project` 再使用相对路径：

```bash
tinyplay -D 0 -d 1 -r 16000 logs/audio-check/s3_20260522_161035.wav
```

---

## 8. 后续可扩展方向

- 增加设备在线状态监测与自动重连
- 将控制器做成单进程常驻，减少重复探测开销
- 页面加入移动端自适应与更细粒度反馈
