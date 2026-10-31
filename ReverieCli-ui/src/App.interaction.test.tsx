// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { readFileSync } from "node:fs";
import { DEFAULT_UI_PREFERENCES, normalizeUiPreferences, type UiPreferences } from "./preferences";
import type { ContextUsage, CustomProviderRecord, DesktopState, ImageModelSourcesState, ModelRecord, ModelSource, ModelSourcesState, ProviderProbe, RatsCustomProviderDefinition, RatsPermission, RatsState, RatsTaskRecord, SessionState } from "./types";

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
    items: [{ name: "Permission", key: "permission_level", kind: "choice", description: "", value: "workspace_write" }, { name: "Stream Responses", key: "stream_responses", kind: "bool", description: "", value: true }],
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
  skills: {
    count: 2,
    invalid_count: 0,
    shadowed_count: 0,
    records: [
      {
        key: "photo-to-3d",
        name: "photo-to-3d",
        description: "Reconstruct a photographed subject as Three.js code",
        summary: "Reconstruct a photographed subject as Three.js code",
        path: "builtin_skills/photo-to-3d/SKILL.md",
        scope: "Built-in",
        root: "builtin",
        plugin_id: "",
        allow_implicit_invocation: true,
        pinned: false,
        shadowed: false,
      },
      {
        key: "reverie-engine",
        name: "reverie-engine",
        description: "Build and verify unified Reverie Engine games",
        summary: "Build and verify unified Reverie Engine games",
        path: "builtin_skills/reverie-engine/SKILL.md",
        scope: "Built-in",
        root: "builtin",
        plugin_id: "",
        allow_implicit_invocation: true,
        pinned: false,
        shadowed: false,
      },
    ],
    pinned: { max: 4, keys: [], names: [], unresolved: [] },
    errors: [],
    shadowed: [],
  },
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
  imageModels?: ImageModelSourcesState;
  initialState?: DesktopState;
  customProviders?: CustomProviderRecord[];
  standardModels?: StandardModelConfig[];
  settingItems?: DesktopState["settings"]["items"];
  gatePrompt?: boolean;
  gateSession?: boolean;
  initialSession?: SessionState;
  initialPreferences?: Partial<UiPreferences>;
  contextUsage?: ContextUsage | null;
  revealedSecret?: string;
} = {}) {
  let promptFinished = false;
  let ratsEnabled = false;
  let ratsTaskCancelled = false;
  /** Definitions the harness has accepted, in the order the core would report them. */
  let ratsCustomProviders: RatsCustomProviderDefinition[] = (options.ratsCustomProviders ?? []).map((definition) => ({ ...definition }));
  let providers: CustomProviderRecord[] = (options.customProviders ?? []).map((record) => ({ ...record }));
  let standardModels: StandardModelConfig[] = (options.standardModels ?? []).map((record) => ({ ...record }));
  let imageModels = options.imageModels;
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
  let settingItems = options.settingItems;
  const settings = (): DesktopState["settings"] => settingItems
    ? { ...desktopState.settings, items: settingItems }
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
    if (action === "getFileChanges") return { type: "file.changes", session_id: payload.sessionId, changes: [] };
    if (action === "initialize") {
      const state = options.initialState ?? { ...desktopState, models: models(), settings: settings() };
      return { type: "state", state, deferred: payload.deferPayloads === true };
    }
    if (action === "getState") {
      const state = options.initialState ?? { ...desktopState, models: models(), settings: settings() };
      return { type: "state", state };
    }
    if (action === "createSession") {
      const session = { ...baseSession, id: "session-new", name: "New session", messages: [] };
      return {
        type: "session.created",
        session,
        sessions: { ...desktopState.sessions, current_session_id: session.id, items: [...desktopState.sessions.items, { id: session.id, name: session.name, created_at: session.created_at, updated_at: session.updated_at, message_count: 0 }] },
      };
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
          : options.initialSession ?? baseSession;
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
    if (action === "refreshImageModelSources") return { type: "image-models", imageModels };
    if (action === "selectImageModel") {
      if (!imageModels) throw new Error("Image models are unavailable.");
      const sourceId = String(payload.source);
      const modelId = String(payload.modelId);
      const source = imageModels.sources.find((item) => item.id === sourceId);
      const model = source?.models.find((item) => item.id === modelId);
      if (!source || !model) throw new Error("Unknown image model.");
      const selected = { id: model.id, display_name: model.display_name, source: sourceId, supports_edit: model.supports_edit };
      imageModels = {
        ...imageModels,
        active_source: sourceId,
        active_model: selected,
        sources: imageModels.sources.map((item) => ({
          ...item,
          active: item.id === sourceId,
          selected_model_id: item.id === sourceId ? modelId : item.selected_model_id,
        })),
      };
      return { type: "image-model.selected", selected, imageModels };
    }
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
      if (payload.key === "api_compatibility") {
        settingItems = (settingItems ?? desktopState.settings.items).map(item => item.key === payload.key ? { ...item, value: payload.value } : item);
        return { type: "setting.updated", success: true, message: "saved", settings: settings(), models: models(), workspace: desktopState.workspace };
      }
      if (payload.key === "stream_responses") {
        settingItems = [...(settingItems ?? desktopState.settings.items).filter(item => item.key !== "stream_responses"), { name: "Stream Responses", key: "stream_responses", kind: "bool", description: "", value: payload.value }];
        return { type: "setting.updated", success: true, message: "saved", settings: settings(), models: models(), workspace: desktopState.workspace };
      }
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
    if (action === "runPrompt" || action === "resumePrompt") {
      promptFinished = true;
      if (options.approvalRequest) emitCoreEvent(options.approvalRequest);
      if (options.gatePrompt) await promptGate;
      return {
        type: "prompt.result",
        result: {
          success: true,
          prompt: String(payload.prompt ?? "Inspect the cache"),
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
    if (action === "getContextUsage") {
      return {
        type: "context.usage",
        usage: options.contextUsage ?? null,
      };
    }
    if (action === "revealProviderSecret") {
      return { type: "provider.secret", value: options.revealedSecret ?? "sk-revealed-key" };
    }
    throw new Error(`Unexpected action: ${action}`);
  });
  // Stateful, like the Electron main process: a toggle that reads its own value
  // back from a constant would snap straight back to the default.
  let preferences = normalizeUiPreferences({ ...DEFAULT_UI_PREFERENCES, ...options.initialPreferences });
  const api = {
    request,
    workbench: vi.fn(async (operation: string, payload: Record<string, unknown>) => {
      if (operation === "validate-input") return { attachments: payload.attachments };
      if (operation === "reviews") return { reviews: [] };
      if (operation === "runs") return { runs: [] };
      if (operation === "list-directory") return { directory: ".", entries: [], truncated: false };
      if (operation === "snapshot") return { root: "C:/workspace", version: "v1", indexVersion: "i1", head: "head", branch: "main", files: [], conflicts: [], scope: "working", base: "" };
      return {};
    }),
    cancel: vi.fn(async () => undefined),
    notify: vi.fn(async () => undefined),
    onEvent: vi.fn((listener: (message: { event: unknown }) => void) => {
      eventListeners.push(listener);
      return () => {
        eventListeners.splice(eventListeners.indexOf(listener), 1);
      };
    }),
    selectWorkspace: vi.fn(async () => null),
    switchWorkspace: vi.fn(async (_root: string) => null as string | null),
    deleteWorkspace: vi.fn(async () => null),
    selectAttachment: vi.fn(async () => null),
    importDroppedFiles: vi.fn(async () => [] as Array<{ name: string; relativePath: string; size: number }>),
    gitStatus: vi.fn(async () => null as null | { repositoryRoot: string; currentBranch: string; dirtyCount: number; localBranches: string[]; remoteBranches: string[] }),
    switchGitBranch: vi.fn(async () => ({ repositoryRoot: "C:/workspace", currentBranch: "feature/ui", dirtyCount: 0, localBranches: ["main", "feature/ui"], remoteBranches: [] })),
    createGitBranch: vi.fn(async (name: string) => ({ repositoryRoot: "C:/workspace", currentBranch: name, dirtyCount: 0, localBranches: ["main", name], remoteBranches: [] })),
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
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
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
  vi.unstubAllGlobals();
});

describe("desktop GUI interactions", () => {
  it("switches UI variants without remounting the composer or workbench", async () => {
    const { api } = installDesktopApi();
    const user = userEvent.setup();
    const { container } = render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ }) as HTMLTextAreaElement;
    fireEvent.change(composer, { target: { value: "保留草稿 while switching" } });
    await user.click(screen.getByRole("button", { name: "打开工作面板" }));
    const workbench = container.querySelector(".workbench-panel");
    for (const [label, value] of [["Liquid Glass", "liquid-glass"], ["经典界面", "classic"]]) {
      await user.click(screen.getByRole("button", { name: "切换主题" }));
      await user.click(screen.getByRole("button", { name: label }));
      await waitFor(() => expect(document.documentElement.dataset.ui).toBe(value));
      expect(api.setUiPreferences).toHaveBeenCalledWith({ uiVariant: value });
      expect(container.querySelector(".composer textarea")).toBe(composer);
      expect(composer.value).toBe("保留草稿 while switching");
      expect(container.querySelector(".workbench-panel")).toBe(workbench);
      expect(workbench?.hasAttribute("inert")).toBe(false);
      expect(container.querySelector(".app-shell")?.classList.contains("with-inspector")).toBe(true);
    }
  });

  it("dispatches parameterized desktop settings and retains terminal-only commands", async () => {
    const {request}=installDesktopApi();const user=userEvent.setup();render(<App/>);
    const composer=await screen.findByRole("textbox",{name:/向 Test Model 提问/});
    for(const [text,key,value] of [["/mode writer","mode","writer"],["/permission mode strict","permission_mode","strict"]]){
      fireEvent.change(composer,{target:{value:text}});await user.click(screen.getByRole("button",{name:"发送"}));
      await waitFor(()=>expect(request).toHaveBeenCalledWith("setSetting",{key,value}));
      await waitFor(()=>expect((composer as HTMLTextAreaElement).value).toBe(""));
    }
    fireEvent.change(composer,{target:{value:"/session fork Current copy"}});await user.click(screen.getByRole("button",{name:"发送"}));
    expect((composer as HTMLTextAreaElement).value).toBe("/session fork Current copy");
    expect(screen.getByText("此终端指令不能在桌面输入框执行，请使用对应页面或 Reverie TUI。")).toBeTruthy();
    expect(request.mock.calls.some(([action])=>action==="runPrompt")).toBe(false);
  });

  it("passes quoted review paths and scope to the review panel without sending a model turn", async () => {
    const {api,request}=installDesktopApi();const user=userEvent.setup();
    Object.assign(api,{workbench:vi.fn(async(operation:string)=>operation==="reviews"?{reviews:[]}:operation==="runs"?{runs:[]}:{files:[],conflicts:[],remotes:[],branches:[],scope:"staged"})});
    const show=vi.fn();window.addEventListener("reverie:workbench",show);
    try{
      render(<App/>);const composer=await screen.findByRole("textbox",{name:/向 Test Model 提问/});
      fireEvent.change(composer,{target:{value:'/review "src/two words.ts" --scope staged --base "origin/main"'}});
      await user.click(screen.getByRole("button",{name:"发送"}));
      expect((show.mock.calls.at(-1)![0] as CustomEvent).detail).toEqual({tab:"review",reviewFile:"src/two words.ts",scope:"staged",base:"origin/main"});
      expect(request.mock.calls.some(([action])=>action==="runPrompt")).toBe(false);
    }finally{window.removeEventListener("reverie:workbench",show);}
  });

  it("selects command results with arrows and Enter while ignoring IME composition", async () => {
    const {request}=installDesktopApi();const user=userEvent.setup();render(<App/>);
    await user.click(await screen.findByRole("button",{name:"命令面板"}));
    const dialog=await screen.findByRole("dialog",{name:"命令面板"});const search=within(dialog).getByRole("combobox");
    const results=within(dialog).getAllByRole("option");expect(results[0].getAttribute("aria-selected")).toBe("true");
    await user.keyboard("{ArrowDown}");expect(results[1].getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(search,{key:"Enter",isComposing:true});expect(screen.getByRole("dialog",{name:"命令面板"})).toBeTruthy();
    await user.keyboard("{Enter}");expect(screen.queryByRole("dialog",{name:"命令面板"})).toBeNull();
    expect(request.mock.calls.some(([action])=>action==="compactContext" || action==="runPrompt")).toBe(false);
    const composer=screen.getByRole("textbox",{name:/向 Test Model 提问/});expect((composer as HTMLTextAreaElement).value.trim()).toBe("/compact");
  });

  it("opens slash suggestions outside the clipped input stack and inserts without sending", async () => {
    const { request } = installDesktopApi();
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    await user.type(composer, "/");
    const menu = screen.getByRole("listbox", { name: "指令与 Skills" });
    expect(document.querySelector(".chat-input-stack")?.contains(menu)).toBe(false);
    expect(within(menu).getAllByRole("option").map(option => option.textContent)).toEqual(expect.arrayContaining([expect.stringContaining("/skill"), expect.stringContaining("/compact")]));
    await user.keyboard("{ArrowDown}{ArrowDown}{Tab}");
    expect((composer as HTMLTextAreaElement).value).toBe("/compact ");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(request.mock.calls.some(([action]) => action === "runPrompt" || action === "compactContext")).toBe(false);
    await user.keyboard("{Enter}");
    await waitFor(() => expect(request.mock.calls.some(([action]) => action === "compactContext")).toBe(true));
  });

  it("pins a slash skill only after the backend acknowledges it and never sends a model turn", async () => {
    const { request } = installDesktopApi();
    const original = request.getMockImplementation()!;
    request.mockImplementation(async (action, payload) => action === "pinSkill" ? {
      type: "skill.pinned", status: "pinned", name: "photo-to-3d",
      skills: { ...desktopState.skills, pinned: { max: 4, keys: ["photo-to-3d"], names: ["photo-to-3d"], unresolved: [] }, records: desktopState.skills.records.map(record => ({ ...record, pinned: record.name === "photo-to-3d" })) },
    } as never : original(action, payload));
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    await user.type(composer, "/");
    await user.keyboard("{Enter}");
    expect((composer as HTMLTextAreaElement).value).toBe("/skill ");
    await user.click(await screen.findByRole("option", { name: /photo-to-3d/ }));
    await waitFor(() => expect(document.querySelector(".composer .skill-chip")?.textContent).toContain("photo-to-3d"));
    expect(request).toHaveBeenCalledWith("pinSkill", { skill: "photo-to-3d" });
    expect((composer as HTMLTextAreaElement).value).toBe("");
    expect(screen.getByText("必须使用")).toBeTruthy();
    expect(request.mock.calls.some(([action]) => action === "runPrompt")).toBe(false);
  });

  it("preserves a failed pin draft, empty-search Enter, and IME composition", async () => {
    const { request } = installDesktopApi();
    const original = request.getMockImplementation()!;
    request.mockImplementation(async (action, payload) => { if (action === "pinSkill") throw new Error("Pin failed"); return original(action, payload); });
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    await user.type(composer, "/skill photo");
    fireEvent.keyDown(composer, { key: "Enter", isComposing: true });
    expect(request.mock.calls.some(([action]) => action === "pinSkill")).toBe(false);
    await user.keyboard("{Enter}");
    await screen.findByText("Pin failed");
    expect((composer as HTMLTextAreaElement).value).toBe("/skill photo");
    expect(document.querySelector(".composer .skill-chip")).toBeNull();
    await user.clear(composer);
    await user.type(composer, "/nothing-matches{Enter}");
    expect((composer as HTMLTextAreaElement).value).toBe("/nothing-matches");
    expect(request.mock.calls.some(([action]) => action === "runPrompt")).toBe(false);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("selects the thirteenth file, preserves text around the caret, and refocuses the composer", async () => {
    const { request } = installDesktopApi();
    const original = request.getMockImplementation()!;
    request.mockImplementation(async (action, payload) => action === "workspaceMentions" ? {
      type: "workspace.mentions", items: Array.from({ length: 24 }, (_, index) => ({ path: `目录/文件 ${index}.txt`, name: `文件 ${index}.txt` })), context_engine: desktopState.workspace.context_engine,
    } as never : original(action, payload));
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ }) as HTMLTextAreaElement;
    await user.type(composer, "Compare @file then explain");
    act(() => { composer.setSelectionRange(13, 13); fireEvent.select(composer); });
    await screen.findByRole("option", { name: /文件 23.txt/ });
    expect(request).toHaveBeenCalledWith("workspaceMentions", { query: "file", limit: 24 });
    await user.keyboard("{ArrowDown>12}{Enter}");
    await waitFor(() => expect(document.querySelector(".attachment-card")?.textContent).toContain("文件 12.txt"));
    expect(composer.value).toBe("Compare  then explain");
    await waitFor(() => expect(document.activeElement).toBe(composer));
    expect(request.mock.calls.some(([action]) => action === "runPrompt")).toBe(false);
  });

  it("does not reopen a dismissed mention on late completion or keep files after changing to slash", async () => {
    const { request } = installDesktopApi();
    const original = request.getMockImplementation()!;
    let resolve!: (value: unknown) => void;
    request.mockImplementation(async (action, payload) => action === "workspaceMentions" ? await new Promise<unknown>(done => { resolve = done; }) as never : original(action, payload));
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    await user.type(composer, "@");
    await waitFor(() => expect(resolve).toBeTypeOf("function"));
    await user.keyboard("{Escape}");
    await act(async () => resolve({ items: [{ path: "late.txt" }], context_engine: desktopState.workspace.context_engine }));
    expect(screen.queryByRole("listbox")).toBeNull();
    await user.clear(composer);
    await user.type(composer, "/");
    expect(screen.getByRole("listbox", { name: "指令与 Skills" })).toBeTruthy();
    expect(screen.queryByRole("option", { name: /late.txt/ })).toBeNull();
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("shows a failed mention lookup instead of an endless spinner and prevents accidental send", async () => {
    const { request } = installDesktopApi();
    const original = request.getMockImplementation()!;
    request.mockImplementation(async (action, payload) => { if (action === "workspaceMentions") throw new Error("Workspace lookup failed"); return original(action, payload); });
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    await user.type(composer, "@");
    await screen.findByText("Workspace lookup failed");
    expect(screen.queryByText("正在查找…")).toBeNull();
    await user.keyboard("{Enter}");
    expect(request.mock.calls.some(([action]) => action === "runPrompt")).toBe(false);
  });

  it("keeps the welcome composer mounted and focused when a starter becomes the first turn", async () => {
    const { request, releasePrompt } = installDesktopApi({ gatePrompt: true });
    const user = userEvent.setup();
    const { container } = render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    await user.click(screen.getByRole("button", { name: /理解代码库/ }));
    expect((composer as HTMLTextAreaElement).value).toBe("分析这个项目的架构、入口和关键模块，并指出最值得关注的技术风险。");
    expect(document.activeElement).toBe(composer);
    await user.keyboard("{Enter}");
    await waitFor(() => expect(request).toHaveBeenCalledWith("runPrompt", expect.anything()));
    expect(container.querySelector(".welcome-header")).toBeNull();
    expect(container.querySelector(".composer textarea")).toBe(composer);
    expect(document.activeElement).toBe(composer);
    await user.type(composer, "继续检查这个想法");
    expect((composer as HTMLTextAreaElement).value).toBe("继续检查这个想法");
    await act(async () => releasePrompt());
  });

  it("updates context during continuous draft edits and streaming before the turn ends", async () => {
    const { request, emitCoreEvent, releasePrompt } = installDesktopApi({ gatePrompt: true });
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    await user.type(composer, "draft context");
    await waitFor(() => expect(request).toHaveBeenCalledWith("getContextUsage", expect.objectContaining({ draftText: "draft context" })));
    await user.keyboard("{Enter}");
    await waitFor(() => expect(request).toHaveBeenCalledWith("runPrompt", expect.anything()));
    for (let index = 0; index < 8; index += 1) {
      act(() => emitCoreEvent({ type: "assistant.delta", text: `stream ${index} ` }));
      await act(async () => { await new Promise(resolve => setTimeout(resolve, 80)); });
    }
    expect(request.mock.calls.some(([action, payload]) => action === "getContextUsage" && String(payload.liveAssistantText || "").includes("stream 0"))).toBe(true);
    expect(request.mock.calls.filter(([action]) => action === "getContextUsage").every(([, payload]) => !("history" in payload) && !("liveAttachments" in payload))).toBe(true);
    expect(screen.getByRole("button", { name: "停止" })).toBeTruthy();
    await act(async () => releasePrompt());
  });

  it("removes manual conversation ordering and its sidebar filter", async () => {
    installDesktopApi();
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: /管理会话 Initial session/ }));
    expect(screen.queryByRole("button", { name: "上移会话" })).toBeNull();
    expect(screen.queryByRole("button", { name: "下移会话" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "会话状态过滤" })).toBeNull();
    expect(screen.getByRole("button", { name: /^置顶$/ })).toBeTruthy();
  });

  it("removes message context summary and keeps the composer editable", async () => {
    installDesktopApi();
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    expect(screen.queryByRole("button", { name: "本条上下文" })).toBeNull();
    expect(screen.queryByRole("dialog", { name: "本条上下文" })).toBeNull();
    await user.type(composer, "existing input remains usable");
    expect((composer as HTMLTextAreaElement).value).toBe("existing input remains usable");
  });

  it("switches running send behavior by keyboard without sending or discarding the pending draft", async () => {
    const { request, releasePrompt } = installDesktopApi({ gatePrompt: true });
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    await user.type(composer, "start this turn{Enter}");
    const modes = await screen.findByRole("radiogroup", { name: "运行中发送方式" });
    const queue = within(modes).getByRole("radio", { name: "排队下一轮" });
    const steer = within(modes).getByRole("radio", { name: "补充当前任务" });
    expect(queue.getAttribute("aria-checked")).toBe("true");
    await user.type(composer, "下一轮草稿");
    act(() => queue.focus());
    await user.keyboard("{ArrowRight}");
    expect(steer.getAttribute("aria-checked")).toBe("true");
    expect(document.activeElement).toBe(steer);
    expect(screen.getByRole("button", { name: "补充当前任务" })).toBeTruthy();
    fireEvent.keyDown(steer, { key: "ArrowLeft", isComposing: true });
    expect(steer.getAttribute("aria-checked")).toBe("true");
    await user.keyboard("{Enter}{ArrowLeft}");
    expect(queue.getAttribute("aria-checked")).toBe("true");
    expect((composer as HTMLTextAreaElement).value).toBe("下一轮草稿");
    expect(request.mock.calls.filter(([action]) => action === "runPrompt")).toHaveLength(1);
    await act(async () => releasePrompt());
    expect((composer as HTMLTextAreaElement).value).toBe("下一轮草稿");
  });

  it("keeps the latest message visible on resize while preserving an earlier reading position", async () => {
    let resized = () => {};
    const disconnect = vi.fn();
    vi.stubGlobal("ResizeObserver", class { constructor(private callback: () => void) {} observe(element: Element) { if (element.classList.contains("transcript")) resized = this.callback; } disconnect = disconnect; });
    installDesktopApi({ initialSession: { ...baseSession, messages: [{ role: "assistant", content: "Existing conversation" }] } });
    render(<App />);
    await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    const transcript = document.querySelector<HTMLDivElement>(".transcript")!;
    Object.defineProperties(transcript, { clientHeight: { configurable: true, value: 220 }, scrollHeight: { configurable: true, value: 800 } });
    act(() => resized());
    expect(transcript.style.getPropertyValue("--transcript-height")).toBe("");
    expect(transcript.scrollTop).toBe(800);
    transcript.scrollTop = 100;
    fireEvent.scroll(transcript);
    act(() => resized());
    expect(transcript.scrollTop).toBe(100);
    cleanup();
    expect(disconnect).toHaveBeenCalled();
  });

  it("follows a new user prompt but preserves older reading when queueing during a run", async () => {
    let resize = () => {};
    vi.stubGlobal("ResizeObserver", class { constructor(private callback: () => void) {} observe(element: Element) { if (element.classList.contains("transcript")) resize = this.callback; } disconnect() {} });
    const { request, releasePrompt } = installDesktopApi({ gatePrompt: true, initialSession: { ...baseSession, messages: [{ role: "assistant", content: "An older reply" }] }, initialState: { ...desktopState, sessions: { ...desktopState.sessions, current_session_id: baseSession.id } } });
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    const transcript = document.querySelector<HTMLDivElement>(".transcript")!;
    let height = 800;
    Object.defineProperties(transcript, { clientHeight: { configurable: true, value: 200 }, scrollHeight: { configurable: true, get: () => height } });
    act(() => resize());
    transcript.scrollTop = 100; fireEvent.scroll(transcript);
    await user.type(composer, "new question");
    expect(transcript.scrollTop).toBe(100);
    await user.keyboard("{Enter}");
    height = 1200; act(() => resize());
    expect(transcript.scrollTop).toBe(1200);
    transcript.scrollTop = 100; fireEvent.scroll(transcript);
    await user.type(composer, "queued question{Enter}");
    act(() => resize());
    expect(transcript.scrollTop).toBe(100);
    expect(request.mock.calls.filter(([action]) => action === "runPrompt")).toHaveLength(1);
    await act(async () => releasePrompt());
  });

  it("keeps a narrow empty conversation at the start of its welcome content", async () => {
    let resized = () => {};
    vi.stubGlobal("ResizeObserver", class { constructor(callback: () => void) { resized = callback; } observe() {} disconnect() {} });
    installDesktopApi();
    render(<App />);
    await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    const transcript = document.querySelector<HTMLDivElement>(".transcript")!;
    Object.defineProperties(transcript, { clientHeight: { configurable: true, value: 220 }, scrollHeight: { configurable: true, value: 800 } });
    act(() => resized());
    expect(transcript.scrollTop).toBe(0);
  });

  it("observes the real message column when an empty conversation receives its first reply", async () => {
    const observe = vi.fn();
    let resize = () => {};
    vi.stubGlobal("ResizeObserver", class { constructor(callback: () => void) { resize = callback; } observe = observe; disconnect() {} });
    const { emitCoreEvent, releasePrompt } = installDesktopApi({ gatePrompt: true });
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    await user.type(composer, "first reply{Enter}");
    const content = document.querySelector(".message-column");
    expect(observe).toHaveBeenCalledWith(content);
    const transcript = document.querySelector<HTMLDivElement>(".transcript")!;
    Object.defineProperties(transcript, { clientHeight: { configurable: true, value: 200 }, scrollHeight: { configurable: true, get: () => height } });
    let height = 900;
    act(() => resize());
    expect(transcript.scrollTop).toBe(900);
    await act(async () => {
      emitCoreEvent({ type: "ui.event", event: { event: "tool_start", tool_call_id: "same-id", tool_name: "file_ops" } });
      await new Promise(resolve => setTimeout(resolve, 80));
    });
    transcript.scrollTop = 100; fireEvent.scroll(transcript);
    expect(screen.queryByRole("button", { name: "回到最新" })).toBeNull();
    height = 1200;
    act(() => { emitCoreEvent({ type: "ui.event", event: { event: "tool_result", tool_call_id: "same-id", output: "much longer result" } }); resize(); });
    expect(transcript.scrollTop).toBe(100);
    expect(await screen.findByRole("button", { name: "回到最新" })).toBeTruthy();
    await act(async () => releasePrompt());
  });

  it("continues rendering sustained deltas and flushes the complete formatted text when a turn ends", async () => {
    const { request, emitCoreEvent, releasePrompt } = installDesktopApi({ gatePrompt: true });
    const original = request.getMockImplementation()!;
    const finalText = "chunk0 chunk1 chunk2 chunk3 chunk4 **FINAL_MARKER**";
    request.mockImplementation(async (action, payload) => {
      const response = await original(action, payload);
      if (action !== "runPrompt") return response;
      const result = response as Extract<typeof response, { result: { success: boolean } }>;
      return { ...result, result: { ...result.result, success: false, output_text: finalText, error: "Provider disconnected" } };
    });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await screen.findByRole("textbox", { name: /向 Test Model 提问/ }), "continuous reply{Enter}");
    vi.useFakeTimers();
    for (let index = 0; index < 5; index += 1) {
      await act(async () => { emitCoreEvent({ type: "assistant.delta", text: `chunk${index} ` }); await vi.advanceTimersByTimeAsync(60); });
    }
    expect(document.querySelector(".live-message .markdown")?.textContent).toContain("chunk2");
    await act(async () => { emitCoreEvent({ type: "assistant.delta", text: "**FINAL_MARKER**" }); await vi.advanceTimersByTimeAsync(40); releasePrompt(); });
    expect(document.querySelector(".live-message .markdown strong")?.textContent).toBe("FINAL_MARKER");
    expect(document.querySelector(".live-message .markdown")?.textContent).toContain("chunk4");
    vi.useRealTimers();
  });

  it.each([false, true])("shows an intentional stop neutrally and clears stopping controls (transport rejection: %s)", async (rejected) => {
    const { request, releasePrompt } = installDesktopApi({ gatePrompt: true });
    const original = request.getMockImplementation()!;
    const detail = "Error processing message: Run stopped by user; check completed actions before continuing.";
    request.mockImplementation(async (action, payload) => {
      const response = await original(action, payload);
      if (action !== "runPrompt") return response;
      if (rejected) throw new Error(detail);
      const result = response as Extract<typeof response, { result: { success: boolean } }>;
      return { ...result, result: { ...result.result, success: false, error: detail, output_text: detail } };
    });
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    await user.type(composer, "stop this turn{Enter}");
    await user.click(screen.getByRole("button", { name: "停止" }));
    expect(await screen.findByText("正在停止，等待当前操作结束")).toBeTruthy();
    await act(async () => releasePrompt());
    expect(await screen.findByText("已停止")).toBeTruthy();
    expect(screen.queryByText("正在停止，等待当前操作结束")).toBeNull();
    expect(screen.queryByText("本轮出错")).toBeNull();
    expect(screen.queryByRole("button", { name: "强制停止" })).toBeNull();
    expect((composer as HTMLTextAreaElement).disabled).toBe(false);
  });

  it("shows a failed live turn once when the saved transcript already contains its messages", async () => {
    const { request, emitCoreEvent } = installDesktopApi();
    const original = request.getMockImplementation()!;
    let sent = false;
    request.mockImplementation(async (action, payload) => {
      const response = await original(action, payload);
      if (action === "runPrompt") {
        sent = true;
        emitCoreEvent({ type: "run.started", history_message_count: 1 });
        emitCoreEvent({ type: "assistant.delta", text: "Partial live answer" });
        const result = response as Extract<typeof response, { result: { success: boolean } }>;
        return { ...result, result: { ...result.result, success: false, error: "Provider disconnected", output_text: "Partial live answer" } };
      }
      if (action === "getSession" && sent) return { type: "session", session: { ...baseSession, messages: [
        { role: "user", content: "Earlier saved turn" },
        { role: "user", content: "Fail this turn" },
        { role: "assistant", content: "Partial live answer" },
      ] }, sessions: desktopState.sessions };
      return response;
    });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await screen.findByRole("textbox", { name: /向 Test Model 提问/ }), "Fail this turn{Enter}");
    await screen.findByText("Provider disconnected");
    expect(await screen.findByText("Earlier saved turn")).toBeTruthy();
    expect(screen.getAllByText("Fail this turn", { selector: ".user-text" })).toHaveLength(1);
    expect(screen.getAllByText("Partial live answer")).toHaveLength(1);
  });

  it.each([true, false])("summarizes an HTML provider failure while retaining its complete diagnostic (Cloudflare: %s)", async (cloudflare) => {
    const { request } = installDesktopApi();
    const original = request.getMockImplementation()!;
    const detail = `Error processing message: <!DOCTYPE html><html><title>${cloudflare ? "Attention Required! | Cloudflare" : "Gateway error"}</title><body>original diagnostic</body></html>`;
    request.mockImplementation(async (action, payload) => {
      if (action === "runPrompt") throw new Error(detail);
      return original(action, payload);
    });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await screen.findByRole("textbox", { name: /向 Test Model 提问/ }), "try provider{Enter}");
    expect(await screen.findByText(cloudflare
      ? "供应商返回了 Cloudflare 拦截页面，本轮未获得模型回复。请检查供应商地址或稍后重试。"
      : "供应商返回了网页内容，本轮未获得模型回复。请检查供应商地址或查看原始错误。")).toBeTruthy();
    const details = document.querySelector<HTMLDetailsElement>(".inline-error-details")!;
    expect(details.open).toBe(false);
    expect(details.querySelector("pre")?.textContent).toBe(detail);
    await user.click(screen.getByText("查看原始错误"));
    expect(details.open).toBe(true);
    await user.click(details.closest(".inline-error")!.querySelector<HTMLButtonElement>(".inline-error-copy")!);
    expect(await navigator.clipboard.readText()).toBe(detail);
  });

  it.each([false, true])("keeps failed-turn diagnostics in the transcript and leaves the composer available for retry (transport error: %s)", async (transportError) => {
    const resizes: Array<() => void> = [];
    vi.stubGlobal("ResizeObserver", class { constructor(private callback: () => void) {} observe(element: Element) { if (element.classList.contains("transcript")) resizes.push(this.callback); } disconnect() {} });
    const { api, emitCoreEvent } = installDesktopApi();
    const original = api.request.getMockImplementation()!;
    const detail = "Provider failed with a long diagnostic. 中文 " + "details ".repeat(120);
    api.request.mockImplementation(async (action, payload) => {
      if (action === "runPrompt" && transportError) throw new Error(detail);
      const response = await original(action, payload);
      if (action !== "runPrompt") return response;
      emitCoreEvent({ type: "assistant.delta", text: detail });
      const failed = response as Extract<typeof response, { result: { success: boolean } }>;
      return { ...failed, result: { ...failed.result, success: false, output_text: detail, error: detail } };
    });
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    await user.type(composer, "retry this request{Enter}");
    await screen.findByText("本轮出错");
    expect(document.querySelectorAll(".inline-error")).toHaveLength(1);
    expect(document.querySelector(".inline-error-body")?.textContent).toBe(detail);
    expect(document.querySelector(".composer .persistent-error")).toBeNull();
    expect(screen.getAllByText(detail.trim())).toHaveLength(1);
    expect((composer as HTMLTextAreaElement).disabled).toBe(false);
    const transcript = document.querySelector<HTMLDivElement>(".transcript")!;
    Object.defineProperty(transcript, "clientHeight", { configurable: true, value: 220 });
    act(() => resizes.forEach(resize => resize()));
    // Resizing bounds only the error diagnostic. An inherited variable on the
    // whole transcript would invalidate the styles of every loaded message.
    expect(document.querySelector<HTMLElement>(".inline-error")!.style.getPropertyValue("--transcript-height")).toBe("220px");
    expect(transcript.style.getPropertyValue("--transcript-height")).toBe("");
    await user.type(composer, " revised");
    expect((composer as HTMLTextAreaElement).value).toContain("revised");
  });

  it("persists a custom user label and renders it on existing messages", async () => {
    const { api } = installDesktopApi({ initialSession: { ...baseSession, messages: [{ role: "user", content: "Hello from me" }] } });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Hello from me");
    await user.click(screen.getByRole("button", { name: "设置" }));
    await user.click(screen.getByRole("button", { name: "对话显示" }));
    await user.clear(screen.getByRole("textbox", { name: "显示名称" }));
    await user.type(screen.getByRole("textbox", { name: "显示名称" }), "  Lin  ");
    await user.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(api.setUiPreferences).toHaveBeenCalledWith({ userDisplayName: "  Lin  " }));
    await user.click(screen.getByRole("button", { name: "设置" }));
    expect(await screen.findByText("Lin")).toBeTruthy();
  });

  it("shows Git branches and switches to a selected branch", async () => {
    const { api } = installDesktopApi();
    api.gitStatus.mockResolvedValue({ repositoryRoot: "C:/workspace", currentBranch: "main", dirtyCount: 2, localBranches: ["main", "feature/ui"], remoteBranches: ["origin/remote-only"] });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: /main.*2 项改动/ }));
    const menu = screen.getByRole("dialog", { name: "Git 分支" });
    expect(within(menu).getByText("远端分支")).toBeTruthy();
    await user.click(within(menu).getByRole("button", { name: "feature/ui" }));
    await waitFor(() => expect(api.switchGitBranch).toHaveBeenCalledWith("feature/ui", false));
  });

  it("imports dropped files into structured cards without changing the text", async () => {
    const { api } = installDesktopApi();
    api.importDroppedFiles.mockResolvedValue([{ name: "notes.txt", relativePath: ".reverie/attachments/notes.txt", size: 5 }]);
    render(<App />);
    await screen.findByRole("button", { name: "选择任意文件作为附件" });
    const composer = document.querySelector(".composer") as HTMLElement;
    const file = new File(["notes"], "notes.txt", { type: "text/plain" });
    const dataTransfer = { types: ["Files"], files: [file], dropEffect: "none" };
    fireEvent.dragEnter(composer, { dataTransfer });
    expect(screen.getByText("拖放文件以添加附件")).toBeTruthy();
    fireEvent.drop(composer, { dataTransfer });
    await waitFor(() => expect(api.importDroppedFiles).toHaveBeenCalledWith([file], "C:/workspace"));
    await waitFor(() => expect(document.querySelector(".attachment-card")?.textContent).toContain("notes.txt"));
    expect((screen.getByRole("textbox", { name: /向 Test Model 提问/ }) as HTMLTextAreaElement).value).toBe("");
    expect(screen.getByRole("button", { name: "发送" }).hasAttribute("disabled")).toBe(false);
  });

  it("keeps files dropped for the next draft when the current turn finishes", async () => {
    const { api, request, releasePrompt } = installDesktopApi({ gatePrompt: true });
    api.importDroppedFiles.mockResolvedValue([{ name: "next.txt", relativePath: ".reverie/attachments/next.txt", size: 4 }]);
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ }) as HTMLTextAreaElement;
    await user.type(composer, "first question{Enter}");
    await waitFor(() => expect(request).toHaveBeenCalledWith("runPrompt", expect.objectContaining({ prompt: "first question" })));

    const file = new File(["next"], "next.txt", { type: "text/plain" });
    fireEvent.drop(document.querySelector(".composer") as HTMLElement, { dataTransfer: { types: ["Files"], files: [file] } });
    await waitFor(() => expect(document.querySelector(".attachment-card")?.textContent).toContain("next.txt"));
    releasePrompt();
    expect(await screen.findByText("Cache inspection complete")).toBeTruthy();
    expect(composer.value).toBe("");
    expect(document.querySelector(".attachment-card")?.textContent).toContain("next.txt");
  });

  it("paints from a compact bootstrap before hydrating the complete desktop state", async () => {
    const { request } = installDesktopApi();
    render(<App />);

    await screen.findByRole("button", { name: "命令面板" });
    expect(request).toHaveBeenCalledWith("initialize", {
      projectRoot: "C:/workspace",
      deferPayloads: true,
    });
    expect(request).toHaveBeenCalledWith("getState", {});
  });

  it("keeps errors visible for twelve seconds and allows early dismissal", async () => {
    const { request } = installDesktopApi();
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "技能" }));
    const refresh = screen.getByRole("button", { name: "重新扫描" });
    vi.useFakeTimers();
    const triggerError = async () => {
      request.mockRejectedValueOnce(new Error("Unable to refresh skills.\nCheck the resource path."));
      await act(async () => { fireEvent.click(refresh); });
    };
    await triggerError();
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Check the resource path.");
    await act(async () => { await vi.advanceTimersByTimeAsync(11_999); });
    expect(screen.getByRole("alert")).toBe(alert);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(screen.queryByRole("alert")).toBeNull();
    await triggerError();
    fireEvent.click(within(screen.getByRole("alert")).getByRole("button", { name: "关闭" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it.each(["writer", "computer-controller"])("keeps skills browsable with mode guidance in %s", async (mode) => {
    installDesktopApi({ initialState: { ...desktopState, skills: { ...desktopState.skills, mode } } });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "技能" }));
    const note = await screen.findByRole("note");
    expect(note.textContent).toContain("Reverie");
    expect(note.textContent).toContain("固定状态会保留");
    expect(screen.getByText("photo-to-3d")).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "筛选技能" })).toBeTruthy();
  });

  it("opens an accessible command dialog, traps focus, and restores focus on Escape", async () => {
    installDesktopApi();
    const user = userEvent.setup();
    render(<App />);
    const commandButton = await screen.findByRole("button", { name: "命令面板" });
    commandButton.focus();

    await user.keyboard("{Control>}k{/Control}");
    const dialog = await screen.findByRole("dialog", { name: "命令面板" });
    const search = within(dialog).getByRole("combobox", { name: "搜索命令、工具和功能…" });
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

  it("creates a new chat from the active project's overflow menu", async () => {
    const { request } = installDesktopApi({ initialSession: { ...baseSession, messages: [{ role: "user", content: "Existing work" }] } });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "命令面板" });

    await user.click(screen.getByRole("button", { name: "管理项目 workspace" }));
    const newChatButtons = screen.getAllByRole("button", { name: "新对话" });
    await user.click(newChatButtons[newChatButtons.length - 1]);

    await waitFor(() => expect(request).toHaveBeenCalledWith("createSession", {}));
    expect((await screen.findAllByText("New session")).length).toBeGreaterThan(0);
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

  it.each([true, false])("uses the selected catalog entry for manual-model photo capability (%s)", async vision => {
    const source = desktopState.models.sources[0];
    const initialState: DesktopState = { ...desktopState,
      workspace: { ...desktopState.workspace, active_source: "standard" },
      models: { ...desktopState.models, active_source: "standard", active_model: { id: "provider-model-id", display_name: "Test Model", provider: "openai-chat" }, sources: [{ ...source, id: "standard", selected_model_id: "0", models: [{ ...source.models[0], id: "0", model: "provider-model-id", vision }] }] },
    };
    const { api } = installDesktopApi({ initialState }); render(<App />);
    await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    api.importDroppedFiles.mockResolvedValue([{ name: "photo.png", relativePath: "photo.png", size: 12 }]);
    fireEvent.drop(document.querySelector(".composer")!, { dataTransfer: { types: ["Files"], files: [new File(["photo"], "photo.png", { type: "image/png" })] } });
    await screen.findByRole("button", { name: "移除附件 photo.png" });
    expect(screen.queryByText("图片输入能力未知，请选择明确支持图片的模型")).toBeNull();
    expect(Boolean(screen.queryByText("当前模型不支持图片，请切换模型或移除图片"))).toBe(!vision);
  });

  it("retains photo identity in the user message while the request is running", async () => {
    const { api } = installDesktopApi({ gatePrompt: true });
    render(<App />);
    await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    api.importDroppedFiles.mockResolvedValue([{ name: "running.png", relativePath: "running.png", size: 12 }]);
    fireEvent.drop(document.querySelector(".composer")!, { dataTransfer: { types: ["Files"], files: [new File(["photo"], "running.png", { type: "image/png" })] } });
    await screen.findByRole("button", { name: "移除附件 running.png" });
    await userEvent.setup().click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByRole("button", { name: "打开文件预览 running.png" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "停止" })).toBeTruthy();
  });

  it("shows a pure local photo in history and opens its workspace preview", async () => {
    installDesktopApi({ initialSession: { ...baseSession, messages: [{ role: "user", content: [{ type: "local_image", file_path: "photos/中文.png", file_name: "中文.png", file_size: 1024 }] }] } });
    const opened = vi.fn();
    window.addEventListener("reverie:file-open", opened);
    try {
      render(<App />);
      await userEvent.setup().click(await screen.findByRole("button", { name: "打开文件预览 中文.png" }));
      expect(opened.mock.calls[0][0].detail).toEqual({ path: "photos/中文.png" });
    } finally { window.removeEventListener("reverie:file-open", opened); }
  });

  it("keeps text and local photos in transcript content order", async () => {
    installDesktopApi({ initialSession: { ...baseSession, messages: [{ role: "user", content: [
      { type: "text", text: "before photo" }, { type: "local_image", file_path: "first.png", file_name: "first.png" },
      { type: "text", text: "between photos" }, { type: "local_image", file_path: "second.png", file_name: "second.png" },
    ] }] } });
    const mounted = render(<App />);
    await screen.findByRole("button", { name: "打开文件预览 second.png" });
    expect([...mounted.container.querySelectorAll(".message.user .message-body > *")].map(node => node.textContent)).toEqual(["before photo", "first.png", "between photos", "second.png"]);
  });

  it("opens a fresh conversation when an empty transcript has an unsent photo draft", async () => {
    const { request, api } = installDesktopApi(); const user = userEvent.setup(); render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ }) as HTMLTextAreaElement;
    await user.type(composer, "unsent photo draft");
    api.importDroppedFiles.mockResolvedValue([{ name: "draft.png", relativePath: "draft.png", size: 12 }]);
    const file = new File(["photo"], "draft.png", { type: "image/png" });
    fireEvent.drop(document.querySelector(".composer")!, { dataTransfer: { types: ["Files"], files: [file] } });
    await screen.findByRole("button", { name: "移除附件 draft.png" });
    await user.click(screen.getAllByRole("button", { name: /新对话/ })[0]);
    await waitFor(() => expect(request).toHaveBeenCalledWith("createSession", {}));
    expect(composer.value).toBe(""); expect(screen.queryByRole("button", { name: "移除附件 draft.png" })).toBeNull();
    await user.click(screen.getAllByRole("button", { name: /Initial session/ })[0]);
    await waitFor(() => expect(composer.value).toBe("unsent photo draft"));
    expect(screen.getByRole("button", { name: "移除附件 draft.png" })).toBeTruthy();
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
      source: "test-source",
      model: "test-model",
      mode: "reverie",
      attachments: [],
      projectRoot: "C:/workspace",
    }));
    expect(await screen.findByText("Cache inspection complete")).toBeTruthy();
  });

  it("switches output mode from the composer, preserves the draft and uses the saved core preference", async () => {
    const { request } = installDesktopApi({ settingItems: [{ name: "Stream Responses", key: "stream_responses", kind: "bool", description: "", value: false }] });
    const user = userEvent.setup();
    render(<App />);
    const toggle = await screen.findByRole("button", { name: "流式输出" });
    const composer = screen.getByRole("textbox", { name: /向 Test Model 提问/ }) as HTMLTextAreaElement;
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    await user.type(composer, "保留中文草稿");
    toggle.focus();
    await user.keyboard(" ");
    await waitFor(() => expect(toggle.getAttribute("aria-pressed")).toBe("true"));
    expect(request).toHaveBeenCalledWith("setSetting", { key: "stream_responses", value: true });
    expect(composer.value).toBe("保留中文草稿");
    expect(request.mock.calls.filter(([action]) => action === "runPrompt")).toHaveLength(0);
    expect(document.activeElement).toBe(toggle);
    await user.keyboard("{Enter}");
    await waitFor(() => expect(toggle.getAttribute("aria-pressed")).toBe("false"));
    await user.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("runPrompt", expect.not.objectContaining({ stream: true })));
  });

  it("keeps output-mode state honest while saving and after a failed save", async () => {
    const { request } = installDesktopApi();
    const original = request.getMockImplementation()!;
    let rejectSave: (error: Error) => void = () => {};
    const saveGate = new Promise<never>((_, reject) => { rejectSave = reject; });
    request.mockImplementation(async (action, payload) => action === "setSetting" ? saveGate : original(action, payload));
    const user = userEvent.setup();
    render(<App />);
    const toggle = await screen.findByRole("button", { name: "流式输出" }) as HTMLButtonElement;
    const composer = screen.getByRole("textbox", { name: /向 Test Model 提问/ }) as HTMLTextAreaElement;
    await user.type(composer, "draft during save");
    await user.click(toggle);
    expect(toggle.disabled).toBe(false);
    expect(toggle.getAttribute("aria-disabled")).toBe("true");
    expect(document.activeElement).toBe(toggle);
    expect(toggle.getAttribute("aria-busy")).toBe("true");
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    await user.click(toggle);
    await user.click(screen.getByRole("button", { name: "发送" }));
    expect(request.mock.calls.filter(([action]) => action === "setSetting")).toHaveLength(1);
    expect(request.mock.calls.filter(([action]) => action === "runPrompt")).toHaveLength(0);
    await act(async () => rejectSave(new Error("Cannot save output mode")));
    await screen.findByText("Cannot save output mode");
    expect(toggle.disabled).toBe(false);
    expect(toggle.getAttribute("aria-disabled")).toBe("false");
    expect(toggle.getAttribute("aria-pressed")).toBe("true");
    expect(composer.value).toBe("draft during save");
  });

  it("changes the next output mode while a turn is running without cancelling or sending the pending draft", async () => {
    const { request, releasePrompt } = installDesktopApi({ gatePrompt: true });
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ }) as HTMLTextAreaElement;
    await user.type(composer, "start this turn{Enter}");
    const toggle = screen.getByRole("button", { name: "流式输出" });
    expect(toggle.title).toContain("下一轮");
    await user.type(composer, "下一轮草稿");
    await user.click(toggle);
    await waitFor(() => expect(toggle.getAttribute("aria-pressed")).toBe("false"));
    expect(request.mock.calls.filter(([action]) => ["runPrompt", "resumePrompt"].includes(action))).toHaveLength(1);
    expect(request.mock.calls.filter(([action]) => ["stopPrompt", "steerPrompt"].includes(action))).toHaveLength(0);
    expect(screen.getByRole("button", { name: "停止" })).toBeTruthy();
    expect(composer.value).toBe("下一轮草稿");
    await act(async () => releasePrompt());
  });

  it("shows the existing SenseNova Writer streaming requirement truthfully", async () => {
    installDesktopApi({ initialState: { ...desktopState, workspace: { ...desktopState.workspace, mode: "writer", active_source: "sensenova" }, settings: { ...desktopState.settings, items: [{ name: "Stream Responses", key: "stream_responses", kind: "bool", description: "", value: false }] } } });
    render(<App />);
    const toggle = await screen.findByRole("button", { name: "流式输出" }) as HTMLButtonElement;
    expect(toggle.disabled).toBe(true);
    expect(toggle.getAttribute("aria-pressed")).toBe("true");
    expect(toggle.title).toContain("SenseNova");
  });

  it("keeps a queued conversation running in the background without clearing another draft", async()=>{
    const {request,releasePrompt}=installDesktopApi({gatePrompt:true});const user=userEvent.setup();render(<App />);
    const composer=await screen.findByRole("textbox",{name:/向 Test Model 提问/}) as HTMLTextAreaElement;
    await user.type(composer,"first background turn{Enter}");await waitFor(()=>expect(request).toHaveBeenCalledWith("runPrompt",expect.objectContaining({prompt:"first background turn"})));
    await user.type(composer,"background queued turn{Enter}");
    await user.click(screen.getAllByRole("button",{name:/Cache investigation/})[0]);
    await waitFor(()=>expect(request).toHaveBeenCalledWith("getSession",{sessionId:"session-2"}));
    await user.type(composer,"other session draft");releasePrompt();
    await waitFor(()=>expect(request).toHaveBeenCalledWith("runPrompt",expect.objectContaining({prompt:"background queued turn",sessionId:"session-1"})));
    expect(composer.value).toBe("other session draft");expect(screen.getByText("Cache investigation",{selector:"strong"})).toBeTruthy();
  });

  it("keeps queued attachments bound to their original workspace after switching projects", async () => {
    const options = { gatePrompt: true, initialState: { ...desktopState } };
    const { request, api, releasePrompt } = installDesktopApi(options);
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ }) as HTMLTextAreaElement;
    await user.type(composer, "first project turn{Enter}");
    await waitFor(() => expect(request).toHaveBeenCalledWith("runPrompt", expect.objectContaining({ prompt: "first project turn" })));
    api.importDroppedFiles.mockResolvedValue([{ name: "photo.png", relativePath: "photo.png", size: 12 }]);
    const file = new File(["photo bytes"], "photo.png", { type: "image/png" });
    fireEvent.drop(document.querySelector(".composer")!, { dataTransfer: { types: ["Files"], files: [file] } });
    await screen.findByRole("button", { name: "移除附件 photo.png" });
    await user.type(composer, "queued photo{Enter}");
    api.switchWorkspace.mockImplementation(async root => {
      options.initialState = { ...desktopState, workspace: { ...desktopState.workspace, project_root: root, project_name: "other" } };
      return root;
    });
    act(() => window.dispatchEvent(new CustomEvent("reverie:workspace-open", { detail: { root: "C:/other" } })));
    await waitFor(() => expect(request).toHaveBeenCalledWith("createSession", {}));
    await screen.findAllByText("New session");
    await user.type(composer, "other project draft");
    releasePrompt();
    await waitFor(() => expect(request).toHaveBeenCalledWith("runPrompt", expect.objectContaining({
      prompt: "queued photo", sessionId: "session-1", projectRoot: "C:/workspace",
      attachments: [expect.objectContaining({ relativePath: "photo.png" })],
    })));
    expect(composer.value).toBe("other project draft");
  });

  it("queues without restarting the core and runs the next message after completion", async () => {
    const { request, api, releasePrompt } = installDesktopApi({ gatePrompt: true });
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ }) as HTMLTextAreaElement;

    await user.type(composer, "first question{Enter}");
    // The turn is held in flight, so the app is in its running state.
    await waitFor(() => expect(request).toHaveBeenCalledWith(
      "runPrompt",
      expect.objectContaining({ prompt: "first question" }),
    ));

    // The composer must stay enabled so the next prompt can be drafted mid-stream.
    expect(composer.disabled).toBe(false);
    await user.type(composer, "drafted while streaming");
    expect(composer.value).toContain("drafted while streaming");

    await user.type(composer, "{Enter}");
    await screen.findByText("drafted while streaming");
    expect(api.cancel).not.toHaveBeenCalled();
    expect(request.mock.calls.filter(call => call[0] === "runPrompt")).toHaveLength(1);
    releasePrompt();
    await waitFor(() => expect(request).toHaveBeenCalledWith(
      "runPrompt",
      expect.objectContaining({ prompt: "drafted while streaming" }),
    ));

  });

  it("jumps back into the active conversation when its title is double-clicked from another view", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "命令面板" });

    // Leave the chat view for Settings.
    await user.click(await screen.findByRole("button", { name: "设置" }));
    expect(await screen.findByText("通用设置")).toBeTruthy();

    // Double-clicking the active conversation's title returns to its content.
    const row = [...document.querySelectorAll(".session-item")]
      .find((item) => item.textContent?.includes("Initial session"));
    if (!row) throw new Error("No active session row");
    await user.dblClick(row);

    await waitFor(() => expect(screen.queryByText("通用设置")).toBeNull());
    expect(screen.getByRole("textbox", { name: /向 Test Model 提问/ })).toBeTruthy();
  });

  it("restores a conversation's unsent draft after a restart", async () => {
    installDesktopApi();
    const user = userEvent.setup();
    const first = render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ }) as HTMLTextAreaElement;

    await user.type(composer, "a half-written thought");
    await waitFor(() => expect(composer.value).toBe("a half-written thought"));

    // Simulate a sudden quit: tear the window down without sending.
    first.unmount();

    // Reopen: a fresh window reads the same crash-safe store and reappears
    // exactly where the composer was left for this conversation.
    render(<App />);
    const restored = await screen.findByRole("textbox", { name: /向 Test Model 提问/ }) as HTMLTextAreaElement;
    await waitFor(() => expect(restored.value).toBe("a half-written thought"));
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

    await user.click(within(dialog).getByRole("button", { name: "我想额外说点" }));
    await user.type(within(dialog).getByRole("textbox"), "先解释清楚再执行");
    await user.click(within(dialog).getByRole("button", { name: "发送并拒绝本次" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("resolveApproval", {
      approvalId: "approval-1",
      projectRoot: "C:/workspace",
      sessionId: "session-1",
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
      projectRoot: "C:/workspace",
      sessionId: "session-1",
      decision: "deny",
    }));
  });

  it("routes /compact with focus through the dedicated context action", async () => {
    const { request } = installDesktopApi();
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });

    await user.click(screen.getByRole("button", { name: "打开工作面板" }));
    await user.click(screen.getByRole("button", { name: "上下文" }));
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

    await user.click(screen.getByRole("button", { name: "打开工作面板" }));
    await user.click(screen.getByRole("button", { name: "上下文" }));
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

    await user.click(within(dialog).getByRole("button", { name: /高/ }));
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

  it("loads image models on demand, explains missing Pollinations credentials, and switches the image model", async () => {
    const imageModels: ImageModelSourcesState = {
      active_source: "local",
      active_model: null,
      sources: [{
        id: "local", display_name: "Local (ComfyUI)", active: true, enabled: true,
        selected_model_id: "", api_key_available: true, requires_api_key: false,
        configured_count: 0, models: [],
      }, {
        id: "pollinations", display_name: "Pollinations", active: false, enabled: true,
        selected_model_id: "flux", api_key_available: false, requires_api_key: true,
        configured_count: 1, models: [{
          id: "flux", display_name: "Flux", description: "", supports_edit: false,
          input_modalities: ["text"], output_modalities: ["image"],
          supported_sizes: ["1024x1024"], default_size: "1024x1024", exists: true,
        }],
      }, {
        id: "sensenova", display_name: "SenseNova", active: false, enabled: true,
        selected_model_id: "sensenova-u1-fast", api_key_available: true, requires_api_key: true,
        configured_count: 1, models: [{
          id: "sensenova-u1.5-lite", display_name: "SenseNova U1.5 Lite", description: "",
          supports_edit: true, input_modalities: ["text", "image"], output_modalities: ["image"],
          supported_sizes: ["2048x2048"], default_size: "2048x2048", exists: true,
        }],
      }],
    };
    const { request } = installDesktopApi({ imageModels });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "设置" });
    expect(request).not.toHaveBeenCalledWith("refreshImageModelSources", {});

    await user.click(screen.getByRole("button", { name: "设置" }));
    await user.click(screen.getByRole("button", { name: "生图模型" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("refreshImageModelSources", {}));
    await user.click(await screen.findByRole("button", { name: "Pollinations" }));
    expect(screen.getByText("需要 API 密钥")).toBeTruthy();
    expect(screen.getByText("使用 /tti source pollinations 配置 API 密钥，然后刷新。") ).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "SenseNova" }));
    await user.click(screen.getByRole("button", { name: /SenseNova U1.5 Lite/ }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("selectImageModel", {
      source: "sensenova", modelId: "sensenova-u1.5-lite",
    }));
    expect(await screen.findByText("已切换生图模型到 SenseNova U1.5 Lite")).toBeTruthy();
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

    expect((await screen.findByRole("button", { name: "选择工作模式" })).textContent).toContain("Computer");
    expect(container.querySelector(".model-trigger")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "打开工作面板" }));
    fireEvent.click(screen.getByRole("button", { name: "上下文" }));
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
    const inspectorHandle = screen.getByRole("separator", { name: "调整工作面板宽度" });
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

  it("shows complete long model IDs for built-in and custom providers", async () => {
    const modelId = "ai21labs/jamba-1.5-large-instruct-2026-extended";
    const model = { ...desktopState.models.sources[0].models[0], id: modelId, display_name: "Jamba Large" };
    const customModel = { ...customProviderRecord().models[0], id: modelId, display_name: "Jamba Large" };
    const provider = customProviderRecord({ models: [customModel] });
    const customSource: ModelSource = {
      id: "custom",
      display_name: "Custom Provider",
      active: false,
      selected_model_id: "",
      selected_reasoning: { control: "none", options: [], value: "" },
      models: [],
      config_fields: [],
      custom_providers: [provider],
    };
    const initialState = {
      ...desktopState,
      models: {
        ...desktopState.models,
        sources: [{ ...desktopState.models.sources[0], models: [model] }, customSource],
      },
    };
    installDesktopApi({ initialState });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "命令面板" });

    await user.click(screen.getByRole("button", { name: "设置" }));
    await user.click(await screen.findByRole("button", { name: "模型与提供商" }));
    expect(screen.getByText(modelId).getAttribute("title")).toBe(modelId);

    await user.click(await screen.findByRole("button", { name: /Custom Provider/ }));
    expect(screen.getByText(modelId).getAttribute("title")).toBe(modelId);
  });

  it("adds a custom provider from the desktop page with the four documented fields", async () => {
    const { request } = installDesktopApi({ customProviders: [] });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "命令面板" });

    await openCustomProviderPage(user);
    expect(screen.getByText("还没有自定义 Provider")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "添加 Provider" }));
    const dialog = await screen.findByRole("dialog", { name: "添加 Provider" });
    expect(within(dialog).getByText("POST <base>/chat/completions —— 使用 Bearer 密钥。")).toBeTruthy();
    const submit = within(dialog).getByRole("button", { name: "添加 Provider" });
    expect((submit as HTMLButtonElement).disabled).toBe(true);

    await user.type(within(dialog).getByLabelText("Provider 名称"), "xkiro");
    await user.type(within(dialog).getByLabelText("基础 URL"), "https://api.xkiro.invalid/v1");
    await user.type(within(dialog).getByLabelText("API 密钥"), "sk-live-secret");
    await user.selectOptions(within(dialog).getByLabelText("API 请求格式"), "anthropic");
    await user.click(within(dialog).getByRole("button", { name: "添加 Provider" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("addCustomProvider", {
      provider: { name: "xkiro", base_url: "https://api.xkiro.invalid/v1", api_key: "sk-live-secret", format: "anthropic" },
    }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "添加 Provider" })).toBeNull());
    expect(await screen.findByText("Anthropic 消息")).toBeTruthy();
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
    expect(screen.queryByText("sk-a…env · 来自环境变量")).toBeNull();
    const relaySummary = screen.getByRole("button", { name: /展开模型列表.*relay/ });
    expect(relaySummary.getAttribute("aria-expanded")).toBe("false");
    await user.click(relaySummary);
    expect(screen.getByText("sk-a…env · 来自环境变量")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /收起模型列表.*relay/ }));
    expect(screen.queryByText("sk-a…env · 来自环境变量")).toBeNull();
    await user.click(screen.getByRole("button", { name: /展开模型列表.*relay/ }));
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
    expect(await screen.findByText("64K 上下文")).toBeTruthy();

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

  it("renders long history in batches while keeping every earlier record accessible", async () => {
    const messages: SessionState["messages"] = Array.from({ length: 180 }, (_, index) => ({ role: "user", content: `History record ${index}` }));
    installDesktopApi({ initialSession: { ...baseSession, messages } });
    render(<App />);
    await screen.findByText("History record 179");
    expect(document.querySelectorAll(".transcript .message").length).toBe(60);
    expect(screen.queryByText("History record 0")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "加载更早的消息" }));
    expect(document.querySelectorAll(".transcript .message").length).toBe(120);
    fireEvent.click(screen.getByRole("button", { name: "加载更早的消息" }));
    expect(screen.getByText("History record 0")).toBeTruthy();
    expect(document.querySelectorAll(".transcript .message").length).toBe(180);
    expect(screen.queryByRole("button", { name: "加载更早的消息" })).toBeNull();
  });

  it("restores loaded earlier history and the reading position after changing conversations", async () => {
    const messages: SessionState["messages"] = Array.from({ length: 180 }, (_, index) => ({ role: "user", content: `Reading record ${index}` }));
    installDesktopApi({ initialSession: { ...baseSession, messages } });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Reading record 179");
    await user.click(screen.getByRole("button", { name: "加载更早的消息" }));
    expect(screen.getByText("Reading record 60")).toBeTruthy();
    const transcript = document.querySelector<HTMLDivElement>(".transcript")!;
    Object.defineProperties(transcript, { clientHeight: { configurable: true, value: 300 }, scrollHeight: { configurable: true, value: 4000 } });
    transcript.scrollTop = 320; fireEvent.scroll(transcript);
    await user.click(screen.getAllByRole("button", { name: /Cache investigation/ })[0]);
    await screen.findByText("Investigate cache invalidation");
    await user.click(screen.getAllByRole("button", { name: /Initial session/ })[0]);
    expect(await screen.findByText("Reading record 60")).toBeTruthy();
    expect(document.querySelectorAll(".transcript .message")).toHaveLength(120);
    expect(transcript.scrollTop).toBe(320);
  });

  it("keeps an existing view mounted when an earlier page reveals its older revision", async () => {
    const viewId = "v0123456789abcdef";
    const messages: SessionState["messages"] = Array.from({ length: 80 }, (_, index) => ({ role: "user", content: `View history record ${index}` }));
    for (const [index, revision] of [[9, 1], [69, 2]]) {
      const callId = `history-view-${revision}`;
      messages[index] = { role: "assistant", content: "", tool_calls: [{ id: callId, function: { name: "render_view", arguments: "{}" } }] };
      messages[index + 1] = {
        role: "tool", name: "render_view", tool_call_id: callId,
        content: `Interactive view ready: "History chart revision ${revision}" (view_id=${viewId}, revision=${revision}). It is shown to the user in the Reverie view panel. Summary: History chart.`,
      };
    }
    const { request } = installDesktopApi({ initialSession: { ...baseSession, messages } });
    const original = request.getMockImplementation()!;
    request.mockImplementation(async (action, payload) => action === "getView" ? {
      type: "view.resolved", view: {
        sessionId: baseSession.id, viewId, revision: 2, title: "History chart revision 2", summary: "History chart.",
        mimeType: "text/html", policyId: "local-offline-v1", state: null,
        url: `reverie-view://${baseSession.id}/${viewId}/2/index.html`,
      },
    } as never : original(action, payload));
    const { container } = render(<App />);
    const frame = await waitFor(() => {
      const frame = container.querySelector(".message-column iframe");
      expect(frame).toBeTruthy();
      return frame!;
    });
    const mount = container.querySelector(".message-column .interactive-view-mount");
    expect(mount).toBeTruthy();
    expect(screen.queryByText("View history record 0")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "加载更早的消息" }));

    expect(await screen.findByText("View history record 0")).toBeTruthy();
    expect(container.querySelectorAll(".message-column .interactive-view-mount")).toHaveLength(1);
    expect(container.querySelector(".message-column .interactive-view-mount")).toBe(mount);
    expect(container.querySelector(".message-column iframe")).toBe(frame);
    expect(screen.getByText("History chart revision 2")).toBeTruthy();
    expect(screen.queryByText("History chart revision 1")).toBeNull();
    expect(request.mock.calls.filter(([action]) => action === "getView")).toHaveLength(1);
  });

  it("preserves expanded history and link focus when the first view is appended", async () => {
    const viewId = "v1234567890abcdef";
    const messages: SessionState["messages"] = [{
      role: "assistant", content: "Review the [saved reference](https://example.invalid/reference).", reasoning_content: "Keep this earlier reasoning open.",
    }];
    const { request, releasePrompt } = installDesktopApi({ initialSession: { ...baseSession, messages }, initialPreferences: { expandReasoning: false }, gatePrompt: true });
    const original = request.getMockImplementation()!;
    let appended = false;
    request.mockImplementation(async (action, payload) => {
      if (action === "getView") return { type: "view.resolved", view: {
        sessionId: baseSession.id, viewId, revision: 1, title: "Appended chart", summary: "New chart.",
        mimeType: "text/html", policyId: "local-offline-v1", state: null,
        url: `reverie-view://${baseSession.id}/${viewId}/1/index.html`,
      } } as never;
      const response = await original(action, payload);
      if (action === "runPrompt") appended = true;
      if (action === "getSession" && appended) return { type: "session", session: { ...baseSession, messages: [
        { role: "system", content: "Fresh workspace memory inserted before the visible history." },
        ...JSON.parse(JSON.stringify(messages)),
        { role: "user", content: "Append a chart" },
        { role: "assistant", content: "", tool_calls: [{ id: "appended-view", function: { name: "render_view", arguments: "{}" } }] },
        { role: "tool", name: "render_view", tool_call_id: "appended-view", content: `Interactive view ready: "Appended chart" (view_id=${viewId}, revision=1). It is shown to the user in the Reverie view panel. Summary: New chart.` },
        { role: "assistant", content: "Appended chart is ready." },
      ] }, sessions: desktopState.sessions };
      return response;
    });
    const user = userEvent.setup();
    const { container } = render(<App />);
    const link = await screen.findByRole("link", { name: "saved reference" });
    await user.type(screen.getByRole("textbox", { name: /向 Test Model 提问/ }), "Append a chart{Enter}");
    await waitFor(() => expect(request).toHaveBeenCalledWith("runPrompt", expect.objectContaining({ prompt: "Append a chart" })));
    const reasoning = container.querySelector<HTMLDetailsElement>(".message-column .reasoning-block")!;
    await user.click(reasoning.querySelector("summary")!);
    expect(await screen.findByText("Keep this earlier reasoning open.")).toBeTruthy();
    link.focus();
    expect(document.activeElement).toBe(link);
    await act(async () => releasePrompt());

    expect(await screen.findByText("Appended chart is ready.")).toBeTruthy();
    expect(container.querySelector(".message-column iframe")).toBeTruthy();
    expect(screen.getByRole("link", { name: "saved reference" })).toBe(link);
    expect(container.querySelector(".message-column .reasoning-block")).toBe(reasoning);
    expect(reasoning.open).toBe(true);
    expect(screen.getByText("Keep this earlier reasoning open.")).toBeTruthy();
    expect(document.activeElement).toBe(link);
  });

  it("keeps the streamed answer and reasoning nodes when it is saved and another turn starts", async () => {
    const answer = "Review the [streamed reference](https://example.invalid/streamed).";
    const reasoningText = "Native reasoning remains expandable.";
    const { request, emitCoreEvent, releasePrompt } = installDesktopApi({ gatePrompt: true, initialPreferences: { expandReasoning: false } });
    const original = request.getMockImplementation()!;
    let finished = false;
    request.mockImplementation(async (action, payload) => {
      if (action === "runPrompt" && finished) return new Promise(() => {});
      const response = await original(action, payload);
      if (action === "runPrompt") {
        finished = true;
        const result = response as Extract<typeof response, { result: { success: boolean } }>;
        return { ...result, result: { ...result.result, output_text: answer, thinking_text: reasoningText } };
      }
      if (action === "getSession" && finished) return { type: "session", session: { ...baseSession, messages: [
        { role: "system", content: "Workspace memory." },
        { role: "user", content: "Give a static answer" },
        { role: "assistant", content: answer, reasoning_content: reasoningText },
      ] }, sessions: desktopState.sessions };
      return response;
    });
    const user = userEvent.setup();
    const { container } = render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    await user.type(composer, "Give a static answer{Enter}");
    await waitFor(() => expect(request).toHaveBeenCalledWith("runPrompt", expect.anything()));
    await act(async () => {
      emitCoreEvent({ type: "reasoning.delta", text: reasoningText });
      emitCoreEvent({ type: "assistant.delta", text: answer });
      await new Promise(resolve => setTimeout(resolve, 180));
    });
    const link = await screen.findByRole("link", { name: "streamed reference" });
    const reasoning = container.querySelector<HTMLDetailsElement>(".reasoning-block")!;
    await user.click(reasoning.querySelector("summary")!);
    link.focus();
    await act(async () => releasePrompt());
    await waitFor(() => expect(screen.queryByRole("button", { name: "停止" })).toBeNull());
    expect(screen.getByRole("link", { name: "streamed reference" })).toBe(link);
    expect(container.querySelector(".reasoning-block")).toBe(reasoning);
    expect(reasoning.open).toBe(true);
    expect(document.activeElement).toBe(link);
    await user.type(composer, "A follow-up{Enter}");
    expect(screen.getByRole("link", { name: "streamed reference" })).toBe(link);
    expect(container.querySelector(".reasoning-block")).toBe(reasoning);
  });

  it("requests one context reading after bootstrap and one after a session switch", async () => {
    const { request } = installDesktopApi();
    render(<App />);
    await screen.findByRole("button", { name: "命令面板" });
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 350)); });
    expect(request.mock.calls.filter(([action]) => action === "getContextUsage")).toEqual([
      ["getContextUsage", expect.objectContaining({ sessionId: baseSession.id })],
    ]);
    const row = [...document.querySelectorAll(".session-item")].find((item) => item.textContent?.includes(searchSession.name));
    fireEvent.click(row!);
    await screen.findByText("Investigate cache invalidation");
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 350)); });
    expect(request.mock.calls.filter(([action]) => action === "getContextUsage")).toEqual([
      ["getContextUsage", expect.objectContaining({ sessionId: baseSession.id })],
      ["getContextUsage", expect.objectContaining({ sessionId: searchSession.id })],
    ]);
  });

  it("ignores a context reading that finishes after navigation", async () => {
    const { api } = installDesktopApi();
    const original = api.request.getMockImplementation()!;
    let release: (value: unknown) => void = () => {};
    const gate = new Promise((resolve) => { release = resolve; });
    api.request.mockImplementation(async (action, payload) => {
      if (action === "getContextUsage" && payload.sessionId === baseSession.id) return await gate as never;
      return original(action, payload);
    });
    render(<App />);
    await screen.findByRole("button", { name: "命令面板" });
    await waitFor(() => expect(api.request).toHaveBeenCalledWith("getContextUsage", expect.objectContaining({ sessionId: baseSession.id })));
    const row = [...document.querySelectorAll(".session-item")].find((item) => item.textContent?.includes(searchSession.name));
    fireEvent.click(row!);
    await screen.findByText("Investigate cache invalidation");
    await act(async () => release({ type: "context.usage", usage: {
      total_tokens: 99, max_tokens: 100, percentage: 99, segments: [], tokenizer: { exact: true },
    } }));
    expect(screen.queryByRole("button", { name: /上下文窗口已用 99%/ })).toBeNull();
  });

  it("lets the user return to the current transcript while another session is loading", async () => {
    const { request, releaseSession } = installDesktopApi({ gateSession: true });
    render(<App />);
    await screen.findByRole("button", { name: "命令面板" });
    const row = (name: string) => [...document.querySelectorAll(".session-item")].find((item) => item.textContent?.includes(name))!;
    fireEvent.click(row(searchSession.name));
    fireEvent.doubleClick(row(searchSession.name));
    expect(request.mock.calls.filter(([action]) => action === "getSession").length).toBe(2);
    expect(screen.getByText("正在切换会话")).toBeTruthy();
    fireEvent.click(row(baseSession.name));
    expect(document.querySelector(".transcript")?.getAttribute("aria-busy")).toBe("false");
    await act(async () => releaseSession());
    expect(document.querySelector(".conversation-header")?.textContent).toContain(baseSession.name);
    expect(screen.queryByText("Investigate cache invalidation")).toBeNull();
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
    expect((within(dialog).getByLabelText("基础 URL") as HTMLInputElement).value).toBe("https://api.example.com/v1");
    expect((within(dialog).getByLabelText(/请求路径/) as HTMLInputElement).value).toBe("/chat/completions");
    expect((within(dialog).getByLabelText("提供者") as HTMLSelectElement).value).toBe("openai-chat");
    // The stored key can now be revealed on demand; until the user clicks the
    // eye the field stays empty, and the hint explains how to view or remove it.
    const key = within(dialog).getByLabelText(/API 密钥/) as HTMLInputElement;
    expect(key.value).toBe("");
    expect(key.placeholder).toBe("••••••••");
    expect(within(dialog).getByText("点击眼睛查看，清空并保存即可移除")).toBeTruthy();
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
    expect(screen.getByText("200K 上下文")).toBeTruthy();

    // Reopening proves the blank key left the stored one in place.
    await user.click(screen.getByRole("button", { name: "编辑标准模型" }));
    const reopened = await screen.findByRole("dialog", { name: "编辑标准模型" });
    expect((within(reopened).getByLabelText(/API 密钥/) as HTMLInputElement).placeholder).toBe("••••••••");
    expect((within(reopened).getByLabelText("上下文长度") as HTMLInputElement).value).toBe("200000");
  });

  it("reveals a stored key and clears it by emptying the field and saving", async () => {
    const { request } = installDesktopApi({
      revealedSecret: "sk-stored-secret",
      standardModels: [{
        model: "gpt-5.4",
        model_display_name: "GPT-5.4",
        provider: "openai-chat",
        base_url: "https://api.example.com/v1",
        api_key: "sk-stored-secret",
        max_context_tokens: 128_000,
        supports_vision: false,
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
    const key = within(dialog).getByLabelText(/API 密钥/) as HTMLInputElement;
    expect(key.value).toBe("");

    // Eye pulls the stored key into the field so it can be seen and edited.
    await user.click(within(dialog).getByRole("button", { name: "查看/隐藏密钥" }));
    await waitFor(() => expect(key.value).toBe("sk-stored-secret"));
    await waitFor(() => expect(request).toHaveBeenCalledWith("revealProviderSecret", expect.objectContaining({ kind: "standard", index: 0 })));

    // Emptying the revealed key and saving is an explicit clear.
    await user.clear(key);
    await user.click(within(dialog).getByRole("button", { name: "保存" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("updateStandardModel", expect.objectContaining({
      index: 0,
      clearFields: ["api_key"],
    })));
  });

  it("shows the context-window ring with a per-segment breakdown after a turn", async () => {
    const usage: ContextUsage = {
      tokenizer: { name: "cl100k_base", label: "cl100k", exact: true, detail: "" },
      total_tokens: 5000,
      max_tokens: 100_000,
      remaining_tokens: 95_000,
      percentage: 5,
      overhead_tokens: 100,
      segments: [
        { key: "system_prompt", tokens: 3000, messages: 1, share: 60 },
        { key: "memory", tokens: 800, messages: 2, share: 16 },
        { key: "user", tokens: 1100, messages: 2, share: 22 },
      ],
      reasoning_tokens: 0,
      payload_message_count: 3,
      history_message_count: 2,
      history_limit: 40,
      compaction_tokens: 70_000,
      rotation_tokens: 82_000,
    };
    const { request } = installDesktopApi({ contextUsage: usage });
    const user = userEvent.setup();
    render(<App />);
    const composer = await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    await user.type(composer, "inspect the cache{Enter}");

    await waitFor(() => expect(request).toHaveBeenCalledWith("getContextUsage", expect.anything()));
    const ring = await screen.findByRole("button", { name: /上下文窗口已用 5%/ });
    await user.hover(ring);
    expect(await screen.findByText("系统提示词")).toBeTruthy();
    expect(screen.getByText("记忆")).toBeTruthy();
    expect(screen.getByText("你的消息")).toBeTruthy();
    expect(screen.getByText("3,000")).toBeTruthy();
  });

  it("keeps the inspector mounted while it collapses, and remembers the choice", async () => {
    const { api } = installDesktopApi();
    const user = userEvent.setup();
    const { container } = render(<App />);
    await screen.findByRole("button", { name: "命令面板" });
    const shell = container.querySelector(".app-shell");

    expect(shell?.classList.contains("with-inspector")).toBe(false);
    expect(container.querySelector(".inspector")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "打开工作面板" }));
    await waitFor(() => expect(shell?.classList.contains("with-inspector")).toBe(true));

    await user.click(screen.getByRole("button", { name: "关闭工作面板" }));

    // A pane that unmounts cannot animate out, so it stays in the tree and is
    // only taken out of the accessibility tree and the tab order.
    await waitFor(() => expect(shell?.classList.contains("with-inspector")).toBe(false));
    const inspector = container.querySelector(".inspector");
    expect(inspector).toBeTruthy();
    expect(inspector?.getAttribute("aria-hidden")).toBe("true");
    expect(inspector?.hasAttribute("inert")).toBe(true);
    expect(api.setUiPreferences).toHaveBeenCalledWith({ inspectorOpen: false });

    await user.click(screen.getByRole("button", { name: "打开工作面板" }));

    await waitFor(() => expect(shell?.classList.contains("with-inspector")).toBe(true));
    expect(container.querySelector(".inspector")?.hasAttribute("aria-hidden")).toBe(false);

    await user.click(screen.getByRole("button", { name: "收起右侧栏" }));
    await waitFor(() => expect(shell?.classList.contains("with-inspector")).toBe(false));
    await user.keyboard("{Control>}{Shift>}b{/Shift}{/Control}");
    await waitFor(() => expect(shell?.classList.contains("with-inspector")).toBe(true));
  });

  it("lays out native reasoning as Markdown without preserving inter-block whitespace", async () => {
    const native = "Consider the costs.\n\n1. Check the inputs.\n\n2. Compare totals.\n\n```text\n  keep indentation\n\n  and the blank line\n```";
    const style = document.createElement("style");
    style.textContent = readFileSync("src/styles.css", "utf8");
    document.head.append(style);
    try {
      installDesktopApi({
        initialPreferences: { expandReasoning: true },
        initialSession: { ...baseSession, messages: [
          { role: "user", content: "Compare the costs" },
          { role: "assistant", content: "The total is 3168.", reasoning_content: native },
        ] },
      });
      render(<App />);
      await screen.findByText("The total is 3168.");
      const markdown = document.querySelector(".reasoning-content .markdown") as HTMLElement;
      expect(markdown.querySelectorAll("li")).toHaveLength(2);
      expect(getComputedStyle(markdown).whiteSpace).toBe("normal");
      expect(markdown.querySelector("pre code")?.textContent).toBe("  keep indentation\n\n  and the blank line\n");
    } finally {
      style.remove();
    }
  });

  it("renders a streaming Thinking Tool call as reasoning instead of a silent activity row", async () => {
    const { emitCoreEvent, releasePrompt } = installDesktopApi({ gatePrompt: true, initialPreferences: { expandReasoning: false } });
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

    expect(document.querySelector(".reasoning-block .reasoning-content")).toBeNull();
    await userEvent.setup().click(document.querySelector(".reasoning-block summary") as HTMLElement);
    expect(await screen.findByText("Cache invalidation")).toBeTruthy();
    const reasoning = document.querySelector(".reasoning-block .reasoning-content") as HTMLElement | null;
    expect(reasoning).toBeTruthy();
    expect(within(reasoning!).getByText(/The index is keyed by mtime/)).toBeTruthy();
    expect(within(reasoning!).getByText(/Next: Compare size as well as mtime\./)).toBeTruthy();

    releasePrompt();
    expect(await screen.findByText("Cache inspection complete")).toBeTruthy();
  });

  it("hides provisional prose stored beside a thinking-only tool call", async () => {
    const provisional = "This provisional answer must not appear as a second reply.";
    installDesktopApi({
      initialSession: {
        ...baseSession,
        messages: [
          { role: "user", content: "hello" },
          {
            role: "assistant",
            content: provisional,
            reasoning_content: "I should think before replying.",
            tool_calls: [{ id: "think-1", type: "function", function: { name: "deep_think", arguments: '{"thought":"check first"}' } }],
          },
          { role: "assistant", content: "The one final reply." },
        ],
      },
    });

    render(<App />);

    expect(await screen.findByText("The one final reply.")).toBeTruthy();
    expect(screen.queryByText(provisional)).toBeNull();
  });

  it("places clickable tool steps beside the explanation that preceded them", async () => {
    installDesktopApi({
      initialSession: {
        ...baseSession,
        messages: [
          { role: "user", content: "Check the project" },
          { role: "assistant", content: "I will inspect the files.", tool_calls: [{ id: "read-1", function: { name: "read_file", arguments: '{"path":"app.py"}' } }] },
          { role: "tool", tool_call_id: "read-1", content: "print('hello')" },
          { role: "assistant", content: "The file is small. I will run tests.", tool_calls: [{ id: "test-1", function: { name: "command_exec", arguments: '{"command":"pytest"}' } }] },
          { role: "tool", tool_call_id: "test-1", content: "1 passed" },
        ],
      },
    });
    const mounted = render(<App />);
    expect(await screen.findByText("The file is small. I will run tests.")).toBeTruthy();
    const rows = [...mounted.container.querySelectorAll(".message-column > .message, .message-column > .activity-group")];
    expect(rows.map(row => row.textContent?.includes("工具调用步骤") ? "tools" : row.textContent?.includes("I will inspect") ? "explain-1" : row.textContent?.includes("The file is small") ? "explain-2" : "other")).toEqual(["other", "explain-1", "tools", "explain-2", "tools"]);
    const group = rows[2] as HTMLElement;
    await userEvent.setup().click(within(group).getByText("工具调用步骤"));
    await userEvent.setup().click(within(group).getByText("read_file"));
    expect(within(group).getByText(/"path":"app.py"/)).toBeTruthy();
    expect(within(group).getByText("print('hello')")).toBeTruthy();
  });

  it("expands the task checklist and resumes without adding prompt text or clearing a draft", async () => {
    const { request, releasePrompt } = installDesktopApi({
      gatePrompt: true,
      initialSession: {
        ...baseSession,
        messages: [{ role: "user", content: "Build the task board" }],
        metadata: {
          prompt_run: { state: "interrupted", prompt: "Build the task board" },
          task_list: [
            { id: "1", name: "Create server", state: "COMPLETED", indent: 0 },
            { id: "2", name: "Test API", state: "IN_PROGRESS", indent: 0 },
            { id: "3", name: "Verify browser", state: "NOT_STARTED", indent: 1 },
          ],
        },
      },
    });
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText("Test API")).toBeTruthy();
    expect(screen.queryByText("Verify browser")).toBeNull();
    await user.click(screen.getByRole("button", { name: "任务列表" }));
    expect(screen.getByText("Create server")).toBeTruthy();
    expect(screen.getByText("Verify browser")).toBeTruthy();
    const composer = screen.getByRole("textbox", { name: /向 Test Model 提问/ }) as HTMLTextAreaElement;
    await user.type(composer, "my unsent draft");
    await user.click(screen.getByRole("button", { name: "继续任务" }));

    await waitFor(() => expect(request.mock.calls.some(([action]) => action === "resumePrompt")).toBe(true));
    const resumeCall = request.mock.calls.find(([action]) => action === "resumePrompt");
    expect(resumeCall?.[1]).toMatchObject({ sessionId: baseSession.id });
    expect(resumeCall?.[1]).not.toHaveProperty("prompt");
    expect(request.mock.calls.some(([action]) => action === "runPrompt")).toBe(false);
    expect(composer.value).toBe("my unsent draft");
    releasePrompt();
    expect(await screen.findByText("Cache inspection complete")).toBeTruthy();
  });

  it("translates the experimental badge in the Chinese interface", async () => {
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

    const badge = await screen.findByText("实验性");
    expect(badge.className).toBe("setting-badge");
    expect(screen.queryByText("Experimental")).toBeNull();
  });

  it("exposes API compatibility only in settings and saves its toggle", async () => {
    const { request } = installDesktopApi({ settingItems: [{
      name: "Broad API Compatibility", key: "api_compatibility", kind: "bool",
      description: "Experimental. Use non-streaming text instructions for gateways that ignore native tools. CLI tools keep their normal permissions. Text only; select the provider's working API format.",
      value: false, experimental: true,
    }] });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("textbox", { name: /向 Test Model 提问/ });
    expect(screen.queryByText("广泛 API 兼容")).toBeNull();
    await user.click(screen.getByRole("button", { name: "设置" }));
    const title = await screen.findByText("广泛 API 兼容");
    const row = title.closest(".setting-row") as HTMLElement;
    expect(within(row).getByText("实验性")).toBeTruthy();
    await user.click(within(row).getByRole("switch"));
    await waitFor(() => expect(request).toHaveBeenCalledWith("setSetting", { key: "api_compatibility", value: true }));
    await user.click(screen.getByRole("button", { name: "对话" }));
    expect(screen.queryByText("广泛 API 兼容")).toBeNull();
  });

  it("returns to chat when the active footer settings button is clicked again", async () => {
    installDesktopApi();
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "设置" }));
    expect(await screen.findByText("通用设置")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "设置" }));
    await waitFor(() => expect(screen.queryByText("通用设置")).toBeNull());
    expect(screen.getByRole("button", { name: "对话" })).toBeTruthy();
  });
  it("opens working mode from the composer and keeps the menu outside the clipped app", async () => {
    const { request } = installDesktopApi();
    const user = userEvent.setup();
    render(<App />);
    const trigger = await screen.findByRole("button", { name: "选择工作模式" });
    expect(trigger.closest(".composer-toolbar")).toBeTruthy();
    expect(document.querySelector(".topbar .mode-trigger")).toBeNull();
    await user.click(trigger);
    const menu = document.querySelector(".mode-menu")!;
    expect(menu.parentElement).toBe(document.body);
    await user.keyboard("{End}{Home}{Escape}");
    expect(document.querySelector(".mode-menu")).toBeNull();
    expect(document.activeElement).toBe(trigger);
    expect(request.mock.calls.some(([action]) => action === "runPrompt")).toBe(false);
  });

  it("filters stored conversation content immediately from the chat header and persists the chosen display", async () => {
    const { api } = installDesktopApi({ initialSession: { ...baseSession, messages: [
      { role: "user", content: "Display question" },
      { role: "assistant", content: "Visible answer", reasoning_content: "Visible reasoning", tool_calls: [{ id: "display-tool", function: { name: "file_ops", arguments: '{"operation":"list"}' } }] },
      { role: "tool", tool_call_id: "display-tool", content: "Tool result" },
    ] } });
    const user = userEvent.setup(); render(<App />);
    await screen.findByText("Visible reasoning");
    expect(screen.getByText("工具调用步骤")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "对话内容显示" }));
    const menu = screen.getByRole("dialog", { name: "对话内容显示" });
    await user.click(within(menu).getByRole("button", { name: /思考与回复/ }));
    expect(screen.getByText("Visible reasoning")).toBeTruthy();
    expect(screen.queryByText("工具调用步骤")).toBeNull();
    await user.click(within(menu).getByRole("button", { name: /仅模型回复/ }));
    expect(screen.queryByText("Visible reasoning")).toBeNull();
    expect(screen.getByText("Visible answer")).toBeTruthy();
    expect(screen.getByText("Display question")).toBeTruthy();
    await waitFor(() => expect(api.setUiPreferences).toHaveBeenCalledWith(expect.objectContaining({ showReasoning: false, showToolCalls: false, showToolResults: false })));
    await user.click(within(menu).getByRole("button", { name: /全部内容/ }));
    expect(screen.getByText("Visible reasoning")).toBeTruthy();
    expect(screen.getByText("工具调用步骤")).toBeTruthy();
    await user.keyboard("{Escape}");
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "对话内容显示" }));
    await user.click(screen.getByRole("button", { name: "打开工作面板" }));
    expect(screen.getAllByRole("region", { name: "工作面板" })).toHaveLength(1);
    expect(screen.getByRole("separator", { name: "调整工作面板宽度" })).toBeTruthy();
    for (const name of ["文件", "AI 改动", "上下文", "活动"]) expect(within(screen.getByRole("region", { name: "工作面板" })).getByRole("button", { name })).toBeTruthy();
  });

  it("restores collapsed thoughts and completed or interrupted tool steps without indefinite spinners", async () => {
    installDesktopApi({ initialPreferences: { expandReasoning: false }, initialSession: { ...baseSession, messages: [
      { role: "user", content: "Inspect the project" },
      { role: "assistant", content: "Checking files", reasoning_content: "Inspect the smallest useful scope first.", tool_calls: [{ id: "finished", function: { name: "file_ops", arguments: '{"operation":"list","path":"."}' } }] },
      { role: "tool", tool_call_id: "finished", content: "README.md" },
      { role: "assistant", content: null, tool_calls: [{ id: "interrupted", function: { name: "command_exec", arguments: '{"command":"pytest"}' } }] },
    ] } });
    const user = userEvent.setup();
    const mounted = render(<App />);
    await screen.findByText("Checking files");
    const thought = document.querySelector(".reasoning-block") as HTMLDetailsElement;
    expect(thought.open).toBe(false);
    expect(thought.querySelector(".reasoning-content")).toBeNull();
    await user.click(within(thought).getByText("已思考"));
    expect(within(thought).getByText("Inspect the smallest useful scope first.")).toBeTruthy();
    await user.click(screen.getByText("工具调用步骤"));
    expect(mounted.container.querySelectorAll(".activity-item.working .spin").length).toBe(0);
    expect(mounted.container.querySelectorAll(".activity-item.success").length).toBe(1);
    expect(mounted.container.querySelectorAll(".activity-item.warning").length).toBe(1);
    await user.click(screen.getByText("file_ops"));
    expect(screen.getByText("README.md")).toBeTruthy();
  });

});
