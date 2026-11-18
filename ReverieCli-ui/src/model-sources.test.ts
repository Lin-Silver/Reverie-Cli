import { describe, expect, it } from "vitest";

import {
  CUSTOM_SOURCE_ID,
  activeSourceId,
  applyModelSelection,
  coreSourceId,
  customProviderIdOf,
  customSourceId,
  expandModelSources,
  settingsModelSources,
  visibleModelSources,
} from "./model-sources";
import type { CustomProviderModel, CustomProviderRecord, DesktopState, ModelSource, ReasoningCapability } from "./types";

const noReasoning: ReasoningCapability = { control: "none", options: [], value: "" };
const effortReasoning: ReasoningCapability = {
  control: "effort",
  options: [{ id: "high", label: "High" }] as ReasoningCapability["options"],
  value: "high",
};

function providerModel(id: string): CustomProviderModel {
  return {
    id,
    display_name: id,
    description: "",
    vision: false,
    tool_calling: true,
    thinking: true,
    reasoning: noReasoning,
    context_limit: 0,
  } as CustomProviderModel;
}

function provider(id: string, name: string, patch: Partial<CustomProviderRecord> = {}): CustomProviderRecord {
  return {
    id,
    name,
    base_url: "https://api.example.com/v1",
    models_url: "",
    format: "openai",
    format_label: "OpenAI",
    enabled: true,
    active: false,
    api_key_masked: "sk-…9f",
    api_key_configured: true,
    api_key_source: "config",
    selected_model_id: `${id}-model`,
    selected_model_display_name: `${id}-model`,
    max_context_tokens: 128000,
    max_tokens: 8192,
    supports_vision: false,
    thinking: true,
    model_context_limits: {},
    models_synced_at: 0,
    models: [providerModel(`${id}-model`)],
    ...patch,
  };
}

function source(id: string, patch: Partial<ModelSource> = {}): ModelSource {
  return {
    id,
    display_name: id,
    active: false,
    selected_model_id: "",
    selected_reasoning: noReasoning,
    models: [],
    config_fields: [],
    ...patch,
  };
}

function customSource(providers: CustomProviderRecord[], patch: Partial<ModelSource> = {}): ModelSource {
  return source(CUSTOM_SOURCE_ID, {
    display_name: "自定义 Provider",
    custom_providers: providers,
    custom_provider_formats: [],
    ...patch,
  });
}

describe("visibleModelSources", () => {
  it("drops retired sources that may still linger in an old config", () => {
    const sources = visibleModelSources([source("rats"), source("UnlimitedSurf"), source("standard")]);

    expect(sources.map((item) => item.id)).toEqual(["rats", "standard"]);
  });

  it("tolerates a missing source list", () => {
    expect(visibleModelSources(undefined as unknown as ModelSource[])).toEqual([]);
  });
});

describe("expandModelSources", () => {
  it("gives every registered provider its own entry under the name the user chose", () => {
    const sources = expandModelSources([
      source("rats"),
      customSource([provider("p1", "Qwen3.8 Max"), provider("p2", "Kimi Studio")]),
    ]);

    expect(sources.map((item) => item.id)).toEqual(["rats", "custom:p1", "custom:p2"]);
    expect(sources.map((item) => item.display_name)).toEqual(["rats", "Qwen3.8 Max", "Kimi Studio"]);
    // The aggregate bucket itself is gone: a provider *is* a source.
    expect(sources.some((item) => item.id === CUSTOM_SOURCE_ID)).toBe(false);
  });

  it("carries each provider's own selection and catalog", () => {
    const [entry] = expandModelSources([customSource([provider("p1", "Qwen3.8 Max")])]);

    expect(entry.selected_model_id).toBe("p1-model");
    expect(entry.models.map((model) => model.id)).toEqual(["p1-model"]);
    expect(entry.custom_provider_id).toBe("p1");
    // The record list belongs to the settings panel, not to one entry.
    expect(entry.custom_providers).toBeUndefined();
  });

  it("only lets the active provider claim the aggregate's reasoning selection", () => {
    const sources = expandModelSources([
      customSource([provider("p1", "One", { active: true }), provider("p2", "Two")], {
        selected_reasoning: effortReasoning,
      }),
    ]);

    expect(sources[0].active).toBe(true);
    expect(sources[0].selected_reasoning).toEqual(effortReasoning);
    expect(sources[1].active).toBe(false);
    expect(sources[1].selected_reasoning).toEqual(noReasoning);
  });

  it("keeps a provider whose catalog failed to sync visible", () => {
    const sources = expandModelSources([
      customSource([provider("p1", "Offline", { models: [], sync_error: "timed out" })]),
    ]);

    expect(sources).toHaveLength(1);
    expect(sources[0].display_name).toBe("Offline");
    expect(sources[0].models).toEqual([]);
  });

  it("falls back to the id, then the aggregate label, for an unnamed provider", () => {
    const sources = expandModelSources([
      customSource([provider("p1", ""), provider("p2", "", { id: "p2" })]),
    ]);

    expect(sources.map((item) => item.display_name)).toEqual(["p1", "p2"]);
  });

  it("skips malformed records instead of producing an unselectable entry", () => {
    const sources = expandModelSources([
      customSource([provider("", "Nameless"), provider("p1", "Real")]),
    ]);

    expect(sources.map((item) => item.display_name)).toEqual(["Real"]);
  });

  it("leaves a config with no custom providers untouched", () => {
    const sources = expandModelSources([source("rats"), customSource([])]);

    expect(sources.map((item) => item.id)).toEqual(["rats"]);
  });
});

describe("settingsModelSources", () => {
  it("keeps the aggregate source the management panel edits", () => {
    const sources = settingsModelSources([source("standard"), customSource([provider("p1", "Qwen3.8 Max")])]);

    expect(sources.map((item) => item.id)).toEqual(["standard", CUSTOM_SOURCE_ID]);
  });

  it("never shows a synthetic per-provider entry as its own settings tab", () => {
    const expanded = expandModelSources([customSource([provider("p1", "Qwen3.8 Max")])]);

    expect(settingsModelSources(expanded)).toEqual([]);
  });
});

describe("id mapping", () => {
  it("round-trips a provider id through the synthetic source id", () => {
    const id = customSourceId("p1");

    expect(id).toBe("custom:p1");
    expect(customProviderIdOf({ id })).toBe("p1");
    expect(coreSourceId({ id })).toBe(CUSTOM_SOURCE_ID);
  });

  it("leaves a real source alone", () => {
    expect(customProviderIdOf({ id: "standard" })).toBe("");
    expect(coreSourceId({ id: "standard" })).toBe("standard");
  });

  it("prefers the explicit field over parsing the id", () => {
    expect(customProviderIdOf({ id: "custom:stale", custom_provider_id: "p1" })).toBe("p1");
  });
});

describe("activeSourceId", () => {
  it("preselects the active provider, whose id the core never reports", () => {
    const sources = expandModelSources([
      source("rats"),
      customSource([provider("p1", "One"), provider("p2", "Two", { active: true })]),
    ]);

    // `active_source` is the core id, which matches no per-provider entry.
    expect(activeSourceId(sources, CUSTOM_SOURCE_ID)).toBe("custom:p2");
  });

  it("falls back to the core id when nothing is flagged active", () => {
    const sources = [source("rats"), source("standard")];

    expect(activeSourceId(sources, "standard")).toBe("standard");
  });

  it("falls back to the first entry when the core id is unknown", () => {
    const sources = [source("rats"), source("standard")];

    expect(activeSourceId(sources, "gone")).toBe("rats");
    expect(activeSourceId([], "gone")).toBe("");
  });
});

it("updates a custom selection without replacing unrelated catalog rows", () => {
  const previous = provider("p1", "One", { active: true });
  const next = provider("p2", "Two");
  const standard = source("standard");
  const aggregate = customSource([previous, next], { active: true });
  const state = { models: { active_source: "custom", sources: [standard, aggregate], active_model: null } } as DesktopState;
  const model = { ...next.models[0], context_length: 96000, context_limit: 96000, needs_context_limit: false, reasoning: effortReasoning };
  const update = applyModelSelection(state, {
    workspace: { active_source: "custom", active_model: { id: model.id, display_name: model.display_name, provider: "openai-chat" } } as DesktopState["workspace"],
    selection: { provider: { ...next, reasoning_effort: "high" }, model },
  });
  const [first, second] = update!.models.sources[1].custom_providers!;
  expect(update!.models.sources[0]).toBe(standard);
  expect(first.active).toBe(false);
  expect(first.models).toBe(previous.models);
  expect(second.active).toBe(true);
  expect(second.models[0]).toBe(model);
  expect(second.model_context_limits[model.id]).toBe(96000);
  expect(update!.models.sources[1].selected_reasoning).toBe(effortReasoning);
});
