import { getJson, postJson } from "./api.js";

export async function refreshDeviceState(state) {
  const res = await getJson("/api/state");
  const s = res.data;
  state.currentLight = {
    r: s.light.r,
    g: s.light.g,
    b: s.light.b,
    brightness: s.light.brightness,
  };
  state.fanSpeed.value = s.fan.speed;
  state.fanSpeedValue.textContent = String(s.fan.speed);
  state.lightBrightness.value = s.light.brightness;
  state.lightBrightnessValue.textContent = String(s.light.brightness);
  state.curtainPos.value = s.curtain.position;
  state.curtainPosValue.textContent = String(s.curtain.position);
}

export function bindDirectControls(state, onResult, onError) {
  state.fanSpeed.addEventListener("input", () => {
    state.fanSpeedValue.textContent = state.fanSpeed.value;
  });
  state.lightBrightness.addEventListener("input", () => {
    state.lightBrightnessValue.textContent = state.lightBrightness.value;
  });
  state.curtainPos.addEventListener("input", () => {
    state.curtainPosValue.textContent = state.curtainPos.value;
  });

  const run = async (userText, url, payload) => {
    try {
      onResult.user(userText);
      const resp = await postJson(url, payload);
      onResult.execution(resp);
      await refreshDeviceState(state);
    } catch (err) {
      onError(`执行失败：${err.message}`);
    }
  };

  document.getElementById("fanOnBtn").addEventListener("click", () => run("打开风扇", "/api/fan/power", { on: true }));
  document.getElementById("fanOffBtn").addEventListener("click", () => run("关闭风扇", "/api/fan/power", { on: false }));
  document.getElementById("fanSetBtn").addEventListener("click", () => run(`风扇速度 ${state.fanSpeed.value}`, "/api/fan/speed", { speed: Number(state.fanSpeed.value) }));
  document.getElementById("lightOnBtn").addEventListener("click", () => run("开灯", "/api/light/power", { on: true }));
  document.getElementById("lightOffBtn").addEventListener("click", () => run("关灯", "/api/light/power", { on: false }));
  document.getElementById("curtainOpenBtn").addEventListener("click", () => run("窗帘全开", "/api/curtain/open", {}));
  document.getElementById("curtainCloseBtn").addEventListener("click", () => run("窗帘全关", "/api/curtain/close", {}));
  document.getElementById("curtainSetBtn").addEventListener("click", () => run(`窗帘开度 ${state.curtainPos.value}`, "/api/curtain/position", { position: Number(state.curtainPos.value) }));

  document.querySelectorAll(".color-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const r = Number(btn.dataset.r);
      const g = Number(btn.dataset.g);
      const b = Number(btn.dataset.b);
      const brightness = Number(state.lightBrightness.value);
      state.currentLight = { r, g, b, brightness };
      run(`灯光颜色 ${btn.textContent}`, "/api/light/rgb", state.currentLight);
    });
  });

  state.lightBrightness.addEventListener("change", () => {
    state.currentLight.brightness = Number(state.lightBrightness.value);
    run(`灯光亮度 ${state.lightBrightness.value}`, "/api/light/rgb", state.currentLight);
  });
}
