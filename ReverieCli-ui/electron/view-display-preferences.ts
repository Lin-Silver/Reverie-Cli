/** Shared host-only display preference codec. No component state or HTML. */
export const VIEW_DISPLAY_MODES = ["inline", "fullscreen", "pip"] as const;
export type ViewDisplayMode = typeof VIEW_DISPLAY_MODES[number];
export type ViewDisplayPreference = { mode: ViewDisplayMode; expanded: boolean; updatedAt: number };

export function normalizeViewDisplayPreferences(value: unknown): Record<string, ViewDisplayPreference> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const entries: Array<[string, ViewDisplayPreference]> = [];
  for (const [key, raw] of Object.entries(value)) {
    if (!key || key.length > 2048 || !raw || typeof raw !== "object" || Array.isArray(raw)) continue;
    const item = raw as Record<string, unknown>;
    if (!VIEW_DISPLAY_MODES.includes(item.mode as ViewDisplayMode)) continue;
    entries.push([key, { mode: item.mode as ViewDisplayMode, expanded: item.expanded !== false, updatedAt: typeof item.updatedAt === "number" && Number.isFinite(item.updatedAt) ? Math.max(0, item.updatedAt) : 0 }]);
  }
  return Object.fromEntries(entries.sort((a, b) => a[1].updatedAt - b[1].updatedAt).slice(-200));
}
