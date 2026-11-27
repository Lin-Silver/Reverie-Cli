import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { coreRequestTimeoutMs } from "./core-timeouts";
import { requestCoreShutdown } from "./core-shutdown";
import type { JsonRecord } from "./core-actions";

type EventHandler = (message: JsonRecord) => void;
type BridgeEnvironment = {
  settingsPath: string;
  tempRoot: string;
  discoveryRoots: string[];
  log: (message: string) => void;
};

export class CoreBridge {
  private child: ChildProcessWithoutNullStreams | null = null;
  private starting: Promise<void> | null = null;
  private sequence = 0;
  private actions: Set<string> | null = null;
  private closed = false;
  browserProtocol?: string;
  onBrowserEvent?: (event: JsonRecord) => void;
  onBrowserDisconnect?: () => void;
  private pending = new Map<string, {
    resolve: (value: JsonRecord) => void;
    reject: (reason: Error) => void;
    timer: ReturnType<typeof setTimeout> | null;
    action: string;
    sessionId?: string;
    onEvent?: EventHandler;
  }>();

  constructor(
    private projectRoot: string,
    private coreAppRoot: string,
    private readonly executablePath: string,
    private readonly sendEvent: EventHandler,
    private readonly environment: BridgeEnvironment,
  ) {}

  setProjectRoot(projectRoot: string): void { this.projectRoot = path.resolve(projectRoot); }
  getProjectRoot(): string { return this.projectRoot; }
  setCoreAppRoot(coreAppRoot: string): void { this.coreAppRoot = path.resolve(coreAppRoot); }
  getCoreAppRoot(): string { return this.coreAppRoot; }
  getPid(): number | undefined { return this.child?.pid; }
  supports(action: string): boolean { return this.actions === null || this.actions.has(action); }
  hasActivePrompt(): boolean {
    return [...this.pending.values()].some(item => ["runPrompt", "resumePrompt", "callViewTool"].includes(item.action));
  }

  private disconnectBrowser(): void {
    if (this.browserProtocol === undefined) return;
    this.browserProtocol = undefined;
    this.onBrowserDisconnect?.();
  }

  async start(): Promise<void> {
    if (this.closed) throw new Error("Reverie core bridge is closing.");
    if (this.starting) return this.starting;
    if (this.child && this.child.exitCode === null && this.child.signalCode === null) return;
    this.actions = null;
    this.starting = new Promise<void>((resolve, reject) => {
      if (!existsSync(this.executablePath)) {
        reject(new Error(`Reverie core not found: ${this.executablePath}`));
        return;
      }
      mkdirSync(this.coreAppRoot, { recursive: true });
      const child = spawn(this.executablePath, ["--sdk-bridge"], {
        cwd: this.projectRoot,
        windowsHide: true,
        env: {
          ...process.env,
          REVERIE_APP_ROOT: this.coreAppRoot,
          REVERIE_DESKTOP_SETTINGS: this.environment.settingsPath,
          REVERIE_RATS_DISCOVERY_ROOTS: [...new Set(this.environment.discoveryRoots.map(item => path.resolve(item)))].join(path.delimiter),
          TEMP: this.environment.tempRoot,
          TMP: this.environment.tempRoot,
        },
      });
      this.child = child;
      let ready = false;
      const timer = setTimeout(() => {
        if (ready) return;
        reject(new Error("Reverie core did not announce readiness."));
        child.kill();
      }, 60_000);
      const lines = readline.createInterface({ input: child.stdout });
      lines.on("line", (line) => {
        let message: JsonRecord;
        try { message = JSON.parse(line) as JsonRecord; }
        catch { this.environment.log(`Invalid core JSON: ${line.slice(0, 500)}`); return; }
        if (!message || typeof message !== "object" || Array.isArray(message)) {
          this.environment.log("Core returned a non-object message.");
          return;
        }
        const capabilities = (message.capabilities ?? (message.state as JsonRecord | undefined)?.capabilities) as JsonRecord | undefined;
        if (Array.isArray(capabilities?.actions)) this.actions = new Set(capabilities.actions.filter((item): item is string => typeof item === "string"));
        if (message.type === "ready" && message.id === undefined && !ready) {
          this.browserProtocol = typeof message.browser_protocol === "string" ? message.browser_protocol : undefined;
          ready = true;
          clearTimeout(timer);
          resolve();
          return;
        }
        const request = this.pending.get(String(message.id ?? ""));
        if (message.type === "prompt.event") {
          const event = message.event as JsonRecord | undefined;
          if (typeof event?.type === "string" && event.type.startsWith("browser.")) {
            this.onBrowserEvent?.(event);
            return;
          }
          (request?.onEvent ?? this.sendEvent)(message);
          return;
        }
        if (!request) return;
        this.pending.delete(String(message.id));
        if (request.timer) clearTimeout(request.timer);
        if (message.type === "error") request.reject(new Error(String(message.error ?? "Unknown core error")));
        else request.resolve(message);
      });
      child.stderr.on("data", (chunk: Buffer) => this.environment.log(`CORE ${chunk.toString("utf8").trimEnd()}`));
      child.once("error", (error) => {
        clearTimeout(timer);
        if (!ready) reject(error);
        this.environment.log(`Core process error: ${error.message}`);
      });
      child.once("exit", (code, signal) => {
        clearTimeout(timer);
        lines.close();
        const error = new Error(`Reverie core exited (${code ?? signal ?? "unknown"})`);
        if (this.child === child) {
          this.disconnectBrowser();
          for (const request of this.pending.values()) {
            if (request.timer) clearTimeout(request.timer);
            request.reject(error);
          }
          this.pending.clear();
          this.child = null;
          this.actions = null;
        }
        if (!ready) reject(error);
        this.environment.log(error.message);
      });
    }).finally(() => { this.starting = null; });
    return this.starting;
  }

  async request(action: string, payload: JsonRecord = {}, onEvent?: EventHandler): Promise<JsonRecord> {
    payload = { projectRoot: this.projectRoot, ...payload };
    await this.start();
    const child = this.child;
    if (!child || child.killed) throw new Error("Reverie core is not running.");
    const id = `desktop-${Date.now()}-${++this.sequence}`;
    const timeoutMs = coreRequestTimeoutMs(action);
    return new Promise<JsonRecord>((resolve, reject) => {
      const timer = timeoutMs > 0 ? setTimeout(() => {
        if (!this.pending.delete(id)) return;
        reject(new Error(`Reverie core request timed out: ${action}`));
      }, timeoutMs) : null;
      this.pending.set(id, { resolve, reject, timer, action, onEvent,
        ...(["runPrompt", "resumePrompt"].includes(action) ? { sessionId: String(payload.sessionId ?? "") } : {}),
      });
      child.stdin.write(`${JSON.stringify({ id, action, payload })}\n`, "utf8", (error) => {
        if (!error) return;
        this.pending.delete(id);
        if (timer) clearTimeout(timer);
        reject(error);
      });
    });
  }

  async stop(reason = "Core stopped", graceful = false, close = false): Promise<void> {
    this.closed = close;
    const child = this.child;
    if (!child) return;
    this.disconnectBrowser();
    for (const request of this.pending.values()) {
      if (request.timer) clearTimeout(request.timer);
      request.reject(new Error(reason));
    }
    this.pending.clear();
    const exited = graceful && await requestCoreShutdown(child);
    if (!exited && child.exitCode === null && child.signalCode === null) {
      if (process.platform === "win32" && child.pid) {
        await new Promise<void>((resolve) => {
          const killer = spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], { windowsHide: true, stdio: "ignore" });
          killer.once("error", () => { child.kill(); resolve(); });
          killer.once("exit", () => resolve());
        });
      } else child.kill();
    }
    if (this.child === child) { this.child = null; this.actions = null; }
  }

  async restart(): Promise<void> {
    await this.stop("Prompt cancelled; core restarted.", true);
    await this.start();
  }
}
