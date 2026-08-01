// @vitest-environment jsdom

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { DEFAULT_UI_PREFERENCES } from "./preferences";
import type { DesktopState, RatsState, SessionState } from "./types";

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
    items: [{ id: "tools", command: "/tools", section: "Workspace", summary: "Open tools", detail: "", overview: "" }],
  },
  recovery: { summary: {}, checkpoints: [], operations: [] },
};

function installDesktopApi() {
  let promptFinished = false;
  let ratsEnabled = false;
  const ratsState = (): RatsState => ({
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
    if (action === "ratsState") return { type: "rats.state", rats: ratsState() };
    if (action === "ratsRegisterProvider" || action === "ratsRemoveRoot") return { type: "rats.state", rats: ratsState() };
    if (action === "ratsSetProviderEnabled") {
      ratsEnabled = payload.enabled === true;
      return { type: "rats.state", rats: ratsState() };
    }
    if (action === "ratsDescribe") {
      return { type: "rats.definitions", service_id: String(payload.serviceId), definitions: [{ name: "project.status", request_schema: { type: "object" }, response_schema: { type: "object" } }] };
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
    throw new Error(`Unexpected action: ${action}`);
  });
  const api = {
    request,
    cancel: vi.fn(async () => undefined),
    onEvent: vi.fn(() => () => undefined),
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
  return { api, request };
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
});
