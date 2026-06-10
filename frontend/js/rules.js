import { deleteJson, getJson, postJson, putJson } from "./api.js";

let metaCache = null;

function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function statusBadge(rule) {
  if (!rule.trigger_implemented) {
    return '<span class="badge pending">触发待接入</span>';
  }
  if (rule.enabled) {
    return '<span class="badge online">已启用</span>';
  }
  return '<span class="badge offline">已停用</span>';
}

function renderRuleCards(listEl, rules) {
  if (!rules || rules.length === 0) {
    listEl.innerHTML = '<p class="placeholder">暂无规则，点击「添加规则」创建。</p>';
    return;
  }

  listEl.innerHTML = rules.map((rule) => {
    const lastRun = rule.last_run_at ? `最近执行：${rule.last_run_at}` : "尚未执行";
    const lastMsg = rule.last_run_message ? ` · ${escapeHtml(rule.last_run_message)}` : "";
    const hint = !rule.trigger_implemented ? `<p class="rule-hint">${escapeHtml(rule.trigger_hint || "触发源待接入")}</p>` : "";
    return `
      <article class="rule-card" data-rule-id="${escapeHtml(rule.id)}">
        <div class="rule-head">
          <div>
            <h3>${escapeHtml(rule.name)}</h3>
            ${statusBadge(rule)}
          </div>
          <label class="switch" title="${rule.enabled ? "停用" : "启用"}">
            <input type="checkbox" data-action="toggle" ${rule.enabled ? "checked" : ""} ${!rule.trigger_implemented ? "" : ""} />
            <span class="slider"></span>
          </label>
        </div>
        <p>${escapeHtml(rule.trigger_summary || "-")}</p>
        <p>${escapeHtml(rule.actions_summary || "-")}</p>
        ${hint}
        <p class="rule-meta">${escapeHtml(lastRun)}${lastMsg}</p>
        <div class="rule-actions">
          <button type="button" class="secondary" data-action="run">测试运行</button>
          <button type="button" class="secondary" data-action="edit">编辑</button>
          <button type="button" class="secondary" data-action="delete">删除</button>
        </div>
      </article>
    `;
  }).join("");
}

function optionItems(items, selected, { valueKey = "id", labelKey = "label", disabledKey = "available" } = {}) {
  return items.map((item) => {
    const value = item[valueKey] ?? item.type ?? item.device ?? item.action;
    const label = item[labelKey] ?? value;
    const disabled = disabledKey && item[disabledKey] === false;
    const suffix = disabled ? "（设备未在线）" : (!item.implemented && item.implemented !== undefined ? "（待接入）" : "");
    return `<option value="${escapeHtml(value)}" ${String(value) === String(selected) ? "selected" : ""} ${disabled ? "disabled" : ""}>${escapeHtml(label)}${suffix}</option>`;
  }).join("");
}

function findStateDevice(meta, deviceId) {
  return (meta.state_devices || []).find((d) => d.device === deviceId);
}

function findActionsForDevice(meta, deviceId) {
  return (meta.actions || []).filter((a) => a.device === deviceId);
}

function renderTriggerFields(form, meta, trigger = {}) {
  const type = form.querySelector("#ruleTriggerType").value;
  const box = form.querySelector("#ruleTriggerFields");
  const triggerMeta = (meta.triggers || []).find((t) => t.type === type);
  let html = "";

  if (type === "manual") {
    html = '<p class="form-hint">手动测试规则：保存后点击卡片上的「测试运行」。</p>';
  } else if (type === "device_state") {
    const device = trigger.device || "curtain";
    const stateDevice = findStateDevice(meta, device) || meta.state_devices[0];
    const fields = stateDevice ? Object.entries(stateDevice.fields) : [];
    const field = trigger.field || (fields[0] ? fields[0][0] : "position");
    const fieldMeta = stateDevice?.fields?.[field] || { type: "number" };
    html = `
      <label>监测设备
        <select id="ruleStateDevice">${optionItems(meta.state_devices || [], device, { valueKey: "device", labelKey: "label", disabledKey: "available" })}</select>
      </label>
      <label>状态字段
        <select id="ruleStateField">${fields.map(([key, info]) => `<option value="${key}" ${key === field ? "selected" : ""}>${escapeHtml(info.label)}</option>`).join("")}</select>
      </label>
      <label>比较
        <select id="ruleStateOperator">${optionItems(meta.operators || [], trigger.operator || "lt", { valueKey: "id", labelKey: "label", disabledKey: null })}</select>
      </label>
      <label>阈值
        <input id="ruleStateValue" type="${fieldMeta.type === "bool" ? "checkbox" : "number"}" ${fieldMeta.type === "bool" ? (trigger.value ? "checked" : "") : `value="${trigger.value ?? 0}"`} />
      </label>
    `;
  } else if (type === "camera_gesture") {
    html = `
      <p class="form-hint">摄像头手势触发待后续接入，可先保存配置。</p>
      <label>手势名称<input id="ruleGesture" type="text" value="${escapeHtml(trigger.gesture || "六")}" placeholder="例如：六" /></label>
    `;
  } else if (type === "key") {
    html = `
      <p class="form-hint">S1 按键触发待后续接入，可先保存配置。</p>
      <label>按键码<input id="ruleKeyCode" type="text" value="${escapeHtml(trigger.key_code || "any")}" /></label>
    `;
  } else if (type === "temperature" || type === "brightness_sensor" || type === "motion") {
    html = `
      <p class="form-hint">${escapeHtml(triggerMeta?.hint || "传感器触发待后续接入")}</p>
      <label>比较
        <select id="ruleSensorOperator">${optionItems(meta.operators || [], trigger.operator || "lt", { valueKey: "id", labelKey: "label", disabledKey: null })}</select>
      </label>
      <label>阈值<input id="ruleSensorValue" type="number" value="${trigger.value ?? 0}" /></label>
    `;
  } else {
    html = `<p class="form-hint">${escapeHtml(triggerMeta?.hint || "")}</p>`;
  }

  box.innerHTML = html;

  const deviceSelect = box.querySelector("#ruleStateDevice");
  if (deviceSelect) {
    deviceSelect.addEventListener("change", () => {
      renderTriggerFields(form, meta, { type: "device_state", device: deviceSelect.value });
    });
  }
}

function renderActionRow(meta, action = {}) {
  const device = action.device || "light";
  const deviceActions = findActionsForDevice(meta, device);
  const act = action.action || (deviceActions[0]?.action ?? "on");
  const params = action.params || {};
  let paramsHtml = "";

  if (act === "set_speed") {
    paramsHtml = `<label>速度<input type="number" min="0" max="100" data-param="speed" value="${params.speed ?? 30}" /></label>`;
  } else if (act === "set_brightness") {
    paramsHtml = `<label>亮度<input type="number" min="0" max="100" data-param="brightness" value="${params.brightness ?? 60}" /></label>`;
  } else if (act === "set_position") {
    paramsHtml = `<label>开度<input type="number" min="0" max="100" data-param="position" value="${params.position ?? 50}" /></label>`;
  } else if (act === "set_rgb") {
    paramsHtml = `
      <label>R<input type="number" min="0" max="255" data-param="r" value="${params.r ?? 255}" /></label>
      <label>G<input type="number" min="0" max="255" data-param="g" value="${params.g ?? 128}" /></label>
      <label>B<input type="number" min="0" max="255" data-param="b" value="${params.b ?? 0}" /></label>
      <label>亮度<input type="number" min="0" max="100" data-param="brightness" value="${params.brightness ?? 100}" /></label>
    `;
  }

  return `
    <div class="action-row">
      <label>设备<select class="action-device">${optionItems(meta.actions.filter((a, i, arr) => arr.findIndex((x) => x.device === a.device) === i), device, { valueKey: "device", labelKey: "label", disabledKey: "available" })}</select></label>
      <label>动作<select class="action-type">${deviceActions.map((a) => `<option value="${a.action}" ${a.action === act ? "selected" : ""} ${a.available === false ? "disabled" : ""}>${escapeHtml(a.label)}</option>`).join("")}</select></label>
      <div class="action-params">${paramsHtml}</div>
      <button type="button" class="secondary action-remove">移除</button>
    </div>
  `;
}

function bindActionRowEvents(container, meta) {
  container.querySelectorAll(".action-row").forEach((row) => {
    const deviceSelect = row.querySelector(".action-device");
    const actionSelect = row.querySelector(".action-type");
    const refresh = () => {
      const device = deviceSelect.value;
      const currentAction = actionSelect.value;
      const actions = findActionsForDevice(meta, device);
      actionSelect.innerHTML = actions.map((a) => `<option value="${a.action}" ${a.available === false ? "disabled" : ""}>${escapeHtml(a.label)}</option>`).join("");
      if (actions.some((a) => a.action === currentAction)) {
        actionSelect.value = currentAction;
      }
      const paramsBox = row.querySelector(".action-params");
      paramsBox.outerHTML = `<div class="action-params"></div>`;
      const newRow = renderActionRow(meta, { device, action: actionSelect.value, params: {} });
      const tmp = document.createElement("div");
      tmp.innerHTML = newRow;
      row.querySelector(".action-params").replaceWith(tmp.querySelector(".action-params"));
    };
    deviceSelect.addEventListener("change", refresh);
    actionSelect.addEventListener("change", refresh);
  });
}

function collectTrigger(form) {
  const type = form.querySelector("#ruleTriggerType").value;
  if (type === "manual") return { type };
  if (type === "device_state") {
    const fieldEl = form.querySelector("#ruleStateField");
    const valueEl = form.querySelector("#ruleStateValue");
    const isBool = valueEl && valueEl.type === "checkbox";
    return {
      type,
      device: form.querySelector("#ruleStateDevice").value,
      field: fieldEl.value,
      operator: form.querySelector("#ruleStateOperator").value,
      value: isBool ? valueEl.checked : Number(valueEl.value),
    };
  }
  if (type === "camera_gesture") {
    return { type, gesture: form.querySelector("#ruleGesture").value.trim() };
  }
  if (type === "key") {
    return { type, key_code: form.querySelector("#ruleKeyCode").value.trim() || "any" };
  }
  if (type === "temperature" || type === "brightness_sensor" || type === "motion") {
    return {
      type,
      operator: form.querySelector("#ruleSensorOperator").value,
      value: Number(form.querySelector("#ruleSensorValue").value),
    };
  }
  return { type };
}

function collectActions(form) {
  const rows = form.querySelectorAll(".action-row");
  if (!rows.length) throw new Error("至少配置一个执行动作");
  return Array.from(rows).map((row) => {
    const device = row.querySelector(".action-device").value;
    const action = row.querySelector(".action-type").value;
    const params = {};
    row.querySelectorAll("[data-param]").forEach((input) => {
      params[input.dataset.param] = Number(input.value);
    });
    return { device, action, params };
  });
}

function openRuleModal(modal, meta, rule) {
  const form = modal.querySelector("#ruleForm");
  const isEdit = Boolean(rule?.id);
  modal.querySelector("#ruleModalTitle").textContent = isEdit ? "编辑规则" : "添加规则";
  form.querySelector("#ruleId").value = rule?.id || "";
  form.querySelector("#ruleName").value = rule?.name || "";
  form.querySelector("#ruleDescription").value = rule?.description || "";
  form.querySelector("#ruleEnabled").checked = rule?.enabled !== false;
  form.querySelector("#ruleCooldown").value = rule?.options?.cooldown_seconds ?? 30;

  const triggerSelect = form.querySelector("#ruleTriggerType");
  triggerSelect.innerHTML = (meta.triggers || []).map((item) => {
    const selected = item.type === (rule?.trigger?.type || "device_state");
    const disabled = item.source_device && item.available === false;
    const suffix = disabled ? "（设备未在线）" : (!item.implemented ? "（待接入）" : "");
    return `<option value="${escapeHtml(item.type)}" ${selected ? "selected" : ""} ${disabled ? "disabled" : ""}>${escapeHtml(item.label)}${suffix}</option>`;
  }).join("");
  renderTriggerFields(form, meta, rule?.trigger || {});

  const actionsBox = form.querySelector("#ruleActionsBox");
  const actions = rule?.actions?.length ? rule.actions : [{ device: "light", action: "on", params: {} }];
  actionsBox.innerHTML = actions.map((a) => renderActionRow(meta, a)).join("");
  bindActionRowEvents(actionsBox, meta);

  modal.classList.remove("hidden");
}

function closeRuleModal(modal) {
  modal.classList.add("hidden");
}

async function loadMeta() {
  if (!metaCache) {
    metaCache = (await getJson("/api/rules/meta")).data;
  }
  return metaCache;
}

export async function refreshRulesView({ listEl, summaryEl, onNotify }) {
  if (!listEl) return;
  try {
    const [rulesResp, meta] = await Promise.all([getJson("/api/rules"), loadMeta()]);
    metaCache = meta;
    const rules = rulesResp.data?.rules || [];
    if (summaryEl) {
      const enabled = rules.filter((r) => r.enabled).length;
      const pending = rules.filter((r) => !r.trigger_implemented).length;
      summaryEl.textContent = `共 ${rules.length} 条 · 已启用 ${enabled} · 触发待接入 ${pending}`;
    }
    renderRuleCards(listEl, rules);
  } catch (err) {
    if (summaryEl) summaryEl.textContent = `规则加载失败：${err.message}`;
    listEl.innerHTML = "";
    onNotify?.(`规则加载失败：${err.message}`, "error");
  }
}

export function bindRulesView({ listEl, summaryEl, addBtn, modal, onNotify, onDeviceRefresh }) {
  if (!listEl || !modal) return;

  const form = modal.querySelector("#ruleForm");
  const triggerTypeSelect = form.querySelector("#ruleTriggerType");

  addBtn?.addEventListener("click", async () => {
    try {
      const meta = await loadMeta();
      openRuleModal(modal, meta, null);
    } catch (err) {
      onNotify?.(err.message, "error");
    }
  });

  modal.querySelector("#ruleModalClose")?.addEventListener("click", () => closeRuleModal(modal));
  modal.querySelector("#ruleModalCancel")?.addEventListener("click", () => closeRuleModal(modal));
  modal.querySelector(".rule-modal-backdrop")?.addEventListener("click", () => closeRuleModal(modal));

  triggerTypeSelect?.addEventListener("change", async () => {
    const meta = await loadMeta();
    renderTriggerFields(form, meta, { type: triggerTypeSelect.value });
  });

  form.querySelector("#ruleAddAction")?.addEventListener("click", async () => {
    const meta = await loadMeta();
    const box = form.querySelector("#ruleActionsBox");
    box.insertAdjacentHTML("beforeend", renderActionRow(meta, { device: "light", action: "on", params: {} }));
    bindActionRowEvents(box, meta);
  });

  form.querySelector("#ruleActionsBox")?.addEventListener("click", (event) => {
    if (!event.target.matches(".action-remove")) return;
    const rows = form.querySelectorAll(".action-row");
    if (rows.length <= 1) {
      onNotify?.("至少保留一个执行动作", "error");
      return;
    }
    event.target.closest(".action-row")?.remove();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = {
        name: form.querySelector("#ruleName").value.trim(),
        description: form.querySelector("#ruleDescription").value.trim(),
        enabled: form.querySelector("#ruleEnabled").checked,
        trigger: collectTrigger(form),
        actions: collectActions(form),
        options: { cooldown_seconds: Number(form.querySelector("#ruleCooldown").value || 30) },
      };
      const ruleId = form.querySelector("#ruleId").value;
      if (ruleId) {
        await putJson(`/api/rules/${ruleId}`, payload);
        onNotify?.("规则已更新", "ok");
      } else {
        await postJson("/api/rules", payload);
        onNotify?.("规则已创建", "ok");
      }
      metaCache = null;
      closeRuleModal(modal);
      await refreshRulesView({ listEl, summaryEl, onNotify });
    } catch (err) {
      onNotify?.(err.message, "error");
    }
  });

  listEl.addEventListener("click", async (event) => {
    const btn = event.target.closest("button[data-action]");
    const card = event.target.closest(".rule-card");
    if (!card) {
      if (event.target.matches('input[data-action="toggle"]')) return;
      return;
    }
    const ruleId = card.dataset.ruleId;

    if (event.target.matches('input[data-action="toggle"]')) {
      try {
        await postJson(`/api/rules/${ruleId}/toggle`, { enabled: event.target.checked });
        metaCache = null;
        await refreshRulesView({ listEl, summaryEl, onNotify });
      } catch (err) {
        event.target.checked = !event.target.checked;
        onNotify?.(err.message, "error");
      }
      return;
    }

    if (!btn) return;
    const action = btn.dataset.action;

    if (action === "run") {
      try {
        const resp = await postJson(`/api/rules/${ruleId}/run`, {});
        onNotify?.(resp.data?.message || resp.message || "测试运行完成", "ok");
        await onDeviceRefresh?.();
        metaCache = null;
        await refreshRulesView({ listEl, summaryEl, onNotify });
      } catch (err) {
        onNotify?.(`测试运行失败：${err.message}`, "error");
      }
      return;
    }

    if (action === "edit") {
      try {
        const meta = await loadMeta();
        const rule = (await getJson(`/api/rules/${ruleId}`)).data;
        openRuleModal(modal, meta, rule);
      } catch (err) {
        onNotify?.(err.message, "error");
      }
      return;
    }

    if (action === "delete") {
      if (!window.confirm("确定删除这条规则吗？")) return;
      try {
        await deleteJson(`/api/rules/${ruleId}`);
        onNotify?.("规则已删除", "ok");
        metaCache = null;
        await refreshRulesView({ listEl, summaryEl, onNotify });
      } catch (err) {
        onNotify?.(err.message, "error");
      }
    }
  });
}
