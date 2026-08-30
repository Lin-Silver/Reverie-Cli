// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { DEFAULT_UI_PREFERENCES, normalizeUiPreferences, type UiPreferences } from "./preferences";
import type { CustomProviderRecord, DesktopState, ModelRecord, ModelSource, ModelSourcesState, ProviderProbe, RatsCustomProviderDefinition, RatsPermission, RatsState, RatsTaskRecord, SessionState } from "./types";

/** One stored manual ("Manual Model") entry, in the core's own config shape. */
type StandardModelConfig = {
  model: string;
  model_display_name: string;
  provider: string;
  base_url: string;
  endpoint?: string;
  api_key?: string;
  max_context_tokens?: number;
  supports_vision?: boolean;
  custom_headers?: Record<string, string>;
};

function customProviderRecord(overrides: Partial<CustomProviderRecord> = {}): CustomProviderRecord {
  return {
    id: "xkiro",
    name: "xkiro",
    base_url: "https://api.xkiro.invalid/v1",
    models_url: "https://api.xkiro.invalid/v1/models",
    format: "openai-chat",
    format_label: "OpenAI Chat Completions",
    enabled: true,
    active: true,
    api_key_masked: "sk-l…9f2c",
    api_key_configured: true,
    api_key_source: "config",
    selected_model_id: "xkiro-pro",
    selected_model_display_name: "xkiro-pro",
    max_context_tokens: 128_000,
    max_tokens: 8_192,
    supports_vision: false,
    thinking: true,
    model_context_limits: { "xkiro-pro": 128_000 },
    models_synced_at: 1_760_000_000,
    models: [{
      id: "xkiro-pro",
      display_name: "xkiro-pro",
      description: "",
      vision: false,
      tool_calling: true,
      thinking: false,
      context_length: 128_000,
      reasoning: { control: "none", options: [], value: "" },
      context_limit: 128_000,
      needs_context_limit: false,
      suggested_context_limit: 128_000,
    }, {
      id: "xkiro-lite",
      display_name: "xkiro-lite",
      description: "",
      vision: false,
      tool_calling: true,
      thinking: false,
      context_length: 32_000,
      reasoning: { control: "none", options: [], value: "" },
      context_limit: 0,
      needs_context_limit: true,
      suggested_context_limit: 32_000,
    }],
    ...overrides,
  };
}

const baseSession: SessionState = {
  id: "session-1",
  name: "Initial session",
  created_at: "2026-07-18T10:00:00Z",
  updated_at: "2026-07-18T10:00:00Z",
  messages: [],
  metadata: {},
};

const searchSession: SessionState = {
  ...baseSession,
  id: "session-2",
  name: "Cache investigation",
  messages: [{ role: "user", content: "Investigate cache invalidation" }],
};

const desktopState: DesktopState = {
  protocol_version: 1,
  core: { version: "2.5.0", interface_version: "1", release_status: "test" },
  workspace: {
    project_root: "C:/workspace",
    project_name: "workspace",
    project_data_dir: "C:/workspace/.reverie",
    config_path: "C:/workspace/.reverie/config.json",
    mode: "reverie",
    active_source: "test-source",
    active_model: { id: "test-model", display_name: "Test Model", provider: "openai-chat" },
    index_ready: true,
    context_engine: {
      ready: true,
      indexing: false,
      files: 42,
      symbols: 128,
      progress: 100,
      label: "Ready",
      automatic_retrieval: true,
    },
  },
  models: {
    active_source: "test-source",
    active_model: { id: "test-model", display_name: "Test Model", provider: "openai-chat" },
    sources: [{
      id: "test-source",
      display_name: "Test Source",
      active: true,
      selected_model_id: "test-model",
      selected_reasoning: { control: "none", options: [], value: "" },
      models: [{
        id: "test-model",
        display_name: "Test Model",
        description: "Test model",
        vision: false,
        tool_calling: true,
        thinking: false,
        reasoning: { control: "none", options: [], value: "" },
      }, {
        id: "thinking-model",
        display_name: "Thinking Model",
        description: "Model with selectable reasoning",
        vision: false,
        tool_calling: true,
        thinking: true,
        reasoning: {
          control: "effort",
          options: [
            { id: "low", label: "Low", description: "Fast reasoning" },
            { id: "high", label: "High", description: "Deep reasoning" },
          ],
          value: "low",
        },
      }],
      config_fields: [],
    }, {
      id: "unlimitedsurf",
      display_name: "UnlimitedSurf",
      active: false,
      selected_model_id: "legacy-model",
      selected_reasoning: { control: "none", options: [], value: "" },
      models: [{
        id: "legacy-model",
        display_name: "Legacy Model",
        description: "Retired source model",
        vision: false,
        tool_calling: false,
        thinking: false,
        reasoning: { control: "none", options: [], value: "" },
      }],
      config_fields: [],
    }],
  },
  settings: {
    items: [{ name: "Permission", key: "permission_level", kind: "choice", description: "", value: "workspace_write" }],
    config_path: "C:/workspace/.reverie/config.json",
    workspace_mode: true,
  },
  sessions: {
    current_session_id: baseSession.id,
    items: [
      { id: baseSession.id, name: baseSession.name, created_at: baseSession.created_at, updated_at: baseSession.updated_at, message_count: 0 },
      { id: searchSession.id, name: searchSession.name, created_at: searchSession.created_at, updated_at: searchSession.updated_at, message_count: 1 },
    ],
  },
  plugins: { summary: {}, records: [] },
  commands: {
    sections: ["Workspace"],
    items: [
      { id: "tools", command: "/tools", section: "Workspace", summary: "Open tools", detail: "", overview: "" },
      { id: "compact", command: "/compact", section: "Workspace", summary: "Compact context", detail: "", overview: "", examples: ["/compact"] },
    ],
  },
  recovery: { summary: {}, checkpoints: [], operations: [] },
};

function installDesktopApi(options: {
  legacyRats?: boolean;
  /** RATS provider definitions the settings file already holds at first paint. */
  ratsCustomProviders?: RatsCustomProviderDefinition[];
  approvalRequest?: Record<string, unknown>;
  ratsStateTransform?: (state: RatsState) => RatsState;
  ratsTasks?: (payload: Record<string, unknown>, cancelled: boolean) => RatsTaskRecord[] | Promise<RatsTaskRecord[]>;
  ratsTaskProgress?: number;
  ratsTaskFailure?: (action: "ratsTaskStatus" | "ratsTaskEvents" | "ratsTaskLogs") => Error | null;
  ratsTaskStatus?: (payload: Record<string, unknown>, cancelled: boolean) => Record<string, unknown>;
  ratsTaskEvents?: (payload: Record<string, unknown>, cancelled: boolean) => Record<string, unknown>;
  ratsTaskLogText?: (payload: Record<string, unknown>) => string;
  refreshedModels?: ModelSourcesState;
  initialState?: DesktopState;
  customProviders?: CustomProviderRecord[];
  standardModels?: StandardModelConfig[];
  settingItems?: DesktopState["settings"]["items"];
  gatePrompt?: boolean;
  gateSession?: boolean;
} = {}) {
  let promptFinished = false;
  let ratsEnabled = false;
  let ratsTaskCancelled = false;
  /** Definitions the harness has accepted, in the order the core would report them. */
  let ratsCustomProviders: RatsCustomProviderDefinition[] = (options.ratsCustomProviders ?? []).map((definition) => ({ ...definition }));
  let providers: CustomProviderRecord[] = (options.customProviders ?? []).map((record) => ({ ...record }));
  let standardModels: StandardModelConfig[] = (options.standardModels ?? []).map((record) => ({ ...record }));
  const customSource = (): ModelSource => ({
    id: "custom",
    display_name: "Custom Provider",
    active: providers.some((record) => record.active),
    selected_model_id: providers.find((record) => record.active)?.selected_model_id ?? "",
    selected_reasoning: { control: "none", options: [], value: "" },
    models: [],
    config_fields: [],
    custom_providers: providers,
    custom_provider_formats: [
      { id: "openai-chat", label: "OpenAI Chat Completions", description: "POST <base>/chat/completions with a Bearer key." },
      { id: "openai-responses", label: "OpenAI Responses", description: "POST <base>/responses with a Bearer key." },
      { id: "anthropic", label: "Anthropic Messages", description: "POST <base>/messages with an x-api-key header." },
    ],
  });
  // Mirrors `_standard_catalog`: the index *is* the model id, and the key itself
  // never crosses the bridge -- only whether one is stored.
  const standardRecord = (record: StandardModelConfig, index: number): ModelRecord => ({
    id: String(index),
    model: record.model,
    display_name: record.model_display_name || record.model,
    description: `Custom ${record.provider} model`,
    transport: record.provider,
    context_length: record.max_context_tokens ?? 128_000,
    vision: Boolean(record.supports_vision),
    tool_calling: true,
    thinking: false,
    base_url: record.base_url,
    endpoint: record.endpoint ?? "",
    configured: Boolean(String(record.api_key ?? "").trim()),
    api_key_configured: Boolean(String(record.api_key ?? "").trim()),
    custom_headers: { ...(record.custom_headers ?? {}) },
    reasoning: { control: "none", options: [], value: "" },
  });
  const standardSource = (): ModelSource => ({
    id: "standard",
    display_name: "Manual Model",
    active: false,
    selected_model_id: "",
    selected_reasoning: { control: "none", options: [], value: "" },
    models: standardModels.map(standardRecord),
    config_fields: [],
  });
  const models = (): ModelSourcesState => {
    // The core activates exactly one source, so a custom provider taking over
    // must stand the built-in ones down -- otherwise the topbar would keep
    // reporting whichever built-in source happens to come first.
    const activeProvider = providers.find((record) => record.active) ?? null;
    const sources = desktopState.models.sources.map((source) => activeProvider ? { ...source, active: false } : source);
    if (options.standardModels) sources.push(standardSource());
    if (options.customProviders) sources.push(customSource());
    return {
      ...desktopState.models,
      active_source: activeProvider ? "custom" : desktopState.models.active_source,
      active_model: activeProvider
        ? {
            id: activeProvider.selected_model_id,
            display_name: activeProvider.selected_model_display_name || activeProvider.selected_model_id,
            provider: activeProvider.format,
          }
        : desktopState.models.active_model,
      sources,
    };
  };
  const customEnvelope = (provider: CustomProviderRecord | null) => ({
    type: "custom-provider.updated",
    provider,
    models: models(),
    workspace: desktopState.workspace,
  });
  const settings = (): DesktopState["settings"] => options.settingItems
    ? { ...desktopState.settings, items: options.settingItems }
    : desktopState.settings;
  const probeFor = (key: string): ProviderProbe => {
    const provider = providers.find((record) => `custom:${record.id}` === key);
    return {
      key,
      name: provider?.name ?? key,
      kind: provider ? "custom" : "builtin",
      source: provider ? "custom" : key,
      provider_id: provider?.id ?? "",
      format_label: provider?.format_label ?? "",
      base_url: provider?.base_url ?? "",
      key_state: "configured",
      key_hint: provider?.api_key_masked ?? "",
      active: provider?.active ?? false,
      enabled: provider?.enabled ?? true,
      probeable: true,
      probe_note: "",
      status: provider?.id === "relay" ? "unauthorized" : "online",
      latency_ms: provider?.id === "relay" ? null : 42,
      model_count: provider?.models.length ?? 0,
      detail: provider?.id === "relay" ? "HTTP 401 from the catalog endpoint." : "2 models",
      probe: "GET /models",
    };
  };
  const eventListeners: Array<(message: { event: unknown }) => void> = [];
  const emitCoreEvent = (event: Record<string, unknown>) => {
    for (const listener of [...eventListeners]) listener({ event });
  };
  // A held prompt keeps the live turn on screen: `sendPrompt` clears it as soon
  // as the result lands, so anything streaming can only be asserted before then.
  let releasePrompt: () => void = () => {};
  const promptGate = new Promise<void>((resolve) => { releasePrompt = resolve; });
  // A held `getSession` is how a slow core is simulated: whatever is on screen
  // while it is held is what the user actually sees when switching sessions.
  // Boot fetches the current session too, so the first call passes through --
  // there is nothing to look at until it lands.
  let sessionFetches = 0;
  let releaseSession: () => void = () => {};
  let sessionGate = new Promise<void>((resolve) => { releaseSession = resolve; });
  const ratsState = (): RatsState => {
    const state: RatsState = ({
    protocol: "reverie.rtp/1",
    stateVersion: 2,
    settingsVersion: 2,
    statePath: "C:/core/.reverie/rats/settings.json",
    diagnosticsPath: "C:/core/.reverie/rats/diagnostics.jsonl",
    discoveryRoots: ["C:/Engine/ReverieLocal/RATS/Services"],
    configuredDiscoveryRoots: ["C:/Engine/ReverieLocal/RATS/Services"],
    enabledProviders: ratsEnabled ? [{ providerId: "reverie.engine", executable: "C:/Engine/reverie.windows.editor.x86_64.exe", permissions: ["read"], discoveryRoot: "C:/Engine/ReverieLocal/RATS/Services" }] : [],
    supportedProviders: [
      { providerId: "reverie.engine", product: "Reverie Engine", serviceKind: "builtin" },
      // The effective registry is the built-ins merged with the definitions and
      // sorted by id, so a definition named earlier in the alphabet really does
      // come first. Anything that picks a default provider positionally is wrong.
      ...ratsCustomProviders.map((definition) => ({
        providerId: definition.providerId,
        product: definition.product,
        serviceKind: definition.serviceKinds[0] ?? "",
        serviceKinds: definition.serviceKinds,
        label: definition.label,
        permissions: definition.permissionClasses as RatsPermission[],
        toolTags: definition.toolTags,
        custom: true,
      })),
    ].sort((left, right) => left.providerId.localeCompare(right.providerId)),
    customProviders: ratsCustomProviders,
    customProviderSchema: "reverie.rats.custom-provider/1",
    customProviderLimit: 16,
    services: [{
      serviceId: "rats-4242-testservice",
      providerId: "reverie.engine",
      serviceKind: "builtin",
      product: "Reverie Engine",
      productVersion: "0.1.dev.custom_build",
      executable: "C:/Engine/reverie.windows.editor.x86_64.exe",
      pid: 4242,
      endpoint: "http://127.0.0.1:17777/rtp",
      protocol: "reverie.rtp/1",
      descriptorPath: "C:/Engine/ReverieLocal/RATS/Services/rats-4242-testservice.json",
      catalogRevision: "catalog",
      nativeToolCount: 35,
      startedUtc: "2026-07-29T12:00:00",
      probeLatencyMs: 7,
      enabled: ratsEnabled,
      connection: ratsEnabled ? "connected" : "available",
      sessionActive: ratsEnabled,
      permissions: ["read"],
      tools: ratsEnabled ? [{ key: "project1", name: "project.status", category: "project", summary: "Read selected project state.", permission: "read", flags: ["main_thread"], schema: "schema" }] : [],
      loadedToolNames: ratsEnabled ? ["project.status"] : [],
      error: "",
    }],
    scanDurationMs: 12,
    rejectedDescriptorCount: 1,
    diagnostics: [
      { timestampUtc: "2026-07-29T12:00:00Z", level: "warning", event: "discovery.rejected", reason: "unsupported_provider", path: "C:/Engine/ReverieLocal/RATS/Services/rats-unknown.json" },
      { timestampUtc: "2026-07-29T12:00:01Z", level: "info", event: "rtp.request", providerId: "reverie.engine", serviceId: "rats-4242-testservice", operation: "hello", durationMs: 7 },
    ],
    updatedAt: "2026-07-29T12:00:00Z",
    });
    const transformedState = options.ratsStateTransform?.(state) ?? state;
    if (!options.legacyRats) return transformedState;
    // A pre-declarative core: no enabledProviders, and no custom-provider layer
    // at all. The page has to hide the define surface rather than offer a form
    // whose submissions that core would refuse.
    const legacy = { ...transformedState, enabledEngines: [{ executable: "C:/Engine/reverie.windows.editor.x86_64.exe", permissions: ["read"] }] } as RatsState & { enabledProviders?: RatsState["enabledProviders"] };
    delete legacy.enabledProviders;
    delete legacy.customProviders;
    delete legacy.customProviderSchema;
    delete legacy.customProviderLimit;
    return legacy;
  };
  const request = vi.fn(async (action: string, payload: Record<string, unknown>) => {
    if (action === "initialize") {
      const state = options.initialState ?? { ...desktopState, models: models(), settings: settings() };
      return { type: "state", state };
    }
    if (action === "addCustomProvider") {
      const input = payload.provider as { name: string; base_url: string; api_key: string; format: string };
      const record = customProviderRecord({
        id: input.name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-"),
        name: input.name.trim(),
        base_url: input.base_url.trim(),
        format: input.format,
        format_label: customSource().custom_provider_formats?.find((item) => item.id === input.format)?.label ?? input.format,
        active: false,
        selected_model_id: "",
        selected_model_display_name: "",
      });
      providers = [...providers, record];
      return customEnvelope(record);
    }
    if (action === "updateCustomProvider") {
      const patch = payload.patch as Partial<CustomProviderRecord>;
      let updated: CustomProviderRecord | null = null;
      providers = providers.map((record) => {
        if (record.id !== payload.providerId) return record;
        updated = { ...record, ...patch };
        return updated;
      });
      return customEnvelope(updated);
    }
    if (action === "deleteCustomProvider") {
      const removed = providers.find((record) => record.id === payload.providerId) ?? null;
      providers = providers.filter((record) => record.id !== payload.providerId);
      return customEnvelope(removed);
    }
    if (action === "refreshCustomProviderModels") {
      const refreshed = providers.find((record) => record.id === payload.providerId) ?? null;
      return customEnvelope(refreshed);
    }
    if (action === "selectCustomProviderModel") {
      let selected: CustomProviderRecord | null = null;
      const modelId = String(payload.modelId);
      const confirmed = payload.contextLimit === undefined ? 0 : Number(payload.contextLimit);
      providers = providers.map((record) => {
        if (record.id !== payload.providerId) return { ...record, active: false };
        // The core stores the confirmed limit, so the model stops asking.
        const limit = confirmed || record.model_context_limits[modelId] || 0;
        selected = {
          ...record,
          active: true,
          selected_model_id: modelId,
          selected_model_display_name: modelId,
          model_context_limits: limit ? { ...record.model_context_limits, [modelId]: limit } : record.model_context_limits,
          models: record.models.map((model) => model.id === modelId && limit
            ? { ...model, context_limit: limit, needs_context_limit: false }
            : model),
        };
        return selected;
      });
      return customEnvelope(selected);
    }
    if (action === "probeProviders") {
      const keys = (payload.keys as string[] | undefined) ?? providers.map((record) => `custom:${record.id}`);
      return { type: "providers.probed", probes: keys.map(probeFor) };
    }
    if (action === "getSession") {
      sessionFetches += 1;
      if (options.gateSession && sessionFetches > 1) await sessionGate;
      const requested = String(payload.sessionId);
      const session = requested === searchSession.id
        ? searchSession
        : promptFinished
          ? { ...baseSession, messages: [{ role: "user", content: "Inspect the cache" }, { role: "assistant", content: "Cache inspection complete" }] }
          : baseSession;
      return { type: "session", session, sessions: desktopState.sessions };
    }
    if (action === "searchSessions") {
      return {
        type: "session.search",
        query: String(payload.query),
        results: [{ session_id: searchSession.id, session_name: searchSession.name, message_index: 0, text: "Investigate cache invalidation" }],
      };
    }
    if (action === "listTools") return { type: "tools", mode: "reverie", tools: [] };
    if (action === "refreshModelSources") return {
      type: "models",
      models: options.refreshedModels ?? models(),
    };
    if (action === "addStandardModel" || action === "updateStandardModel" || action === "deleteStandardModel") {
      const draft = (payload.model ?? {}) as Partial<StandardModelConfig>;
      let index = standardModels.length;
      if (action === "addStandardModel") {
        standardModels = [...standardModels, { provider: "openai-chat", ...draft } as StandardModelConfig];
      } else {
        index = Number(payload.index);
        if (index < 0 || index >= standardModels.length) throw new Error("Standard model index is out of range.");
        if (action === "deleteStandardModel") {
          standardModels = standardModels.filter((_record, position) => position !== index);
        } else {
          // The core merges over the stored record and *skips* an empty key, so a
          // blank API Key field must leave the saved one in place.
          const merged: StandardModelConfig = { ...standardModels[index] };
          for (const [key, value] of Object.entries(draft)) {
            if (key === "api_key" && !String(value ?? "").trim()) continue;
            (merged as Record<string, unknown>)[key] = value;
          }
          standardModels = standardModels.map((record, position) => position === index ? merged : record);
        }
      }
      return { type: "standard-model.updated", index, models: models(), workspace: desktopState.workspace };
    }
    if (action === "ratsState") return { type: "rats.state", rats: ratsState() };
    if (action === "ratsStateCached") {
      // A packaged core older than the cached view has no such action, and the
      // page must still paint from the scan that follows.
      if (options.legacyRats) throw new Error("Unsupported Reverie core action: ratsStateCached");
      return { type: "rats.state", rats: ratsState() };
    }
    if (action === "ratsDefineCustomProvider") {
      const definition = payload.definition as Record<string, unknown>;
      const providerId = String(definition.providerId ?? "");
      // The refusals a user can actually provoke from the form. Each one names
      // the offending field, which is why the page keeps the draft on failure.
      if (providerId === "reverie.engine") throw new Error(`reserved_provider_id: ${providerId}`);
      if (ratsCustomProviders.some((entry) => entry.providerId === providerId)) throw new Error(`duplicate_provider_id: ${providerId}`);
      if (ratsCustomProviders.length >= 16) throw new Error("too_many_custom_providers");
      const discoveryRoot = String(definition.discoveryRoot ?? "ReverieLocal/RATS/Services");
      if (/^([A-Za-z]:|[\\/~])/.test(discoveryRoot)) throw new Error(`invalid_discovery_root: ${discoveryRoot}`);
      const product = String(definition.product ?? "");
      ratsCustomProviders = [...ratsCustomProviders, {
        schema: "reverie.rats.custom-provider/1",
        providerId,
        product,
        label: String(definition.label ?? "") || product,
        serviceKinds: (definition.serviceKinds as string[] | undefined) ?? [],
        permissionClasses: (definition.permissionClasses as string[] | undefined) ?? [],
        toolTags: (definition.toolTags as string[] | undefined) ?? [],
        // The core splits the root itself; the client sends it whole so that an
        // absolute path is refused instead of silently becoming relative.
        discoveryRoot: discoveryRoot.split(/[\\/]+/).filter(Boolean),
        executableIdentity: definition.executableIdentity === "product_name" ? "product_name" : "path",
        executableProductNames: (definition.executableProductNames as string[] | undefined) ?? [],
        executableError: String(definition.executableError ?? ""),
      }];
      return { type: "rats.state", rats: ratsState() };
    }
    if (action === "ratsRemoveCustomProvider") {
      ratsCustomProviders = ratsCustomProviders.filter((entry) => entry.providerId !== payload.providerId);
      return { type: "rats.state", rats: ratsState() };
    }
    if (action === "ratsRegisterProvider" || action === "ratsRemoveRoot") return { type: "rats.state", rats: ratsState() };
    if (action === "ratsSetProviderEnabled") {
      ratsEnabled = payload.enabled === true;
      return { type: "rats.state", rats: ratsState() };
    }
    if (action === "ratsDescribe") {
      return { type: "rats.definitions", service_id: String(payload.serviceId), definitions: [{ name: "project.status", request_schema: { type: "object" }, response_schema: { type: "object" } }] };
    }
    if (action === "ratsTasks") {
      const taskRecords = options.ratsTasks
        ? await options.ratsTasks(payload, ratsTaskCancelled)
        : ratsEnabled
          ? [{ provider_id: "reverie.engine", service_id: "rats-4242-testservice", task_id: "task-e2e-1", tool: "run.play", deadline_msec: 5_000, cursor: 1, status: { running: !ratsTaskCancelled, next_cursor: 2, output: { running: !ratsTaskCancelled } }, events: [{ sequence: 1, type: "task.started", timestamp_utc: "2026-07-29T12:00:02Z", payload: { tool: "run.play" } }] }]
          : [];
      return {
        type: "rats.tasks",
        service_id: String(payload.serviceId ?? ""),
        provider_id: String(payload.providerId ?? ""),
        tasks: taskRecords,
      };
    }
    if (action === "ratsTaskStatus") {
      const failure = options.ratsTaskFailure?.(action);
      if (failure) throw failure;
      const result = options.ratsTaskStatus?.(payload, ratsTaskCancelled)
        ?? { running: !ratsTaskCancelled, next_cursor: 2, output: { running: !ratsTaskCancelled, ...(options.ratsTaskProgress === undefined ? {} : { progress: options.ratsTaskProgress }) } };
      return { type: "rats.task.status", service_id: String(payload.serviceId), task_id: String(payload.taskId), result };
    }
    if (action === "ratsTaskEvents") {
      const failure = options.ratsTaskFailure?.(action);
      if (failure) throw failure;
      const result = options.ratsTaskEvents?.(payload, ratsTaskCancelled)
        ?? { schema: "reverie.rtp.task/1", events: [{ sequence: 1, type: "task.started", timestamp_utc: "2026-07-29T12:00:02Z", payload: { tool: "run.play" } }], next_cursor: 2 };
      return { type: "rats.task.events", service_id: String(payload.serviceId), task_id: String(payload.taskId), result };
    }
    if (action === "ratsTaskLogs") {
      const failure = options.ratsTaskFailure?.(action);
      if (failure) throw failure;
      const text = options.ratsTaskLogText?.(payload) ?? "run.play started\n";
      return { type: "rats.task.logs", service_id: String(payload.serviceId), task_id: String(payload.taskId), result: { text, next_cursor: Number(payload.cursor ?? 0) + text.length } };
    }
    if (action === "ratsTaskCancel") {
      ratsTaskCancelled = true;
      return { type: "rats.task.cancelled", service_id: String(payload.serviceId), task_id: String(payload.taskId), result: { cancelled: true, output: { running: false } } };
    }
    if (action === "getSubagents") {
      return {
        type: "subagents",
        subagents: {
          available: true,
          agents: [{ id: "reviewer", name: "Reviewer", enabled: true, color: "#7c8cff", mode: "reverie", created_at: "2026-08-14T10:00:00Z", updated_at: "2026-08-14T10:00:02Z", model_ref: { display_name: "Review Model" } }],
          runs: [{ run_id: "reviewer-run-1", subagent_id: "reviewer", task_id: "task-1", status: "completed", started_at: "2026-08-14T10:00:00Z", ended_at: "2026-08-14T10:00:02Z", summary: "Validated the selected files.", error: "", log_path: "subagents/reviewer/runs/reviewer-run-1.json" }],
        },
      };
    }
    if (action === "getSubagentRunLog") {
      return {
        type: "subagent.log",
        run_id: String(payload.runId),
        log: {
          run: { run_id: "reviewer-run-1", subagent_id: "reviewer", task_id: "task-1", status: "completed", started_at: "2026-08-14T10:00:00Z", ended_at: "2026-08-14T10:00:02Z", summary: "Validated the selected files.", error: "", log_path: "subagents/reviewer/runs/reviewer-run-1.json" },
          subagent: { id: "reviewer", name: "Reviewer", color: "#7c8cff" },
          model: { model: "review-model", display_name: "Review Model", provider: "request" },
          assignment: "Validate the selected files.",
          events: [{ category: "SubAgent", message: "Validation complete", status: "success", agent_id: "reviewer" }],
        },
      };
    }
    if (action === "selectModel") {
      return {
        type: "model.selected",
        selected: { id: String(payload.modelId) },
        models: models(),
        workspace: desktopState.workspace,
      };
    }
    if (action === "setSetting") {
      const mode = String(payload.value);
      const activeModel = mode === "computer-controller"
        ? { id: "meta/muse-glimmer-30b", display_name: "Muse Glimmer 30B", provider: "openai-chat" }
        : desktopState.models.active_model;
      return {
        type: "setting.updated",
        success: true,
        message: "saved",
        settings: settings(),
        models: { ...models(), active_model: activeModel },
        workspace: { ...desktopState.workspace, mode, active_model: activeModel },
      };
    }
    if (action === "runPrompt") {
      promptFinished = true;
      if (options.approvalRequest) emitCoreEvent(options.approvalRequest);
      if (options.gatePrompt) await promptGate;
      return {
        type: "prompt.result",
        result: {
          success: true,
          prompt: String(payload.prompt),
          output_text: "Cache inspection complete",
          thinking_text: "",
          error: "",
          mode: "reverie",
          model_display_name: "Test Model",
          provider_label: "Test Source",
          session_id: baseSession.id,
          session_name: baseSession.name,
          duration_seconds: 0.1,
          ui_events: [],
          activity_events: [],
        },
        sessions: desktopState.sessions,
        recovery: desktopState.recovery,
      };
    }
    if (action === "resolveApproval") {
      return {
        type: "approval.resolved",
        approval_id: String(payload.approvalId),
        decision: payload.decision as "once" | "session" | "deny" | "message",
      };
    }
    if (action === "compactContext") {
      return {
        type: "context.compacted",
        success: true,
        message: "Context compressed: 1,200 -> 500 tokens",
        session: {
          ...baseSession,
          messages: [{ role: "system", content: "# Continuation Summary\n## Current objective\nKeep GUI parity." }],
        },
        sessions: desktopState.sessions,
        recovery: desktopState.recovery,
        context_engine: desktopState.workspace.context_engine,
      };
    }
    throw new Error(`Unexpected action: ${action}`);
  });
  // Stateful, like the Electron main process: a toggle that reads its own value
  // back from a constant would snap straight back to the default.
  let preferences: UiPreferences = DEFAULT_UI_PREFERENCES;
  const api = {
    request,
    cancel: vi.fn(async () => undefined),
    onEvent: vi.fn((listener: (message: { event: unknown }) => void) => {
      eventListeners.push(listener);
      return () => {
        eventListeners.splice(eventListeners.indexOf(listener), 1);
      };
    }),
    selectWorkspace: vi.fn(async () => null),
    switchWorkspace: vi.fn(async () => null),
    deleteWorkspace: vi.fn(async () => null),
    selectAttachment: vi.fn(async () => null),
    selectCoreData: vi.fn(async () => null),
    paths: vi.fn(async () => ({ projectRoot: "C:/workspace", kernelPath: "C:/reverie.exe", coreAppRoot: "C:/core", runtimeRoot: "C:/runtime" })),
    appearance: vi.fn(async () => ({ theme: "dark" as const, resolved: "dark" as const })),
    setAppearance: vi.fn(async () => ({ theme: "dark" as const, resolved: "dark" as const })),
    onAppearance: vi.fn(() => () => undefined),
    uiPreferences: vi.fn(async () => preferences),
    setUiPreferences: vi.fn(async (patch: Partial<UiPreferences>) => {
      preferences = normalizeUiPreferences({ ...preferences, ...patch });
      return preferences;
    }),
    selectBackground: vi.fn(async () => null),
    clearBackground: vi.fn(async () => DEFAULT_UI_PREFERENCES),
    reveal: vi.fn(async () => true),
    openExternal: vi.fn(async () => true),
    selectRatsProvider: vi.fn(async () => "C:/Engine/reverie.windows.editor.x86_64.exe"),
    selectRatsEngine: vi.fn(async () => "C:/Engine/reverie.windows.editor.x86_64.exe"),
    platform: "win32",
    versions: {},
  };
  Object.defineProperty(window, "reverie", { configurable: true, value: api });
  return {
    api,
    request,
    emitCoreEvent,
    releasePrompt: () => releasePrompt(),
    /** Let the held `getSession` resolve, and arm the gate for the next switch. */
    releaseSession: () => {
      const open = releaseSession;
      sessionGate = new Promise<void>((resolve) => { releaseSession = resolve; });
      open();
    },
  };
}

beforeEach(() => {
  localStorage.clear();
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(() => true),
    })),
  });
});

afterEach(() => {
  vi.useRealTimers();
  cleanup();
  vi.restoreAllMocks();
});

describe("desktop GUI interactions", () => {
  it("opens an accessible command dialog, traps focus, and restores focus on Escape", async () => {
    installDesktopApi();
    const user = userEvent.setup();
    render(<App />);
    const commandButton = await screen.findByRole("button", { name: "命令面板" });
    commandButton.focus();

    await user.keyboard("{Control>}k{/Control}");
    const dialog = await screen.findByRole("dialog", { name: "命令面板" });
    const search = within(dialog).getByRole("textbox", { name: "搜索命令、工具和功能…" });
    expect(document.activeElement).toBe(search);

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "命令面板" })).toBeNull();
    expect(document.activeElement).toBe(commandButton);
  });

  it("collapses and restores the left sidebar with the documented shortcut", async () => {
    installDesktopApi();
    const user = userEvent.setup();
    const { container } = render(<App />);
    await screen.findByRole("button", { name: "命令面板" });
    const shell = container.querySelector(".app-shell");
    expect(shell?.classList.contains("sidebar-collapsed")).toBe(false);

    await user.keyboard("{Control>}b{/Control}");
    expect(shell?.classList.contains("sidebar-collapsed")).toBe(true);
    expect(localStorage.getItem("reverie.layout.sidebar-collapsed")).toBe("true");

    await user.keyboard("{Control>}b{/Control}");
    expect(shell?.classList.contains("sidebar-collapsed")).toBe(false);
  });

  it("searches session content and opens the selected session", async () => {
    const { request } = installDesktopApi();
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "命令面板" });

    await user.keyboard("{Control>}f{/Control}");
    const dialog = await screen.findByRole("dialog", { name: "搜索所有会话内容…" });
    await user.type(within(dialog).getByRole("textbox", { name: "搜索所有会话内容…" }), "cache");
    const result = await within(dialog).findByRole("button", { name: /Cache investigation/ }, { timeout: 1500 });
    await user.click(result);

    await waitFor(() => expect(request).toHaveBeenCalledWith("getSession", { sessionId: searchSession.id }));
    expect(screen.getAllByText("Cache investigation").length).toBeGreaterThan(0);
  });

  it("sends a prompt through the typed bridge and renders the refreshed response", async () => {
    const { request } = installDesktopApi();
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });

    await user.type(composer, "Inspect the cache{Enter}");

    await waitFor(() => expect(request).toHaveBeenCalledWith("runPrompt", {
      prompt: "Inspect the cache",
      sessionId: baseSession.id,
      mode: "reverie",
      stream: true,
    }));
    expect(await screen.findByText("Cache inspection complete")).toBeTruthy();
  });

  it("shows SubAgent runs as a timeline with a separate readable output view", async () => {
    const { request } = installDesktopApi();
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "命令面板" });

    await user.click(screen.getByRole("button", { name: "SubAgents" }));

    expect((await screen.findAllByText("Reviewer")).length).toBeGreaterThan(0);
    expect(await screen.findByText("Validate the selected files.")).toBeTruthy();
    expect(await screen.findByText("Validation complete")).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "输出" }));
    const output = document.querySelector(".subagent-output");
    expect(output).toBeTruthy();
    expect(within(output as HTMLElement).getByText("Validated the selected files.")).toBeTruthy();
    expect(request).toHaveBeenCalledWith("getSubagentRunLog", { runId: "reviewer-run-1" });
  });

  it("sends a personalized approval reply back to the model through the typed bridge", async () => {
    const { request } = installDesktopApi({
      approvalRequest: {
        type: "approval.request",
        approval_id: "approval-1",
        tool: "bash",
        message: "Auto Check rated this call 'high'.",
        risk: "high",
        permission_mode: "auto_check",
        concerns: ["deletes-files"],
        review_source: "reviewer",
        read_only: false,
      },
    });
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });

    await user.type(composer, "Inspect the cache{Enter}");

    const dialog = await screen.findByRole("alertdialog", { name: "工具请求更高权限" });
    expect(within(dialog).getByText("high")).toBeTruthy();
    expect(within(dialog).getByText("deletes-files")).toBeTruthy();

    await user.click(within(dialog).getByRole("button", { name: "个性化回复" }));
    await user.type(within(dialog).getByRole("textbox"), "先解释清楚再执行");
    await user.click(within(dialog).getByRole("button", { name: "发送给模型" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("resolveApproval", {
      approvalId: "approval-1",
      decision: "message",
      message: "先解释清楚再执行",
    }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
  });

  it("denies a strict-mode approval without sending a message", async () => {
    const { request } = installDesktopApi({
      approvalRequest: {
        type: "approval.request",
        approval_id: "approval-2",
        tool: "write_file",
        message: "Strict mode: every tool call needs your explicit approval.",
        risk: "medium",
        permission_mode: "strict",
        concerns: [],
        review_source: "policy",
        read_only: false,
      },
    });
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });

    await user.type(composer, "Inspect the cache{Enter}");

    const dialog = await screen.findByRole("alertdialog", { name: "工具请求更高权限" });
    expect(within(dialog).getByText("Strict 模式：每次工具调用都需要你的批准。")).toBeTruthy();
    expect(within(dialog).queryByText(/审查/)).toBeNull();

    await user.click(within(dialog).getByRole("button", { name: "拒绝" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("resolveApproval", {
      approvalId: "approval-2",
      decision: "deny",
    }));
  });

  it("routes /compact with focus through the dedicated context action", async () => {
    const { request } = installDesktopApi();
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });

    expect(await screen.findByTitle("压缩上下文")).toBeTruthy();
    await user.type(composer, "/compact preserve provider failures{Enter}");

    await waitFor(() => expect(request).toHaveBeenCalledWith("compactContext", {
      sessionId: baseSession.id,
      focus: "preserve provider failures",
      projectRoot: "C:/workspace",
    }));
    expect(request).not.toHaveBeenCalledWith("runPrompt", expect.objectContaining({ prompt: expect.stringContaining("/compact") }));
    expect(await screen.findByText("Context compressed: 1,200 -> 500 tokens")).toBeTruthy();
  });

  it("compacts from the inspector without discarding the current draft", async () => {
    const { request } = installDesktopApi();
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    await user.type(composer, "unfinished draft");

    await user.click(await screen.findByRole("button", { name: "压缩上下文" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("compactContext", {
      sessionId: baseSession.id,
      focus: undefined,
      projectRoot: "C:/workspace",
    }));
    expect((composer as HTMLTextAreaElement).value).toBe("unfinished draft");
  });

  it("asks for model reasoning before switching and hides retired sources", async () => {
    const { request } = installDesktopApi();
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: /Test Model/ }));
    const dialog = await screen.findByRole("dialog", { name: "模型来源" });
    expect(within(dialog).queryByText("UnlimitedSurf")).toBeNull();

    await user.click(within(dialog).getByRole("button", { name: /Thinking Model/ }));
    expect(request).not.toHaveBeenCalledWith("selectModel", expect.anything());
    expect(within(dialog).getByText("选择思考程度")).toBeTruthy();

    await user.click(within(dialog).getByRole("button", { name: /High/ }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("selectModel", {
      source: "test-source",
      modelId: "thinking-model",
      reasoning: "high",
    }));
  });

  it("refreshes the provider catalog when the model picker opens", async () => {
    const refreshedModels: ModelSourcesState = {
      ...desktopState.models,
      sources: [...desktopState.models.sources, {
        id: "sensenova",
        display_name: "SenseNova",
        active: false,
        selected_model_id: "sensenova-6.8-flash-lite",
        selected_reasoning: { control: "provider-managed", options: [], value: "" },
        models: [{
          id: "sensenova-6.8-flash-lite",
          display_name: "SenseNova 6.8 Flash Lite",
          description: "Live model",
          vision: true,
          tool_calling: true,
          thinking: true,
          reasoning: { control: "provider-managed", options: [], value: "" },
        }],
        config_fields: [],
        catalog_live: true,
      }],
    };
    const { request } = installDesktopApi({ refreshedModels });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: /Test Model/ }));
    const dialog = await screen.findByRole("dialog", { name: "模型来源" });
    await waitFor(() => expect(request).toHaveBeenCalledWith("refreshModelSources", {}));
    await user.click(await within(dialog).findByRole("button", { name: /SenseNova/ }));

    expect(await within(dialog).findByRole("button", { name: /SenseNova 6.8 Flash Lite/ })).toBeTruthy();
  });

  it("hides model selection while Computer mode uses its pinned model", async () => {
    installDesktopApi({
      initialState: {
        ...desktopState,
        models: {
          ...desktopState.models,
          active_model: { id: "meta/muse-glimmer-30b", display_name: "Muse Glimmer 30B", provider: "openai-chat" },
        },
        workspace: {
          ...desktopState.workspace,
          mode: "computer-controller",
          active_source: "nvidia",
          active_model: { id: "meta/muse-glimmer-30b", display_name: "Muse Glimmer 30B", provider: "openai-chat" },
        },
      },
    });
    const { container } = render(<App />);

    expect(await screen.findByRole("button", { name: /Computer/ })).toBeTruthy();
    expect(container.querySelector(".model-trigger")).toBeNull();
    expect(screen.getByText("Muse Glimmer 30B")).toBeTruthy();
    expect(screen.queryByRole("dialog", { name: "模型来源" })).toBeNull();
  });

  it("opens the RATS page, explicitly enables a service, and inspects one progressive definition", async () => {
    const { api } = installDesktopApi();
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "RATS" }));
    expect(await screen.findByText("Reverie Engine")).toBeTruthy();
    expect(screen.getByText("RATS 支持多个经过批准的 Reverie/Rilance 提供者；当前主动选择列表中只有 Reverie Engine 已实现并验证。")).toBeTruthy();
    expect(screen.getByText("http://127.0.0.1:17777/rtp")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "登记提供者应用" }));
    await waitFor(() => expect(api.request).toHaveBeenCalledWith("ratsRegisterProvider", {
      providerId: "reverie.engine",
      executable: "C:/Engine/reverie.windows.editor.x86_64.exe",
    }));

    await user.click(screen.getByRole("button", { name: "RTP 日志" }));
    const logPanel = await screen.findByRole("region", { name: "RTP 检索日志" });
    expect(within(logPanel).getByText(/unsupported_provider/)).toBeTruthy();
    expect(within(logPanel).getByText("7 ms")).toBeTruthy();
    await user.click(within(logPanel).getByRole("button", { name: "关闭 RTP 日志" }));
    expect(screen.queryByRole("region", { name: "RTP 检索日志" })).toBeNull();

    await user.click(screen.getByRole("switch"));
    await waitFor(() => expect(api.request).toHaveBeenCalledWith("ratsSetProviderEnabled", {
      providerId: "reverie.engine",
      executable: "C:/Engine/reverie.windows.editor.x86_64.exe",
      enabled: true,
      permissions: ["read"],
    }));
    await user.click(await screen.findByText("project.status"));
    await user.click(screen.getByRole("button", { name: "检查完整定义" }));
    await waitFor(() => expect(api.request).toHaveBeenCalledWith("ratsDescribe", { serviceId: "rats-4242-testservice", names: ["project.status"] }));
    expect(await screen.findByText(/request_schema/)).toBeTruthy();
  });

  it("keeps the RATS page compatible with a legacy core state", async () => {
    installDesktopApi({ legacyRats: true });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "RATS" }));
    expect(await screen.findByText("Reverie Engine")).toBeTruthy();
    expect(screen.queryByText(/display error/i)).toBeNull();
    // That core has no declarative layer, so the page must not offer a form
    // whose submissions it would refuse -- nor report the missing cached view
    // as a failure.
    expect(screen.queryByRole("button", { name: "定义新提供者" })).toBeNull();
    expect(screen.queryByText(/ratsStateCached/)).toBeNull();
  });

  it("defines a custom RATS provider from the GUI, keeps the draft when the core refuses it, then removes it", async () => {
    const { api } = installDesktopApi();
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "RATS" }));
    expect(await screen.findByText("还没有自定义提供者。内置提供者的 ID 是保留的，不能被定义覆盖。")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "定义新提供者" }));
    await user.type(screen.getByLabelText("提供者 ID"), "Acme.ToolHost");
    await user.type(screen.getByLabelText("产品名称"), "Acme Tool Host");
    await user.type(screen.getByLabelText("服务种类"), "editor, headless");
    await user.type(screen.getByLabelText("发现目录（相对）"), "C:/Anywhere/RATS");

    // An absolute root is the core's call to refuse, which is why the client
    // sends the string whole instead of splitting it into segments first.
    await user.click(screen.getByRole("button", { name: "保存定义" }));
    expect(await screen.findByText(/invalid_discovery_root/)).toBeTruthy();
    // The refusal names a field, so the draft has to survive to be correctable.
    expect((screen.getByLabelText("提供者 ID") as HTMLInputElement).value).toBe("Acme.ToolHost");
    // And the 2.5s background poll must not take the message off screen while it
    // is still being read: a poll that succeeded says nothing about this failure.
    const scansAtRefusal = api.request.mock.calls.filter(([action]) => action === "ratsState").length;
    await waitFor(
      () => expect(api.request.mock.calls.filter(([action]) => action === "ratsState").length).toBeGreaterThan(scansAtRefusal),
      { timeout: 6000 },
    );
    expect(screen.getByText(/invalid_discovery_root/)).toBeTruthy();

    await user.clear(screen.getByLabelText("发现目录（相对）"));
    await user.type(screen.getByLabelText("发现目录（相对）"), "Custom/RATS/Services");
    await user.click(screen.getByText("查看将要提交的定义"));
    expect(screen.getByText(/"discoveryRoot": "Custom\/RATS\/Services"/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "保存定义" }));
    await waitFor(() => expect(api.request).toHaveBeenCalledWith("ratsDefineCustomProvider", {
      definition: {
        providerId: "acme.toolhost",
        product: "Acme Tool Host",
        serviceKinds: ["editor", "headless"],
        permissionClasses: ["read"],
        toolTags: [],
        executableIdentity: "path",
        discoveryRoot: "Custom/RATS/Services",
      },
    }));
    // The id now appears in three places at once -- the definition row, the
    // recognized-provider strip, and the header's target picker -- so the row is
    // identified by the one label that is unique to it.
    expect(await screen.findByRole("button", { name: "移除自定义提供者 acme.toolhost" })).toBeTruthy();
    expect(screen.getByText("Acme Tool Host · editor/headless · Custom/RATS/Services · path")).toBeTruthy();
    expect(screen.getByRole("option", { name: "acme.toolhost" })).toBeTruthy();
    // A state update that adds a provider must not move a selection the user is
    // already pointing at, so the button still registers the engine.
    await user.click(screen.getByRole("button", { name: "登记提供者应用" }));
    await waitFor(() => expect(api.request).toHaveBeenCalledWith("ratsRegisterProvider", {
      providerId: "reverie.engine",
      executable: "C:/Engine/reverie.windows.editor.x86_64.exe",
    }));

    await user.click(screen.getByRole("button", { name: "移除自定义提供者 acme.toolhost" }));
    await waitFor(() => expect(api.request).toHaveBeenCalledWith("ratsRemoveCustomProvider", { providerId: "acme.toolhost" }));
    await waitFor(() => expect(screen.queryByText("Acme Tool Host · editor/headless · Custom/RATS/Services · path")).toBeNull());
    expect(screen.queryByRole("button", { name: "移除自定义提供者 acme.toolhost" })).toBeNull();
  });

  it("keeps the built-in as the default register target when a stored definition sorts ahead of it", async () => {
    // The core returns the effective registry sorted by id, so a definition the
    // settings file already holds can be the first entry at first paint -- when
    // nothing is selected yet and the default is being chosen.
    const { api } = installDesktopApi({
      ratsCustomProviders: [{
        schema: "reverie.rats.custom-provider/1",
        providerId: "acme.toolhost",
        product: "Acme Tool Host",
        label: "Acme Tool Host",
        serviceKinds: ["editor"],
        permissionClasses: ["read"],
        toolTags: [],
        discoveryRoot: ["Custom", "RATS", "Services"],
        executableIdentity: "path",
        executableProductNames: [],
        executableError: "",
      }],
    });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "RATS" }));
    const picker = await screen.findByLabelText("选择要登记的提供者") as HTMLSelectElement;
    expect([...picker.options].map((option) => option.value)).toEqual(["acme.toolhost", "reverie.engine"]);
    // Indexing into that list would default to the third-party entry and the
    // register button would then quietly ask for the wrong application.
    expect(picker.value).toBe("reverie.engine");

    await user.click(screen.getByRole("button", { name: "登记提供者应用" }));
    // The file dialog filters by the target's own product name, so choosing the
    // wrong target picks the wrong file long before the core sees the request.
    await waitFor(() => expect(api.selectRatsProvider).toHaveBeenCalledWith("reverie.engine"));
    await waitFor(() => expect(api.request).toHaveBeenCalledWith("ratsRegisterProvider", {
      providerId: "reverie.engine",
      executable: "C:/Engine/reverie.windows.editor.x86_64.exe",
    }));
  });

  it("confirms one discovered service item by item against a fresh scan", async () => {
    installDesktopApi();
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "RATS" }));
    const confirm = await screen.findByRole("button", { name: "确认服务" });
    expect(confirm.getAttribute("aria-expanded")).toBe("false");

    await user.click(confirm);
    // Same six checks, in the same order and under the same names, as the
    // `/rats confirm` verb reports in the terminal.
    const rows = await screen.findAllByText(/descriptor verified|protocol agreed|endpoint reachable|enabled by you|session open|catalog readable/);
    expect(rows.map((row) => row.textContent)).toEqual([
      "descriptor verified", "protocol agreed", "endpoint reachable", "enabled by you", "session open", "catalog readable",
    ]);
    // The service is discovered but not enabled, so the last three fail and the
    // page says so rather than reporting a usable service.
    const verdicts = rows.map((row) => row.parentElement?.className);
    expect(verdicts).toEqual([
      "rats-confirm-row passed", "rats-confirm-row passed", "rats-confirm-row passed",
      "rats-confirm-row failed", "rats-confirm-row failed", "rats-confirm-row failed",
    ]);

    await user.click(screen.getByRole("button", { name: "确认服务" }));
    await waitFor(() => expect(screen.queryByText("descriptor verified")).toBeNull());
  });

  it("aggregates RTP tasks across services and routes details and cancellation through the task", async () => {
    const task: RatsTaskRecord = {
      provider_id: "reverie.second",
      service_id: "rats-second",
      task_id: "task-second-1",
      tool: "run.play",
      deadline_msec: 5_000,
      cursor: 1,
      status: { running: true, next_cursor: 2, output: { running: true } },
      events: [{ sequence: 1, type: "task.started", timestamp_utc: "2026-07-29T12:00:02Z", payload: { tool: "run.play" } }],
    };
    const { api } = installDesktopApi({
      ratsStateTransform: (state) => ({
        ...state,
        services: [
          {
            ...state.services[0],
            providerId: "reverie.empty",
            serviceId: "rats-empty",
            enabled: true,
            connection: "connected",
            sessionActive: true,
          },
          {
            ...state.services[0],
            providerId: task.provider_id,
            serviceId: task.service_id,
            enabled: true,
            connection: "connected",
            sessionActive: true,
          },
        ],
      }),
      ratsTasks: (payload, cancelled) => Object.keys(payload).length === 0
        ? [{ ...task, cancelled, status: { ...task.status, running: !cancelled, output: { running: !cancelled } } }]
        : [],
      ratsTaskProgress: 0.25,
    });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "RTP 任务" }));
    expect(await screen.findByText("RTP 任务详情")).toBeTruthy();
    expect((await screen.findAllByText(task.task_id)).length).toBeGreaterThanOrEqual(2);
    expect(await screen.findByText("25%")).toBeTruthy();
    expect(await screen.findByText("task.started")).toBeTruthy();
    expect(await screen.findByText(/run\.play started/)).toBeTruthy();
    expect(api.request).toHaveBeenCalledWith("ratsTasks", {});
    expect(api.request).toHaveBeenCalledWith("ratsTaskStatus", expect.objectContaining({ providerId: task.provider_id, serviceId: task.service_id, taskId: task.task_id }));
    expect(api.request).toHaveBeenCalledWith("ratsTaskEvents", expect.objectContaining({ providerId: task.provider_id, serviceId: task.service_id, taskId: task.task_id, limit: 32 }));
    expect(api.request).toHaveBeenCalledWith("ratsTaskLogs", expect.objectContaining({ providerId: task.provider_id, serviceId: task.service_id, taskId: task.task_id, limit: 8192 }));

    await user.click(screen.getByRole("button", { name: "取消任务" }));
    await waitFor(() => expect(api.request).toHaveBeenCalledWith("ratsTaskCancel", {
      providerId: task.provider_id,
      serviceId: task.service_id,
      taskId: task.task_id,
      deadlineMs: 5_000,
    }));
    expect((await screen.findAllByText("已取消")).length).toBeGreaterThanOrEqual(2);
  });

  it("drags each side pane to a new width and stores it once the pointer is released", async () => {
    const { api } = installDesktopApi();
    const { container } = render(<App />);
    await screen.findByRole("button", { name: "命令面板" });
    const shell = container.querySelector(".app-shell") as HTMLElement;
    expect(shell.style.getPropertyValue("--sidebar-width")).toBe("268px");

    const sidebarHandle = screen.getByRole("separator", { name: "调整会话侧栏宽度" });
    fireEvent.pointerDown(sidebarHandle, { button: 0, pointerId: 1, clientX: 268 });
    fireEvent.pointerMove(sidebarHandle, { pointerId: 1, clientX: 352 });

    // The drag runs off local state: one preference write per pointer frame would
    // put the persisted reply behind the cursor and fight it.
    await waitFor(() => expect(shell.style.getPropertyValue("--sidebar-width")).toBe("352px"));
    expect(shell.classList.contains("pane-resizing")).toBe(true);
    expect(api.setUiPreferences).not.toHaveBeenCalledWith(expect.objectContaining({ sidebarWidth: expect.anything() }));

    fireEvent.pointerUp(sidebarHandle, { pointerId: 1, clientX: 352 });
    await waitFor(() => expect(api.setUiPreferences).toHaveBeenCalledWith({ sidebarWidth: 352 }));
    expect(shell.classList.contains("pane-resizing")).toBe(false);

    // Anchored to the opposite edge, so the same cursor travel means the inverse
    // width: a shell reporting no geometry under jsdom puts its right edge at 0.
    const inspectorHandle = screen.getByRole("separator", { name: "调整检查器宽度" });
    fireEvent.pointerDown(inspectorHandle, { button: 0, pointerId: 2, clientX: 0 });
    fireEvent.pointerMove(inspectorHandle, { pointerId: 2, clientX: -404 });
    await waitFor(() => expect(shell.style.getPropertyValue("--inspector-width")).toBe("404px"));
    fireEvent.pointerUp(inspectorHandle, { pointerId: 2, clientX: -404 });
    await waitFor(() => expect(api.setUiPreferences).toHaveBeenCalledWith({ inspectorWidth: 404 }));

    // Keyboard and double-click reach the same widths without a pointer.
    fireEvent.keyDown(sidebarHandle, { key: "ArrowRight" });
    await waitFor(() => expect(api.setUiPreferences).toHaveBeenCalledWith({ sidebarWidth: 368 }));
    fireEvent.doubleClick(sidebarHandle);
    await waitFor(() => expect(api.setUiPreferences).toHaveBeenCalledWith({ sidebarWidth: 268 }));
  });

  it("reports every registered RATS provider on the RTP page, live or not", async () => {
    const engineTask: RatsTaskRecord = {
      provider_id: "reverie.engine",
      service_id: "rats-4242-testservice",
      task_id: "task-engine-1",
      tool: "project.scan",
      deadline_msec: 5_000,
      cursor: 0,
      status: { running: true, next_cursor: 1, output: { running: true } },
      events: [],
    };
    const secondTask: RatsTaskRecord = { ...engineTask, provider_id: "reverie.second", service_id: "rats-second", task_id: "task-second-1", tool: "run.play" };
    installDesktopApi({
      ratsStateTransform: (state) => ({
        ...state,
        supportedProviders: [
          ...state.supportedProviders,
          { providerId: "reverie.second", product: "Second Engine", serviceKind: "builtin", custom: true },
          { providerId: "reverie.offline", product: "Offline Engine", serviceKind: "builtin", custom: true },
        ],
        // Authorized in an earlier run and never came back up. The page has to
        // name it anyway, which is the whole point of a per-provider board.
        enabledProviders: [
          ...(state.enabledProviders ?? []),
          { providerId: "reverie.offline", executable: "C:/Offline/engine.exe", permissions: ["read"], discoveryRoot: "C:/Offline/ReverieLocal/RATS/Services" },
        ],
        services: [
          { ...state.services[0], enabled: true, connection: "connected", sessionActive: true },
          { ...state.services[0], providerId: "reverie.second", serviceId: "rats-second", enabled: true, connection: "connected", sessionActive: true },
        ],
      }),
      ratsTasks: (payload) => Object.keys(payload).length === 0 ? [engineTask, secondTask] : [],
    });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "RTP 任务" }));
    const panel = await screen.findByRole("region", { name: "提供者实时状态" });
    const rows = within(panel).getAllByRole("button");
    expect(rows.map((row) => row.querySelector("strong")?.textContent))
      .toEqual(["reverie.engine", "reverie.second", "reverie.offline"]);
    expect(rows.map((row) => row.querySelector(".rats-status")?.textContent))
      .toEqual(["已连接", "已连接", "已授权待启动"]);
    expect(within(panel).getByText("2/3")).toBeTruthy();
    expect(within(rows[2]).getByText("0 个任务")).toBeTruthy();

    // Both providers' tasks arrive on one page, each labelled with its owner.
    expect((await screen.findAllByText("task-engine-1")).length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText("task-second-1")).toBeTruthy();
    expect(screen.getAllByText("reverie.second").length).toBeGreaterThanOrEqual(2);

    await user.click(rows[1]);
    expect(await screen.findByText("仅显示 reverie.second 的任务")).toBeTruthy();
    await waitFor(() => expect(screen.queryByText("task-engine-1")).toBeNull());
    expect((await screen.findAllByText("task-second-1")).length).toBeGreaterThanOrEqual(2);

    await user.click(rows[2]);
    expect(await screen.findByText("该提供者暂无任务")).toBeTruthy();
  });

  it("expands the RTP provider board's contract detail only once it is ticked", async () => {
    const { api } = installDesktopApi({
      ratsCustomProviders: [{
        schema: "reverie.rats.custom-provider/1",
        providerId: "studio.blender",
        product: "Blender",
        label: "Blender Studio",
        serviceKinds: ["dcc"],
        permissionClasses: ["read", "asset"],
        toolTags: ["mesh", "render"],
        discoveryRoot: ["ReverieLocal", "RATS", "Services"],
        executableIdentity: "product_name",
        executableProductNames: ["blender"],
        executableError: "",
      }],
      ratsStateTransform: (state) => ({
        ...state,
        services: [{
          ...state.services[0],
          enabled: true,
          connection: "connected",
          sessionActive: true,
          // The capability-contract fields an older core omits entirely. They
          // are the whole reason the detail pane exists, so the test supplies
          // them here rather than leaning on the base fixture.
          contract: "reverie.rats.capability/1",
          declaredPermissions: ["read", "project", "cinematic"],
          permissionToolCounts: { read: 12, project: 9 },
          features: ["task.cancel", "log.tail"],
          constraints: ["main_thread_only"],
          limits: { max_events: 512 },
          // Deliberately three different numbers: loaded < compact < native is
          // the normal shape once a session is granted fewer classes than the
          // service publishes, and the detail row has to keep them apart.
          tools: [
            { key: "project1", name: "project.status", category: "project", summary: "Read selected project state.", permission: "read", flags: ["main_thread"], schema: "schema" },
            { key: "asset1", name: "asset.import", category: "asset", summary: "Import an asset.", permission: "asset", flags: [], schema: "schema" },
          ],
          loadedToolNames: ["project.status"],
        }],
      }),
    });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "RTP 任务" }));
    const panel = await screen.findByRole("region", { name: "提供者实时状态" });
    // Collapsed by default, so the board stays scannable until asked otherwise.
    expect(within(panel).queryByText("能力契约")).toBeNull();

    const toggle = within(panel).getByRole("checkbox", { name: "显示详细信息" }) as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    await user.click(toggle);
    await waitFor(() => expect(api.setUiPreferences).toHaveBeenCalledWith({ rtpProviderDetails: true }));

    // A live service reports its negotiated contract, not just its endpoint.
    expect(await within(panel).findByText("reverie.rats.capability/1")).toBeTruthy();
    expect(within(panel).getByText("http://127.0.0.1:17777/rtp")).toBeTruthy();
    expect(within(panel).getByText("PID 4242")).toBeTruthy();
    // Loaded / compact / native diverge whenever a session loads fewer tools
    // than the service publishes, which is exactly what this row shows.
    expect(within(panel).getByText("1 / 2 / 35")).toBeTruthy();
    for (const chip of ["cinematic", "task.cancel", "main_thread_only", "read 12", "max_events 512"]) {
      expect(within(panel).getByText(chip)).toBeTruthy();
    }

    // The user-declared provider has no service, so its block is the definition
    // the core stored plus a plain reason the runtime rows are missing.
    expect(within(panel).getByText("ReverieLocal/RATS/Services")).toBeTruthy();
    expect(within(panel).getByText("product_name")).toBeTruthy();
    expect(within(panel).getByText("blender")).toBeTruthy();
    expect(within(panel).getByText("asset")).toBeTruthy();
    expect(within(panel).getByText("尚未在这台机器上发现该提供者的服务。")).toBeTruthy();

    // Rows still filter while expanded: the detail is not a modal state.
    await user.click(within(panel).getAllByRole("button")[0]);
    expect(await screen.findByText("仅显示 reverie.engine 的任务")).toBeTruthy();

    await user.click(toggle);
    await waitFor(() => expect(api.setUiPreferences).toHaveBeenCalledWith({ rtpProviderDetails: false }));
    await waitFor(() => expect(within(panel).queryByText("能力契约")).toBeNull());
  });

  it("keeps slow RTP polling single-flight", async () => {
    let releaseTasks: () => void = () => {};
    const taskGate = new Promise<void>((resolve) => {
      releaseTasks = resolve;
    });
    let activeRequests = 0;
    let maximumConcurrentRequests = 0;
    let taskRequests = 0;
    installDesktopApi({
      ratsStateTransform: (state) => ({
        ...state,
        services: state.services.map((service) => ({
          ...service,
          enabled: true,
          connection: "connected",
          sessionActive: true,
        })),
      }),
      ratsTasks: async () => {
        taskRequests += 1;
        activeRequests += 1;
        maximumConcurrentRequests = Math.max(maximumConcurrentRequests, activeRequests);
        await taskGate;
        activeRequests -= 1;
        return [];
      },
    });
    const { unmount } = render(<App />);
    const tasksButton = await screen.findByRole("button", { name: "RTP 任务" });

    vi.useFakeTimers();
    try {
      await act(async () => {
        fireEvent.click(tasksButton);
        await Promise.resolve();
        await Promise.resolve();
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(6_000);
      });

      expect(taskRequests).toBe(1);
      expect(maximumConcurrentRequests).toBe(1);
    } finally {
      releaseTasks();
      await act(async () => {
        await taskGate;
      });
      unmount();
      vi.useRealTimers();
    }
  });

  it("clears stale RTP task detail and reports a detail request failure", async () => {
    let failStatus = false;
    installDesktopApi({
      ratsStateTransform: (state) => ({
        ...state,
        services: state.services.map((service) => ({ ...service, enabled: true, connection: "connected", sessionActive: true })),
      }),
      ratsTasks: () => [{
        provider_id: "reverie.engine",
        service_id: "rats-4242-testservice",
        task_id: "task-detail-error",
        tool: "run.play",
        deadline_msec: 5_000,
        cursor: 1,
        status: { running: true, next_cursor: 2, output: { running: true } },
        events: [],
      }],
      ratsTaskFailure: (action) => failStatus && action === "ratsTaskStatus" ? new Error("status transport failed") : null,
    });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "RTP 任务" }));
    expect(await screen.findByText(/run\.play started/)).toBeTruthy();
    failStatus = true;
    await user.click(screen.getByRole("button", { name: "刷新" }));

    expect(await screen.findByText(/status transport failed/)).toBeTruthy();
    await waitFor(() => expect(screen.queryByText(/run\.play started/)).toBeNull());
  });

  it("bounds retained RTP task logs to the latest 64 Ki characters", async () => {
    let logRequest = 0;
    installDesktopApi({
      ratsStateTransform: (state) => ({
        ...state,
        services: state.services.map((service) => ({ ...service, enabled: true, connection: "connected", sessionActive: true })),
      }),
      ratsTasks: () => [{
        provider_id: "reverie.engine",
        service_id: "rats-4242-testservice",
        task_id: "task-bounded-logs",
        tool: "run.play",
        deadline_msec: 5_000,
        cursor: 1,
        status: { running: true, next_cursor: 2, output: { running: true } },
        events: [],
      }],
      ratsTaskLogText: () => logRequest++ === 0 ? "A".repeat(65_536) : "B".repeat(1_024),
    });
    const user = userEvent.setup();
    const { container } = render(<App />);

    await user.click(await screen.findByRole("button", { name: "RTP 任务" }));
    await waitFor(() => expect(container.querySelector(".rats-task-log-output")?.textContent?.length).toBe(65_536));
    await user.click(screen.getByRole("button", { name: "刷新" }));

    await waitFor(() => {
      const text = container.querySelector(".rats-task-log-output")?.textContent ?? "";
      expect(text.length).toBe(65_536);
      expect(text.endsWith("B".repeat(1_024))).toBe(true);
      expect(text.startsWith("A".repeat(1_024))).toBe(true);
    });
  });

  it("evicts disappeared and offline RTP task caches before the same key is reused", async () => {
    let phase = 0;
    const reusedLogCursors: number[] = [];
    const reconnectedLogCursors: number[] = [];
    const taskId = "task-reused-key";
    const taskRecord = (running: boolean): RatsTaskRecord => ({
      provider_id: "reverie.engine",
      service_id: "rats-4242-testservice",
      task_id: taskId,
      tool: "run.play",
      deadline_msec: 5_000,
      cursor: 0,
      status: { running, next_cursor: 0, output: { running } },
      events: [],
    });
    installDesktopApi({
      ratsStateTransform: (state) => ({
        ...state,
        services: state.services.map((service) => ({
          ...service,
          enabled: true,
          connection: phase === 3 ? "available" : "connected",
          sessionActive: phase !== 3,
        })),
      }),
      ratsTasks: (_payload, cancelled) => {
        if (phase === 1) return [];
        return [taskRecord(phase >= 2 || !cancelled)];
      },
      ratsTaskStatus: (_payload, cancelled) => {
        const running = phase >= 2 || !cancelled;
        return { running, next_cursor: 0, output: { running } };
      },
      ratsTaskEvents: () => {
        const type = phase >= 4 ? "task.reconnected" : phase >= 2 ? "task.reused" : "task.initial";
        return {
          schema: "reverie.rtp.task/1",
          events: [{ sequence: 1, type, timestamp_utc: "2026-08-09T00:00:00Z", payload: {} }],
          next_cursor: 1,
        };
      },
      ratsTaskLogText: (payload) => {
        const cursor = Number(payload.cursor ?? 0);
        if (phase >= 4) {
          reconnectedLogCursors.push(cursor);
          return "reconnected-log\n";
        }
        if (phase >= 2) {
          reusedLogCursors.push(cursor);
          return "reused-log\n";
        }
        return "initial-log\n";
      },
    });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "RTP 任务" }));
    expect(await screen.findByText("task.initial")).toBeTruthy();
    expect(await screen.findByText(/initial-log/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "取消任务" }));
    expect((await screen.findAllByText("已取消")).length).toBeGreaterThanOrEqual(1);

    phase = 1;
    await user.click(screen.getByRole("button", { name: "刷新" }));
    await waitFor(() => expect(screen.queryByText(taskId)).toBeNull());

    phase = 2;
    await user.click(screen.getByRole("button", { name: "刷新" }));
    expect(await screen.findByText("task.reused")).toBeTruthy();
    expect(await screen.findByText(/reused-log/)).toBeTruthy();
    expect(screen.queryByText("task.initial")).toBeNull();
    expect(screen.queryByText(/initial-log/)).toBeNull();
    expect(screen.queryByText("已取消")).toBeNull();
    expect(screen.getByRole("button", { name: "取消任务" })).toBeTruthy();
    expect(reusedLogCursors[0]).toBe(0);

    phase = 3;
    await user.click(screen.getByRole("button", { name: "刷新" }));
    expect(await screen.findByText("尚未启用 RTP 服务")).toBeTruthy();

    phase = 4;
    await user.click(screen.getByRole("button", { name: "刷新" }));
    expect(await screen.findByText("task.reconnected")).toBeTruthy();
    expect(await screen.findByText(/reconnected-log/)).toBeTruthy();
    expect(screen.queryByText("task.reused")).toBeNull();
    expect(screen.queryByText(/reused-log/)).toBeNull();
    expect(reconnectedLogCursors[0]).toBe(0);
  });

  async function openCustomProviderPage(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole("button", { name: "设置" }));
    await user.click(await screen.findByRole("button", { name: "模型与提供商" }));
    await user.click(await screen.findByRole("button", { name: /Custom Provider/ }));
  }

  it("adds a custom provider from the desktop page with the four documented fields", async () => {
    const { request } = installDesktopApi({ customProviders: [] });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "命令面板" });

    await openCustomProviderPage(user);
    expect(screen.getByText("还没有自定义 Provider")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "添加 Provider" }));
    const dialog = await screen.findByRole("dialog", { name: "添加 Provider" });
    expect(within(dialog).getByText("POST <base>/chat/completions with a Bearer key.")).toBeTruthy();
    const submit = within(dialog).getByRole("button", { name: "添加 Provider" });
    expect((submit as HTMLButtonElement).disabled).toBe(true);

    await user.type(within(dialog).getByLabelText("Provider 名称"), "xkiro");
    await user.type(within(dialog).getByLabelText("Base URL"), "https://api.xkiro.invalid/v1");
    await user.type(within(dialog).getByLabelText("API Key"), "sk-live-secret");
    await user.selectOptions(within(dialog).getByLabelText("API 请求格式"), "anthropic");
    await user.click(within(dialog).getByRole("button", { name: "添加 Provider" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("addCustomProvider", {
      provider: { name: "xkiro", base_url: "https://api.xkiro.invalid/v1", api_key: "sk-live-secret", format: "anthropic" },
    }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "添加 Provider" })).toBeNull());
    expect(await screen.findByText("Anthropic Messages")).toBeTruthy();
    expect(document.body.textContent).not.toContain("sk-live-secret");
  });

  it("shows every custom provider with a masked key and tests availability in one pass", async () => {
    const { request } = installDesktopApi({
      customProviders: [
        customProviderRecord(),
        customProviderRecord({ id: "relay", name: "relay", base_url: "https://relay.invalid", format: "anthropic", format_label: "Anthropic Messages", api_key_masked: "sk-a…env", api_key_source: "env", active: false, selected_model_id: "", models: [] }),
      ],
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "命令面板" });

    await openCustomProviderPage(user);
    expect(screen.getByText("sk-l…9f2c")).toBeTruthy();
    expect(screen.getByText("sk-a…env · 来自环境变量")).toBeTruthy();
    expect(screen.getByText("使用中")).toBeTruthy();
    expect(screen.getByText("目录还是空的")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "测试全部" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("probeProviders", { keys: ["custom:xkiro", "custom:relay"] }));
    expect(await screen.findByText("在线")).toBeTruthy();
    expect(await screen.findByText("密钥无效")).toBeTruthy();
    expect(screen.getByText("HTTP 401 from the catalog endpoint.")).toBeTruthy();
    expect(screen.getByText("42ms")).toBeTruthy();
  });

  it("selects a model from a custom provider's fetched catalog", async () => {
    const { request } = installDesktopApi({
      customProviders: [customProviderRecord({ active: false, selected_model_id: "" })],
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "命令面板" });

    await openCustomProviderPage(user);
    // xkiro-pro already carries a saved limit, so selecting it must not ask again.
    await user.click(screen.getByRole("button", { name: /xkiro-pro/ }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("selectCustomProviderModel", {
      providerId: "xkiro",
      modelId: "xkiro-pro",
    }));
    expect(screen.queryByRole("dialog", { name: "模型上下文限额" })).toBeNull();
    expect(await screen.findByText("使用中")).toBeTruthy();
  });

  it("asks for a context limit the first time a model is chosen, then reuses it", async () => {
    const { request } = installDesktopApi({
      customProviders: [customProviderRecord({ active: false, selected_model_id: "" })],
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "命令面板" });

    await openCustomProviderPage(user);
    await user.click(screen.getByRole("button", { name: /xkiro-lite/ }));

    // Nothing is stored until the user confirms the limit.
    const dialog = await screen.findByRole("dialog", { name: "模型上下文限额" });
    expect(request).not.toHaveBeenCalledWith("selectCustomProviderModel", expect.anything());
    const input = within(dialog).getByLabelText("上下文限额") as HTMLInputElement;
    expect(input.value).toBe("32000");
    await user.clear(input);
    await user.type(input, "64k");
    await user.click(within(dialog).getByRole("button", { name: "保存并使用" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("selectCustomProviderModel", {
      providerId: "xkiro",
      modelId: "xkiro-lite",
      contextLimit: 64_000,
    }));
    expect(await screen.findByText("64K ctx")).toBeTruthy();

    // The second selection of the same model reuses the stored limit silently.
    await user.click(screen.getByRole("button", { name: /xkiro-pro/ }));
    await user.click(screen.getByRole("button", { name: /xkiro-lite/ }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("selectCustomProviderModel", {
      providerId: "xkiro",
      modelId: "xkiro-lite",
    }));
    expect(screen.queryByRole("dialog", { name: "模型上下文限额" })).toBeNull();
  });

  it("turns thinking mode off for a custom provider", async () => {
    const { request } = installDesktopApi({ customProviders: [customProviderRecord()] });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "命令面板" });

    await openCustomProviderPage(user);
    expect(screen.getByText("已开启（默认）")).toBeTruthy();
    await user.click(screen.getByRole("switch", { name: "思考模式" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("updateCustomProvider", {
      providerId: "xkiro",
      patch: { thinking: false },
    }));
    expect(await screen.findByText("已关闭")).toBeTruthy();
  });

  it("disables and deletes a custom provider, asking for confirmation only before deletion", async () => {
    const { request } = installDesktopApi({ customProviders: [customProviderRecord()] });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "命令面板" });

    await openCustomProviderPage(user);
    await user.click(screen.getByRole("switch", { name: "启用" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("updateCustomProvider", {
      providerId: "xkiro",
      patch: { enabled: false },
    }));
    expect(await screen.findByText("已停用")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "删除" }));
    expect(request).not.toHaveBeenCalledWith("deleteCustomProvider", expect.anything());
    await user.click(await screen.findByRole("button", { name: "删除 Provider" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("deleteCustomProvider", { providerId: "xkiro" }));
    expect(await screen.findByText("还没有自定义 Provider")).toBeTruthy();
  });

  it("repaints an already-visited session immediately instead of waiting on the core", async () => {
    const { request, releaseSession } = installDesktopApi({ gateSession: true });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "命令面板" });
    const transcript = () => document.querySelector(".transcript");
    // The row's overflow menu is also labelled with the session name, so pick the
    // row button itself.
    const openSession = (name: string) => {
      const row = [...document.querySelectorAll(".session-item")]
        .find((item) => item.textContent?.includes(name));
      if (!row) throw new Error(`No session row for ${name}`);
      return user.click(row);
    };

    // First visit: nothing cached, so the switch is honest about waiting.
    await openSession("Cache investigation");
    expect(screen.getByText("正在切换会话")).toBeTruthy();
    expect(transcript()?.getAttribute("aria-busy")).toBe("true");
    expect(screen.queryByText("Investigate cache invalidation")).toBeNull();

    releaseSession();
    expect(await screen.findByText("Investigate cache invalidation")).toBeTruthy();
    await waitFor(() => expect(screen.queryByText("正在切换会话")).toBeNull());

    // Back to the first session: read once already, so it paints now.
    await openSession("Initial session");
    expect(screen.queryByText("正在切换会话")).toBeNull();
    expect(transcript()?.getAttribute("aria-busy")).toBe("false");
    expect(screen.queryByText("Investigate cache invalidation")).toBeNull();
    releaseSession();

    // And the return trip to a cached session shows its transcript before the
    // core has answered -- the switch the user notices most.
    await openSession("Cache investigation");
    expect(screen.getByText("Investigate cache invalidation")).toBeTruthy();
    expect(screen.queryByText("正在切换会话")).toBeNull();
    releaseSession();

    await waitFor(() => expect(request).toHaveBeenCalledWith("getSession", { sessionId: "session-2" }));
    // Every switch still reconciles with the core; the cache only decides what
    // is on screen while that is in flight.
    const fetches = request.mock.calls.filter(([action]) => action === "getSession");
    expect(fetches.length).toBe(4);
  });

  it("lists every custom provider in the picker under the name the user gave it", async () => {
    const { request } = installDesktopApi({
      customProviders: [
        customProviderRecord({ active: false, selected_model_id: "", selected_model_display_name: "" }),
        customProviderRecord({
          id: "qwen",
          name: "Qwen3.8 Max",
          base_url: "https://api.qwen.invalid/v1",
          active: false,
          selected_model_id: "",
          selected_model_display_name: "",
          models: [],
          model_context_limits: {},
        }),
      ],
    });
    const user = userEvent.setup();
    const { container } = render(<App />);

    await user.click(await screen.findByRole("button", { name: /Test Model/ }));
    const dialog = await screen.findByRole("dialog", { name: "模型来源" });
    // The generic bucket is gone: a named provider is a source by that name.
    await waitFor(() => expect(within(dialog).getByText("Qwen3.8 Max")).toBeTruthy());
    expect(within(dialog).getByText("xkiro")).toBeTruthy();
    expect(within(dialog).queryByText("Custom Provider")).toBeNull();

    await user.click(within(dialog).getByText("xkiro"));
    await user.click(await within(dialog).findByRole("button", { name: /xkiro-pro/ }));

    // Activating a provider is its own core call, not a `selectModel` on a
    // source the core has never heard of.
    await waitFor(() => expect(request).toHaveBeenCalledWith("selectCustomProviderModel", {
      providerId: "xkiro",
      modelId: "xkiro-pro",
    }));
    expect(request).not.toHaveBeenCalledWith("selectModel", expect.objectContaining({ source: "custom:xkiro" }));
    await waitFor(() => expect(container.querySelector(".model-trigger small")?.textContent).toBe("xkiro"));
  });

  it("edits a manual model in place, keeping the stored key and custom headers", async () => {
    const { request } = installDesktopApi({
      standardModels: [{
        model: "gpt-5.4",
        model_display_name: "GPT-5.4",
        provider: "openai-chat",
        base_url: "https://api.example.com/v1",
        endpoint: "/chat/completions",
        api_key: "sk-stored-secret",
        max_context_tokens: 128_000,
        supports_vision: false,
        custom_headers: { "x-tenant": "reverie" },
      }],
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "命令面板" });

    await user.click(screen.getByRole("button", { name: "设置" }));
    await user.click(await screen.findByRole("button", { name: "模型与提供商" }));
    await user.click(await screen.findByRole("button", { name: /Manual Model/ }));
    await user.click(screen.getByRole("button", { name: "编辑标准模型" }));

    const dialog = await screen.findByRole("dialog", { name: "编辑标准模型" });
    expect((within(dialog).getByLabelText("模型 ID") as HTMLInputElement).value).toBe("gpt-5.4");
    expect((within(dialog).getByLabelText("Base URL") as HTMLInputElement).value).toBe("https://api.example.com/v1");
    expect((within(dialog).getByLabelText(/请求路径/) as HTMLInputElement).value).toBe("/chat/completions");
    expect((within(dialog).getByLabelText("Provider") as HTMLSelectElement).value).toBe("openai-chat");
    // The key never reaches the renderer, so the form says so instead of
    // pretending the empty field means "erase it".
    const key = within(dialog).getByLabelText(/API Key/) as HTMLInputElement;
    expect(key.value).toBe("");
    expect(key.placeholder).toBe("••••••••");
    expect(within(dialog).getByText("留空表示保留现有密钥")).toBeTruthy();
    expect(within(dialog).getByText("1 个自定义请求头会原样保留。")).toBeTruthy();

    const displayName = within(dialog).getByLabelText("显示名称") as HTMLInputElement;
    await user.clear(displayName);
    await user.type(displayName, "GPT-5.4 Turbo");
    const context = within(dialog).getByLabelText("上下文长度") as HTMLInputElement;
    await user.clear(context);
    await user.type(context, "200000");
    await user.click(within(dialog).getByRole("button", { name: "保存" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("updateStandardModel", {
      index: 0,
      model: {
        model: "gpt-5.4",
        model_display_name: "GPT-5.4 Turbo",
        provider: "openai-chat",
        base_url: "https://api.example.com/v1",
        endpoint: "/chat/completions",
        max_context_tokens: 200_000,
        supports_vision: false,
        custom_headers: { "x-tenant": "reverie" },
      },
    }));
    expect(await screen.findByText("标准模型已更新")).toBeTruthy();
    expect(await screen.findByText("GPT-5.4 Turbo")).toBeTruthy();
    expect(screen.getByText("200K ctx")).toBeTruthy();

    // Reopening proves the blank key left the stored one in place.
    await user.click(screen.getByRole("button", { name: "编辑标准模型" }));
    const reopened = await screen.findByRole("dialog", { name: "编辑标准模型" });
    expect((within(reopened).getByLabelText(/API Key/) as HTMLInputElement).placeholder).toBe("••••••••");
    expect((within(reopened).getByLabelText("上下文长度") as HTMLInputElement).value).toBe("200000");
  });

  it("keeps the inspector mounted while it collapses, and remembers the choice", async () => {
    const { api } = installDesktopApi();
    const user = userEvent.setup();
    const { container } = render(<App />);
    await screen.findByRole("button", { name: "命令面板" });
    const shell = container.querySelector(".app-shell");

    expect(shell?.classList.contains("with-inspector")).toBe(true);
    expect(container.querySelector(".inspector")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "关闭检查器" }));

    // A pane that unmounts cannot animate out, so it stays in the tree and is
    // only taken out of the accessibility tree and the tab order.
    await waitFor(() => expect(shell?.classList.contains("with-inspector")).toBe(false));
    const inspector = container.querySelector(".inspector");
    expect(inspector).toBeTruthy();
    expect(inspector?.getAttribute("aria-hidden")).toBe("true");
    expect(inspector?.hasAttribute("inert")).toBe(true);
    expect(api.setUiPreferences).toHaveBeenCalledWith({ inspectorOpen: false });

    await user.click(screen.getByRole("button", { name: "打开检查器" }));

    await waitFor(() => expect(shell?.classList.contains("with-inspector")).toBe(true));
    expect(container.querySelector(".inspector")?.hasAttribute("aria-hidden")).toBe(false);
  });

  it("renders a streaming Thinking Tool call as reasoning instead of a silent activity row", async () => {
    const { emitCoreEvent, releasePrompt } = installDesktopApi({ gatePrompt: true });
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });

    await user.type(composer, "Inspect the cache{Enter}");
    await act(async () => {
      // The wire shape the core actually emits: `encode_stream_event` puts the
      // kind under `event`, and the deliberation arrives as call arguments.
      emitCoreEvent({
        type: "ui.event",
        event: {
          event: "tool_start",
          tool_name: "deep_think",
          tool_call_id: "call-1",
          message: "deep_think",
          arguments: JSON.stringify({
            topic: "Cache invalidation",
            thought: "The index is keyed by mtime, so a same-second write is missed.",
            next_step: "Compare size as well as mtime.",
          }),
        },
      });
      await new Promise((resolve) => setTimeout(resolve, 80));
    });

    expect(await screen.findByText("Cache invalidation")).toBeTruthy();
    // Scope to the expanded body: the summary carries a truncated copy of the
    // same prose, so an unscoped regex would match twice.
    const reasoning = document.querySelector(".reasoning-block .reasoning-content") as HTMLElement | null;
    expect(reasoning).toBeTruthy();
    expect(within(reasoning!).getByText(/The index is keyed by mtime/)).toBeTruthy();
    expect(within(reasoning!).getByText(/Next: Compare size as well as mtime\./)).toBeTruthy();

    releasePrompt();
    expect(await screen.findByText("Cache inspection complete")).toBeTruthy();
  });

  it("keeps the experimental badge in English, matching the core's own setting copy", async () => {
    installDesktopApi({
      settingItems: [{
        name: "Thinking Tool",
        key: "thinking_tool",
        kind: "bool",
        description: "Give the model a private scratchpad for deliberate reasoning.",
        value: true,
        experimental: true,
      }],
    });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "设置" }));

    const badge = await screen.findByText("Experimental");
    expect(badge.className).toBe("setting-badge");
    expect(screen.queryByText("实验性")).toBeNull();
  });
});
