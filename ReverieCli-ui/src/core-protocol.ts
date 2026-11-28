import type { CoreActionName } from "../electron/core-actions";
import type { ComposerAttachment } from "../electron/attachments";
import type {McpServerRecord,McpConfigurationState,McpSnapshotState,McpConfigurationRequest,McpControlRequest,McpResourceRequest,McpPromptRequest,ConnectorsState,ConnectorDiscovery,ConnectorRequest,AuthorizeConnectorRequest,CompleteConnectorAuthorizationRequest,CancelConnectorAuthorizationRequest,ConnectorApiKeyRequest,ClearConnectorCredentialsRequest,StartedConnectorAuthorization} from './generated/core-types';
import type {SemanticDevice,SemanticResourcesState,SkillLookupRequest,AddMarketRequest,SetMarketEnabledRequest,MarketRequest,MarketsState,MarketSource,MarketEntry,PreparePluginRequest,ActivatePluginRequest,PluginControlRequest,PluginCandidate} from './generated/core-types';
import type {
  ContextUsage,
  TokenFilters,
  TokenPrice,
  TokenStatisticsData,
  CommandsState,
  CustomProviderRecord,
  DesktopState,
  FileChange,
  ImageModelSourcesState,
  ModelSourcesState,
  ModelSelectionUpdate,
  PluginsState,
  PluginRecord,
  PromptResult,
  ProviderProbe,
  RecoveryState,
  ResolvedViewRef,
  SessionListState,
  SessionState,
  SettingsState,
  SkillDetail,
  SkillsState,
  SubagentRunLog,
  SubagentsState,
  ToolRecord,
  RatsState,
  WorkspaceState,
} from "./types";

type EmptyPayload = Record<never, never>;
type ExtensionContext={projectRoot?:string;sessionId?:string;operation_id?:string;operationId?:string};
type McpManagementFields={mcp:McpConfigurationState;servers:McpServerRecord[];effective_server_ids:string[];operation_id:string};
type ConnectorUpdateEnvelope=Envelope<'connector.updated',{connector:Record<string,unknown>;connectors:ConnectorsState;operation_id:string}>;
type ContextOperationPayload={operationId?:string;expectedRevision?:number;device?:SemanticDevice;threads?:number};
type SemanticEnvelope=Envelope<'context.resources',{semantic:SemanticResourcesState;operation_id?:string;health?:Record<string,unknown>;pending_restart?:boolean}>;
type PluginUpdateEnvelope=Envelope<'plugin.updated',{plugin_id:string;plugins:PluginsState;settings:SettingsState}>;
type PluginPreparedEnvelope=Envelope<'plugin.prepared',{plugin_id:string;candidate:PluginCandidate;plugins:PluginsState}>;
export interface PluginInspection {plugin_id:string;record:PluginRecord;active:PluginCandidate|null;revision:number}
export interface AiOState {assistant_id:'aio';mainline_id:string;enabled:boolean;proactive:boolean;paused:boolean;tasks:Array<{id:string;branch:string;workspace:string;state:string;revision:number}>}
/** Native context accounting is a local estimate, even with exact text tokenization. */
export interface CoreContextUsage extends ContextUsage {
  basis?: string;
  text_exact?: boolean;
  envelope_estimated?: boolean;
  media_estimated?: boolean;
  fallback_reason?: string | null;
  session_id?: string;
  revision?: number;
}
type Envelope<Type extends string, Body extends object> = { id?: string | number | null; type: Type } & Body;
/** Every custom-provider mutation answers with the record it touched plus fresh state. */
type CustomProviderEnvelope = Envelope<
  "custom-provider.updated",
  { provider: CustomProviderRecord | null; models: ModelSourcesState; workspace: WorkspaceState }
>;
type ModelSelectionResult = { workspace: WorkspaceState } & (
  { selection: ModelSelectionUpdate; models?: undefined } | { models: ModelSourcesState; selection?: undefined }
);
type StandardModelTarget = { index: number; profileId?: string } | { profileId: string; index?: number };
/** Pin, unpin, and clear all answer with the outcome plus the whole pin set. */
type SkillPinEnvelope = Envelope<
  "skill.pinned",
  { status: string; name: string; released: string[]; skills: SkillsState }
>;

/** Decisions the approval prompt can return. `message` carries a free-form reply to the model. */
export type ApprovalDecision = "once" | "session" | "project" | "global" | "deny" | "message";

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
  listMcp:{payload:ExtensionContext;response:Envelope<'mcp',McpManagementFields>};
  configureMcp:{payload:McpConfigurationRequest&ExtensionContext;response:Envelope<'mcp.updated',McpManagementFields>};
  removeMcp:{payload:McpControlRequest&ExtensionContext;response:Envelope<'mcp.updated',McpManagementFields>};
  setMcpTrust:{payload:McpControlRequest&ExtensionContext;response:Envelope<'mcp.updated',McpManagementFields>};
  setMcpEnabled:{payload:McpControlRequest&ExtensionContext;response:Envelope<'mcp.updated',McpManagementFields>};
  refreshMcp:{payload:ExtensionContext&{server_id?:string};response:Envelope<'mcp.result',{mcp:McpSnapshotState;operation_id:string;mcp_diagnostics:Record<string,unknown>[];authorization_diagnostics:Record<string,unknown>[]}>};
  readMcpResource:{payload:McpResourceRequest&ExtensionContext;response:Envelope<'mcp.result',{mcp:Record<string,unknown>;operation_id:string}>};
  getMcpPrompt:{payload:McpPromptRequest&ExtensionContext;response:Envelope<'mcp.result',{mcp:Record<string,unknown>;operation_id:string}>};
  listConnectors:{payload:ExtensionContext;response:Envelope<'connectors',{connectors:ConnectorsState;mcp_diagnostics:Record<string,unknown>[];operation_id:string}>};
  discoverConnector:{payload:ConnectorRequest&ExtensionContext;response:Envelope<'connector.updated',{connector:ConnectorDiscovery;connectors:ConnectorsState;operation_id:string}>};
  authorizeConnector:{payload:AuthorizeConnectorRequest&ExtensionContext;response:Envelope<'connector.updated',{connector:StartedConnectorAuthorization;connectors:ConnectorsState;operation_id:string}>};
  completeConnectorAuthorization:{payload:CompleteConnectorAuthorizationRequest&ExtensionContext;response:ConnectorUpdateEnvelope};
  revokeConnector:{payload:ConnectorRequest&ExtensionContext;response:ConnectorUpdateEnvelope};
  clearConnectorCredentials:{payload:ClearConnectorCredentialsRequest&ExtensionContext;response:ConnectorUpdateEnvelope};
  setConnectorApiKey:{payload:ConnectorApiKeyRequest&ExtensionContext;response:ConnectorUpdateEnvelope};
  cancelConnectorAuthorization:{payload:CancelConnectorAuthorizationRequest;response:Envelope<'connector.control',{authorization_id:string;cancelled:boolean}>};
  wstyleCommand: {payload:{args:string;projectRoot?:string;sessionId?:string};response:Envelope<'wstyle.result',{success:boolean;output:string;error:string;data:Record<string,unknown>;session_id:string}>};
  listCommands: {payload:EmptyPayload;response:Envelope<'commands',{commands:CommandsState}>};
  archiveSession: {payload:{projectRoot:string;assistantId?:'aio';sessionId:string;revision:number;archived:boolean};response:Envelope<'sessions',{sessions:SessionListState}>};
  getWorkspaceConfig: {payload:{projectRoot:string};response:Envelope<'workspace.config',{models:ModelSourcesState;workspace:WorkspaceState;settings:SettingsState}>};
  queueConversationRun: {payload:{projectRoot:string;sessionId:string;assistantId?:'aio';runId:string;configuration:Record<string,unknown>;configurationRevision:number;executionRoot?:string};response:Envelope<'conversation.run',{revision:number}>};
  updateConversationRun: {payload:{projectRoot:string;sessionId:string;assistantId?:'aio';runId:string;revision:number;state:string;executionRoot?:string;result?:Record<string,unknown>};response:Envelope<'conversation.run',{revision:number}>};
  listConversationRuns: {payload:{projectRoot:string;sessionId:string;assistantId?:'aio'};response:Envelope<'conversation.runs',{runs:Record<string,unknown>[]}>};
  recoverConversationRuns: {payload:{projectRoot:string};response:Envelope<'conversation.runs',{runs:Record<string,unknown>[]}>};
  aioState: {payload:{assistantId:'aio'};response:Envelope<'aio.state',{aio:AiOState}>};
  aioControl: {payload:{assistantId:'aio';enable?:boolean;changes?:{enabled?:boolean;proactive?:boolean;paused?:boolean}};response:Envelope<'aio.state',{aio:AiOState}>};
  aioObserve: {payload:{assistantId:'aio';excludePids?:number[];idleSeconds?:number};response:Envelope<'aio.observation',{observation:Record<string,unknown>|null}>};
  aioDecision: {payload:{assistantId:'aio';observation:Record<string,unknown>;workspaces:string[];urgent?:boolean};response:Envelope<'aio.decision',{decision:Record<string,unknown>}>};
  aioMessages: {payload:{assistantId:'aio'};response:Envelope<'aio.messages',{messages:Record<string,unknown>[]}>};
  aioPendingSignals: {payload:{assistantId:'aio'};response:Envelope<'aio.signals',{signals:Record<string,unknown>[]}>};
  aioAcknowledgeSignal: {payload:{assistantId:'aio';eventId:string};response:Envelope<'aio.signal-state',{saved:boolean}>};
  aioPendingTasks: {payload:{assistantId:'aio'};response:Envelope<'aio.tasks',{tasks:Record<string,unknown>[]}>};
  aioRecoverHost: {payload:{assistantId:'aio'};response:Envelope<'aio.state',{aio:AiOState}>};
  aioMessageState: {payload:{assistantId:'aio';messageId:string;state:string};response:Envelope<'aio.message-state',{claimed:boolean}>};
  aioReply: {payload:{assistantId:'aio';messageId:string;replyId:string;text:string};response:Envelope<'aio.state',{aio:AiOState}>};
  aioTaskState: {payload:{assistantId:'aio';taskId:string;state:string;revision:number;result?:Record<string,unknown>};response:Envelope<'aio.task-state',{revision:number}>};
  aioMemory: {payload:{assistantId:'aio';memoryId?:string;content?:string};response:Envelope<'aio.memory',{memories:Record<string,unknown>[]}>};
  steerPrompt: { payload: { sessionId: string; projectRoot?: string; prompt: string; attachments?: ComposerAttachment[] }; response: Envelope<"run.control", { state: string; run_id: string; message_id?: string }> };
  stopPrompt: { payload: { sessionId: string; projectRoot?: string; runId?: string }; response: Envelope<"run.control", { state: string; run_id: string }> };
  pausePrompt: { payload: { sessionId: string; projectRoot?: string }; response: Envelope<"run.control", { state: string; run_id: string }> };
  continuePrompt: { payload: { sessionId: string; projectRoot?: string }; response: Envelope<"run.control", { state: string; run_id: string }> };
  listTools: { payload: { mode: string }; response: Envelope<"tools", { mode: string; tools: ToolRecord[] }> };
  listSkills: { payload: EmptyPayload; response: Envelope<"skills", { skills: SkillsState }> };
  listPlugins: { payload: EmptyPayload; response: Envelope<"plugins", { plugins: PluginsState }> };
  ratsState: { payload: EmptyPayload; response: Envelope<"rats.state", { rats: RatsState }> };
  /** The last scan, without walking the discovery roots again. `ratsState` is the rescan. */
  ratsStateCached: { payload: EmptyPayload; response: Envelope<"rats.state", { rats: RatsState }> };
  ratsDefineCustomProvider: { payload: { definition: Record<string, unknown> }; response: Envelope<"rats.state", { rats: RatsState }> };
  ratsRemoveCustomProvider: { payload: { providerId: string }; response: Envelope<"rats.state", { rats: RatsState }> };
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
  initialize: { payload: { projectRoot: string; deferPayloads?: boolean }; response: Envelope<"state", { state: DesktopState; deferred?: boolean }> };
  getState: { payload: EmptyPayload; response: Envelope<"state", { state: DesktopState }> };
  getSession: { payload: { sessionId: string; before?: number; limit?: number; select?: boolean }; response: Envelope<"session", { session: SessionState; sessions: SessionListState; skills?: SkillsState }> };
  getConversationConfig: { payload: { sessionId: string; configuration?: Record<string, unknown>; revision?: number }; response: Envelope<"conversation.config", { configuration: Record<string, unknown>; revision: number; error: string; models: ModelSourcesState; workspace: WorkspaceState; settings: SettingsState }> };
  getFileChanges: { payload: { sessionId: string }; response: Envelope<"file.changes", { session_id: string; changes: FileChange[] }> };
  getContextStatus: { payload: EmptyPayload; response: Envelope<"context.status", { context_engine: NonNullable<WorkspaceState["context_engine"]> }> };
  getSemanticResources:{payload:EmptyPayload;response:SemanticEnvelope};
  installSemanticResources:{payload:ContextOperationPayload&{directory:string;manifestSha256:string};response:SemanticEnvelope};
  selectSemanticResources:{payload:ContextOperationPayload&{manifestSha256:string};response:SemanticEnvelope};
  rollbackSemanticResources:{payload:ContextOperationPayload;response:SemanticEnvelope};
  disableSemanticResources:{payload:ContextOperationPayload;response:SemanticEnvelope};
  removeSemanticResources:{payload:ContextOperationPayload&{manifestSha256:string;confirmed:true};response:SemanticEnvelope};
  warmSemanticResources:{payload:ContextOperationPayload;response:SemanticEnvelope};
  unloadSemanticModels:{payload:ContextOperationPayload;response:SemanticEnvelope};
  indexSemanticWorkspace:{payload:ContextOperationPayload&{force?:boolean};response:Envelope<'context.semantic-indexed',{result:Record<string,unknown>;context_engine:NonNullable<WorkspaceState['context_engine']>;semantic:SemanticResourcesState;operation_id:string}>};
  stopContextOperation:{payload:{operationId:string};response:Envelope<'context.control',{operation_id:string;state:string}>};
  queryContext:{payload:ContextOperationPayload&{query:string;strategy?:'auto'|'basic'|'hybrid';limit?:number;estimatedTokens?:number};response:Envelope<'context.results',{results:Array<{file_path:string;start_line:number;end_line:number;content:string;content_hash:string;revision:number;sources:string[]}>;context_engine:NonNullable<WorkspaceState['context_engine']>;retrieval:Record<string,unknown>;operation_id:string}>};
  getContextUsage: { payload: { sessionId?: string }; response: Envelope<"context.usage", { usage: CoreContextUsage | null }> };
  revealProviderSecret: { payload: { kind: "provider" | "standard" | "custom"; field?: string; source?: string; index?: number; providerId?: string }; response: Envelope<"provider.secret", { value: string }> };
  listApiKeyEnvironmentVariables: { payload: Record<string, never>; response: Envelope<"provider.environment", { names: string[] }> };
  getSubagents: { payload: EmptyPayload; response: Envelope<"subagents", { subagents: SubagentsState }> };
  getSubagentRunLog: { payload: { runId: string }; response: Envelope<"subagent.log", { run_id: string; log: SubagentRunLog }> };
  createSession: { payload: { name?: string }; response: Envelope<"session.created", { session: SessionState; sessions: SessionListState; skills?: SkillsState }> };
  runPrompt: {
    payload: { prompt: string; sessionId: string; mode?: string; configuration?: Record<string, unknown>; stream?: boolean; projectRoot?: string; noIndex?: boolean; freshSession?: boolean; source?: string; model?: string; reasoning?: string; attachments?: ComposerAttachment[]; runId?: string; runType?: "prompt" | "review"; goalContext?: string };
    response: Envelope<"prompt.result", { result: PromptResult; sessions: SessionListState; recovery: RecoveryState }>;
  };
  resumePrompt: {
    payload: { sessionId: string; mode?: string; configuration?: Record<string, unknown>; stream?: boolean; runId?: string };
    response: Envelope<"prompt.result", { result: PromptResult; sessions: SessionListState; recovery: RecoveryState }>;
  };
  compactContext: {
    payload: { sessionId: string; focus?: string; projectRoot?: string; runId?: string };
    response: Envelope<"context.compacted", { success: boolean; message: string; session: SessionState; sessions: SessionListState; recovery: RecoveryState; context_engine: NonNullable<WorkspaceState["context_engine"]>; compaction?: Record<string, unknown>; usage?: CoreContextUsage; session_id?: string; run_id?: string; project_root?: string }>;
  };
  renameSession: { payload: { sessionId: string; name: string }; response: Envelope<"session.updated", { session: SessionState | null; updated_session?: SessionState | null; sessions: SessionListState }> };
  forkSession: { payload: { sessionId: string; messageCount: number; name?: string }; response: Envelope<"session.updated", { session: SessionState; sessions: SessionListState }> };
  rewindSession: { payload: { sessionId: string; messageCount: number; confirmed: true }; response: Envelope<"session.updated", { session: SessionState; sessions: SessionListState }> };
  deleteSession: { payload: { sessionId: string; confirmed: true }; response: Envelope<"session.updated", { session: SessionState | null; sessions: SessionListState }> };
  deleteSessions: { payload: { sessionIds: string[]; confirmed: true }; response: Envelope<"sessions.deleted", { deleted_session_ids: string[]; session: SessionState | null; sessions: SessionListState }> };
  resolveApproval: { payload: { approvalId: unknown; sessionId?: string; projectRoot?: string; decision: ApprovalDecision; message?: string }; response: Envelope<"approval.resolved", { approval_id: string; decision: ApprovalDecision }> };
  resolveUserInput: { payload: { questionId: string; sessionId: string; projectRoot: string; answer?: string; cancelled?: boolean }; response: Envelope<"user.resolved", { question_id: string }> };
  getModelSources: { payload: EmptyPayload; response: Envelope<"models", { models: ModelSourcesState }> };
  getTokenStatistics: { payload: { filters?: TokenFilters; projectRoot?: string }; response: Envelope<"token.statistics", { statistics: TokenStatisticsData }> };
  exportTokenStatistics: { payload: { filters?: TokenFilters; projectRoot?: string }; response: Envelope<"token.csv", { filename: string; content: string }> };
  setTokenPrice: { payload: { modelKey: string; price: TokenPrice }; response: Envelope<"token.price", { model_key: string; price: TokenPrice }> };
  refreshModelSources: { payload: EmptyPayload; response: Envelope<"models", { models: ModelSourcesState }> };
  selectModel: { payload: { source: string; modelId: string; profileId?: string; reasoning?: string; compact?: boolean }; response: Envelope<"model.selected", ModelSelectionResult> };
  getImageModelSources: { payload: EmptyPayload; response: Envelope<"image-models", { imageModels: ImageModelSourcesState }> };
  refreshImageModelSources: { payload: EmptyPayload; response: Envelope<"image-models", { imageModels: ImageModelSourcesState }> };
  selectImageModel: { payload: { source: string; modelId: string }; response: Envelope<"image-model.selected", { selected: Record<string, unknown>; imageModels: ImageModelSourcesState }> };
  setSetting: { payload: { key: string; value: unknown }; response: Envelope<"setting.updated", { success: boolean; message: string; settings: SettingsState; models?: ModelSourcesState; workspace?: WorkspaceState }> };
  listSettings: { payload: EmptyPayload; response: Envelope<"settings", { settings: SettingsState }> };
  setProviderConfig: { payload: { source: string; patch: Record<string, unknown>; clearFields?: string[] }; response: Envelope<"provider.updated", { models: ModelSourcesState; workspace: WorkspaceState }> };
  addStandardModel: { payload: { model: Record<string, unknown> }; response: Envelope<"standard-model.updated", { index: number; profile_id?: string; models: ModelSourcesState; workspace: WorkspaceState }> };
  updateStandardModel: { payload: StandardModelTarget & { model: Record<string, unknown>; clearFields?: string[] }; response: Envelope<"standard-model.updated", { index: number; models: ModelSourcesState; workspace: WorkspaceState }> };
  deleteStandardModel: { payload: StandardModelTarget; response: Envelope<"standard-model.updated", { index: number; models: ModelSourcesState; workspace: WorkspaceState }> };
  addCustomProvider: { payload: { provider: { name: string; base_url: string; api_key: string; api_key_env?: string; format: string } }; response: CustomProviderEnvelope };
  updateCustomProvider: { payload: { providerId: string; patch: Record<string, unknown>; clearFields?: string[] }; response: CustomProviderEnvelope };
  deleteCustomProvider: { payload: { providerId: string }; response: CustomProviderEnvelope };
  refreshCustomProviderModels: { payload: { providerId: string }; response: CustomProviderEnvelope };
  selectCustomProviderModel: { payload: { providerId: string; modelId: string; contextLimit?: number; reasoning?: string; compact?: boolean }; response: Envelope<"custom-provider.updated", ModelSelectionResult> };
  probeProviders: { payload: { keys?: string[] }; response: Envelope<"providers.probed", { probes: ProviderProbe[] }> };
  setPluginEnabled: { payload: PluginControlRequest; response: PluginUpdateEnvelope };
  setPluginTrust: { payload: PluginControlRequest; response: PluginUpdateEnvelope };
  inspectPlugin: {payload:{pluginId:string;projectRoot?:string};response:Envelope<'plugin.inspect',PluginInspection>};
  preparePlugin: {payload:PreparePluginRequest;response:PluginPreparedEnvelope};
  updatePlugin: {payload:{pluginId:string;operation_id?:string;expected_revision?:number};response:PluginPreparedEnvelope};
  activatePlugin: {payload:ActivatePluginRequest;response:PluginUpdateEnvelope};
  rollbackPlugin: {payload:PluginControlRequest;response:PluginUpdateEnvelope};
  removePlugin: {payload:PluginControlRequest;response:PluginUpdateEnvelope};
  setPluginHooks: {payload:PluginControlRequest;response:PluginUpdateEnvelope};
  setPluginAutoUpdate: {payload:PluginControlRequest;response:PluginUpdateEnvelope};
  stopPluginOperation: {payload:{operation_id:string};response:Envelope<'plugin.control',{operation_id:string;cancelled:boolean}>};
  refreshPlugins: { payload: EmptyPayload; response: Envelope<"plugins", { plugins: PluginsState }> };
  refreshSkills: { payload: EmptyPayload; response: Envelope<"skills", { skills: SkillsState }> };
  pinSkill: { payload: { skill: string; draft?:boolean }; response: SkillPinEnvelope };
  unpinSkill: { payload: { skill: string; draft?:boolean }; response: SkillPinEnvelope };
  clearPinnedSkills: { payload: {draft?:boolean}; response: SkillPinEnvelope };
  inspectSkill: { payload: { skill: string }; response: Envelope<"skill.inspect", { record: SkillDetail | null }> };
  lookupSkill: { payload: SkillLookupRequest; response: Envelope<"skill.lookup", { data: Record<string, unknown> }> };
  listMarkets: { payload: EmptyPayload; response: Envelope<"markets", {markets: MarketsState}> };
  addMarket: { payload: AddMarketRequest; response: Envelope<"market.updated", {source: MarketSource; markets: MarketsState}> };
  removeMarket: { payload: MarketRequest; response: Envelope<"market.updated", {market_id: string; markets: MarketsState}> };
  setMarketEnabled: { payload: SetMarketEnabledRequest; response: Envelope<"market.updated", {source: MarketSource; markets: MarketsState}> };
  queryMarket: { payload: MarketRequest; response: Envelope<"market.entries", {source: MarketSource; items: MarketEntry[]; total: number; offset: number; next_offset: number|null; markets: MarketsState}> };
  refreshMarket: { payload: MarketRequest; response: CoreResponse<"queryMarket"> };
  stopMarketRefresh: { payload: {market_id: string}; response: Envelope<"market.control", {market_id: string; cancelled: boolean}> };
  indexWorkspace: { payload: EmptyPayload; response: Envelope<"workspace.indexed", { result: Record<string, unknown>; workspace: WorkspaceState }> };
  rollbackCheckpoint: { payload: { checkpointId: string; confirmed: true }; response: Envelope<"rollback.result", { result: Record<string, unknown>; recovery: RecoveryState }> };
  workspaceMentions: { payload: { query: string; limit: number }; response: Envelope<"workspace.mentions", { query: string; items: WorkspaceMention[]; elapsed_ms: number; context_engine: NonNullable<WorkspaceState["context_engine"]> }> };
  deleteProjectData: { payload: { projectRoot: string; confirmed: true }; response: Envelope<"project.deleted", { project_root: string; project_data_dir: string; deleted_sessions: number; deleted: string[] }> };
  /** RIU P1 view dereference. The renderer receives only the model-safe, path-free
   *  reference: main.ts resolves the kernel's authoritative paths through the host
   *  registrar (see electron/view-resolve.ts) and strips them before this crosses IPC. */
  getView: { payload: { viewId: string; sessionId?: string; revision?: number }; response: Envelope<"view.resolved", { view: ResolvedViewRef }> };
  setViewState: { payload: { viewId: string; sessionId: string; revision: number; interactionId: string; state: Record<string, unknown>; baseRevision: number }; response: Envelope<"view.state", { revision: number }> };
  /** RIU P2 gated tool callback. The renderer never names the tool executor: callViewTool
   *  routes through the kernel's single gated ToolExecutor (cancel -> read-only review ->
   *  security_policy -> approval gate). viewId is the controller's kernel-bound ref, never
   *  frame-supplied; `source` is clamped provenance; a duplicate callId answers `duplicate`
   *  without re-running the write. */
  callViewTool: {
    payload: { viewId: string; sessionId: string; revision: number; interactionId: string; toolName: string; arguments?: Record<string, unknown>; callId: string; source?: string };
    response: Envelope<"view.tool_result", { viewId: string; callId: string; status: string; duplicate?: boolean; output?: string; error?: string; reason?: string; data?: Record<string, unknown>; source?: string }>;
  };
  /** RIU P2 untrusted model-context summary. Stored capped (MAX_VIEW_SUMMARY_BYTES) and tagged
   *  untrusted-user-data, kept separate from the private setViewState display state and never
   *  escalated to a system role. */
  updateViewModelContext: { payload: { viewId: string; sessionId: string; revision: number; interactionId: string; summary: string }; response: Envelope<"view.model_context", { status: string }> };
  releaseView: { payload: { interactionId: string }; response: Envelope<"view.released", Record<string, never>> };
}

export type CoreAction = keyof CoreRequestMap;
export type CorePayload<Action extends CoreAction> = CoreRequestMap[Action]["payload"] & {projectRoot?: string; sessionId?: string; revision?: number;assistantId?:'aio';markRead?:boolean};
export type CoreResponse<Action extends CoreAction> = CoreRequestMap[Action]["response"];

type MissingRuntimeAction = Exclude<CoreAction, CoreActionName>;
type MissingTypedAction = Exclude<CoreActionName, CoreAction>;
const coreProtocolIsComplete: [MissingRuntimeAction, MissingTypedAction] extends [never, never] ? true : never = true;
void coreProtocolIsComplete;
