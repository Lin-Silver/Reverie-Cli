/** Standard notifications and bounded host-initiated teardown; no component adapter. */
export interface McpAppHydration { toolInput: Record<string, unknown>; toolResult: Record<string, unknown> }
export class McpAppLifecycle {
  #ready = false;
  #closing?: Promise<void>;
  #finish?: () => void;
  #teardownId = `host-teardown:${crypto.randomUUID()}`;
  constructor(private source: unknown, private post: (message: Record<string, unknown>) => void, private hydration: McpAppHydration) {}

  ready(): void {
    if (this.#ready || this.#closing) return;
    this.#ready = true;
    this.post({ jsonrpc: "2.0", method: "ui/notifications/tool-input", params: this.hydration.toolInput });
    this.post({ jsonrpc: "2.0", method: "ui/notifications/tool-result", params: this.hydration.toolResult });
  }

  teardown(): Promise<void> {
    if (this.#closing) return this.#closing;
    this.#closing = new Promise(resolve => {
      if (!this.#ready) { resolve(); return; }
      const timeout = setTimeout(() => { this.#finish = undefined; resolve(); }, 500);
      this.#finish = () => { clearTimeout(timeout); this.#finish = undefined; resolve(); };
      this.post({ jsonrpc: "2.0", id: this.#teardownId, method: "ui/resource-teardown", params: {} });
    });
    return this.#closing;
  }

  receive(event: { source?: unknown; data?: unknown }): boolean {
    if (event.source !== this.source || !this.#finish) return false;
    const data = event.data as Record<string, unknown> | null;
    if (!data || data.jsonrpc !== "2.0" || data.id !== this.#teardownId || data.method !== undefined || (!data.result && !data.error)) return false;
    this.#finish(); return true;
  }
}
