const state = {
  requestSeq: 1,
  config: null,
  sessions: null,
  tools: [],
  currentAssistant: null,
  busy: false
};

const el = {
  runtimeStatus: document.getElementById("runtimeStatus"),
  workspaceInput: document.getElementById("workspaceInput"),
  workspaceApply: document.getElementById("workspaceApply"),
  modeSelect: document.getElementById("modeSelect"),
  newSessionButton: document.getElementById("newSessionButton"),
  clearSessionButton: document.getElementById("clearSessionButton"),
  sessionList: document.getElementById("sessionList"),
  workspaceName: document.getElementById("workspaceName"),
  modelStatus: document.getElementById("modelStatus"),
  indexButton: document.getElementById("indexButton"),
  diagnosticsButton: document.getElementById("diagnosticsButton"),
  messageList: document.getElementById("messageList"),
  composer: document.getElementById("composer"),
  messageInput: document.getElementById("messageInput"),
  sendButton: document.getElementById("sendButton"),
  turnStatus: document.getElementById("turnStatus"),
  indexSummary: document.getElementById("indexSummary"),
  indexMeter: document.getElementById("indexMeter"),
  diagnosticsList: document.getElementById("diagnosticsList"),
  configPath: document.getElementById("configPath"),
  modelForm: document.getElementById("modelForm"),
  modelIndex: document.getElementById("modelIndex"),
  modelDisplayName: document.getElementById("modelDisplayName"),
  modelId: document.getElementById("modelId"),
  modelBaseUrl: document.getElementById("modelBaseUrl"),
  modelApiKey: document.getElementById("modelApiKey"),
  modelProvider: document.getElementById("modelProvider"),
  modelContextTokens: document.getElementById("modelContextTokens"),
  modelList: document.getElementById("modelList"),
  toolSummary: document.getElementById("toolSummary"),
  toolFilter: document.getElementById("toolFilter"),
  toolList: document.getElementById("toolList"),
  logOutput: document.getElementById("logOutput")
};

function send(action, payload = {}) {
  const id = `ui-${state.requestSeq++}`;
  window.chrome.webview.postMessage({ id, action, payload });
  return id;
}

function log(message) {
  const stamp = new Date().toLocaleTimeString();
  el.logOutput.textContent += `[${stamp}] ${message}\n`;
  el.logOutput.scrollTop = el.logOutput.scrollHeight;
}

function basename(path) {
  const value = String(path || "").replaceAll("\\", "/").replace(/\/$/, "");
  return value.split("/").pop() || value || "Workspace";
}

function setBusy(value, label = "Ready") {
  state.busy = value;
  el.sendButton.disabled = value;
  el.turnStatus.textContent = label;
}

function addMessage(role, content, className = "") {
  const row = document.createElement("article");
  row.className = `message ${role} ${className}`.trim();
  const roleEl = document.createElement("div");
  roleEl.className = "message-role";
  roleEl.textContent = role;
  const contentEl = document.createElement("div");
  contentEl.className = "message-content";
  contentEl.textContent = content || "";
  row.append(roleEl, contentEl);
  el.messageList.append(row);
  el.messageList.scrollTop = el.messageList.scrollHeight;
  return contentEl;
}

function renderState(message) {
  state.config = message.config;
  state.sessions = message.sessions;
  state.tools = message.tools || state.tools;

  el.runtimeStatus.textContent = "Connected";
  el.workspaceInput.value = message.project_root || el.workspaceInput.value;
  el.workspaceName.textContent = basename(message.project_root);

  const activeModel = state.config?.active_model;
  el.modelStatus.textContent = activeModel
    ? `${activeModel.model_display_name || activeModel.model} via ${activeModel.provider || "provider"}`
    : "No active model configured";
  el.configPath.textContent = state.config?.config_path || "Config path pending.";

  renderModes();
  renderSessions();
  renderModels();
  renderTools();

  if (state.sessions?.messages && !state.busy) {
    el.messageList.replaceChildren();
    for (const messageItem of state.sessions.messages) {
      if (messageItem.role === "system") {
        continue;
      }
      addMessage(messageItem.role || "message", messageItem.content || "");
    }
  }
}

function renderModes() {
  const selected = state.config?.mode || "reverie";
  el.modeSelect.replaceChildren();
  for (const mode of state.config?.modes || []) {
    const option = document.createElement("option");
    option.value = mode.id;
    option.textContent = mode.name || mode.id;
    option.selected = mode.id === selected;
    el.modeSelect.append(option);
  }
}

function renderSessions() {
  const currentId = state.sessions?.current_session_id || "";
  el.sessionList.replaceChildren();
  for (const session of state.sessions?.sessions || []) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `session-item ${session.id === currentId ? "active" : ""}`;
    item.innerHTML = `<div class="session-title"></div><div class="session-meta"></div>`;
    item.querySelector(".session-title").textContent = session.name || session.id;
    item.querySelector(".session-meta").textContent = `${session.message_count || 0} messages`;
    item.addEventListener("click", () => send("switchSession", { sessionId: session.id }));
    el.sessionList.append(item);
  }
}

function renderModels() {
  el.modelList.replaceChildren();
  const activeIndex = state.config?.active_model_index ?? -1;
  for (const model of state.config?.models || []) {
    const item = document.createElement("div");
    item.className = `model-item ${model.index === activeIndex ? "active" : ""}`;
    const name = document.createElement("div");
    name.className = "model-name";
    name.textContent = model.model_display_name || model.model || "Unnamed model";
    const meta = document.createElement("div");
    meta.className = "model-meta";
    meta.textContent = `${model.provider || "provider"} | ${model.base_url || "no base url"}`;
    const badges = document.createElement("div");
    badges.className = "badge-row";
    const edit = makeBadge("Edit");
    const select = makeBadge("Use");
    edit.addEventListener("click", () => fillModelForm(model));
    select.addEventListener("click", () => send("selectModel", { index: model.index }));
    badges.append(edit, select);
    item.append(name, meta, badges);
    el.modelList.append(item);
  }
}

function renderTools() {
  const filter = (el.toolFilter.value || "").toLowerCase();
  const visible = state.tools.filter(tool => {
    const haystack = `${tool.name} ${tool.description} ${tool.category} ${(tool.tags || []).join(" ")}`.toLowerCase();
    return !filter || haystack.includes(filter);
  });
  const exposed = state.tools.filter(tool => tool.visible).length;
  el.toolSummary.textContent = `${exposed} visible, ${state.tools.length} registered.`;
  el.toolList.replaceChildren();
  for (const tool of visible) {
    const item = document.createElement("div");
    item.className = "tool-item";
    const name = document.createElement("div");
    name.className = "tool-name";
    name.textContent = tool.name;
    const meta = document.createElement("div");
    meta.className = "tool-meta";
    meta.textContent = tool.description || tool.category || "";
    const badges = document.createElement("div");
    badges.className = "badge-row";
    badges.append(makeBadge(tool.visible ? "visible" : "hidden", tool.visible ? "ok" : ""));
    if (tool.read_only) badges.append(makeBadge("read only"));
    if (tool.destructive) badges.append(makeBadge("destructive", "warn"));
    item.append(name, meta, badges);
    el.toolList.append(item);
  }
}

function makeBadge(text, className = "") {
  const badge = document.createElement("span");
  badge.className = `badge ${className}`.trim();
  badge.textContent = text;
  return badge;
}

function fillModelForm(model) {
  el.modelIndex.value = model.index ?? -1;
  el.modelDisplayName.value = model.model_display_name || "";
  el.modelId.value = model.model || "";
  el.modelBaseUrl.value = model.base_url || "";
  el.modelApiKey.value = "";
  el.modelProvider.value = model.provider || "openai-sdk";
  el.modelContextTokens.value = model.max_context_tokens || 128000;
}

function handleBridgeMessage(message) {
  switch (message.type) {
    case "ready":
      el.runtimeStatus.textContent = "Bridge ready";
      log(`Bridge ready: ${message.runtime_root || ""}`);
      break;
    case "host.info":
      el.workspaceInput.value = message.workspaceRoot || message.cwd || "";
      send("initialize", { projectRoot: el.workspaceInput.value });
      break;
    case "state":
      renderState(message);
      break;
    case "chat.started":
      state.currentAssistant = addMessage("assistant", "");
      setBusy(true, "Streaming");
      break;
    case "chat.context":
      log(`Context engine initialized: ${message.context_engine_initialized}`);
      break;
    case "chat.chunk":
      if (!state.currentAssistant) state.currentAssistant = addMessage("assistant", "");
      state.currentAssistant.textContent += message.chunk || "";
      el.messageList.scrollTop = el.messageList.scrollHeight;
      break;
    case "chat.thinking":
      log(`thinking: ${message.chunk || ""}`);
      break;
    case "chat.tool":
      renderToolEvent(message.event);
      break;
    case "chat.complete":
      state.currentAssistant = null;
      setBusy(false, "Ready");
      break;
    case "index.started":
      el.indexSummary.textContent = "Indexing started.";
      el.indexMeter.style.width = "1%";
      break;
    case "index.progress":
      el.indexSummary.textContent = `${message.stage || "index"}: ${message.current_file || message.message || ""}`;
      el.indexMeter.style.width = `${Math.max(1, Math.min(99, Number(message.percent || 0)))}%`;
      break;
    case "index.complete":
      el.indexMeter.style.width = "100%";
      renderIndexResult(message);
      break;
    case "diagnostics":
      renderDiagnostics(message.items || []);
      break;
    case "tools":
      state.tools = message.tools || [];
      renderTools();
      break;
    case "host.log":
      log(message.message || "");
      break;
    case "host.error":
    case "error":
      setBusy(false, "Error");
      log(`error: ${message.error || "Unknown error"}`);
      addMessage("system", message.error || "Unknown error");
      break;
    default:
      log(`${message.type || "event"} ${JSON.stringify(message)}`);
      break;
  }
}

function renderToolEvent(event) {
  if (!event) return;
  const title = event.event || "tool";
  const tool = event.tool || event.name || "";
  log(`tool ${title}: ${tool}`);
}

function renderIndexResult(message) {
  const result = message.result || {};
  el.indexSummary.textContent = `${result.files_parsed || 0} parsed, ${result.symbols_extracted || 0} symbols, ${Math.round(result.total_time_ms || 0)}ms.`;
}

function renderDiagnostics(items) {
  el.diagnosticsList.replaceChildren();
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "diagnostic-item";
    const label = document.createElement("div");
    label.className = "tool-name";
    label.textContent = `${item.ok ? "OK" : "Check"} ${item.label}`;
    const value = document.createElement("div");
    value.className = "diagnostic-value";
    value.textContent = item.value || "";
    row.append(label, value);
    el.diagnosticsList.append(row);
  }
}

document.querySelectorAll(".tab-button").forEach(button => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab-button").forEach(item => item.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    document.getElementById(`${button.dataset.tab}Tab`).classList.add("active");
  });
});

el.workspaceApply.addEventListener("click", () => {
  send("setWorkspace", { projectRoot: el.workspaceInput.value });
});

el.modeSelect.addEventListener("change", () => {
  send("setMode", { mode: el.modeSelect.value });
});

el.newSessionButton.addEventListener("click", () => {
  el.messageList.replaceChildren();
  send("newSession", {});
});

el.clearSessionButton.addEventListener("click", () => {
  el.messageList.replaceChildren();
  send("clearSession", {});
});

el.indexButton.addEventListener("click", () => {
  send("indexWorkspace", { projectRoot: el.workspaceInput.value });
});

el.diagnosticsButton.addEventListener("click", () => {
  send("diagnostics", {});
});

el.toolFilter.addEventListener("input", renderTools);

el.modelForm.addEventListener("submit", event => {
  event.preventDefault();
  send("saveModel", {
    index: Number(el.modelIndex.value),
    model_display_name: el.modelDisplayName.value,
    model: el.modelId.value,
    base_url: el.modelBaseUrl.value,
    api_key: el.modelApiKey.value,
    provider: el.modelProvider.value,
    max_context_tokens: Number(el.modelContextTokens.value || 128000)
  });
  el.modelForm.reset();
  el.modelIndex.value = "-1";
  el.modelContextTokens.value = "128000";
});

el.composer.addEventListener("submit", event => {
  event.preventDefault();
  const message = el.messageInput.value.trim();
  if (!message || state.busy) return;
  addMessage("user", message);
  el.messageInput.value = "";
  setBusy(true, "Starting");
  send("chat", {
    message,
    projectRoot: el.workspaceInput.value,
    mode: el.modeSelect.value,
    sessionId: state.sessions?.current_session_id || ""
  });
});

el.messageInput.addEventListener("keydown", event => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    el.composer.requestSubmit();
  }
});

window.chrome.webview.addEventListener("message", event => {
  handleBridgeMessage(event.data || {});
});

send("hostInfo");
