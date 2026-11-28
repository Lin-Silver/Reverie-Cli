/**
 * How model sources are presented in the picker.
 *
 * The core reports custom providers as one aggregate `custom` source carrying a
 * list of records. That is the right shape for the settings panel, which manages
 * the list, but it is the wrong shape for the picker: the user names every
 * provider they add, so a provider *is* a source by that name. Expanding the
 * aggregate here keeps the protocol unchanged while the GUI shows `Qwen3.8 Max`
 * instead of a generic "Custom Provider" bucket.
 */

import type { CustomProviderModel, CustomProviderRecord, DesktopState, ModelRecord, ModelSelectionUpdate, ModelSource, ModelSourcesState, WorkspaceState } from "./types";

/** Sources retired from the product but possibly still present in old configs. */
const RETIRED_MODEL_SOURCE_IDS = new Set(["unlimitedsurf", "unlimited_surf", "unlimited.surf", "us", "ue", "webgemini", "wgemini"]);

/** The aggregate source id that holds every user-defined provider. */
export const CUSTOM_SOURCE_ID = "custom";

/** Prefix of a synthetic per-provider source id. */
const CUSTOM_SOURCE_PREFIX = `${CUSTOM_SOURCE_ID}:`;

/** Drop sources that no longer exist in the product. */
export function visibleModelSources(sources: ModelSource[]): ModelSource[] {
  return (sources ?? []).filter((source) => !RETIRED_MODEL_SOURCE_IDS.has(source.id.trim().toLowerCase()));
}

/** The synthetic picker id for one custom provider. */
export function customSourceId(providerId: string): string {
  return `${CUSTOM_SOURCE_PREFIX}${providerId}`;
}

/** The provider id behind a synthetic source id, or "" for a real source. */
export function customProviderIdOf(source: Pick<ModelSource, "id" | "custom_provider_id">): string {
  if (source.custom_provider_id) return source.custom_provider_id;
  return source.id.startsWith(CUSTOM_SOURCE_PREFIX) ? source.id.slice(CUSTOM_SOURCE_PREFIX.length) : "";
}

/** The id the core understands for a source the picker may have synthesized. */
export function coreSourceId(source: Pick<ModelSource, "id" | "custom_provider_id">): string {
  return customProviderIdOf(source) ? CUSTOM_SOURCE_ID : source.id;
}

function providerSource(aggregate: ModelSource, provider: CustomProviderRecord): ModelSource {
  const active = Boolean(provider.active);
  return {
    ...aggregate,
    id: customSourceId(provider.id),
    custom_provider_id: provider.id,
    display_name: provider.name || provider.id || aggregate.display_name,
    active,
    selected_model_id: provider.selected_model_id || "",
    // Reasoning is a property of the active selection, so only the provider
    // that is actually in use can claim the aggregate's value.
    selected_reasoning: active
      ? aggregate.selected_reasoning
      : { control: "none", options: [], value: "" },
    config: provider.reasoning_effort === undefined ? undefined : {
      values: { reasoning_effort: provider.reasoning_effort }, configured_secrets: {},
    },
    models: provider.models ?? [],
    // The record list belongs to the settings panel, not to a single provider.
    custom_providers: undefined,
    custom_provider_formats: undefined,
  };
}

/** Apply a core selection using the catalogs already held by the renderer. */
export function applyModelSelection(
  current: DesktopState | null,
  response: { workspace: WorkspaceState; models?: ModelSourcesState; selection?: ModelSelectionUpdate },
): DesktopState | null {
  if (!current) return null;
  const { workspace, selection } = response;
  if (response.models) return { ...current, models: response.models, workspace };
  if (!selection) return current;
  const { active_source, active_model } = workspace;
  const sources = current.models.sources.map(source => {
    const active = source.id === active_source;
    const custom_providers = source.custom_providers?.map(provider => {
      if (active && selection.provider?.id === provider.id) {
        const model = selection.model as CustomProviderModel;
        const key = model.id.toLowerCase();
        // Row metadata changes only when the limit changes. The reasoning
        // control reads its current value from the source and provider.
        const limitChanged = (provider.model_context_limits[key] ?? 0) !== model.context_limit;
        return {
          ...provider, ...selection.provider, active: true,
          model_context_limits: limitChanged ? { ...provider.model_context_limits, [key]: model.context_limit } : provider.model_context_limits,
          models: limitChanged ? provider.models.map(item => item.id === model.id ? model : item) : provider.models,
        };
      }
      return provider.active ? { ...provider, active: false } : provider;
    });
    if (active) return {
      ...source, active, custom_providers,
      selected_model_id: selection.model.id,
      selected_profile_id: selection.model.profile_id,
      selected_reasoning: selection.model.reasoning,
      config: selection.provider ? source.config : selection.config ?? source.config,
    };
    return source.active ? { ...source, active, custom_providers } : source;
  });
  return { ...current, workspace, models: { active_source, active_model, sources } };
}

export function isSelectedModel(source: ModelSource, model: ModelRecord): boolean {
  return source.selected_model_id === model.id && (!source.selected_profile_id || source.selected_profile_id === model.profile_id);
}

export function modelReasoningForPicker(source: ModelSource, model: ModelRecord): ModelRecord['reasoning'] {
  if (isSelectedModel(source, model) && source.selected_reasoning.options.length) return source.selected_reasoning;
  const values = source.config?.values;
  const preferred = model.reasoning.control === "toggle" && typeof values?.enable_thinking === "boolean"
    ? String(values.enable_thinking)
    : (values?.thinking_mode ?? values?.reasoning_effort);
  return model.reasoning.options.some(option => option.id === preferred)
    ? { ...model.reasoning, value: String(preferred) }
    : model.reasoning;
}

/**
 * Replace the aggregate `custom` source with one entry per registered provider.
 *
 * Providers with no fetched catalog still get an entry, so a provider whose
 * model list failed to sync stays visible and selectable once it does.
 */
export function expandModelSources(sources: ModelSource[]): ModelSource[] {
  const expanded: ModelSource[] = [];
  for (const source of visibleModelSources(sources)) {
    if (source.id !== CUSTOM_SOURCE_ID) {
      expanded.push(source);
      continue;
    }
    for (const provider of source.custom_providers ?? []) {
      if (!provider?.id) continue;
      expanded.push(providerSource(source, provider));
    }
  }
  return expanded;
}

/** Sources the settings panel manages: the aggregate `custom`, never a synthetic one. */
export function settingsModelSources(sources: ModelSource[]): ModelSource[] {
  return visibleModelSources(sources).filter((source) => !customProviderIdOf(source));
}

/**
 * The entry the picker should preselect from a possibly expanded list.
 *
 * `models.active_source` is a core id, so it never matches a per-provider entry.
 * The `active` flag is authoritative in both shapes -- at most one entry in the
 * list carries it -- so trust that first and fall back to the core id.
 */
export function activeSourceId(sources: ModelSource[], coreActiveSource: string): string {
  const active = sources.find((source) => source.active);
  if (active) return active.id;
  const matched = sources.find((source) => source.id === coreActiveSource);
  if (matched) return matched.id;
  return sources[0]?.id ?? "";
}
