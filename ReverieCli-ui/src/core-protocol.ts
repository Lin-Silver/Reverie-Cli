import type { CoreActionName } from "../electron/core-actions";
import type {
  DesktopState,
  ModelSourcesState,
  PluginsState,
  PromptResult,
  RecoveryState,
  SessionListState,
  SessionState,
  SettingsState,
  ToolRecord,
  RatsState,
  WorkspaceState,
} from "./types";

type EmptyPayload = Record<never, never>;
type Envelope<Type extends string, Body extends object> = { id?: string | number | null; type: Type } & Body;

/** Decisions the approval prompt can return. `message` carries a free-form reply to the model. */
export type ApprovalDecision = "once" | "session" | "deny" | "message";

export interface SessionSearchResult extends Record<string, unknown> {
  session_id: string;
  session_name: string;
  message_index: number;
  text: string;
}

export interface WorkspaceMention extends Record<string, unknown> {
  path: string;
  name: string;
  kind: "file" | "symbol" | string;
  score?: number;
  reason?: string;
  summary?: string;
}

interface CoreRequestMap {
  listTools: { payload: { mode: string }; response: Envelope<"tools", { mode: string; tools: ToolRecord[] }> };
  ratsState: { payload: EmptyPayload; response: Envelope<"rats.state", { rats: RatsState }> };
  ratsRegisterProvider: { payload: { providerId: string; executable: string }; response: Envelope<"rats.state", { rats: RatsState }> };
  ratsSetProviderEnabled: { payload: { providerId: string; executable: string; enabled: boolean; permissions: string[] }; response: Envelope<"rats.state", { rats: RatsState }> };
  // Deprecated aliases retained for packaged Desktop/Core compatibility.
  ratsAddEngine: { payload: { executable: string }; response: Envelope<"rats.state", { rats: RatsState }> };
  ratsRemoveRoot: { payload: { root: string }; response: Envelope<"rats.state", { rats: RatsState }> };
  ratsSetEnabled: { payload: { executable: string; enabled: boolean; permissions: string[] }; response: Envelope<"rats.state", { rats: RatsState }> };
  ratsDescribe: { payload: { providerId?: string; serviceId: string; names: string[] }; response: Envelope<"rats.definitions", { provider_id?: string; service_id: string; definitions: Record<string, unknown>[] }> };
  ratsTasks: { payload: { providerId?: string; serviceId?: string }; response: Envelope<"rats.tasks", { provider_id?: string; service_id?: string; tasks: Record<string, unknown>[] }> };
  ratsTaskStatus: { payload: { providerId?: string; serviceId: string; taskId: string; deadlineMs?: number }; response: Envelope<"rats.task.status", { service_id: string; task_id: string; result: Record<string, unknown> }> };
  ratsTaskEvents: { payload: { providerId?: string; serviceId: string; taskId: string; cursor?: number; limit?: number; deadlineMs?: number }; response: Envelope<"rats.task.events", { service_id: string; task_id: string; result: Record<string, unknown> }> };
  ratsTaskCancel: { payload: { providerId?: string; serviceId: string; taskId: string; deadlineMs?: number }; response: Envelope<"rats.task.cancelled", { service_id: string; task_id: string; result: Record<string, unknown> }> };
  ratsTaskLogs: { payload: { providerId?: string; serviceId: string; taskId: string; cursor?: number; limit?: number; deadlineMs?: number }; response: Envelope<"rats.task.logs", { service_id: string; task_id: string; result: Record<string, unknown> }> };
  searchSessions: { payload: { query: string }; response: Envelope<"session.search", { query: string; results: SessionSearchResult[] }> };
  initialize: { payload: { projectRoot: string }; response: Envelope<"state", { state: DesktopState }> };
  getSession: { payload: { sessionId: string }; response: Envelope<"session", { session: SessionState; sessions: SessionListState }> };
  getContextStatus: { payload: EmptyPayload; response: Envelope<"context.status", { context_engine: NonNullable<WorkspaceState["context_engine"]> }> };
  createSession: { payload: { name?: string }; response: Envelope<"session.created", { session: SessionState; sessions: SessionListState }> };
  runPrompt: {
    payload: { prompt: string; sessionId: string; mode: string; stream: boolean; projectRoot?: string; noIndex?: boolean; freshSession?: boolean; source?: string; model?: string; reasoning?: string };
    response: Envelope<"prompt.result", { result: PromptResult; sessions: SessionListState; recovery: RecoveryState }>;
  };
  compactContext: {
    payload: { sessionId: string; focus?: string; projectRoot?: string };
    response: Envelope<"context.compacted", { success: boolean; message: string; session: SessionState; sessions: SessionListState; recovery: RecoveryState; context_engine: NonNullable<WorkspaceState["context_engine"]> }>;
  };
  renameSession: { payload: { sessionId: string; name: string }; response: Envelope<"session.updated", { session: SessionState | null; updated_session?: SessionState | null; sessions: SessionListState }> };
  forkSession: { payload: { sessionId: string; messageCount: number; name?: string }; response: Envelope<"session.updated", { session: SessionState; sessions: SessionListState }> };
  rewindSession: { payload: { sessionId: string; messageCount: number; confirmed: true }; response: Envelope<"session.updated", { session: SessionState; sessions: SessionListState }> };
  deleteSession: { payload: { sessionId: string; confirmed: true }; response: Envelope<"session.updated", { session: SessionState | null; sessions: SessionListState }> };
  deleteSessions: { payload: { sessionIds: string[]; confirmed: true }; response: Envelope<"sessions.deleted", { deleted_session_ids: string[]; session: SessionState | null; sessions: SessionListState }> };
  resolveApproval: { payload: { approvalId: unknown; decision: ApprovalDecision; message?: string }; response: Envelope<"approval.resolved", { approval_id: string; decision: ApprovalDecision }> };
  getModelSources: { payload: EmptyPayload; response: Envelope<"models", { models: ModelSourcesState }> };
  refreshModelSources: { payload: EmptyPayload; response: Envelope<"models", { models: ModelSourcesState }> };
  selectModel: { payload: { source: string; modelId: string; reasoning?: string }; response: Envelope<"model.selected", { selected: Record<string, unknown>; models: ModelSourcesState; workspace: WorkspaceState }> };
  setSetting: { payload: { key: string; value: unknown }; response: Envelope<"setting.updated", { success: boolean; message: string; settings: SettingsState }> };
  setProviderConfig: { payload: { source: string; patch: Record<string, unknown>; clearFields?: string[] }; response: Envelope<"provider.updated", { models: ModelSourcesState; workspace: WorkspaceState }> };
  addStandardModel: { payload: { model: Record<string, unknown> }; response: Envelope<"standard-model.updated", { index: number; models: ModelSourcesState; workspace: WorkspaceState }> };
  deleteStandardModel: { payload: { index: number }; response: Envelope<"standard-model.updated", { index: number; models: ModelSourcesState; workspace: WorkspaceState }> };
  setPluginEnabled: { payload: { pluginId: string; enabled: boolean }; response: Envelope<"plugin.updated", { plugin_id: string; plugins: PluginsState; settings: SettingsState }> };
  setPluginTrust: { payload: { pluginId: string; trusted: boolean }; response: Envelope<"plugin.updated", { plugin_id: string; plugins: PluginsState; settings: SettingsState }> };
  refreshPlugins: { payload: EmptyPayload; response: Envelope<"plugins", { plugins: PluginsState }> };
  indexWorkspace: { payload: EmptyPayload; response: Envelope<"workspace.indexed", { result: Record<string, unknown>; workspace: WorkspaceState }> };
  rollbackCheckpoint: { payload: { checkpointId: string; confirmed: true }; response: Envelope<"rollback.result", { result: Record<string, unknown>; recovery: RecoveryState }> };
  workspaceMentions: { payload: { query: string; limit: number }; response: Envelope<"workspace.mentions", { query: string; items: WorkspaceMention[]; elapsed_ms: number; context_engine: NonNullable<WorkspaceState["context_engine"]> }> };
  deleteProjectData: { payload: { projectRoot: string; confirmed: true }; response: Envelope<"project.deleted", { project_root: string; project_data_dir: string; deleted_sessions: number; deleted: string[] }> };
}

export type CoreAction = keyof CoreRequestMap;
export type CorePayload<Action extends CoreAction> = CoreRequestMap[Action]["payload"];
export type CoreResponse<Action extends CoreAction> = CoreRequestMap[Action]["response"];

type MissingRuntimeAction = Exclude<CoreAction, CoreActionName>;
type MissingTypedAction = Exclude<CoreActionName, CoreAction>;
const coreProtocolIsComplete: [MissingRuntimeAction, MissingTypedAction] extends [never, never] ? true : never = true;
void coreProtocolIsComplete;
