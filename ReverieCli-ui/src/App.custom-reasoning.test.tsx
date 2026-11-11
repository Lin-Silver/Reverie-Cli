// @vitest-environment jsdom

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { DEFAULT_UI_PREFERENCES } from "./preferences";
import type { CustomProviderRecord, DesktopState } from "./types";


function installCustomReasoningFixture(needsContextLimit: boolean) {
  const reasoning = {
    control: "effort",
    options: [
      { id: "low", label: "Low", description: "Use less reasoning" },
      { id: "high", label: "High", description: "Use more reasoning" },
    ],
    value: "high",
  };
  const provider: CustomProviderRecord = {
    id: "fixture-provider", name: "Fixture Provider",
    base_url: "https://fixture.invalid/v1", models_url: "https://fixture.invalid/v1/models",
    format: "openai-chat", format_label: "OpenAI Chat Completions",
    enabled: true, active: true, api_key_masked: "", api_key_configured: false,
    api_key_source: "none", selected_model_id: "thought-model", selected_model_display_name: "Thought Model",
    max_context_tokens: 128000, max_tokens: 8192, supports_vision: false, thinking: true,
    model_context_limits: needsContextLimit ? {} : { "thought-model": 128000 },
    models_synced_at: 0,
    models: [{
      id: "thought-model", display_name: "Thought Model", description: "A model with selectable depth",
      context_length: 128000, vision: false, tool_calling: true, thinking: true, reasoning,
      context_limit: needsContextLimit ? 0 : 128000, needs_context_limit: needsContextLimit,
      suggested_context_limit: 128000,
    }],
  };
  const activeModel = { id: "thought-model", display_name: "Thought Model", provider: "openai-chat" };
  const state: DesktopState = {
    protocol_version: 1,
    core: { version: "fixture", interface_version: "1", release_status: "test" },
    workspace: {
      project_root: "C:/fixture", project_name: "fixture", project_data_dir: "C:/fixture/.reverie",
      config_path: "C:/fixture/.reverie/config.json", mode: "reverie", active_source: "custom",
      active_model: activeModel, index_ready: true,
      context_engine: { ready: true, indexing: false, files: 0, symbols: 0, progress: 100, label: "Ready", automatic_retrieval: true },
    },
    models: {
      active_source: "custom", active_model: activeModel,
      sources: [{
        id: "custom", display_name: "Custom Provider", active: true, selected_model_id: "thought-model",
        selected_reasoning: reasoning, models: provider.models, config_fields: [],
        custom_providers: [provider], custom_provider_formats: [],
      }],
    },
    settings: { items: [], config_path: "fixture", workspace_mode: true },
    sessions: { current_session_id: "", items: [] },
    plugins: { summary: {}, records: [] },
    skills: {
      count: 0, invalid_count: 0, shadowed_count: 0, records: [],
      pinned: { max: 4, keys: [], names: [], unresolved: [] }, errors: [], shadowed: [],
    },
    commands: { sections: [], items: [] },
    recovery: { summary: {}, checkpoints: [], operations: [] },
  };
  const request = vi.fn(async (action: string, payload: Record<string, unknown> = {}) => {
    if (action === "initialize" || action === "getState") return { type: "state", state };
    if (action === "getModelSources" || action === "refreshModelSources") return { type: "models", models: state.models };
    if (action === "getContextUsage") return { type: "context.usage", usage: null };
    if (action === "getContextStatus") return { type: "context.status", context_engine: state.workspace.context_engine };
    if (action === "getFileChanges") return { type: "file.changes", changes: [] };
    if (action === "getImageModelSources") return { type: "image-models", imageModels: { sources: [], active_source: "local" } };
    if (action === "selectCustomProviderModel") {
      // Omitted reasoning preserves the previously saved depth, as the core does.
      state.models = {
        ...state.models,
        sources: [{
          ...state.models.sources[0],
          selected_reasoning: { ...reasoning, value: String(payload.reasoning ?? reasoning.value) },
        }],
      };
      return { type: "custom-provider.model-selected", models: state.models, workspace: state.workspace };
    }
    throw new Error(`Unexpected fixture request: ${action}`);
  });
  const api = new Proxy({
    request, platform: "win32", versions: {},
    paths: async () => ({ projectRoot: "C:/fixture", kernelPath: "fixture", coreAppRoot: "fixture", runtimeRoot: "fixture" }),
    appearance: async () => ({ theme: "dark", resolved: "dark" }),
    uiPreferences: async () => DEFAULT_UI_PREFERENCES,
    gitStatus: async () => null,
    onEvent: () => () => undefined,
    onAppearance: () => () => undefined,
  }, {
    get(target, name) {
      if (name in target) return Reflect.get(target, name);
      if (String(name).startsWith("on")) return () => () => undefined;
      return async () => null;
    },
  });
  Object.defineProperty(window, "reverie", { configurable: true, value: api });
  return request;
}


beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn((query: string) => ({
      matches: false, media: query, onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(() => true),
    })),
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});


async function chooseLowInCustomPicker(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: /Thought Model.*Fixture Provider/ }));
  const picker = await screen.findByRole("dialog", { name: "模型来源" });
  await user.click(within(picker).getByRole("button", { name: /Thought Model/ }));
  await user.click(within(picker).getByRole("button", { name: /Use less reasoning/ }));
}


describe("custom provider reasoning selection", () => {
  it("sends the chosen Low depth from the custom model picker", async () => {
    const request = installCustomReasoningFixture(false);
    const user = userEvent.setup();
    render(<App />);

    await chooseLowInCustomPicker(user);

    await waitFor(() => expect(request).toHaveBeenCalledWith("selectCustomProviderModel", {
      projectRoot:'C:/fixture',sessionId:undefined,
      providerId: "fixture-provider", modelId: "thought-model", reasoning: "low",
    }));
    expect(document.querySelector(".reasoning-trigger")?.textContent).toContain("低");
  });

  it("retains Low until the first context confirmation is saved", async () => {
    const request = installCustomReasoningFixture(true);
    const user = userEvent.setup();
    render(<App />);

    await chooseLowInCustomPicker(user);
    const confirmation = await screen.findByRole("dialog", { name: "模型上下文限额" });
    expect(request.mock.calls.some(([action]) => action === "selectCustomProviderModel")).toBe(false);
    await user.clear(within(confirmation).getByRole("textbox", { name: "上下文限额" }));
    await user.type(within(confirmation).getByRole("textbox", { name: "上下文限额" }), "128000");
    await user.click(within(confirmation).getByRole("button", { name: "保存并使用" }));

    await waitFor(() => expect(request).toHaveBeenCalledWith("selectCustomProviderModel", {
      projectRoot:'C:/fixture',sessionId:undefined,
      providerId: "fixture-provider", modelId: "thought-model", contextLimit: 128000, reasoning: "low",
    }));
    expect(document.querySelector(".reasoning-trigger")?.textContent).toContain("低");
  });
});
