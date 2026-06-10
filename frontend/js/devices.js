import { getJson } from "./api.js";

function statusText(device) {
  const status = (device.status || "idle").toLowerCase();
  if (status === "offline") return "离线";
  if (status === "busy") return "忙碌";
  if (status === "error") return "异常";
  return "在线";
}

function statusClass(device) {
  const status = (device.status || "idle").toLowerCase();
  if (status === "offline") return "offline";
  if (status === "busy") return "busy";
  if (status === "error") return "error";
  if (device.online) return "online";
  return "offline";
}

function renderDeviceCards(deviceList, items) {
  if (!items || items.length === 0) {
    deviceList.innerHTML = "<p class=\"placeholder\">暂无设备信息</p>";
    return;
  }

  deviceList.innerHTML = items.map((d) => {
    const capabilities = Array.isArray(d.capabilities) ? d.capabilities : [];
    const capHtml = capabilities.map((cap) => `<li>${cap}</li>`).join("");
    const lastSeen = d.last_seen || "-";
    const lastError = d.last_error || "无";
    return `
      <article class="device-card">
        <div class="device-head">
          <strong>${d.device_id} · ${d.name}</strong>
          <span class="badge ${statusClass(d)}">${statusText(d)}</span>
        </div>
        <div>类型：${d.type || "-"}</div>
        <div>最后活跃：${lastSeen}</div>
        <div>最近异常：${lastError}</div>
        <ul class="cap-list">${capHtml}</ul>
      </article>
    `;
  }).join("");
}

export async function refreshDevicesView({ summaryEl, listEl }) {
  if (!summaryEl || !listEl) return;
  try {
    const data = (await getJson("/api/devices")).data || {};
    const summary = data.summary || {};
    summaryEl.textContent = `在线 ${summary.online || 0} / ${summary.total || 0} · 忙碌 ${summary.busy || 0} · 异常 ${summary.error || 0} · 更新时间 ${data.updated_at || "-"}`;
    renderDeviceCards(listEl, data.devices || []);
  } catch (err) {
    summaryEl.textContent = `设备状态获取失败：${err.message}`;
    listEl.innerHTML = "";
  }
}
