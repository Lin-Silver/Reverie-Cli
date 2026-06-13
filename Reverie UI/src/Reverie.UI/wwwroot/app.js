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
  totals: null,
  plugins: null,
  settings: null,
  currentAssistant: null,
  currentAssistantText: "",
  pendingAssistantChunk: "",
  streamFrame: 0,
  busy: false,
  logs: [],
  selectedSettingKey: "",
  selectedPluginId: "",
  selectedBuiltinSource: "",
  pluginProgress: {},
  theme: loadThemePreference(),
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
  themeSelect: $("themeSelect"),
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
  pluginSummary: $("pluginSummary"),
  totalsSummary: $("totalsSummary"),
  totalsRefreshButton: $("totalsRefreshButton"),
  runRegressionButton: $("runRegressionButton"),
  totalsMetrics: $("totalsMetrics"),
  auditList: $("auditList"),
  regressionList: $("regressionList"),
  hookRuleList: $("hookRuleList"),
  pluginRemoteSummary: $("pluginRemoteSummary"),
  pluginRefreshButton: $("pluginRefreshButton"),
  remoteRefreshButton: $("remoteRefreshButton"),
  pluginFilter: $("pluginFilter"),
  pluginList: $("pluginList"),
  pluginDetail: $("pluginDetail"),
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
  modelSupportsVision: $("modelSupportsVision"),
  modelList: $("modelList"),
  builtinSourceList: $("builtinSourceList"),
  builtinSourceSelect: $("builtinSourceSelect"),
  builtinSourceModel: $("builtinSourceModel"),
  builtinSourceApiKey: $("builtinSourceApiKey"),
  builtinSourceApiUrl: $("builtinSourceApiUrl"),
  builtinSourceEndpoint: $("builtinSourceEndpoint"),
  builtinSourceProject: $("builtinSourceProject"),
  builtinSourceThinking: $("builtinSourceThinking"),
  builtinSourceSave: $("builtinSourceSave"),
  providerSmokeButton: $("providerSmokeButton"),
  providerSmokeStatus: $("providerSmokeStatus"),
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

function loadThemePreference() {
  const fallback = { name: "reverie-dark", theme: "reverie", appearance: "dark" };
  try {
    const saved = localStorage.getItem("reverie.uiTheme") || "";
    if (saved) return normalizeThemePreference(saved);
  } catch {
  }
  return fallback;
}

function normalizeThemePreference(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "reverie-light") {
    return { name: "reverie-light", theme: "reverie", appearance: "light" };
  }
  if (normalized === "classic-dark") {
    return { name: "classic-dark", theme: "classic", appearance: "dark" };
  }
  return { name: "reverie-dark", theme: "reverie", appearance: "dark" };
}

function applyTheme(value = state.theme.name, persist = true) {
  state.theme = normalizeThemePreference(value);
  document.documentElement.dataset.theme = state.theme.theme;
  document.documentElement.dataset.appearance = state.theme.appearance;
  if (el.themeSelect) el.themeSelect.value = state.theme.name;
  if (persist) {
    localStorage.setItem("reverie.uiTheme", state.theme.name);
  }
  send("setHostTheme", {
    theme: state.theme.theme,
    appearance: state.theme.appearance
  });
}

function rememberProject(path) {
  const value = String(path || "").trim();
  if (!value) return;
  state.recentProjects = [value, ...state.recentProjects.filter(item => item !== value)].slice(0, 8);
  localStorage.setItem("reverie.recentProjects", JSON.stringify(state.recentProjects));
  renderProjects();
}

function applyShellLayout() {
  const sidebar = Number(localStorage.getItem("reverie.sidebarWidth") || 260);
  const inspector = Number(localStorage.getItem("reverie.inspectorWidth") || 354);
  document.documentElement.style.setProperty("--sidebar-width", `${Math.max(220, Math.min(420, sidebar))}px`);
  document.documentElement.style.setProperty("--inspector-width", `${Math.max(280, Math.min(560, inspector))}px`);
}

function setupShellResizers() {
  applyShellLayout();
  for (const handle of document.querySelectorAll(".shell-resizer")) {
    handle.addEventListener("pointerdown", event => {
      event.preventDefault();
      handle.setPointerCapture(event.pointerId);
      document.body.classList.add("is-resizing");
      const mode = handle.dataset.resizer;
      const startX = event.clientX;
      const initialSidebar = Number(localStorage.getItem("reverie.sidebarWidth") || 260);
      const initialInspector = Number(localStorage.getItem("reverie.inspectorWidth") || 354);
      const move = moveEvent => {
        if (mode === "sidebar") {
          const width = Math.max(220, Math.min(420, initialSidebar + moveEvent.clientX - startX));
          localStorage.setItem("reverie.sidebarWidth", String(width));
        } else {
          const width = Math.max(280, Math.min(560, initialInspector - (moveEvent.clientX - startX)));
          localStorage.setItem("reverie.inspectorWidth", String(width));
        }
        applyShellLayout();
      };
      const stop = stopEvent => {
        document.body.classList.remove("is-resizing");
        handle.releasePointerCapture(stopEvent.pointerId);
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", stop);
        handle.removeEventListener("pointercancel", stop);
      };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", stop);
      handle.addEventListener("pointercancel", stop);
    });
  }
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

function modelSourceLabel(source) {
  const labels = {
    standard: "Custom Providers",
    geminicli: "Gemini CLI",
    codex: "Codex",
    webgemini: "WebGemini",
    aihubmix: "AIhubMix",
    agnes: "Agnes",
    nvidia: "NVIDIA",
    modelscope: "ModelScope"
  };
  return labels[String(source || "standard").trim().toLowerCase()] || "Custom Providers";
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
  if (name === "totals") send("getTotals");
  if (name === "settings" && !state.settings) send("listSettings");
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
  state.totals = message.totals || state.totals;
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

  const activeSourceLabel = modelSourceLabel(state.config?.active_model_source);
  const customProfileCount = state.config?.models?.length || 0;
  el.configPath.textContent = `${activeSourceLabel} active | ${customProfileCount} custom profile${customProfileCount === 1 ? "" : "s"}`;
  renderStatusPills();
  renderModes();
  el.thinkingStyleSelect.value = state.config?.thinking_output_style || "full";
  renderProjects();
  renderSessions();
  renderModels();
  renderTools();
  renderTotals();
  renderGit(state.git);

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
  setPill(el.configStatusPill, `Profile ${modelSourceLabel(state.config?.active_model_source)}`, state.config ? "ok" : "");
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
      send("getTotals");
      send("listSettings");
      send("listPlugins");
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
  state.sessions = state.sessions || {};
  state.sessions.sessions = (state.sessions.sessions || []).filter(item => item.id !== session.id);
  if (state.sessions.current_session_id === session.id) {
    state.sessions.current_session_id = "";
    state.sessions.current_session_name = "";
    state.sessions.messages = [];
    el.messageList.replaceChildren();
    el.emptyState.hidden = false;
  }
  renderSessions();
  send("deleteSession", { sessionId: session.id });
}

function renderModels() {
  renderBuiltinSources();
  el.modelList.replaceChildren();
  const activeIndex = state.config?.active_model_index ?? -1;
  const models = state.config?.models || [];
  if (!models.length) {
    const item = document.createElement("div");
    item.className = "model-item empty";
    const name = document.createElement("div");
    name.className = "model-name";
    name.textContent = "No custom provider profiles";
    const meta = document.createElement("div");
    meta.className = "model-meta";
    meta.textContent = "Use the form below to add an OpenAI-compatible model, or choose a built-in source above.";
    const actions = document.createElement("div");
    actions.className = "badge-row";
    actions.append(makeBadge("manual profiles"));
    item.append(name, meta, actions);
    el.modelList.append(item);
  }
  for (const model of models) {
    const item = document.createElement("div");
    item.className = `model-item ${model.index === activeIndex ? "active" : ""}`;
    const name = document.createElement("div");
    name.className = "model-name";
    name.textContent = model.model_display_name || model.model || "Unnamed model";
    const meta = document.createElement("div");
    meta.className = "model-meta";
    meta.textContent = `${model.provider || "provider"} | ${model.base_url || "no base url"} | vision ${model.supports_vision ? "on" : "off"}`;
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

function getBuiltinSources() {
  return state.config?.builtin_sources || [];
}

function getBuiltinSource(sourceId = "") {
  const sources = getBuiltinSources();
  const wanted = sourceId || state.selectedBuiltinSource || sources.find(item => item.active)?.source || sources[0]?.source || "modelscope";
  return sources.find(item => item.source === wanted) || sources[0] || null;
}

function getVisibleBuiltinModels(source) {
  const models = source?.models || [];
  const visible = models.filter(model => String(model.visibility || "list").toLowerCase() !== "hide");
  return visible.length ? visible : models;
}

function getSelectedBuiltinModel(source) {
  const selectedId = el.builtinSourceModel?.value || source?.selected_model_id || "";
  return (source?.models || []).find(model => String(model.id || "") === String(selectedId || "")) || null;
}

function appendSelectOption(select, value, label, selectedValue = "") {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label || value || "Not applicable";
  option.selected = String(value || "") === String(selectedValue || "");
  select.append(option);
  return option;
}

function normalizeThinkingChoice(choice) {
  const value = String(choice || "").trim().toLowerCase();
  return value.replaceAll(" ", "");
}

function thinkingChoiceLabel(choice) {
  const labels = {
    minimal: "Minimal",
    low: "Low",
    medium: "Medium",
    high: "High",
    xhigh: "Extra High",
    max: "Max",
    none: "Non-think",
    true: "Thinking ON",
    false: "Thinking OFF"
  };
  return labels[normalizeThinkingChoice(choice)] || String(choice || "").trim() || "Not applicable";
}

function populateBuiltinThinkingOptions(source) {
  el.builtinSourceThinking.replaceChildren();
  const sourceId = String(source?.source || "");
  const selectedModel = getSelectedBuiltinModel(source);
  let choices = [];
  let selected = "";

  if (sourceId === "codex") {
    const catalogChoices = new Map((source.reasoning_choices || []).map(item => [normalizeThinkingChoice(item.id), item]));
    const levels = selectedModel?.reasoning_levels || [];
    choices = levels.map(level => {
      const id = normalizeThinkingChoice(level);
      const catalogItem = catalogChoices.get(id) || {};
      return {
        id,
        label: catalogItem.label || thinkingChoiceLabel(id),
        description: catalogItem.description || ""
      };
    }).filter(item => item.id);
    if (!choices.length) {
      choices = source.reasoning_choices || [];
    }
    selected = normalizeThinkingChoice(source.reasoning_effort || choices[0]?.id || "medium");
  } else if (sourceId === "nvidia") {
    choices = selectedModel?.thinking_options || source.thinking_options || [];
    selected = normalizeThinkingChoice(source.thinking_choice || choices[0]?.id || "");
  }

  const seen = new Set();
  for (const choice of choices) {
    const id = normalizeThinkingChoice(choice.id);
    if (!id || seen.has(id)) continue;
    seen.add(id);
    appendSelectOption(el.builtinSourceThinking, id, choice.label || thinkingChoiceLabel(id), selected);
  }
  if (selected && !seen.has(selected)) {
    appendSelectOption(el.builtinSourceThinking, selected, thinkingChoiceLabel(selected), selected);
  }
  if (!el.builtinSourceThinking.options.length) {
    const option = appendSelectOption(el.builtinSourceThinking, "", "Not applicable", "");
    option.disabled = true;
  }
  el.builtinSourceThinking.disabled = !["codex", "nvidia"].includes(sourceId) || !seen.size;
}

function renderBuiltinSources() {
  const sources = getBuiltinSources();
  if (!state.selectedBuiltinSource) {
    state.selectedBuiltinSource = sources.find(item => item.active)?.source || sources[0]?.source || "modelscope";
  }
  el.builtinSourceList.replaceChildren();
  if (!sources.length) {
    el.builtinSourceList.append(makeValueLine("Built-in model source catalog is not available from the current SDK bridge."));
    fillBuiltinSourceForm(state.selectedBuiltinSource);
    return;
  }
  for (const source of sources) {
    const item = document.createElement("div");
    item.className = `source-item ${source.active ? "active" : ""}`;
    const name = document.createElement("div");
    name.className = "model-name";
    name.textContent = source.label || source.source;
    const meta = document.createElement("div");
    meta.className = "model-meta";
    const selected = source.selected_model_display_name || source.selected_model_id || "no model selected";
    meta.textContent = `${selected} | ${source.credential === "found" ? "credentials ready" : "credentials missing"}`;
    const actions = document.createElement("div");
    actions.className = "badge-row";
    actions.append(
      makeBadge(source.active ? "active" : "idle", source.active ? "ok" : ""),
      makeButton("Edit", () => {
        state.selectedBuiltinSource = source.source;
        fillBuiltinSourceForm(source.source);
      }),
      makeButton("Use", () => send("selectBuiltinSource", { source: source.source }))
    );
    item.append(name, meta, actions);
    el.builtinSourceList.append(item);
  }
  fillBuiltinSourceForm(state.selectedBuiltinSource);
}

function fillBuiltinSourceForm(sourceId = "") {
  const source = getBuiltinSource(sourceId);
  if (!source) return;
  state.selectedBuiltinSource = source.source;
  el.builtinSourceSelect.value = source.source;
  el.builtinSourceModel.replaceChildren();
  for (const model of getVisibleBuiltinModels(source)) {
    const option = document.createElement("option");
    option.value = model.id;
    option.textContent = model.display_name ? `${model.display_name} (${model.id})` : model.id;
    option.selected = model.id === source.selected_model_id;
    el.builtinSourceModel.append(option);
  }
  const hasSelectedModelOption = Array.from(el.builtinSourceModel.options)
    .some(option => option.value === source.selected_model_id);
  if (source.selected_model_id && !hasSelectedModelOption) {
    const option = document.createElement("option");
    option.value = source.selected_model_id;
    option.textContent = source.selected_model_display_name || source.selected_model_id;
    option.selected = true;
    el.builtinSourceModel.prepend(option);
  }
  if (!el.builtinSourceModel.options.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No catalog models available";
    option.disabled = true;
    option.selected = true;
    el.builtinSourceModel.append(option);
  }
  el.builtinSourceApiKey.value = "";
  el.builtinSourceApiKey.disabled = !["aihubmix", "agnes", "nvidia", "modelscope"].includes(source.source);
  el.builtinSourceApiUrl.value = source.api_url || "";
  el.builtinSourceEndpoint.value = source.endpoint || "";
  el.builtinSourceEndpoint.disabled = ["modelscope", "webgemini"].includes(source.source);
  el.builtinSourceProject.value = source.project_id || "";
  el.builtinSourceProject.disabled = source.source !== "geminicli";
  populateBuiltinThinkingOptions(source);
}

function renderProviderSmoke(results = []) {
  if (!results.length) {
    el.providerSmokeStatus.textContent = "Provider smoke test pending.";
    return;
  }
  el.providerSmokeStatus.textContent = results.map(item => {
    const status = item.status || "unknown";
    const detail = item.error_class ? ` ${item.error_class}` : "";
    return `${item.provider}\t${item.model || "-"}\t${status}\t${item.latency_ms || 0}ms${detail}`;
  }).join("\n");
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

function renderTotals() {
  const totals = state.totals || {};
  const usage = totals.usage || {};
  const lifecycle = totals.lifecycle || {};
  const regression = totals.regression || {};
  const recent = lifecycle.recent || [];
  const rules = lifecycle.rules || [];
  const results = regression.results || [];

  if (!el.totalsSummary) return;
  const regressionLabel = regression.passed == null ? "baseline not run" : (regression.passed ? "baseline passing" : "baseline failing");
  el.totalsSummary.textContent = `${usage.workspace_name || totals.workspace?.name || "Workspace"} | ${regressionLabel} | ${Number(lifecycle.events || 0).toLocaleString()} hook events`;

  el.totalsMetrics.replaceChildren();
  const metrics = [
    ["Active work", formatDuration(usage.total_active_seconds || 0), `${Number(usage.total_calls || 0).toLocaleString()} model calls`],
    ["Tokens", `${Number(usage.total_input_tokens || 0).toLocaleString()} in`, `${Number(usage.total_output_tokens || 0).toLocaleString()} out`],
    ["Hooks", Number(lifecycle.events || 0).toLocaleString(), `${Number(lifecycle.denied || 0).toLocaleString()} denied`],
    ["Regression", regression.passed == null ? "Not run" : `${regression.passed_count || 0}/${regression.total || 0}`, `score ${regression.score || 0}`]
  ];
  for (const [label, value, meta] of metrics) {
    const card = document.createElement("article");
    card.className = "metric-card";
    const title = document.createElement("div");
    title.className = "metric-label";
    title.textContent = label;
    const amount = document.createElement("div");
    amount.className = "metric-value";
    amount.textContent = value;
    const hint = document.createElement("div");
    hint.className = "metric-meta";
    hint.textContent = meta;
    card.append(title, amount, hint);
    el.totalsMetrics.append(card);
  }

  el.auditList.replaceChildren();
  if (!recent.length) {
    el.auditList.append(makeValueLine("No lifecycle audit events yet."));
  } else {
    for (const item of recent.slice(-24).reverse()) {
      const row = document.createElement("article");
      row.className = "audit-item";
      const head = document.createElement("div");
      head.className = "audit-head";
      const title = document.createElement("strong");
      title.textContent = item.tool || "runtime";
      const outcome = item.allowed === false ? "denied" : (item.success === false ? "failed" : "ok");
      head.append(title, makeBadge(outcome, outcome === "ok" ? "ok" : "warn"));
      const meta = document.createElement("div");
      meta.className = "audit-meta";
      meta.textContent = `${formatDate(item.timestamp)} | ${item.phase || "event"}${item.reason ? ` | ${item.reason}` : ""}`;
      row.append(head, meta);
      el.auditList.append(row);
    }
  }

  el.regressionList.replaceChildren();
  if (!results.length) {
    el.regressionList.append(makeValueLine("Run the baseline to create deterministic agent behavior results."));
  } else {
    for (const item of results) {
      const row = document.createElement("article");
      row.className = `regression-item ${item.passed ? "passed" : "failed"}`;
      const head = document.createElement("div");
      head.className = "audit-head";
      const title = document.createElement("strong");
      title.textContent = item.title || item.id;
      head.append(title, makeBadge(item.passed ? "pass" : "fail", item.passed ? "ok" : "warn"));
      const meta = document.createElement("div");
      meta.className = "audit-meta";
      meta.textContent = `${item.duration_ms || 0}ms | ${item.detail || ""}`;
      row.append(head, meta);
      el.regressionList.append(row);
    }
  }

  el.hookRuleList.replaceChildren();
  if (!rules.length) {
    el.hookRuleList.append(makeValueLine("No hook rules loaded."));
  } else {
    for (const rule of rules) {
      const row = document.createElement("article");
      row.className = "hook-rule";
      const name = document.createElement("strong");
      name.textContent = rule.id || "hook";
      const meta = document.createElement("div");
      meta.className = "audit-meta";
      meta.textContent = `${rule.phase || "*"} | ${rule.tool || "*"} | ${rule.action || "audit"}${rule.message ? ` | ${rule.message}` : ""}`;
      row.append(name, meta);
      el.hookRuleList.append(row);
    }
  }
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
  el.modelSupportsVision.checked = Boolean(model.supports_vision);
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

function formatDuration(seconds) {
  const total = Math.max(0, Number(seconds || 0));
  if (total < 60) return `${Math.round(total)}s`;
  if (total < 3600) return `${Math.floor(total / 60)}m ${Math.round(total % 60)}s`;
  return `${Math.floor(total / 3600)}h ${Math.round((total % 3600) / 60)}m`;
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
      send("getTotals");
      send("listSettings");
      send("listPlugins");
      break;
    case "state":
      renderState(message);
      break;
    case "settings":
      state.settings = message.settings || {};
      renderSettings();
      break;
    case "totals":
      state.totals = message.totals || {};
      renderTotals();
      setBusy(false, "Ready");
      break;
    case "agent.regression.started":
      setBusy(true, "Running baseline");
      activateView("totals");
      break;
    case "agent.regression.complete":
      state.totals = state.totals || {};
      state.totals.regression = message.summary || {};
      renderTotals();
      setBusy(false, "Ready");
      break;
    case "setting.updated":
      log(message.message || `Setting ${message.key} updated`);
      break;
    case "builtin.source.saved":
    case "builtin.source.selected":
      log(`${message.source || "source"} ${message.type.endsWith("saved") ? "saved" : "selected"}`);
      break;
    case "provider.smoke.started":
      el.providerSmokeStatus.textContent = `Testing ${((message.providers || []).join(", ")) || "providers"}...`;
      setBusy(true, "Testing APIs");
      break;
    case "provider.smoke":
      renderProviderSmoke(message.results || []);
      setBusy(false, "Ready");
      break;
    case "plugins":
      state.plugins = message.plugins || {};
      renderPlugins();
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
      break;
    case "session.deleted":
      log(`Deleted session ${message.session_id || ""}${message.file_exists_after ? " (file still exists)" : ""}`);
      if (message.session_id && state.sessions?.sessions) {
        state.sessions.sessions = state.sessions.sessions.filter(item => item.id !== message.session_id);
        renderSessions();
      }
      setBusy(false, "Ready");
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
el.totalsRefreshButton.addEventListener("click", () => send("getTotals"));
el.runRegressionButton.addEventListener("click", () => {
  setBusy(true, "Running baseline");
  send("runAgentRegression");
});

el.workspaceApply.addEventListener("click", () => {
  rememberProject(el.workspaceInput.value);
  send("setWorkspace", { projectRoot: el.workspaceInput.value });
  send("getTotals");
  send("listSettings");
  send("listPlugins");
});

el.modeSelect.addEventListener("change", () => send("setMode", { mode: el.modeSelect.value }));
el.thinkingStyleSelect.addEventListener("change", () => send("setSetting", { key: "thinking_output_style", value: el.thinkingStyleSelect.value }));
el.themeSelect.addEventListener("change", () => applyTheme(el.themeSelect.value));

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
el.builtinSourceSelect.addEventListener("change", () => {
  state.selectedBuiltinSource = el.builtinSourceSelect.value;
  fillBuiltinSourceForm(state.selectedBuiltinSource);
});
el.builtinSourceModel.addEventListener("change", () => {
  const source = getBuiltinSource(el.builtinSourceSelect.value);
  if (source) populateBuiltinThinkingOptions(source);
});
el.providerSmokeButton.addEventListener("click", () => {
  activateTab("models");
  send("testProviders", {
    providers: getBuiltinSources().map(item => item.source),
    timeout_seconds: 45
  });
});
el.builtinSourceSave.addEventListener("click", () => {
  const source = el.builtinSourceSelect.value;
  send("saveBuiltinSource", {
    source,
    selected_model_id: el.builtinSourceModel.value,
    api_key: el.builtinSourceApiKey.value,
    api_url: el.builtinSourceApiUrl.value,
    endpoint: el.builtinSourceEndpoint.value,
    project_id: el.builtinSourceProject.value,
    reasoning_effort: source === "codex" ? el.builtinSourceThinking.value : "",
    thinking_choice: source === "nvidia" ? el.builtinSourceThinking.value : "",
    activate: true
  });
  el.builtinSourceApiKey.value = "";
});

el.modelForm.addEventListener("submit", event => {
  event.preventDefault();
  send("saveModel", {
    index: Number(el.modelIndex.value),
    model_display_name: el.modelDisplayName.value,
    model: el.modelId.value,
    base_url: el.modelBaseUrl.value,
    api_key: el.modelApiKey.value,
    provider: el.modelProvider.value,
    max_context_tokens: Number(el.modelContextTokens.value || 128000),
    supports_vision: Boolean(el.modelSupportsVision.checked)
  });
  el.modelForm.reset();
  el.modelIndex.value = "-1";
  el.modelContextTokens.value = "128000";
  el.modelSupportsVision.checked = false;
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

document.addEventListener("keydown", event => {
  const key = String(event.key || "").toLowerCase();
  const command = event.ctrlKey || event.metaKey;
  if (command && key === "k") {
    event.preventDefault();
    el.messageInput.focus();
    return;
  }
  if (command && key === "l") {
    event.preventDefault();
    el.workspaceInput.focus();
    el.workspaceInput.select();
    return;
  }
  if (command && event.shiftKey && key === "t") {
    event.preventDefault();
    const themes = ["classic-dark", "reverie-dark", "reverie-light"];
    const next = themes[(themes.indexOf(state.theme.name) + 1) % themes.length];
    applyTheme(next);
    return;
  }
  if (command && ["1", "2", "3", "4"].includes(key)) {
    event.preventDefault();
    activateView({ "1": "chat", "2": "totals", "3": "plugins", "4": "settings" }[key]);
    return;
  }
  if (event.altKey && ["1", "2", "3", "4"].includes(key)) {
    event.preventDefault();
    activateTab({ "1": "context", "2": "models", "3": "tools", "4": "git" }[key]);
  }
});

document.querySelectorAll(".suggestion").forEach(button => {
  button.addEventListener("click", () => {
    el.messageInput.value = button.textContent.trim();
    el.messageInput.focus();
  });
});

window.chrome.webview.addEventListener("message", event => handleBridgeMessage(event.data || {}));

setupShellResizers();
applyTheme(state.theme.name, false);
updateEmptyState();
send("hostInfo");
