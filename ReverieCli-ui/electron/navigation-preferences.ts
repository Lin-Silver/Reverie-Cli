export const NAVIGATION_PAGES = ["chat", "tools", "subagents", "rats", "tasks", "skills", "plugins", "context", "recovery", "markets", "connectors", "settings"] as const;
export type NavigationPage = typeof NAVIGATION_PAGES[number];
export const DEFAULT_PINNED_PAGES: NavigationPage[] = ["chat", "tools", "subagents", "rats", "tasks", "skills", "plugins", "context", "recovery"];

function knownPages(value: unknown): NavigationPage[] {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter((item): item is NavigationPage => NAVIGATION_PAGES.includes(item)))];
}

export function normalizePinnedPages(value: unknown): NavigationPage[] {
  return Array.isArray(value) ? knownPages(value) : [...DEFAULT_PINNED_PAGES];
}

export function normalizePageOrder(value: unknown): NavigationPage[] {
  const order = knownPages(value);
  return [...order, ...NAVIGATION_PAGES.filter(page => !order.includes(page))];
}
