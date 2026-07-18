export type JsonRecord = Record<string, unknown>;

export const CORE_RESPONSE_CONTRACT = {
  listTools: { type: "tools", required: ["tools"] },
  searchSessions: { type: "session.search", required: ["results"] },
  initialize: { type: "state", required: ["state"] },
  getSession: { type: "session", required: ["session", "sessions"] },
  getContextStatus: { type: "context.status", required: ["context_engine"] },
  createSession: { type: "session.created", required: ["session", "sessions"] },
  runPrompt: { type: "prompt.result", required: ["result", "sessions", "recovery"] },
  renameSession: { type: "session.updated", required: ["session", "sessions"] },
  forkSession: { type: "session.updated", required: ["session", "sessions"] },
  rewindSession: { type: "session.updated", required: ["session", "sessions"] },
  deleteSession: { type: "session.updated", required: ["session", "sessions"] },
  deleteSessions: { type: "sessions.deleted", required: ["deleted_session_ids", "session", "sessions"] },
  resolveApproval: { type: "approval.resolved", required: ["approval_id", "decision"] },
  selectModel: { type: "model.selected", required: ["models", "workspace"] },
  setSetting: { type: "setting.updated", required: ["success", "message", "settings"] },
  setProviderConfig: { type: "provider.updated", required: ["models", "workspace"] },
  addStandardModel: { type: "standard-model.updated", required: ["models", "workspace"] },
  deleteStandardModel: { type: "standard-model.updated", required: ["models", "workspace"] },
  setPluginEnabled: { type: "plugin.updated", required: ["plugins", "settings"] },
  setPluginTrust: { type: "plugin.updated", required: ["plugins", "settings"] },
  refreshPlugins: { type: "plugins", required: ["plugins"] },
  indexWorkspace: { type: "workspace.indexed", required: ["result", "workspace"] },
  rollbackCheckpoint: { type: "rollback.result", required: ["result", "recovery"] },
  workspaceMentions: { type: "workspace.mentions", required: ["items", "context_engine"] },
  deleteProjectData: { type: "project.deleted", required: ["project_root", "deleted_sessions"] },
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
  const missing = contract.required.filter((key) => !(key in response));
  if (missing.length) {
    throw new TypeError(`Reverie core response for ${action} is missing: ${missing.join(", ")}.`);
  }
  return response;
}
