const statusBox = document.getElementById("statusBox");

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

let currentLight = { r: 255, g: 255, b: 255, brightness: 100 };
let recording = false;
let recordStartTs = 0;
let recordTimerId = null;
const MAX_RECORD_SECONDS = 60;

function setStatus(text, isError = false) {
  statusBox.textContent = text;
  statusBox.style.color = isError ? "#ff9da4" : "#c9f0c9";
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
  try {
    const data = await postJson("/api/ai/command", { text });
    setStatus(`已执行: ${data.message}`);
    await refreshState();
  } catch (err) {
    setStatus(`文本指令执行失败: ${err.message}`, true);
  }
}

cmdSendBtn.addEventListener("click", submitTextCommand);
cmdInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    submitTextCommand();
  }
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
    pttBtn.textContent = "松开结束";
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
  pttBtn.textContent = "按住说话";
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
    setVoiceHint("待命（最长60秒）");
  } catch (err) {
    setVoiceHint("待命（最长60秒）");
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

refreshState();
