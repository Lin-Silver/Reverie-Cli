// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { DEFAULT_UI_PREFERENCES } from "./preferences";
import type { DesktopState, ModelSourcesState, RatsState, RatsTaskRecord, SessionState } from "./types";

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
  approvalRequest?: Record<string, unknown>;
  ratsStateTransform?: (state: RatsState) => RatsState;
  ratsTasks?: (payload: Record<string, unknown>, cancelled: boolean) => RatsTaskRecord[] | Promise<RatsTaskRecord[]>;
  ratsTaskProgress?: number;
  ratsTaskFailure?: (action: "ratsTaskStatus" | "ratsTaskEvents" | "ratsTaskLogs") => Error | null;
  ratsTaskStatus?: (payload: Record<string, unknown>, cancelled: boolean) => Record<string, unknown>;
  ratsTaskEvents?: (payload: Record<string, unknown>, cancelled: boolean) => Record<string, unknown>;
  ratsTaskLogText?: (payload: Record<string, unknown>) => string;
  refreshedModels?: ModelSourcesState;
} = {}) {
  let promptFinished = false;
  let ratsEnabled = false;
  let ratsTaskCancelled = false;
  const eventListeners: Array<(message: { event: unknown }) => void> = [];
  const emitCoreEvent = (event: Record<string, unknown>) => {
    for (const listener of [...eventListeners]) listener({ event });
  };
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
    supportedProviders: [{ providerId: "reverie.engine", product: "Reverie Engine", serviceKind: "builtin" }],
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
    const legacy = { ...transformedState, enabledEngines: [{ executable: "C:/Engine/reverie.windows.editor.x86_64.exe", permissions: ["read"] }] } as RatsState & { enabledProviders?: RatsState["enabledProviders"] };
    delete legacy.enabledProviders;
    return legacy;
  };
  const request = vi.fn(async (action: string, payload: Record<string, unknown>) => {
    if (action === "initialize") return { type: "state", state: desktopState };
    if (action === "getSession") {
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
      models: options.refreshedModels ?? desktopState.models,
    };
    if (action === "ratsState") return { type: "rats.state", rats: ratsState() };
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
    if (action === "selectModel") {
      return {
        type: "model.selected",
        selected: { id: String(payload.modelId) },
        models: desktopState.models,
        workspace: desktopState.workspace,
      };
    }
    if (action === "runPrompt") {
      promptFinished = true;
      if (options.approvalRequest) emitCoreEvent(options.approvalRequest);
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
    uiPreferences: vi.fn(async () => DEFAULT_UI_PREFERENCES),
    setUiPreferences: vi.fn(async () => DEFAULT_UI_PREFERENCES),
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
  return { api, request, emitCoreEvent };
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
});
