export type JsonRecord = Record<string, unknown>;

export const CORE_RESPONSE_CONTRACT = {
  wstyleCommand: { type: "wstyle.result", required: ["success", "output", "error", "data", "session_id"] },
  listCommands: { type: "commands", required: ["commands"] },
  listTools: { type: "tools", required: ["tools"] },
  listMcp: {type:"mcp",required:["mcp","servers","effective_server_ids"]},
  refreshMcp: {type:"mcp.result",required:["mcp"]},
  configureMcp: {type:"mcp.updated",required:["mcp","servers","effective_server_ids"]},
  removeMcp: {type:"mcp.updated",required:["mcp","servers","effective_server_ids"]},
  setMcpTrust: {type:"mcp.updated",required:["mcp","servers","effective_server_ids"]},
  setMcpEnabled: {type:"mcp.updated",required:["mcp","servers","effective_server_ids"]},
  readMcpResource: {type:"mcp.result",required:["mcp"]},
  getMcpPrompt: {type:"mcp.result",required:["mcp"]},
  listConnectors: {type:"connectors",required:["connectors"]},
  discoverConnector: {type:"connector.updated",required:["connector","connectors"]},
  authorizeConnector: {type:"connector.updated",required:["connector","connectors"]},
  completeConnectorAuthorization: {type:"connector.updated",required:["connector","connectors"]},
  revokeConnector: {type:"connector.updated",required:["connector","connectors"]},
  clearConnectorCredentials: {type:"connector.updated",required:["connector","connectors"]},
  setConnectorApiKey: {type:"connector.updated",required:["connector","connectors"]},
  cancelConnectorAuthorization: {type:"connector.control",required:["authorization_id","cancelled"]},
  listSettings: { type: "settings", required: ["settings"] },
  listSkills: { type: "skills", required: ["skills"] },
  lookupSkill: { type: "skill.lookup", required: ["data"] },
  listMarkets: { type: "markets", required: ["markets"] },
  addMarket: { type: "market.updated", required: ["source", "markets"] },
  removeMarket: { type: "market.updated", required: ["market_id", "markets"] },
  setMarketEnabled: { type: "market.updated", required: ["source", "markets"] },
  queryMarket: { type: "market.entries", required: ["source", "items", "total", "offset", "next_offset", "markets"] },
  refreshMarket: { type: "market.entries", required: ["source", "items", "total", "offset", "next_offset", "markets"] },
  stopMarketRefresh: { type: "market.control", required: ["market_id", "cancelled"] },
  listPlugins: { type: "plugins", required: ["plugins"] },
  ratsState: { type: "rats.state", required: ["rats"] },
  ratsStateCached: { type: "rats.state", required: ["rats"] },
  ratsDefineCustomProvider: { type: "rats.state", required: ["rats"] },
  ratsRemoveCustomProvider: { type: "rats.state", required: ["rats"] },
  ratsRegisterProvider: { type: "rats.state", required: ["rats"] },
  ratsSetProviderEnabled: { type: "rats.state", required: ["rats"] },
  // Deprecated protocol aliases retained until packaged Desktop clients migrate.
  ratsAddEngine: { type: "rats.state", required: ["rats"] },
  ratsRemoveRoot: { type: "rats.state", required: ["rats"] },
  ratsSetEnabled: { type: "rats.state", required: ["rats"] },
  ratsDescribe: { type: "rats.definitions", required: ["definitions"] },
  ratsTasks: { type: "rats.tasks", required: ["tasks"] },
  ratsTaskStatus: { type: "rats.task.status", required: ["result", "task_id"] },
  ratsTaskEvents: { type: "rats.task.events", required: ["result", "task_id"] },
  ratsTaskCancel: { type: "rats.task.cancelled", required: ["result", "task_id"] },
  ratsTaskLogs: { type: "rats.task.logs", required: ["result", "task_id"] },
  searchSessions: { type: "session.search", required: ["results"] },
  initialize: { type: "state", required: ["state"] },
  getState: { type: "state", required: ["state"] },
  getSession: { type: "session", required: ["session", "sessions"] },
  archiveSession: {type:'sessions',required:['sessions']},
  getConversationConfig: { type: "conversation.config", required: ["configuration", "revision", "error", "models", "workspace", "settings"] },
  getWorkspaceConfig: {type:'workspace.config',required:['models','workspace','settings']},
  queueConversationRun: {type:'conversation.run',required:['revision']},
  updateConversationRun: {type:'conversation.run',required:['revision']},
  listConversationRuns: {type:'conversation.runs',required:['runs']},
  recoverConversationRuns: {type:'conversation.runs',required:['runs']},
  aioState: {type:'aio.state',required:['aio']},
  aioControl: {type:'aio.state',required:['aio']},
  aioObserve: {type:'aio.observation',required:['observation']},
  aioDecision: {type:'aio.decision',required:['decision']},
  aioMessages: {type:'aio.messages',required:['messages']},
  aioPendingSignals: {type:'aio.signals',required:['signals']},
  aioAcknowledgeSignal: {type:'aio.signal-state',required:['saved']},
  aioPendingTasks: {type:'aio.tasks',required:['tasks']},
  aioRecoverHost: {type:'aio.state',required:['aio']},
  aioMessageState: {type:'aio.message-state',required:['claimed']},
  aioReply: {type:'aio.state',required:['aio']},
  aioTaskState: {type:'aio.task-state',required:['revision']},
  aioMemory: {type:'aio.memory',required:['memories']},
  getFileChanges: { type: "file.changes", required: ["session_id", "changes"] },
  getContextStatus: { type: "context.status", required: ["context_engine"] },
  getSemanticResources: {type:"context.resources",required:["semantic"]},
  installSemanticResources: {type:"context.resources",required:["semantic"]},
  selectSemanticResources: {type:"context.resources",required:["semantic"]},
  rollbackSemanticResources: {type:"context.resources",required:["semantic"]},
  disableSemanticResources: {type:"context.resources",required:["semantic"]},
  removeSemanticResources: {type:"context.resources",required:["semantic"]},
  warmSemanticResources: {type:"context.resources",required:["semantic"]},
  unloadSemanticModels: {type:"context.resources",required:["semantic"]},
  indexSemanticWorkspace: {type:"context.semantic-indexed",required:["result","context_engine","semantic"]},
  stopContextOperation: {type:"context.control",required:["operation_id","state"]},
  queryContext: {type:"context.results",required:["results","context_engine","retrieval"]},
  getContextUsage: { type: "context.usage", required: ["usage"] },
  getTokenStatistics: { type: "token.statistics", required: ["statistics"] },
  exportTokenStatistics: { type: "token.csv", required: ["filename", "content"] },
  setTokenPrice: { type: "token.price", required: ["model_key", "price"] },
  revealProviderSecret: { type: "provider.secret", required: ["value"] },
  listApiKeyEnvironmentVariables: { type: "provider.environment", required: ["names"] },
  getSubagents: { type: "subagents", required: ["subagents"] },
  getSubagentRunLog: { type: "subagent.log", required: ["run_id", "log"] },
  createSession: { type: "session.created", required: ["session", "sessions"] },
  runPrompt: { type: "prompt.result", required: ["result", "sessions", "recovery"] },
  steerPrompt: { type: "run.control", required: ["state", "run_id"] },
  stopPrompt: { type: "run.control", required: ["state", "run_id"] },
  pausePrompt: { type: "run.control", required: ["state", "run_id"] },
  continuePrompt: { type: "run.control", required: ["state", "run_id"] },
  resumePrompt: { type: "prompt.result", required: ["result", "sessions", "recovery"] },
  compactContext: { type: "context.compacted", required: ["success", "message", "session", "sessions", "recovery", "context_engine"] },
  renameSession: { type: "session.updated", required: ["session", "sessions"] },
  forkSession: { type: "session.updated", required: ["session", "sessions"] },
  rewindSession: { type: "session.updated", required: ["session", "sessions"] },
  deleteSession: { type: "session.updated", required: ["session", "sessions"] },
  deleteSessions: { type: "sessions.deleted", required: ["deleted_session_ids", "session", "sessions"] },
  resolveApproval: { type: "approval.resolved", required: ["approval_id", "decision"] },
  resolveUserInput: { type: "user.resolved", required: ["question_id"] },
  getModelSources: { type: "models", required: ["models"] },
  refreshModelSources: { type: "models", required: ["models"] },
  selectModel: { type: "model.selected", required: ["workspace"] },
  getImageModelSources: { type: "image-models", required: ["imageModels"] },
  refreshImageModelSources: { type: "image-models", required: ["imageModels"] },
  selectImageModel: { type: "image-model.selected", required: ["imageModels", "selected"] },
  setSetting: { type: "setting.updated", required: ["success", "message", "settings"] },
  setProviderConfig: { type: "provider.updated", required: ["models", "workspace"] },
  addStandardModel: { type: "standard-model.updated", required: ["models", "workspace"] },
  updateStandardModel: { type: "standard-model.updated", required: ["models", "workspace"] },
  deleteStandardModel: { type: "standard-model.updated", required: ["models", "workspace"] },
  addCustomProvider: { type: "custom-provider.updated", required: ["models", "workspace"] },
  updateCustomProvider: { type: "custom-provider.updated", required: ["models", "workspace"] },
  deleteCustomProvider: { type: "custom-provider.updated", required: ["models", "workspace"] },
  refreshCustomProviderModels: { type: "custom-provider.updated", required: ["models", "workspace"] },
  selectCustomProviderModel: { type: "custom-provider.updated", required: ["workspace"] },
  probeProviders: { type: "providers.probed", required: ["probes"] },
  setPluginEnabled: { type: "plugin.updated", required: ["plugins", "settings"] },
  setPluginTrust: { type: "plugin.updated", required: ["plugins", "settings"] },
  refreshPlugins: { type: "plugins", required: ["plugins"] },
  inspectPlugin: {type:"plugin.inspect",required:["plugin_id","record","active","revision"]},
  preparePlugin: {type:"plugin.prepared",required:["plugin_id","candidate","plugins"]},
  updatePlugin: {type:"plugin.prepared",required:["plugin_id","candidate","plugins"]},
  activatePlugin: {type:"plugin.updated",required:["plugin_id","plugins","settings"]},
  rollbackPlugin: {type:"plugin.updated",required:["plugin_id","plugins","settings"]},
  removePlugin: {type:"plugin.updated",required:["plugin_id","plugins","settings"]},
  setPluginHooks: {type:"plugin.updated",required:["plugin_id","plugins","settings"]},
  setPluginAutoUpdate: {type:"plugin.updated",required:["plugin_id","plugins","settings"]},
  stopPluginOperation: {type:"plugin.control",required:["operation_id","cancelled"]},
  refreshSkills: { type: "skills", required: ["skills"] },
  pinSkill: { type: "skill.pinned", required: ["status", "name", "skills"] },
  unpinSkill: { type: "skill.pinned", required: ["status", "name", "skills"] },
  clearPinnedSkills: { type: "skill.pinned", required: ["status", "name", "skills"] },
  inspectSkill: { type: "skill.inspect", required: ["record"] },
  indexWorkspace: { type: "workspace.indexed", required: ["result", "workspace"] },
  rollbackCheckpoint: { type: "rollback.result", required: ["result", "recovery"] },
  workspaceMentions: { type: "workspace.mentions", required: ["items", "context_engine"] },
  deleteProjectData: { type: "project.deleted", required: ["project_root", "deleted_sessions"] },
  // RIU P1 view channel. getView's envelope is rebuilt in main.ts from the
  // kernel's authoritative response (the model-safe `view` only; the `resolved`
  // path block is consumed by the host registrar and never forwarded), so the
  // renderer-facing contract requires just `view`. setViewState rides the tail.
  getView: { type: "view.resolved", required: ["view"] },
  setViewState: { type: "view.state", required: ["revision"] },
  // RIU P2 gated interaction. callViewTool funnels through the kernel's single
  // gated ToolExecutor; the envelope always carries the bound viewId/callId and a
  // terminal status (success | error | busy | cancelled). updateViewModelContext
  // stores the untrusted, size-capped model-context summary.
  callViewTool: { type: "view.tool_result", required: ["viewId", "callId", "status"] },
  updateViewModelContext: { type: "view.model_context", required: ["status"] },
  releaseView: { type: "view.released", required: [] },
} as const;

export type CoreActionName = keyof typeof CORE_RESPONSE_CONTRACT;

export function assertCoreAction(value: unknown): CoreActionName {
  if (typeof value !== "string" || !(value in CORE_RESPONSE_CONTRACT)) {
    throw new TypeError(`Unsupported Reverie core action: ${String(value)}`);
  }
  return value as CoreActionName;
}

export function normalizeCorePayload(value: unknown): JsonRecord {
  if (value === undefined) return {};
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError("Reverie core request payload must be an object.");
  }
  return value as JsonRecord;
}

export function assertCoreResponse(action: CoreActionName, value: unknown): JsonRecord {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError(`Reverie core returned a non-object response for ${action}.`);
  }
  const response = value as JsonRecord;
  const contract = CORE_RESPONSE_CONTRACT[action];
  if (response.type !== contract.type) {
    throw new TypeError(
      `Reverie core protocol mismatch for ${action}: expected ${contract.type}, received ${String(response.type)}.`,
    );
  }
  const missing: string[] = contract.required.filter((key) => !(key in response));
  if ((action === "selectModel" || action === "selectCustomProviderModel") && !response.models && !response.selection) {
    missing.push("models or selection");
  }
  if (missing.length) {
    throw new TypeError(`Reverie core response for ${action} is missing: ${missing.join(", ")}.`);
  }
  return response;
}
