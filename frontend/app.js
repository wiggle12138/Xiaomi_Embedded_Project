import { getJson, postJson } from "./js/api.js";
import { createChatThread } from "./js/chat.js";
import { refreshDevicesView } from "./js/devices.js";
import { bindDirectControls, refreshDeviceState } from "./js/controls.js";
import { bindRulesView, refreshRulesView } from "./js/rules.js";

const state = {
  fanSpeed: document.getElementById("fanSpeed"),
  fanSpeedValue: document.getElementById("fanSpeedValue"),
  lightBrightness: document.getElementById("lightBrightness"),
  lightBrightnessValue: document.getElementById("lightBrightnessValue"),
  curtainPos: document.getElementById("curtainPos"),
  curtainPosValue: document.getElementById("curtainPosValue"),
  currentLight: { r: 255, g: 255, b: 255, brightness: 100 },
};

const wakeBanner = document.getElementById("wakeBanner");
const sidebar = document.getElementById("sidebar");
const sidebarBackdrop = document.getElementById("sidebarBackdrop");
const sidebarToggleBtn = document.getElementById("sidebarToggleBtn");
const navItems = document.querySelectorAll(".nav-item");
const viewPanels = document.querySelectorAll(".view-panel");
const deviceSummary = document.getElementById("deviceSummary");
const deviceList = document.getElementById("deviceList");
const refreshDevicesBtn = document.getElementById("refreshDevicesBtn");
const ruleSummary = document.getElementById("ruleSummary");
const ruleList = document.getElementById("ruleList");
const addRuleBtn = document.getElementById("addRuleBtn");
const ruleModal = document.getElementById("ruleModal");
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
const chat = createChatThread(document.getElementById("chatThread"));

let activeView = "aiView";
let inputMode = "text";
let recording = false;
let recordStartTs = 0;
let recordTimerId = null;
let textCommandInFlight = false;
const MAX_RECORD_SECONDS = 60;
const MOBILE_MEDIA = window.matchMedia("(max-width: 768px)");

function setVoiceHint(text) {
  voiceHint.textContent = text;
}

function isMobileLayout() {
  return MOBILE_MEDIA.matches;
}

function setSidebarOpen(open) {
  if (!sidebar || !sidebarBackdrop || !sidebarToggleBtn) return;
  sidebar.classList.toggle("open", open);
  sidebarBackdrop.classList.toggle("hidden", !open);
  sidebarBackdrop.setAttribute("aria-hidden", open ? "false" : "true");
  sidebarToggleBtn.setAttribute("aria-expanded", open ? "true" : "false");
  sidebarToggleBtn.setAttribute("aria-label", open ? "关闭导航" : "打开导航");
  document.body.classList.toggle("sidebar-open", open);
}

function closeSidebar() {
  setSidebarOpen(false);
}

function toggleSidebar() {
  if (!sidebar) return;
  setSidebarOpen(!sidebar.classList.contains("open"));
}

function notifyRuleMessage(message, level = "ok") {
  if (level === "error") {
    chat.error(message);
  } else {
    chat.assistantText(message);
  }
}

function showView(viewId) {
  activeView = viewId;
  viewPanels.forEach((panel) => panel.classList.toggle("hidden", panel.id !== viewId));
  navItems.forEach((item) => item.classList.toggle("active", item.dataset.view === viewId));
  if (viewId === "deviceView") {
    refreshDevicesView({ summaryEl: deviceSummary, listEl: deviceList });
  }
  if (viewId === "ruleView") {
    refreshRulesView({ listEl: ruleList, summaryEl: ruleSummary, onNotify: notifyRuleMessage });
  }
  if (isMobileLayout()) {
    closeSidebar();
  }
}

function setInputMode(mode) {
  if (mode !== "text" && mode !== "voice") return;
  inputMode = mode;
  const isText = mode === "text";
  textPanel.classList.toggle("hidden", !isText);
  voicePanel.classList.toggle("hidden", isText);
  iconVoice.classList.toggle("hidden", !isText);
  iconKeyboard.classList.toggle("hidden", isText);
  modeToggleBtn.setAttribute("aria-label", isText ? "切换到语音输入" : "切换到文字输入");
  modeToggleBtn.title = isText ? "语音输入" : "文字输入";
}

function stopRecordTimer() {
  if (!recordTimerId) return;
  clearInterval(recordTimerId);
  recordTimerId = null;
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

async function submitTextCommand() {
  const text = (cmdInput.value || "").trim();
  if (!text) {
    chat.error("请输入要执行的文本指令");
    return;
  }
  if (textCommandInFlight) {
    chat.error("上一条文本指令仍在处理中，请稍候");
    return;
  }

  textCommandInFlight = true;
  cmdSendBtn.disabled = true;
  cmdInput.disabled = true;
  chat.user(text);
  try {
    const resp = await postJson("/api/ai/command", { text });
    chat.execution(resp);
    await refreshDeviceState(state);
  } catch (err) {
    chat.error(`文本指令执行失败：${err.message}`);
  } finally {
    textCommandInFlight = false;
    cmdSendBtn.disabled = false;
    cmdInput.disabled = false;
  }
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
    chat.assistantText("录音已开始，请说话。");
    startRecordTimer();
  } catch (err) {
    chat.error(`开始录音失败：${err.message}`);
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
    if (mockText) chat.user(`[语音识别] ${mockText}`);
    const resp = await postJson("/api/voice/stop", payload);
    if (resp?.data?.action || mockText) {
      chat.execution(resp);
      await refreshDeviceState(state);
    } else {
      chat.assistantText(`录音完成：${resp?.data?.audio_file || "-"}`);
    }
    setVoiceHint("待命（最长 60 秒）");
  } catch (err) {
    setVoiceHint("待命（最长 60 秒）");
    chat.error(`停止录音失败：${err.message}`);
  }
}

async function pollWakeStatus() {
  try {
    const json = await getJson("/api/wake/status");
    const w = json.data;
    const awake = w.state === "awake";
    wakeBanner.classList.toggle("awake", awake);
    wakeBanner.textContent = awake && w.greeting ? w.greeting : w.message || "—";
  } catch (_) {
    // 唤醒关闭时不报错
  }
}

bindDirectControls(
  state,
  {
    user: (text) => chat.user(text),
    execution: (resp) => chat.execution(resp),
  },
  (msg) => chat.error(msg),
);

navItems.forEach((item) => item.addEventListener("click", () => showView(item.dataset.view)));
if (sidebarToggleBtn) sidebarToggleBtn.addEventListener("click", toggleSidebar);
if (sidebarBackdrop) sidebarBackdrop.addEventListener("click", closeSidebar);
if (MOBILE_MEDIA.addEventListener) {
  MOBILE_MEDIA.addEventListener("change", (event) => {
    if (!event.matches) closeSidebar();
  });
} else if (MOBILE_MEDIA.addListener) {
  MOBILE_MEDIA.addListener((event) => {
    if (!event.matches) closeSidebar();
  });
}
if (refreshDevicesBtn) refreshDevicesBtn.addEventListener("click", () => refreshDevicesView({ summaryEl: deviceSummary, listEl: deviceList }));

bindRulesView({
  listEl: ruleList,
  summaryEl: ruleSummary,
  addBtn: addRuleBtn,
  modal: ruleModal,
  onNotify: notifyRuleMessage,
  onDeviceRefresh: () => refreshDeviceState(state),
});

cmdSendBtn.addEventListener("click", submitTextCommand);
cmdInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") submitTextCommand();
});

modeToggleBtn.addEventListener("click", () => setInputMode(inputMode === "text" ? "voice" : "text"));
mockToggleBtn.addEventListener("click", () => {
  const show = mockPanel.classList.toggle("hidden");
  mockToggleBtn.classList.toggle("active", !show);
});
voicePlayBtn.addEventListener("click", async () => {
  try {
    const resp = await postJson("/api/voice/playback", {});
    chat.assistantText(`回放完成：${resp?.data?.audio_file || "-"}`);
  } catch (err) {
    chat.error(`回放失败：${err.message}`);
  }
});

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

refreshDeviceState(state).catch((err) => chat.error(`状态刷新失败：${err.message}`));
showView("aiView");
pollWakeStatus();
setInterval(pollWakeStatus, 3000);
setInterval(() => {
  if (activeView === "deviceView") {
    refreshDevicesView({ summaryEl: deviceSummary, listEl: deviceList });
  }
}, 5000);
