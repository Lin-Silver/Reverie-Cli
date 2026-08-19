export type ViewId = "chat" | "tools" | "rats" | "tasks" | "subagents" | "plugins" | "recovery" | "settings";

export interface SubagentSpecRecord {
  id: string;
  name: string;
  enabled: boolean;
  color: string;
  mode: string;
  created_at: string;
  updated_at: string;
  model_ref: Record<string, unknown>;
}

export interface SubagentRunRecord {
  run_id: string;
  subagent_id: string;
  task_id: string;
  status: string;
  started_at: string;
  ended_at: string;
  summary: string;
  error: string;
  log_path: string;
}

export interface SubagentsState {
  available: boolean;
  agents: SubagentSpecRecord[];
  runs: SubagentRunRecord[];
}

export interface SubagentRunLog {
  run: SubagentRunRecord;
  subagent: Partial<SubagentSpecRecord>;
  model: { model?: string; display_name?: string; provider?: string };
  assignment: string;
  events: Array<Record<string, unknown>>;
}

export type RatsPermission = "read" | "project" | "edit" | "asset" | "ai" | "run" | "build";

export interface RatsCompactTool {
  key: string;
  name: string;
  category: string;
  summary: string;
  permission: string;
  flags: string[];
  schema: string | null;
}

export interface RatsProviderSelection {
  providerId: string;
  executable: string;
  permissions: RatsPermission[];
  discoveryRoot?: string;
}

/** Deprecated compatibility view for pre-provider-neutral packaged Desktop clients. */
export interface RatsEngineSelection {
  executable: string;
  permissions: RatsPermission[];
}

export interface RatsServiceRecord {
  serviceId: string;
  providerId: string;
  serviceKind: string;
  product: string;
  productVersion: string;
  executable: string;
  pid: number;
  endpoint: string;
  protocol: string;
  descriptorPath: string;
  catalogRevision: string;
  nativeToolCount: number;
  startedUtc: string;
  probeLatencyMs: number;
  enabled: boolean;
  connection: "connected" | "available" | "unreachable";
  sessionActive: boolean;
  permissions: RatsPermission[];
  tools: RatsCompactTool[];
  loadedToolNames: string[];
  error: string;
}

export interface RatsProviderRecord {
  providerId: string;
  product: string;
  serviceKind: string;
  label?: string;
  permissions?: RatsPermission[];
  toolTags?: string[];
}

export interface RatsDiagnosticEntry {
  timestampUtc: string;
  level: "info" | "warning" | "error";
  event: string;
  serviceId?: string;
  providerId?: string;
  operation?: string;
  reason?: string;
  path?: string;
  durationMs?: number;
  count?: number;
}

export interface RatsTaskRecord extends Record<string, unknown> {
  provider_id: string;
  service_id: string;
  task_id: string;
  tool: string;
  status?: Record<string, unknown>;
  events?: Array<Record<string, unknown>>;
}

export interface RatsState {
  protocol: "reverie.rtp/1";
  stateVersion?: number;
  settingsVersion?: number;
  statePath: string;
  diagnosticsPath: string;
  discoveryRoots: string[];
  configuredDiscoveryRoots: string[];
  /** Optional while older packaged cores still expose only enabledEngines. */
  enabledProviders?: RatsProviderSelection[];
  enabledEngines?: RatsEngineSelection[];
  supportedProviders: RatsProviderRecord[];
  services: RatsServiceRecord[];
  scanDurationMs: number;
  rejectedDescriptorCount: number;
  diagnostics: RatsDiagnosticEntry[];
  updatedAt: string;
}

export interface CoreInfo {
  version: string;
  interface_version: string;
  release_status: string;
}

export interface WorkspaceState {
  project_root: string;
  project_name: string;
  project_data_dir: string;
  config_path: string;
  mode: string;
  active_source: string;
  active_model: ActiveModel | null;
  index_ready: boolean;
  context_engine?: {
    ready: boolean;
    indexing: boolean;
    files: number;
    symbols: number;
    progress: number;
    label: string;
    automatic_retrieval: boolean;
  };
}

export interface ActiveModel {
  id: string;
  display_name: string;
  provider: string;
}

export interface ReasoningOption {
  id: string;
  label: string;
  description?: string;
}

export interface ReasoningCapability {
  control: "none" | "effort" | "toggle" | "fixed" | "provider-managed" | string;
  options: ReasoningOption[];
  value: string;
}

export interface ModelRecord {
  id: string;
  model?: string;
  display_name: string;
  description: string;
  transport?: string;
  context_length?: number | null;
  max_output_tokens?: number | null;
  vision: boolean;
  tool_calling: boolean;
  thinking: boolean;
  base_url?: string;
  configured?: boolean;
  reasoning: ReasoningCapability;
}

export interface ConfigField {
  key: string;
  label: string;
  kind: "text" | "secret" | "url" | "path" | "choice" | "bool" | "int" | "float";
  choices?: string[];
  optional?: boolean;
  multiline?: boolean;
  min?: number;
  max?: number;
}

export interface CustomProviderFormat {
  id: string;
  label: string;
  description: string;
}

export interface CustomProviderRecord {
  id: string;
  name: string;
  base_url: string;
  models_url: string;
  format: string;
  format_label: string;
  enabled: boolean;
  active: boolean;
  /** Masked for display; the raw key never leaves the core. */
  api_key_masked: string;
  api_key_configured: boolean;
  api_key_source: "config" | "env" | "none";
  selected_model_id: string;
  selected_model_display_name: string;
  max_context_tokens: number;
  max_tokens: number;
  supports_vision: boolean;
  /** Thinking mode is on by default for custom providers. */
  thinking: boolean;
  /** Context limits the user has confirmed, keyed by lowercased model id. */
  model_context_limits: Record<string, number>;
  models_synced_at: number;
  models: CustomProviderModel[];
  /** Present when the record saved but its catalog call failed. */
  sync_error?: string;
}

export interface CustomProviderModel extends ModelRecord {
  /** Tokens the user confirmed for this model, or 0 when never asked. */
  context_limit: number;
  /** True until the user has confirmed this model's context limit once. */
  needs_context_limit: boolean;
  /** What to prefill when asking for the limit. */
  suggested_context_limit: number;
}

export type ProviderProbeStatus =
  | "online"
  | "empty"
  | "unauthorized"
  | "throttled"
  | "offline"
  | "error"
  | "unconfigured"
  | "not-probed";

export interface ProviderProbe {
  key: string;
  name: string;
  kind: "builtin" | "custom";
  source: string;
  provider_id: string;
  format_label: string;
  base_url: string;
  key_state: string;
  key_hint: string;
  active: boolean;
  enabled: boolean;
  probeable: boolean;
  probe_note: string;
  status: ProviderProbeStatus;
  latency_ms: number | null;
  model_count: number;
  detail: string;
  probe: string;
}

export interface ModelSource {
  id: string;
  display_name: string;
  active: boolean;
  selected_model_id: string;
  selected_reasoning: ReasoningCapability;
  models: ModelRecord[];
  config_fields: ConfigField[];
  config?: {
    values: Record<string, unknown>;
    configured_secrets: Record<string, boolean>;
  };
  catalog_live?: boolean;
  modalities?: {
    live: boolean;
    llm: number;
    tti: number;
    ttv: number;
  };
  custom_providers?: CustomProviderRecord[];
  custom_provider_formats?: CustomProviderFormat[];
}

export interface ModelSourcesState {
  active_source: string;
  active_model: ActiveModel | null;
  sources: ModelSource[];
}

export interface SessionInfo {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ToolRecord {
  name: string;
  description: string;
  kind: "built-in" | "mcp" | "runtime-plugin" | string;
  category: string;
  aliases: string[];
  tags: string[];
  traits: string[];
  required: string[];
  properties: string[];
  supported_modes: string[];
}

export interface SessionListState {
  current_session_id: string;
  items: SessionInfo[];
}

export interface SessionMessage {
  role: "system" | "user" | "assistant" | "tool" | string;
  content: unknown;
  name?: string;
  tool_call_id?: string;
  reasoning_content?: string;
  thinking?: unknown;
  reasoning?: unknown;
  analysis?: unknown;
  tool_calls?: Array<{
    id?: string;
    type?: string;
    function?: { name?: string; arguments?: string | Record<string, unknown> };
  }>;
}

export interface SessionState {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  messages: SessionMessage[];
  metadata: Record<string, unknown>;
}

export interface SettingItem {
  name: string;
  key: string;
  kind: string;
  choices?: Array<string | number>;
  labels?: Record<string, string>;
  descriptions?: Record<string, string>;
  description: string;
  command?: string;
  value: unknown;
  min?: number;
  max?: number;
  step?: number;
  trusted?: boolean;
}

export interface SettingsState {
  items: SettingItem[];
  config_path: string;
  workspace_mode: boolean;
}

export interface PluginRecord {
  id: string;
  name: string;
  family: string;
  version: string;
  status: string;
  status_label: string;
  enabled: boolean;
  trusted: boolean;
  protocol_status: string;
  protocol_label: string;
  tool_count: number;
  command_count: number;
  skill_count: number;
  entry_path: string;
  install_dir: string;
}

export interface PluginsState {
  summary: Record<string, unknown>;
  records: PluginRecord[];
}

export interface CommandRecord {
  id: string;
  command: string;
  section: string;
  summary: string;
  detail: string;
  overview: string;
  examples?: string[];
  aliases?: string[];
}

export interface CommandsState {
  sections: string[];
  items: CommandRecord[];
}

export interface CheckpointRecord {
  id: string;
  session_id: string;
  description: string;
  created_at: string;
  message_count: number;
  file_checkpoints: string[];
}

export interface OperationRecord {
  id: string;
  operation_type: string;
  timestamp: string;
  description: string;
  file_operation?: { file_path?: string; operation?: string } | null;
  tool_call?: { tool_name?: string; success?: boolean } | null;
}

export interface RecoveryState {
  summary: Record<string, unknown>;
  checkpoints: CheckpointRecord[];
  operations: OperationRecord[];
}

export interface DesktopState {
  protocol_version: number;
  core: CoreInfo;
  workspace: WorkspaceState;
  models: ModelSourcesState;
  settings: SettingsState;
  sessions: SessionListState;
  plugins: PluginsState;
  commands: CommandsState;
  recovery: RecoveryState;
}

export interface PromptResult {
  success: boolean;
  prompt: string;
  output_text: string;
  thinking_text: string;
  error: string;
  mode: string;
  model_display_name: string;
  provider_label: string;
  session_id: string;
  session_name: string;
  duration_seconds: number;
  ui_events: Array<Record<string, unknown>>;
  activity_events: Array<Record<string, unknown>>;
}

export interface LiveTurn {
  userText: string;
  assistantText: string;
  reasoningText: string;
  events: Array<Record<string, unknown>>;
  error: string;
  startedAt?: number;
}

export interface DesktopPaths {
  projectRoot: string;
  kernelPath: string;
  coreAppRoot: string;
  runtimeRoot: string;
}
