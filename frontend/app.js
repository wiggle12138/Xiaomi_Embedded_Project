const statusBox = document.getElementById("statusBox");
const wakeBanner = document.getElementById("wakeBanner");

const fanSpeed = document.getElementById("fanSpeed");
const fanSpeedValue = document.getElementById("fanSpeedValue");

const lightBrightness = document.getElementById("lightBrightness");
const lightBrightnessValue = document.getElementById("lightBrightnessValue");

const curtainPos = document.getElementById("curtainPos");
const curtainPosValue = document.getElementById("curtainPosValue");
const cmdInput = document.getElementById("cmdInput");
const cmdSendBtn = document.getElementById("cmdSendBtn");
const pttBtn = document.getElementById("pttBtn");
const voiceHint = document.getElementById("voiceHint");
const voicePlayBtn = document.getElementById("voicePlayBtn");
const voiceMockText = document.getElementById("voiceMockText");
const modeToggleBtn = document.getElementById("modeToggleBtn");
const textPanel = document.getElementById("textPanel");
const voicePanel = document.getElementById("voicePanel");
const mockPanel = document.getElementById("mockPanel");
const mockToggleBtn = document.getElementById("mockToggleBtn");
const iconVoice = modeToggleBtn.querySelector(".icon-voice");
const iconKeyboard = modeToggleBtn.querySelector(".icon-keyboard");

let currentLight = { r: 255, g: 255, b: 255, brightness: 100 };
let inputMode = "text"; // text | voice
let recording = false;
let recordStartTs = 0;
let recordTimerId = null;
const MAX_RECORD_SECONDS = 60;
let textCommandInFlight = false;

function setStatus(text, isError = false) {
  statusBox.textContent = text;
  statusBox.style.color = isError ? "#ff9da4" : "#c9f0c9";
}

function buildTextCommandStatus(resp) {
  const data = resp && resp.data ? resp.data : {};
  const text = data.text || "";
  const branchMode = data.nlp && data.nlp.mode ? data.nlp.mode : "unknown";
  let branchLabel = "分支: 未知";
  if (branchMode === "direct") branchLabel = "分支: 直接指令";
  if (branchMode === "llm") branchLabel = "分支: LLM";
  if (branchMode === "rule_fallback") branchLabel = "分支: 规则兜底";

  const action = data.action || {};
  const actionText = action.device && action.action
    ? `动作: ${action.device}.${action.action}`
    : "动作: -";

  const lines = [
    `请求: ${text || "-"}`,
    branchLabel,
    actionText,
  ];
  if (branchMode === "llm" && data.nlp && Number.isFinite(Number(data.nlp.llm_elapsed_ms))) {
    lines.push(`LLM 思考时间: ${Number(data.nlp.llm_elapsed_ms)} ms`);
  }
  lines.push(`结果: ${resp.message || data.message || "-"}`);
  return lines.join("\n");
}

async function postJson(url, payload = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

async function refreshState() {
  try {
    const res = await fetch("/api/state");
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "获取状态失败");
    const s = data.data;

    fanSpeed.value = s.fan.speed;
    fanSpeedValue.textContent = String(s.fan.speed);

    lightBrightness.value = s.light.brightness;
    lightBrightnessValue.textContent = String(s.light.brightness);
    currentLight = {
      r: s.light.r,
      g: s.light.g,
      b: s.light.b,
      brightness: s.light.brightness,
    };

    curtainPos.value = s.curtain.position;
    curtainPosValue.textContent = String(s.curtain.position);
  } catch (err) {
    setStatus(`状态刷新失败: ${err.message}`, true);
  }
}

fanSpeed.addEventListener("input", () => {
  fanSpeedValue.textContent = fanSpeed.value;
});

lightBrightness.addEventListener("input", () => {
  lightBrightnessValue.textContent = lightBrightness.value;
});

curtainPos.addEventListener("input", () => {
  curtainPosValue.textContent = curtainPos.value;
});

document.getElementById("fanOnBtn").addEventListener("click", async () => {
  try {
    const data = await postJson("/api/fan/power", { on: true });
    setStatus(data.message);
    await refreshState();
  } catch (err) {
    setStatus(err.message, true);
  }
});

document.getElementById("fanOffBtn").addEventListener("click", async () => {
  try {
    const data = await postJson("/api/fan/power", { on: false });
    setStatus(data.message);
    await refreshState();
  } catch (err) {
    setStatus(err.message, true);
  }
});

document.getElementById("fanSetBtn").addEventListener("click", async () => {
  try {
    const speed = Number(fanSpeed.value);
    const data = await postJson("/api/fan/speed", { speed });
    setStatus(data.message);
    await refreshState();
  } catch (err) {
    setStatus(err.message, true);
  }
});

document.getElementById("lightOnBtn").addEventListener("click", async () => {
  try {
    const data = await postJson("/api/light/power", { on: true });
    setStatus(data.message);
    await refreshState();
  } catch (err) {
    setStatus(err.message, true);
  }
});

document.getElementById("lightOffBtn").addEventListener("click", async () => {
  try {
    const data = await postJson("/api/light/power", { on: false });
    setStatus(data.message);
    await refreshState();
  } catch (err) {
    setStatus(err.message, true);
  }
});

document.querySelectorAll(".color-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    try {
      const r = Number(btn.dataset.r);
      const g = Number(btn.dataset.g);
      const b = Number(btn.dataset.b);
      const brightness = Number(lightBrightness.value);
      currentLight = { r, g, b, brightness };
      const data = await postJson("/api/light/rgb", currentLight);
      setStatus(data.message);
      await refreshState();
    } catch (err) {
      setStatus(err.message, true);
    }
  });
});

lightBrightness.addEventListener("change", async () => {
  try {
    currentLight.brightness = Number(lightBrightness.value);
    const data = await postJson("/api/light/rgb", currentLight);
    setStatus(data.message);
    await refreshState();
  } catch (err) {
    setStatus(err.message, true);
  }
});

document.getElementById("curtainOpenBtn").addEventListener("click", async () => {
  try {
    const data = await postJson("/api/curtain/open", {});
    setStatus(data.message);
    await refreshState();
  } catch (err) {
    setStatus(err.message, true);
  }
});

document.getElementById("curtainCloseBtn").addEventListener("click", async () => {
  try {
    const data = await postJson("/api/curtain/close", {});
    setStatus(data.message);
    await refreshState();
  } catch (err) {
    setStatus(err.message, true);
  }
});

document.getElementById("curtainSetBtn").addEventListener("click", async () => {
  try {
    const position = Number(curtainPos.value);
    const data = await postJson("/api/curtain/position", { position });
    setStatus(data.message);
    await refreshState();
  } catch (err) {
    setStatus(err.message, true);
  }
});

async function submitTextCommand() {
  const text = (cmdInput.value || "").trim();
  if (!text) {
    setStatus("请输入要执行的文本指令", true);
    return;
  }
  if (textCommandInFlight) {
    setStatus("上一条文本指令仍在处理中，请稍候...", true);
    return;
  }

  textCommandInFlight = true;
  cmdSendBtn.disabled = true;
  cmdInput.disabled = true;

  let routeLabel = "分支: 未知";
  try {
    const routeResp = await postJson("/api/ai/route", { text });
    const mode = routeResp?.data?.route?.mode;
    if (mode === "direct") routeLabel = "分支: 直接指令";
    if (mode === "llm") routeLabel = "分支: LLM";
    setStatus(`请求: ${text}\n${routeLabel}\n处理中...`);
  } catch (err) {
    setStatus(`请求: ${text}\n分支预判失败，继续执行...\n${err.message}`);
  }

  try {
    const data = await postJson("/api/ai/command", { text });
    setStatus(buildTextCommandStatus(data));
    await refreshState();
  } catch (err) {
    setStatus(`文本指令执行失败: ${err.message}`, true);
  } finally {
    textCommandInFlight = false;
    cmdSendBtn.disabled = false;
    cmdInput.disabled = false;
  }
}

cmdSendBtn.addEventListener("click", submitTextCommand);
cmdInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    submitTextCommand();
  }
});

/** 切换底部输入模式：文字 ↔ 语音 */
function setInputMode(mode) {
  if (mode !== "text" && mode !== "voice") return;
  if (mode === "text" && recording) {
    stopVoiceRecording();
  }
  inputMode = mode;
  const isText = mode === "text";
  textPanel.classList.toggle("hidden", !isText);
  voicePanel.classList.toggle("hidden", isText);
  iconVoice.classList.toggle("hidden", !isText);
  iconKeyboard.classList.toggle("hidden", isText);
  modeToggleBtn.setAttribute(
    "aria-label",
    isText ? "切换到语音输入" : "切换到文字输入"
  );
  modeToggleBtn.title = isText ? "语音输入" : "文字输入";
}

modeToggleBtn.addEventListener("click", () => {
  setInputMode(inputMode === "text" ? "voice" : "text");
});

mockToggleBtn.addEventListener("click", () => {
  const show = mockPanel.classList.toggle("hidden");
  mockToggleBtn.classList.toggle("active", !show);
});

voicePlayBtn.addEventListener("click", async () => {
  try {
    const data = await postJson("/api/voice/playback", {});
    setStatus(`回放完成: ${data.data.audio_file}`);
  } catch (err) {
    setStatus(`回放失败: ${err.message}`, true);
  }
});

function setVoiceHint(text) {
  voiceHint.textContent = text;
}

function stopRecordTimer() {
  if (recordTimerId) {
    clearInterval(recordTimerId);
    recordTimerId = null;
  }
}

function startRecordTimer() {
  stopRecordTimer();
  recordTimerId = setInterval(() => {
    if (!recording) return;
    const elapsed = Math.floor((Date.now() - recordStartTs) / 1000);
    const remaining = Math.max(0, MAX_RECORD_SECONDS - elapsed);
    setVoiceHint(`正在说话... ${elapsed}s（剩余${remaining}s）`);
    if (remaining <= 0) {
      stopVoiceRecording();
    }
  }, 300);
}

async function startVoiceRecording() {
  if (recording) return;
  try {
    await postJson("/api/voice/start", { max_seconds: MAX_RECORD_SECONDS, rate: 16000 });
    recording = true;
    recordStartTs = Date.now();
    pttBtn.classList.add("recording");
    pttBtn.textContent = "松开 结束";
    setVoiceHint("正在说话...");
    setStatus("录音已开始，正在说话...");
    startRecordTimer();
  } catch (err) {
    setStatus(`开始录音失败: ${err.message}`, true);
  }
}

async function stopVoiceRecording() {
  if (!recording) return;
  recording = false;
  stopRecordTimer();
  pttBtn.classList.remove("recording");
  pttBtn.textContent = "按住 说话";
  setVoiceHint("正在停止录音...");

  try {
    const mockText = (voiceMockText.value || "").trim();
    const payload = {};
    if (mockText) payload.mock_text = mockText;
    const data = await postJson("/api/voice/stop", payload);
    if (mockText) {
      setStatus(`语音执行成功: ${data.message}`);
      await refreshState();
    } else {
      setStatus(`录音完成: ${data.data.audio_file}`);
    }
    setVoiceHint("待命（最长 60 秒）");
  } catch (err) {
    setVoiceHint("待命（最长 60 秒）");
    setStatus(`停止录音失败: ${err.message}`, true);
  }
}

pttBtn.addEventListener("mousedown", (event) => {
  event.preventDefault();
  startVoiceRecording();
});
pttBtn.addEventListener("mouseup", (event) => {
  event.preventDefault();
  stopVoiceRecording();
});
pttBtn.addEventListener("mouseleave", () => {
  if (recording) stopVoiceRecording();
});
pttBtn.addEventListener("touchstart", (event) => {
  event.preventDefault();
  startVoiceRecording();
}, { passive: false });
pttBtn.addEventListener("touchend", (event) => {
  event.preventDefault();
  stopVoiceRecording();
}, { passive: false });
pttBtn.addEventListener("touchcancel", (event) => {
  event.preventDefault();
  stopVoiceRecording();
}, { passive: false });

async function pollWakeStatus() {
  try {
    const res = await fetch("/api/wake/status");
    const json = await res.json();
    if (!json.ok) return;
    const w = json.data;
    const awake = w.state === "awake";
    wakeBanner.classList.toggle("awake", awake);
    wakeBanner.textContent = awake && w.greeting ? w.greeting : w.message || "—";
  } catch (_) {
    /* 唤醒未启用时忽略 */
  }
}

const WAKE_POLL_INTERVAL_MS = 3000;
refreshState();
pollWakeStatus();
setInterval(pollWakeStatus, WAKE_POLL_INTERVAL_MS);
