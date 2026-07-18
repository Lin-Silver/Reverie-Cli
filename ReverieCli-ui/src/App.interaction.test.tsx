// @vitest-environment jsdom

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { DEFAULT_UI_PREFERENCES } from "./preferences";
import type { DesktopState, SessionState } from "./types";

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
});
