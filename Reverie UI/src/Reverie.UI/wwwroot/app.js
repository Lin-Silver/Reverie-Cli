const OFFICIAL_PLUGINS = ["blender", "godot", "o3de", "game_models"];

const state = {
  requestSeq: 1,
  activeView: "chat",
  host: {},
  runtime: {},
  config: null,
  sessions: null,
  tools: [],
  git: null,
  plugins: null,
  settings: null,
  automations: null,
  currentAssistant: null,
  currentAssistantText: "",
  pendingAssistantChunk: "",
  streamFrame: 0,
  busy: false,
  logs: [],
  selectedSettingKey: "",
  selectedPluginId: "",
  pluginProgress: {},
  recentProjects: loadRecentProjects()
};

const $ = id => document.getElementById(id);

const el = {
  runtimeStatus: $("runtimeStatus"),
  workspaceInput: $("workspaceInput"),
  workspaceApply: $("workspaceApply"),
  projectList: $("projectList"),
  sessionSearch: $("sessionSearch"),
  sessionList: $("sessionList"),
  settingsNavButton: $("settingsNavButton"),
  newSessionButton: $("newSessionButton"),
  clearSessionButton: $("clearSessionButton"),
  workspaceName: $("workspaceName"),
  modelStatus: $("modelStatus"),
  cliStatusPill: $("cliStatusPill"),
  bridgeStatusPill: $("bridgeStatusPill"),
  gitStatusPill: $("gitStatusPill"),
  configStatusPill: $("configStatusPill"),
  indexButton: $("indexButton"),
  diagnosticsButton: $("diagnosticsButton"),
  gitRefreshButton: $("gitRefreshButton"),
  emptyState: $("emptyState"),
  messageList: $("messageList"),
  composer: $("composer"),
  messageInput: $("messageInput"),
  sendButton: $("sendButton"),
  turnStatus: $("turnStatus"),
  modeSelect: $("modeSelect"),
  thinkingStyleSelect: $("thinkingStyleSelect"),
  globalSearchInput: $("globalSearchInput"),
  searchResults: $("searchResults"),
  pluginSummary: $("pluginSummary"),
  pluginRemoteSummary: $("pluginRemoteSummary"),
  pluginRefreshButton: $("pluginRefreshButton"),
  remoteRefreshButton: $("remoteRefreshButton"),
  pluginFilter: $("pluginFilter"),
  pluginList: $("pluginList"),
  pluginDetail: $("pluginDetail"),
  automationSummary: $("automationSummary"),
  automationForm: $("automationForm"),
  automationId: $("automationId"),
  automationName: $("automationName"),
  automationInterval: $("automationInterval"),
  automationEnabled: $("automationEnabled"),
  automationPrompt: $("automationPrompt"),
  automationResetButton: $("automationResetButton"),
  automationList: $("automationList"),
  automationLog: $("automationLog"),
  settingsSummary: $("settingsSummary"),
  settingsRefreshButton: $("settingsRefreshButton"),
  settingsList: $("settingsList"),
  settingDetail: $("settingDetail"),
  indexSummary: $("indexSummary"),
  indexMeter: $("indexMeter"),
  diagnosticsList: $("diagnosticsList"),
  configPath: $("configPath"),
  modelForm: $("modelForm"),
  modelIndex: $("modelIndex"),
  modelDisplayName: $("modelDisplayName"),
  modelId: $("modelId"),
  modelBaseUrl: $("modelBaseUrl"),
  modelApiKey: $("modelApiKey"),
  modelProvider: $("modelProvider"),
  modelContextTokens: $("modelContextTokens"),
  modelList: $("modelList"),
  toolSummary: $("toolSummary"),
  toolFilter: $("toolFilter"),
  toolList: $("toolList"),
  gitSummary: $("gitSummary"),
  gitOutput: $("gitOutput"),
  logOutput: $("logOutput")
};

function send(action, payload = {}) {
  const id = `ui-${state.requestSeq++}`;
  window.chrome.webview.postMessage({ id, action, payload });
  return id;
}

function loadRecentProjects() {
  try {
    const raw = JSON.parse(localStorage.getItem("reverie.recentProjects") || "[]");
    return Array.isArray(raw) ? raw.filter(Boolean).slice(0, 8) : [];
  } catch {
    return [];
  }
}

function rememberProject(path) {
  const value = String(path || "").trim();
  if (!value) return;
  state.recentProjects = [value, ...state.recentProjects.filter(item => item !== value)].slice(0, 8);
  localStorage.setItem("reverie.recentProjects", JSON.stringify(state.recentProjects));
  renderProjects();
}

function log(message) {
  const stamp = new Date().toLocaleTimeString();
  state.logs.push(`[${stamp}] ${message}`);
  if (state.logs.length > 400) state.logs.splice(0, state.logs.length - 400);
  el.logOutput.textContent = state.logs.join("\n");
  el.logOutput.scrollTop = el.logOutput.scrollHeight;
}

function basename(path) {
  const value = String(path || "").replaceAll("\\", "/").replace(/\/$/, "");
  return value.split("/").pop() || value || "Workspace";
}

function compactPath(path) {
  const text = String(path || "");
  if (text.length <= 58) return text;
  return `${text.slice(0, 26)}...${text.slice(-28)}`;
}

function setBusy(value, label = "Ready") {
  state.busy = value;
  el.sendButton.disabled = value;
  el.turnStatus.textContent = label;
}

function setPill(node, text, className = "") {
  node.textContent = text;
  node.className = `status-pill ${className}`.trim();
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderInlineMarkdown(text) {
  let html = escapeHtml(text);
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  return html.replace(/\n/g, "<br>");
}

function renderMarkdownLite(text) {
  const parts = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").split(/```/);
  return parts.map((part, index) => {
    if (index % 2 === 0) return renderInlineMarkdown(part);
    const lines = part.split("\n");
    if (lines.length > 1 && /^[A-Za-z0-9_+.-]+$/.test(lines[0].trim())) lines.shift();
    return `<pre><code>${escapeHtml(lines.join("\n").trim())}</code></pre>`;
  }).join("");
}

function setMessageContent(node, content) {
  node.innerHTML = renderMarkdownLite(content);
}

function buildMessageElement(role, content) {
  const row = document.createElement("article");
  row.className = `message ${role}`.trim();
  const roleEl = document.createElement("div");
  roleEl.className = "message-role";
  roleEl.textContent = role;
  const contentEl = document.createElement("div");
  contentEl.className = "message-content";
  setMessageContent(contentEl, content || "");
  row.append(roleEl, contentEl);
  return row;
}

function addMessage(role, content, className = "") {
  const row = buildMessageElement(role, content);
  if (className) row.classList.add(className);
  el.messageList.append(row);
  updateEmptyState();
  el.messageList.scrollTop = el.messageList.scrollHeight;
  return row.querySelector(".message-content");
}

function updateEmptyState() {
  const hasMessages = Boolean(el.messageList.children.length);
  el.emptyState.classList.toggle("hidden", hasMessages);
  el.messageList.classList.toggle("active", hasMessages);
}

function flushAssistantChunk() {
  if (!state.currentAssistant || !state.pendingAssistantChunk) return;
  state.currentAssistantText += state.pendingAssistantChunk;
  state.pendingAssistantChunk = "";
  setMessageContent(state.currentAssistant, state.currentAssistantText);
  el.messageList.scrollTop = el.messageList.scrollHeight;
}

function queueAssistantChunk(chunk) {
  state.pendingAssistantChunk += chunk || "";
  if (state.streamFrame) return;
  state.streamFrame = requestAnimationFrame(() => {
    state.streamFrame = 0;
    flushAssistantChunk();
  });
}

function activateView(name) {
  state.activeView = name;
  document.querySelectorAll(".main-view").forEach(view => {
    view.classList.toggle("active", view.id === `${name}View`);
  });
  document.querySelectorAll(".nav-item").forEach(item => {
    item.classList.toggle("active", item.dataset.view === name);
  });
  el.settingsNavButton.classList.toggle("active", name === "settings");
  if (name === "plugins" && !state.plugins) send("listPlugins");
  if (name === "settings" && !state.settings) send("listSettings");
  if (name === "automations" && !state.automations) send("listAutomations");
  if (name === "search") {
    renderSearch();
    el.globalSearchInput.focus();
  }
}

function activateTab(name) {
  document.querySelectorAll(".tab-button").forEach(item => {
    item.classList.toggle("active", item.dataset.tab === name);
  });
  document.querySelectorAll(".tab-panel").forEach(item => {
    item.classList.toggle("active", item.id === `${name}Tab`);
  });
}

function renderState(message) {
  state.config = message.config || state.config;
  state.sessions = message.sessions || state.sessions;
  state.tools = message.tools || state.tools;
  state.runtime = message.runtime || state.runtime;
  state.git = message.git || state.git;

  const projectRoot = message.project_root || el.workspaceInput.value || state.host.workspaceRoot || "";
  el.runtimeStatus.textContent = "Connected";
  el.workspaceInput.value = projectRoot;
  el.workspaceName.textContent = basename(projectRoot);
  rememberProject(projectRoot);

  const activeModel = state.config?.active_model;
  el.modelStatus.textContent = activeModel
    ? `${activeModel.model_display_name || activeModel.model} via ${activeModel.provider || "provider"}`
    : "No active model configured";

  el.configPath.textContent = state.config?.config_path || "Config path pending.";
  renderStatusPills();
  renderModes();
  el.thinkingStyleSelect.value = state.config?.thinking_output_style || "full";
  renderProjects();
  renderSessions();
  renderModels();
  renderTools();
  renderGit(state.git);
  renderSearch();

  if (state.sessions?.messages && !state.busy) {
    el.messageList.replaceChildren();
    const fragment = document.createDocumentFragment();
    const visibleMessages = state.sessions.messages.filter(item => item.role !== "system").slice(-160);
    for (const item of visibleMessages) fragment.append(buildMessageElement(item.role || "message", item.content || ""));
    el.messageList.append(fragment);
    updateEmptyState();
    el.messageList.scrollTop = el.messageList.scrollHeight;
  }
}

function renderStatusPills() {
  const cliPath = state.host.reverieCliPath || state.runtime.executable || "";
  setPill(el.cliStatusPill, cliPath ? `CLI ${compactPath(cliPath)}` : "CLI not found", cliPath ? "ok" : "warn");
  setPill(el.bridgeStatusPill, state.runtime.kind || state.host.bridgeKind || "Bridge starting", state.runtime.kind ? "ok" : "");
  const configPath = state.config?.config_path || "";
  setPill(el.configStatusPill, configPath ? `Config ${compactPath(configPath)}` : "Config pending", configPath ? "ok" : "");
  if (state.git?.available) {
    setPill(el.gitStatusPill, state.git.dirty ? `Git dirty ${state.git.change_count || 0}` : "Git clean", state.git.dirty ? "hot" : "ok");
  } else {
    setPill(el.gitStatusPill, "Git unavailable", "warn");
  }
}

function renderModes() {
  const selected = state.config?.mode || "reverie";
  const current = el.modeSelect.value;
  el.modeSelect.replaceChildren();
  for (const mode of state.config?.modes || []) {
    const option = document.createElement("option");
    option.value = mode.id;
    option.textContent = mode.name || mode.id;
    option.selected = mode.id === (current || selected);
    el.modeSelect.append(option);
  }
}

function renderProjects() {
  const active = el.workspaceInput.value;
  const projects = [...new Set([active, ...state.recentProjects].filter(Boolean))];
  el.projectList.replaceChildren();
  for (const project of projects.slice(0, 6)) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `project-item ${project === active ? "active" : ""}`;
    button.textContent = basename(project);
    button.title = project;
    button.addEventListener("click", () => {
      el.workspaceInput.value = project;
      send("setWorkspace", { projectRoot: project });
      send("listSettings");
      send("listPlugins");
      send("listAutomations");
    });
    el.projectList.append(button);
  }
}

function renderSessions() {
  const currentId = state.sessions?.current_session_id || "";
  const filter = (el.sessionSearch.value || "").toLowerCase();
  el.sessionList.replaceChildren();
  for (const session of state.sessions?.sessions || []) {
    const title = session.name || session.id;
    if (filter && !`${title} ${session.id}`.toLowerCase().includes(filter)) continue;

    const item = document.createElement("div");
    item.className = `session-item ${session.id === currentId ? "active" : ""}`;
    const row = document.createElement("div");
    row.className = "session-row";
    const titleEl = document.createElement("button");
    titleEl.type = "button";
    titleEl.className = "session-title link-button";
    titleEl.textContent = title;
    titleEl.addEventListener("click", () => {
      activateView("chat");
      send("switchSession", { sessionId: session.id });
    });
    const actions = document.createElement("div");
    actions.className = "session-actions";
    actions.append(
      makeButton("Rename", () => renameSession(session)),
      makeButton("Delete", () => deleteSession(session))
    );
    row.append(titleEl, actions);
    const meta = document.createElement("div");
    meta.className = "session-meta";
    meta.textContent = `${session.message_count || 0} messages | ${formatDate(session.updated_at)}`;
    item.append(row, meta);
    el.sessionList.append(item);
  }
}

function renameSession(session) {
  const name = prompt("Rename chat", session.name || session.id);
  if (!name || !name.trim()) return;
  send("renameSession", { sessionId: session.id, name: name.trim() });
}

function deleteSession(session) {
  if (!confirm(`Delete chat "${session.name || session.id}"?`)) return;
  send("deleteSession", { sessionId: session.id });
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
    badges.append(
      makeButton("Edit", () => fillModelForm(model)),
      makeButton("Use", () => send("selectModel", { index: model.index })),
      makeButton("Delete", () => send("deleteModel", { index: model.index }))
    );
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
  const fragment = document.createDocumentFragment();
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
    fragment.append(item);
  }
  el.toolList.append(fragment);
}

function renderSettings() {
  const settings = state.settings || {};
  const items = settings.items || [];
  if (!state.selectedSettingKey && items.length) state.selectedSettingKey = items[0].key;
  el.settingsSummary.textContent = settings.config_path
    ? `${settings.workspace_mode ? "Workspace" : "Global"} config | ${settings.config_path}`
    : "CLI settings pending.";
  el.settingsList.replaceChildren();
  for (const item of items) {
    const row = document.createElement("article");
    row.className = `setting-item ${item.key === state.selectedSettingKey ? "active" : ""}`;
    const title = document.createElement("div");
    title.className = "setting-title-row";
    const name = document.createElement("div");
    name.className = "setting-name";
    name.textContent = item.name || item.key;
    title.append(name, makeBadge(item.kind || "setting"));
    const meta = document.createElement("div");
    meta.className = "setting-meta";
    meta.textContent = item.description || item.command || "";
    const control = buildSettingControl(item);
    row.append(title, meta, control);
    row.addEventListener("click", () => selectSetting(item));
    el.settingsList.append(row);
  }
  const selected = items.find(item => item.key === state.selectedSettingKey) || items[0];
  if (selected) selectSetting(selected, false);
}

function buildSettingControl(item) {
  const wrap = document.createElement("div");
  wrap.className = "setting-control";
  wrap.addEventListener("click", event => event.stopPropagation());
  if (item.kind === "readonly") {
    wrap.append(makeValueLine(formatValue(item.value)));
    return wrap;
  }
  if (item.kind === "bool" || item.kind === "workspace") {
    const label = document.createElement("label");
    label.className = "toggle-row";
    const span = document.createElement("span");
    span.textContent = item.value ? "On" : "Off";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = Boolean(item.value);
    checkbox.addEventListener("change", event => {
      event.stopPropagation();
      send("setSetting", { key: item.key, value: checkbox.checked });
    });
    label.append(span, checkbox);
    wrap.append(label);
    return wrap;
  }
  if (item.kind === "choice") {
    const select = document.createElement("select");
    select.className = "select-input";
    const options = item.options || [];
    if (!options.length) {
      const option = document.createElement("option");
      option.textContent = "No choices available";
      option.value = "";
      select.append(option);
      select.disabled = true;
    } else {
      for (const opt of options) {
        const option = document.createElement("option");
        option.value = opt.value;
        option.textContent = opt.label || opt.value;
        option.selected = String(opt.value) === String(item.value);
        select.append(option);
      }
    }
    select.addEventListener("change", event => {
      event.stopPropagation();
      send("setSetting", { key: item.key, value: select.value });
    });
    wrap.append(select);
    return wrap;
  }
  if (item.kind === "int") {
    const input = document.createElement("input");
    input.className = "text-input";
    input.type = "number";
    input.min = item.min ?? 0;
    input.max = item.max ?? 999999;
    input.step = item.step ?? 1;
    input.value = item.value ?? "";
    input.addEventListener("change", event => {
      event.stopPropagation();
      send("setSetting", { key: item.key, value: Number(input.value) });
    });
    wrap.append(input);
    return wrap;
  }
  if (item.kind === "rules") {
    const textarea = document.createElement("textarea");
    textarea.rows = 6;
    textarea.value = item.value || "";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "primary-button";
    button.textContent = "Save rules";
    button.addEventListener("click", event => {
      event.stopPropagation();
      send("setSetting", { key: item.key, value: textarea.value });
    });
    wrap.append(textarea, button);
    return wrap;
  }
  wrap.append(makeValueLine(formatValue(item.value)));
  return wrap;
}

function selectSetting(item, scroll = true) {
  state.selectedSettingKey = item.key;
  el.settingDetail.innerHTML = `
    <div class="setting-name">${escapeHtml(item.name || item.key)}</div>
    <p>${escapeHtml(item.description || "")}</p>
    <p><strong>Current:</strong> ${escapeHtml(formatValue(item.value))}</p>
    <p><strong>Command:</strong> <code>${escapeHtml(item.command || "")}</code></p>
  `;
  if (scroll) renderSettings();
}

function renderPlugins() {
  const data = state.plugins || {};
  const localRecords = data.records || [];
  const remote = data.remote || {};
  const remotePlugins = remote.manifest?.plugins || [];
  const validations = data.source_validations || [];
  const filter = (el.pluginFilter.value || "").toLowerCase();
  const localMap = new Map(localRecords.map(record => [record.id, record]));
  const remoteMap = new Map(remotePlugins.map(plugin => [plugin.id, plugin]));
  const validationMap = new Map(validations.map(item => [item.plugin_id, item]));
  const ids = [...new Set([...OFFICIAL_PLUGINS, ...localMap.keys(), ...remoteMap.keys()])];
  const summary = data.summary || {};
  el.pluginSummary.textContent = summary.summary_label || `${localRecords.length} local plugins`;
  el.pluginRemoteSummary.textContent = remote.success
    ? `Remote ${remote.tag_name || "latest"} | ${remotePlugins.length} compiled plugin assets`
    : `Remote unavailable: ${remote.error || "not queried"}`;
  el.pluginList.replaceChildren();

  for (const id of ids) {
    const record = localMap.get(id);
    const remotePlugin = remoteMap.get(id);
    const validation = validationMap.get(id);
    const haystack = `${id} ${record?.name || ""} ${record?.description || ""} ${remotePlugin?.name || ""}`.toLowerCase();
    if (filter && !haystack.includes(filter)) continue;
    const item = document.createElement("article");
    item.className = "plugin-item";
    const title = document.createElement("div");
    title.className = "plugin-title-row";
    const name = document.createElement("div");
    name.className = "plugin-name";
    name.textContent = record?.name || remotePlugin?.name || id;
    title.append(name, makeBadge(record?.status_label || record?.status || "not installed", record?.status === "ready" ? "ok" : "warn"));

    const meta = document.createElement("div");
    meta.className = "plugin-meta";
    meta.textContent = [
      record ? `local ${record.delivery || ""}` : "local missing",
      remotePlugin ? `remote ${remotePlugin.version || remote.tag_name || "latest"}` : "remote missing",
      validation ? `source ${validation.success ? "valid" : "needs check"}` : ""
    ].filter(Boolean).join(" | ");

    const badges = document.createElement("div");
    badges.className = "badge-row";
    if (record?.protocol_status) badges.append(makeBadge(record.protocol_label || record.protocol_status, record.protocol_status === "ready" ? "ok" : "warn"));
    if (record?.tool_count) badges.append(makeBadge(`${record.tool_count} tools`, "ok"));
    if (remotePlugin?.size) badges.append(makeBadge(formatBytes(remotePlugin.size)));
    const progress = state.pluginProgress[id];
    const progressRow = document.createElement("div");
    progressRow.className = `plugin-progress ${progress ? "visible" : ""}`;
    if (progress) {
      const label = document.createElement("div");
      label.className = "plugin-progress-label";
      const downloaded = progress.downloaded ? formatBytes(progress.downloaded) : "";
      const total = progress.total ? formatBytes(progress.total) : "";
      label.textContent = progress.percent
        ? `${progress.status || "Downloading"} ${progress.percent}% (${downloaded}/${total})`
        : `${progress.status || "Downloading"} ${downloaded}`;
      const track = document.createElement("div");
      track.className = "plugin-progress-track";
      const meter = document.createElement("div");
      meter.className = "plugin-progress-meter";
      meter.style.width = `${Math.max(3, Math.min(100, Number(progress.percent || 3)))}%`;
      track.append(meter);
      progressRow.append(label, track);
    }

    const actions = document.createElement("div");
    actions.className = "badge-row";
    actions.append(makeButton("Inspect", () => {
      state.selectedPluginId = id;
      send("inspectPlugin", { pluginId: id });
    }));
    if (remotePlugin?.download_url) {
      actions.append(makeButton(record ? "Update exe" : "Download exe", () => {
        setBusy(true, "Installing");
        state.pluginProgress[id] = {
          status: record ? "Updating" : "Downloading",
          downloaded: 0,
          total: remotePlugin.size || 0,
          percent: 0
        };
        renderPlugins();
        send("installRemotePlugin", {
          pluginId: id,
          assetName: remotePlugin.asset_name,
          downloadUrl: remotePlugin.download_url,
          sha256: remotePlugin.sha256 || ""
        });
      }));
    }
    if (validation) {
      actions.append(makeButton("Build", () => {
        setBusy(true, "Building");
        send("buildPlugin", { pluginId: id, install: true, overwrite: true });
      }));
    }
    actions.append(makeButton("Deploy", () => send("deployPlugin", { pluginId: id })));
    const quickCommands = (record?.commands || [])
      .filter(command => !(command.parameters?.required || []).length)
      .slice(0, 3);
    for (const command of quickCommands) {
      actions.append(makeButton(command.name, () => {
        setBusy(true, command.name);
        send("callPluginCommand", { pluginId: id, command: command.name, arguments: {} });
      }));
    }

    item.append(title, meta, badges, progressRow, actions);
    item.addEventListener("click", () => {
      state.selectedPluginId = id;
      el.pluginDetail.textContent = JSON.stringify({ local: record || null, remote: remotePlugin || null, source: validation || null }, null, 2);
    });
    el.pluginList.append(item);
  }
}

function renderAutomations() {
  const payload = state.automations || {};
  const items = payload.automations || [];
  el.automationSummary.textContent = `${items.length} task(s) | ${payload.scheduler || "local"} | ${payload.root || ""}`;
  el.automationList.replaceChildren();
  for (const automation of items) {
    const item = document.createElement("article");
    item.className = "automation-item";
    const title = document.createElement("div");
    title.className = "automation-title-row";
    const name = document.createElement("div");
    name.className = "automation-name";
    name.textContent = automation.name || automation.id;
    title.append(name, makeBadge(automation.enabled ? "enabled" : "paused", automation.enabled ? "ok" : "warn"));
    const meta = document.createElement("div");
    meta.className = "automation-meta";
    meta.textContent = `Every ${automation.schedule?.interval_minutes || 60} min | ${automation.workspace || ""}`;
    const actions = document.createElement("div");
    actions.className = "badge-row";
    actions.append(
      makeButton("Edit", () => fillAutomationForm(automation)),
      makeButton(automation.enabled ? "Pause" : "Resume", () => send("toggleAutomation", { id: automation.id, enabled: !automation.enabled })),
      makeButton("Run", () => {
        setBusy(true, "Running automation");
        send("runAutomation", { id: automation.id });
      }),
      makeButton("Delete", () => {
        if (confirm(`Delete automation "${automation.name || automation.id}"?`)) send("deleteAutomation", { id: automation.id });
      })
    );
    item.append(title, meta, actions);
    item.addEventListener("click", () => {
      el.automationLog.textContent = automation.runtime?.last_log || "No run log yet.";
    });
    el.automationList.append(item);
  }
}

function fillAutomationForm(automation) {
  el.automationId.value = automation.id || "";
  el.automationName.value = automation.name || "";
  el.automationInterval.value = automation.schedule?.interval_minutes || 60;
  el.automationEnabled.checked = Boolean(automation.enabled);
  el.automationPrompt.value = automation.prompt || "";
}

function resetAutomationForm() {
  el.automationId.value = "";
  el.automationName.value = "";
  el.automationInterval.value = 60;
  el.automationEnabled.checked = true;
  el.automationPrompt.value = "";
}

function renderGit(git) {
  if (!git) return;
  state.git = git;
  if (!git.available) {
    el.gitSummary.textContent = git.error || "Git repository unavailable.";
    el.gitOutput.textContent = "";
    renderStatusPills();
    return;
  }
  el.gitSummary.textContent = `${git.branch || "branch"} | ${git.change_count || 0} changed files`;
  el.gitOutput.textContent = (git.changes || []).join("\n") || "Working tree clean.";
  renderStatusPills();
}

function renderSearch() {
  const query = (el.globalSearchInput.value || "").toLowerCase();
  const groups = [
    { type: "chat", title: "Chats", rows: [] },
    { type: "plugin", title: "Plugins", rows: [] },
    { type: "tool", title: "Tools", rows: [] },
    { type: "model", title: "Models", rows: [] },
    { type: "setting", title: "Settings", rows: [] },
    { type: "automation", title: "Automations", rows: [] }
  ];
  const byType = Object.fromEntries(groups.map(group => [group.type, group]));
  for (const session of state.sessions?.sessions || []) {
    byType.chat.rows.push({
      type: "chat",
      title: session.name || session.id,
      detail: `${session.message_count || 0} messages | ${formatDate(session.updated_at)}`,
      open: () => {
        activateView("chat");
        send("switchSession", { sessionId: session.id });
      },
      remove: () => deleteSession(session)
    });
  }
  for (const plugin of state.plugins?.records || []) {
    byType.plugin.rows.push({
      type: "plugin",
      title: plugin.name || plugin.id,
      detail: `${plugin.status_label || plugin.status || ""} | ${plugin.tool_count || 0} tools | ${(plugin.capabilities || []).slice(0, 4).join(", ")}`,
      open: () => {
        state.selectedPluginId = plugin.id;
        activateView("plugins");
      }
    });
  }
  for (const plugin of state.plugins?.remote?.manifest?.plugins || []) {
    byType.plugin.rows.push({
      type: "plugin",
      title: `${plugin.name || plugin.id} (remote)`,
      detail: `${plugin.version || "latest"} | ${formatBytes(plugin.size || 0)} | ${plugin.asset_name || ""}`,
      open: () => activateView("plugins")
    });
  }
  for (const tool of state.tools || []) byType.tool.rows.push({ type: "tool", title: tool.name, detail: tool.description || tool.category || "" });
  for (const model of state.config?.models || []) byType.model.rows.push({ type: "model", title: model.model_display_name || model.model, detail: `${model.provider || ""} | ${model.base_url || ""}` });
  for (const setting of state.settings?.items || []) byType.setting.rows.push({ type: "setting", title: setting.name, detail: setting.description || "", open: () => activateView("settings") });
  for (const automation of state.automations?.automations || []) byType.automation.rows.push({
    type: "automation",
    title: automation.name || automation.id,
    detail: `${automation.enabled ? "enabled" : "paused"} | every ${automation.schedule?.interval_minutes || 60} min`,
    open: () => activateView("automations")
  });

  el.searchResults.replaceChildren();
  let total = 0;
  for (const group of groups) {
    const visible = group.rows
      .filter(row => !query || `${row.type} ${row.title} ${row.detail}`.toLowerCase().includes(query))
      .slice(0, 30);
    total += visible.length;
    if (!visible.length) continue;

    const section = document.createElement("section");
    section.className = "search-section";
    const header = document.createElement("div");
    header.className = "search-section-header";
    header.innerHTML = `<span>${escapeHtml(group.title)}</span><strong>${visible.length}</strong>`;
    section.append(header);

    for (const row of visible) {
      const item = document.createElement("article");
      item.className = "result-item";
      const body = document.createElement("button");
      body.type = "button";
      body.className = "result-body";
      body.innerHTML = `<div class="setting-name">${escapeHtml(row.title)}</div><div class="setting-meta">${escapeHtml(row.detail)}</div>`;
      body.addEventListener("click", row.open || (() => {}));
      const actions = document.createElement("div");
      actions.className = "result-actions";
      if (row.remove) actions.append(makeButton("Delete", row.remove));
      item.append(body, actions);
      section.append(item);
    }
    el.searchResults.append(section);
  }
  if (!total) {
    const empty = document.createElement("div");
    empty.className = "empty-results";
    empty.textContent = query ? "No matching chats, plugins, tools, models, settings, or automations." : "No searchable data loaded yet.";
    el.searchResults.append(empty);
  }
}

function renderDiagnostics(items) {
  el.diagnosticsList.replaceChildren();
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "diagnostic-item";
    const label = document.createElement("div");
    label.className = "diagnostic-title";
    label.textContent = `${item.ok ? "OK" : "Check"} ${item.label}`;
    const value = document.createElement("div");
    value.className = "diagnostic-value";
    value.textContent = item.value || "";
    row.append(label, value);
    el.diagnosticsList.append(row);
  }
}

function fillModelForm(model) {
  activateTab("models");
  el.modelIndex.value = model.index ?? -1;
  el.modelDisplayName.value = model.model_display_name || "";
  el.modelId.value = model.model || "";
  el.modelBaseUrl.value = model.base_url || "";
  el.modelApiKey.value = "";
  el.modelProvider.value = model.provider || "openai-sdk";
  el.modelContextTokens.value = model.max_context_tokens || 128000;
}

function makeBadge(text, className = "") {
  const badge = document.createElement("span");
  badge.className = `badge ${className}`.trim();
  badge.textContent = text;
  return badge;
}

function makeButton(text, handler) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "badge-button";
  button.textContent = text;
  button.addEventListener("click", event => {
    event.stopPropagation();
    handler();
  });
  return button;
}

function makeValueLine(text) {
  const line = document.createElement("div");
  line.className = "setting-meta";
  line.textContent = text;
  return line;
}

function formatValue(value) {
  if (value === true) return "on";
  if (value === false) return "off";
  if (value === null || value === undefined || value === "") return "(empty)";
  return String(value);
}

function formatBytes(value) {
  const size = Number(value || 0);
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${Math.round(size / 1024 / 1024)} MB`;
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16).replace("T", " ");
  return date.toLocaleString();
}

function renderIndexResult(message) {
  const result = message.result || {};
  el.indexSummary.textContent = `${result.files_parsed || 0} parsed, ${result.symbols_extracted || 0} symbols, ${Math.round(result.total_time_ms || 0)}ms.`;
}

function handleBridgeMessage(message) {
  switch (message.type) {
    case "ready":
      state.runtime = { ...state.runtime, ...message };
      el.runtimeStatus.textContent = "Bridge ready";
      log(`Bridge ready: ${message.kind || message.runtime_root || ""}`);
      renderStatusPills();
      break;
    case "runtime":
      state.runtime = { ...state.runtime, ...message };
      renderStatusPills();
      break;
    case "host.info":
      state.host = message;
      el.workspaceInput.value = message.workspaceRoot || message.cwd || "";
      rememberProject(el.workspaceInput.value);
      renderStatusPills();
      send("initialize", { projectRoot: el.workspaceInput.value });
      send("listSettings");
      send("listPlugins");
      send("listAutomations");
      break;
    case "state":
      renderState(message);
      break;
    case "settings":
      state.settings = message.settings || {};
      renderSettings();
      renderSearch();
      break;
    case "setting.updated":
      log(message.message || `Setting ${message.key} updated`);
      break;
    case "plugins":
      state.plugins = message.plugins || {};
      renderPlugins();
      renderSearch();
      setBusy(false, "Ready");
      break;
    case "remote.release":
      state.plugins = state.plugins || {};
      state.plugins.remote = message.remote || {};
      renderPlugins();
      break;
    case "plugin.inspect":
    case "plugin.build.complete":
    case "plugin.deploy.complete":
    case "plugin.command.complete":
    case "plugin.installed":
      if (message.plugin_id && state.pluginProgress[message.plugin_id]) {
        state.pluginProgress[message.plugin_id] = {
          ...state.pluginProgress[message.plugin_id],
          status: message.type === "plugin.installed" ? "Installed" : "Complete",
          percent: 100
        };
        renderPlugins();
      }
      el.pluginDetail.textContent = JSON.stringify(message, null, 2);
      setBusy(false, "Ready");
      break;
    case "plugin.install.started":
      if (message.plugin_id) {
        state.pluginProgress[message.plugin_id] = {
          status: "Starting download",
          downloaded: 0,
          total: 0,
          percent: 0
        };
        renderPlugins();
      }
      log(`${message.type}: ${message.plugin_id || ""} ${message.asset_name || ""}`);
      break;
    case "plugin.install.progress":
      if (message.plugin_id) {
        state.pluginProgress[message.plugin_id] = {
          status: "Downloading",
          downloaded: message.downloaded || 0,
          total: message.total || 0,
          percent: message.percent || 0
        };
        renderPlugins();
      }
      break;
    case "plugin.build.started":
    case "plugin.command.started":
      log(`${message.type}: ${message.plugin_id || ""} ${message.command || ""}`);
      break;
    case "error":
      if (message.id) setBusy(false, "Ready");
      log(`error: ${message.error || "Unknown error"}`);
      break;
    case "automations":
      state.automations = message.automations || {};
      renderAutomations();
      renderSearch();
      setBusy(false, "Ready");
      break;
    case "automation.saved":
    case "automation.deleted":
    case "automation.toggled":
    case "automation.run.complete":
      el.automationLog.textContent = JSON.stringify(message.result || message, null, 2);
      setBusy(false, "Ready");
      break;
    case "chat.started":
      activateView("chat");
      state.currentAssistantText = "";
      state.pendingAssistantChunk = "";
      state.currentAssistant = addMessage("assistant", "");
      setBusy(true, "Streaming");
      break;
    case "chat.context":
      log(`Context engine initialized: ${message.context_engine_initialized}`);
      break;
    case "chat.chunk":
      if (!state.currentAssistant) state.currentAssistant = addMessage("assistant", "");
      queueAssistantChunk(message.chunk || "");
      break;
    case "chat.thinking":
      log(`thinking: ${message.chunk || ""}`);
      break;
    case "chat.tool":
      log(`tool ${message.event?.event || ""}: ${message.event?.tool || message.event?.name || ""}`);
      break;
    case "chat.complete":
      flushAssistantChunk();
      state.currentAssistant = null;
      setBusy(false, "Ready");
      send("gitStatus", { projectRoot: el.workspaceInput.value });
      break;
    case "index.started":
      el.indexSummary.textContent = "Indexing started.";
      el.indexMeter.style.width = "1%";
      setBusy(true, "Indexing");
      activateTab("context");
      break;
    case "index.progress":
      el.indexSummary.textContent = `${message.stage || "index"}: ${message.current_file || message.message || ""}`;
      el.indexMeter.style.width = `${Math.max(1, Math.min(99, Number(message.percent || 0)))}%`;
      break;
    case "index.complete":
      el.indexMeter.style.width = "100%";
      renderIndexResult(message);
      setBusy(false, "Ready");
      break;
    case "diagnostics":
      activateTab("context");
      renderDiagnostics(message.items || []);
      break;
    case "tools":
      state.tools = message.tools || [];
      renderTools();
      renderSearch();
      break;
    case "git.status":
      renderGit(message.git);
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

document.querySelectorAll(".nav-item").forEach(button => {
  button.addEventListener("click", () => activateView(button.dataset.view));
});

document.querySelectorAll(".tab-button").forEach(button => {
  button.addEventListener("click", () => activateTab(button.dataset.tab));
});

el.settingsNavButton.addEventListener("click", () => activateView("settings"));

el.workspaceApply.addEventListener("click", () => {
  rememberProject(el.workspaceInput.value);
  send("setWorkspace", { projectRoot: el.workspaceInput.value });
  send("listSettings");
  send("listPlugins");
  send("listAutomations");
});

el.modeSelect.addEventListener("change", () => send("setMode", { mode: el.modeSelect.value }));
el.thinkingStyleSelect.addEventListener("change", () => send("setSetting", { key: "thinking_output_style", value: el.thinkingStyleSelect.value }));

el.newSessionButton.addEventListener("click", () => {
  el.messageList.replaceChildren();
  updateEmptyState();
  activateView("chat");
  send("newSession", {});
});

el.clearSessionButton.addEventListener("click", () => {
  if (!confirm("Clear the current chat transcript?")) return;
  el.messageList.replaceChildren();
  updateEmptyState();
  send("clearSession", {});
});

el.indexButton.addEventListener("click", () => {
  activateTab("context");
  send("indexWorkspace", { projectRoot: el.workspaceInput.value });
});

el.diagnosticsButton.addEventListener("click", () => {
  activateTab("context");
  send("diagnostics", {});
});

el.gitRefreshButton.addEventListener("click", () => {
  activateTab("git");
  send("gitStatus", { projectRoot: el.workspaceInput.value });
});

el.pluginRefreshButton.addEventListener("click", () => {
  setBusy(true, "Refreshing plugins");
  send("refreshPlugins");
});
el.remoteRefreshButton.addEventListener("click", () => send("listRemoteReleases", { force: true }));
el.pluginFilter.addEventListener("input", renderPlugins);
el.settingsRefreshButton.addEventListener("click", () => send("listSettings"));
el.sessionSearch.addEventListener("input", renderSessions);
el.toolFilter.addEventListener("input", renderTools);
el.globalSearchInput.addEventListener("input", renderSearch);
el.automationResetButton.addEventListener("click", resetAutomationForm);

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

el.automationForm.addEventListener("submit", event => {
  event.preventDefault();
  send("saveAutomation", {
    id: el.automationId.value,
    name: el.automationName.value,
    prompt: el.automationPrompt.value,
    enabled: el.automationEnabled.checked,
    workspace: el.workspaceInput.value,
    schedule: { type: "interval", interval_minutes: Number(el.automationInterval.value || 60) }
  });
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

document.querySelectorAll(".suggestion").forEach(button => {
  button.addEventListener("click", () => {
    el.messageInput.value = button.textContent.trim();
    el.messageInput.focus();
  });
});

window.chrome.webview.addEventListener("message", event => handleBridgeMessage(event.data || {}));

updateEmptyState();
send("hostInfo");
