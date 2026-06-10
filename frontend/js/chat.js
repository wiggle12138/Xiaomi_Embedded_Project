function esc(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function buildNlpBlocks(data) {
  const blocks = [];
  const mode = data?.nlp?.mode || "unknown";
  blocks.push(`<div class="meta-chip chip-route">路由分支：${esc(mode)}</div>`);

  if (mode === "llm") {
    const model = data?.nlp?.model || "unknown";
    const elapsed = data?.nlp?.llm_elapsed_ms;
    const reason = data?.nlp?.reason || "模型已输出结构化命令";
    const elapsedText = Number.isFinite(Number(elapsed)) ? ` · ${Number(elapsed)}ms` : "";
    blocks.push(`<div class="meta-chip chip-thinking">模型思考：${esc(model)}${elapsedText}<br/>${esc(reason)}</div>`);
  }

  const action = data?.action || {};
  if (action.device && action.action) {
    const paramsText = JSON.stringify(action.params || {}, null, 0);
    blocks.push(`<div class="meta-chip chip-tool">工具调用：${esc(action.device)}.${esc(action.action)} ${esc(paramsText)}</div>`);
  }

  const msg = data?.message || data?.text || "执行完成";
  blocks.push(`<div class="meta-chip chip-result">执行结果：${esc(msg)}</div>`);
  return blocks.join("");
}

export function createChatThread(threadEl) {
  function appendRow(role, html) {
    const row = document.createElement("div");
    row.className = `chat-row ${role}`;
    row.innerHTML = `<div class="chat-bubble">${html}</div>`;
    threadEl.appendChild(row);
    threadEl.scrollTop = threadEl.scrollHeight;
  }

  return {
    user(text) {
      appendRow("user", esc(text));
    },
    error(text) {
      appendRow("assistant", `<div class="meta-chip chip-error">${esc(text)}</div>`);
    },
    assistantText(text) {
      appendRow("assistant", esc(text));
    },
    execution(resp) {
      const data = resp?.data || {};
      appendRow("assistant", buildNlpBlocks(data));
    },
  };
}
