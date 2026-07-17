export type ViewId = "chat" | "tools" | "plugins" | "recovery" | "settings";

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
  modalities?: {
    live: boolean;
    llm: number;
    tti: number;
    ttv: number;
  };
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
  description: string;
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
