// Workspace/session discovery can be cold after an update or a large history
// migration, so initialization gets a longer budget than ordinary IPC calls.
const CORE_INITIALIZE_TIMEOUT_MS = 300_000;

export function coreRequestTimeoutMs(action: string): number {
  if (action === "runPrompt" || action === "indexWorkspace") return 0;
  if (action === "initialize") return CORE_INITIALIZE_TIMEOUT_MS;
  if (action === "compactContext") return 180_000;
  if (action === "refreshModelSources") return 120_000;
  if (action === "getSession") return 15_000;
  return 60_000;
}
