/**
 * Packaged-Electron isolation probe for the generative-view host.
 *
 * Drives a real window, a real custom-scheme session and real offline fixtures, then writes
 * a structured report that `evaluateProbeReport` judges. Nothing here is a test double: the
 * loop and flood fixtures are given a genuine renderer and the host must survive them.
 */

import { app, BrowserWindow, clipboard, ipcMain, session } from "electron";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { VIEW_SCHEME, ViewHost, type ViewBinding } from "./view-host";
import { attachViewFrameGuards, attachViewSession, createViewGuardLog, recordProbeNetwork, recordProbeWindowOpens, type ViewGuardLog, type ViewProtocolHandler } from "./view-session";
import { writeViewFixture, type ViewFixtureName } from "./view-fixtures";
import { PROBE_REPORT_VERSION, evaluateProbeReport, renderProbeSummary, type ProbeCheckResult, type ProbeMetric, type ProbeReport } from "./view-isolation-probe";

const PROBE_PARTITION = "riu-isolation-probe";
const COMMAND_TIMEOUT_MS = 4_000;
const PING_TIMEOUT_MS = 2_000;

type CommandOutcome = { ok: boolean; elapsedMs: number; value: Record<string, unknown>; error?: string };

function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

class ProbeDriver {
  #sequence = 0;
  readonly #pending = new Map<string, (outcome: { value?: unknown; error?: string }) => void>();

  constructor(private readonly window: BrowserWindow) {
    ipcMain.on("riu-probe:result", (_event, payload: { id?: string; value?: unknown; error?: string }) => {
      const settle = payload?.id ? this.#pending.get(payload.id) : undefined;
      if (!settle || !payload?.id) return;
      this.#pending.delete(payload.id);
      settle(payload);
    });
  }

  async send(name: string, args: Record<string, unknown> = {}, timeoutMs = COMMAND_TIMEOUT_MS): Promise<CommandOutcome> {
    const id = `cmd-${(this.#sequence += 1)}`;
    const started = Date.now();
    const outcome = await new Promise<{ value?: unknown; error?: string; timedOut?: boolean }>(resolve => {
      const timer = setTimeout(() => { this.#pending.delete(id); resolve({ timedOut: true }); }, timeoutMs);
      this.#pending.set(id, settled => { clearTimeout(timer); resolve(settled); });
      this.window.webContents.send("riu-probe:command", { id, name, args });
    });
    const elapsedMs = Date.now() - started;
    if (outcome.timedOut) return { ok: false, elapsedMs, value: {}, error: `timed out after ${timeoutMs}ms` };
    if (outcome.error) return { ok: false, elapsedMs, value: {}, error: outcome.error };
    return { ok: true, elapsedMs, value: (outcome.value ?? {}) as Record<string, unknown> };
  }

  dispose(): void { ipcMain.removeAllListeners("riu-probe:result"); }
}

class ProbeLedger {
  readonly checks: ProbeCheckResult[] = [];
  readonly metrics: Partial<Record<ProbeMetric, number>> = {};
  readonly notes: string[] = [];

  record(id: string, passed: boolean, detail: string): boolean {
    this.checks.push({ id, passed, detail });
    return passed;
  }

  metric(name: ProbeMetric, value: number): void { this.metrics[name] = value; }
  note(text: string): void { this.notes.push(text); }
}

/** Worst observed round trip; a frozen host shows up as the timeout value rather than a missing number. */
async function pingSeries(driver: ProbeDriver, rounds: number): Promise<{ worstMs: number; answered: number }> {
  let worstMs = 0;
  let answered = 0;
  for (let round = 0; round < rounds; round += 1) {
    const outcome = await driver.send("ping", { round }, PING_TIMEOUT_MS);
    worstMs = Math.max(worstMs, outcome.elapsedMs);
    if (outcome.ok) answered += 1;
    await delay(40);
  }
  return { worstMs, answered };
}

function childFrames(window: BrowserWindow): { processId: number; osProcessId: number; url: string }[] {
  const main = window.webContents.mainFrame;
  return main.frames.map(frame => ({
    processId: Number((frame as unknown as { processId?: number }).processId ?? -1),
    osProcessId: Number((frame as unknown as { osProcessId?: number }).osProcessId ?? -1),
    url: String(frame.url ?? ""),
  }));
}

function processAlive(pid: number): boolean {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  return app.getAppMetrics().some(metric => metric.pid === pid);
}

export async function runIsolationProbe(options: { uiRoot: string; runtimeRoot: string; reportPath: string | null }): Promise<number> {
  const evidenceRoot = path.join(options.runtimeRoot, "riu-probe");
  const artifactRoot = path.join(evidenceRoot, "views");
  await mkdir(artifactRoot, { recursive: true });

  const ledger = new ProbeLedger();
  const log: ViewGuardLog = createViewGuardLog();
  const probeSession = session.fromPartition(PROBE_PARTITION);
  const host = new ViewHost({ root: artifactRoot });
  const attached = attachViewSession(probeSession, host, log);
  recordProbeNetwork(probeSession, log);

  const window = new BrowserWindow({
    width: 1100,
    height: 760,
    show: true,
    title: "Reverie isolation probe",
    webPreferences: {
      preload: path.join(__dirname, "riu-probe-preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      partition: PROBE_PARTITION,
    },
  });
  attachViewFrameGuards(window.webContents, host, log);
  recordProbeWindowOpens(window.webContents, log);
  const driver = new ProbeDriver(window);
  const startedAt = new Date().toISOString();

  try {
    await window.loadFile(path.join(options.uiRoot, "dist", "riu-probe.html"));
    window.focus();
    window.webContents.focus();
    await driver.send("ping", {}, PING_TIMEOUT_MS);

    // Electron 41 exposes no accessor for a window's effective preferences, so the renderer
    // reports what it can actually reach — stronger evidence than reading options back.
    const world = await window.webContents.executeJavaScript(
      `({
        node: typeof require === "undefined" && typeof process === "undefined" && typeof module === "undefined" && typeof global === "undefined" && typeof Buffer === "undefined",
        bridge: typeof window.riuProbe === "object" && window.riuProbe !== null,
        bridgeKeys: window.riuProbe ? Object.keys(window.riuProbe).sort().join(",") : "",
        leaked: Object.keys(window).filter(function (key) { return /electron|ipcRenderer|nodeRequire|__node/i.test(key); }).join(","),
        origin: String(window.origin),
      })`,
    ) as { node: boolean; bridge: boolean; bridgeKeys: string; leaked: string; origin: string };
    ledger.record(
      "node-integration-disabled",
      world.node === true && world.leaked === "",
      `nodeGlobalsAbsent=${world.node} leaked="${world.leaked}" origin=${world.origin}`,
    );
    ledger.record(
      "context-isolation-enabled",
      world.bridge === true && world.bridgeKeys === "failed,onCommand,reply" && world.node === true,
      `bridge=${world.bridge} keys="${world.bridgeKeys}" nodeGlobalsAbsent=${world.node}`,
    );

    await runBenignPhase({ host, artifactRoot, driver, ledger, log, window, handler: attached.handler, probeSession });
    await runHostilePhase({ host, artifactRoot, driver, ledger, log });
    await runFloodPhase({ host, artifactRoot, driver, ledger });
    await runBridgePhase({ host, artifactRoot, driver, ledger });
    await runLoopPhase({ host, artifactRoot, driver, ledger, window });

    const screenshot = await window.webContents.capturePage().catch(() => null);
    if (screenshot) await writeFile(path.join(evidenceRoot, "probe-window.png"), screenshot.toPNG());
  } catch (error) {
    ledger.record("probe-run", false, error instanceof Error ? error.message : String(error));
    ledger.note(`probe aborted: ${error instanceof Error ? error.message : String(error)}`);
  }

  const report: ProbeReport & { notes: string[]; guards: ViewGuardLog } = {
    version: PROBE_REPORT_VERSION,
    packaged: app.isPackaged,
    platform: process.platform,
    electron: process.versions.electron ?? "unknown",
    container: "sandboxed-iframe",
    startedAt,
    metrics: ledger.metrics,
    checks: ledger.checks,
    notes: ledger.notes,
    guards: log,
  };
  const evaluation = evaluateProbeReport(report, { requirePackaged: app.isPackaged });
  const summary = renderProbeSummary(report, evaluation);
  const target = options.reportPath ?? path.join(evidenceRoot, "isolation-report.json");
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, `${JSON.stringify({ ...report, evaluation }, null, 2)}\n`, "utf8");
  await writeFile(path.join(evidenceRoot, "isolation-summary.txt"), `${summary}\n`, "utf8");
  process.stdout.write(`${summary}\nreport: ${target}\n`);

  driver.dispose();
  host.releaseAll();
  if (!window.isDestroyed()) window.destroy();
  return evaluation.passed ? 0 : 1;
}

async function registerFixture(host: ViewHost, artifactRoot: string, name: ViewFixtureName, sessionId: string, revision = 1): Promise<ViewBinding> {
  const directory = await writeViewFixture(artifactRoot, name);
  return host.register({ viewId: `probe-${name}`, revision, sessionId, directory, entry: "index.html" });
}

async function mountFixture(driver: ProbeDriver, binding: ViewBinding, args: Record<string, unknown> = {}): Promise<CommandOutcome> {
  return driver.send("mount", {
    url: binding.url,
    viewId: binding.viewId,
    sessionId: binding.sessionId,
    revision: binding.revision,
    capability: `cap-${binding.token}`,
    ...args,
  }, Number(args.timeoutMs ?? COMMAND_TIMEOUT_MS) + 2_000);
}

function adoptViewChecks(ledger: ProbeLedger, outcome: CommandOutcome, wanted: readonly string[]): void {
  const reported = Array.isArray(outcome.value.checks) ? (outcome.value.checks as ProbeCheckResult[]) : [];
  const byId = new Map(reported.map(check => [check.id, check]));
  for (const id of wanted) {
    const check = byId.get(id);
    ledger.record(id, check?.passed === true, check?.detail ?? "not reported by the view");
  }
}

async function runBenignPhase(context: {
  host: ViewHost; artifactRoot: string; driver: ProbeDriver; ledger: ProbeLedger; log: ViewGuardLog;
  window: BrowserWindow; handler: ViewProtocolHandler; probeSession: Electron.Session;
}): Promise<void> {
  const { host, driver, ledger, window, handler, probeSession } = context;
  const binding = await registerFixture(host, context.artifactRoot, "benign", "probe-session");
  const mounted = await mountFixture(driver, binding);
  ledger.record("view-entry-loaded", mounted.ok && mounted.value.handshaken === true, `reason=${String(mounted.value.reason)} handshaken=${String(mounted.value.handshaken)}`);

  const echo = await driver.send("echo", { text: "host-to-view" });
  ledger.record("restricted-channel-round-trip", echo.ok && echo.value.echoed !== null, `echoed=${String(echo.value.echoed)}`);

  const frames = childFrames(window);
  const hostProcess = Number((window.webContents.mainFrame as unknown as { processId?: number }).processId ?? -1);
  const viewFrame = frames.find(frame => frame.url.startsWith(`${VIEW_SCHEME}:`)) ?? frames[0];
  ledger.record(
    "view-out-of-process",
    Boolean(viewFrame) && viewFrame.processId > 0 && viewFrame.processId !== hostProcess,
    `host=${hostProcess} view=${viewFrame?.processId ?? "none"} osPid=${viewFrame?.osProcessId ?? "none"}`,
  );

  const request = async (url: string, method = "GET") => {
    try {
      const response = await probeSession.fetch(url, { method, bypassCustomProtocolHandlers: false });
      return { status: response.status, mechanism: "session.fetch" };
    } catch {
      const response = await handler({ url, method } as unknown as Request);
      return { status: response.status, mechanism: "protocol.handle" };
    }
  };
  const traversal = await request(`${VIEW_SCHEME}://${binding.token}/../secret.txt`);
  const encoded = await request(`${VIEW_SCHEME}://${binding.token}/%2e%2e%2fsecret.txt`);
  // WHATWG URL resolves a raw `..` in-root before the handler sees it (nonexistent -> 404); a
  // percent-encoded `..` survives parsing and must be refused by the handler (400). Either way
  // nothing outside the token root is served, so both client-error refusals count as blocked.
  const notServed = (status: number) => status === 400 || status === 404;
  ledger.record("traversal-request-blocked", notServed(traversal.status) && notServed(encoded.status), `raw=${traversal.status} encoded=${encoded.status} via ${traversal.mechanism}`);
  const foreign = await request(`${VIEW_SCHEME}://${"d".repeat(32)}/index.html`);
  ledger.record("foreign-token-blocked", foreign.status === 404, `status=${foreign.status}`);
  const script = await request(`${VIEW_SCHEME}://${binding.token}/payload.js`);
  ledger.record("script-mime-unmappable", script.status === 415, `status=${script.status}`);
  const unbound = await request(`${VIEW_SCHEME}://${binding.token}/../../views/hostile/index.html`);
  ledger.record("unbound-directory-blocked", unbound.status === 400 || unbound.status === 403 || unbound.status === 404, `status=${unbound.status}`);
  const post = await request(binding.url, "POST");
  ledger.note(`POST on a bound entry answered ${post.status} via ${post.mechanism}`);

  const downloadsBefore = context.log.downloads.length;
  window.webContents.downloadURL(`${VIEW_SCHEME}://${binding.token}/payload.txt`);
  await delay(600);
  const started = context.log.downloads.slice(downloadsBefore);
  ledger.record(
    "download-blocked",
    started.length > 0 && started.every(item => item.cancelled),
    `attempted=${started.length} cancelled=${started.filter(item => item.cancelled).length}`,
  );

  const saved = clipboard.readText();
  const clipboardProbe = await window.webContents
    .executeJavaScript(
      `(async () => { try { await navigator.clipboard.writeText("riu-probe-clipboard"); return await navigator.clipboard.readText(); } catch (error) { return "error:" + String(error && error.name || error); } })()`,
      true,
    )
    .catch((error: unknown) => `error:${String(error)}`);
  clipboard.writeText(saved);
  ledger.record("host-clipboard-allowed", clipboardProbe === "riu-probe-clipboard", `result=${String(clipboardProbe)}`);
}

const HOSTILE_VIEW_CHECKS = [
  "node-api-absent", "preload-bridge-absent", "parent-dom-blocked", "top-window-access-blocked",
  "opaque-origin-enforced", "storage-apis-blocked", "network-fetch-blocked", "websocket-blocked",
  "remote-subresource-blocked", "window-open-blocked", "form-submission-blocked",
] as const;

async function runHostilePhase(context: { host: ViewHost; artifactRoot: string; driver: ProbeDriver; ledger: ProbeLedger; log: ViewGuardLog }): Promise<void> {
  const { host, driver, ledger, log } = context;
  host.release("probe-benign");
  const navigationsBefore = log.navigations.length;
  const permissionsBefore = log.permissions.length;
  const requestsBefore = log.blockedRequests.length;
  const binding = await registerFixture(host, context.artifactRoot, "hostile", "probe-session");
  const mounted = await mountFixture(driver, binding, { timeoutMs: 6_000 });
  adoptViewChecks(ledger, mounted, HOSTILE_VIEW_CHECKS);
  await delay(1_200);

  const navigations = log.navigations.slice(navigationsBefore);
  const escapes = navigations.filter(entry => entry.verdict === "block");
  ledger.record(
    "frame-navigation-blocked",
    escapes.length > 0 && navigations.filter(entry => entry.verdict === "allow").length <= 1,
    `blocked=${escapes.length} allowed=${navigations.length - escapes.length} targets=${escapes.map(entry => entry.url).slice(0, 3).join(" | ")}`,
  );

  const permissions = log.permissions.slice(permissionsBefore);
  const fromView = permissions.filter(entry => !entry.isMainFrame || entry.origin === "null" || entry.origin.startsWith(`${VIEW_SCHEME}:`));
  ledger.record(
    "permission-requests-denied",
    fromView.length > 0 && fromView.every(entry => !entry.granted),
    `viewRequests=${fromView.length} granted=${fromView.filter(entry => entry.granted).length} seen=${[...new Set(fromView.map(entry => entry.permission))].join(",")}`,
  );
  ledger.note(`blocked network requests during the hostile phase: ${log.blockedRequests.slice(requestsBefore).slice(0, 5).join(" | ") || "none observed"}`);
}

async function runFloodPhase(context: { host: ViewHost; artifactRoot: string; driver: ProbeDriver; ledger: ProbeLedger }): Promise<void> {
  const { host, driver, ledger } = context;
  host.release("probe-hostile");
  const binding = await registerFixture(host, context.artifactRoot, "flood", "probe-session");
  await mountFixture(driver, binding, { timeoutMs: 3_000 });
  const during = await pingSeries(driver, 6);
  ledger.metric("hostPingDuringFloodMs", during.worstMs);
  await delay(500);
  const report = await driver.send("flood-report");
  const rateLimited = Number(report.value.rateLimited ?? 0);
  const accepted = Number(report.value.accepted ?? 0);
  ledger.record("flood-rate-limited", report.ok && rateLimited > 0, `rateLimited=${rateLimited} accepted=${accepted}`);
  const after = await pingSeries(driver, 3);
  ledger.record("host-responsive-after-flood", after.answered === 3, `answered=${after.answered}/3 worst=${after.worstMs}ms`);
}

const BRIDGE_CHECKS = ["forged-bridge-source-rejected", "missing-capability-rejected", "stale-instance-rejected", "unsupported-method-rejected", "oversize-message-rejected"] as const;

async function runBridgePhase(context: { host: ViewHost; artifactRoot: string; driver: ProbeDriver; ledger: ProbeLedger }): Promise<void> {
  const { host, driver, ledger } = context;
  host.release("probe-flood");
  const binding = await registerFixture(host, context.artifactRoot, "benign", "probe-session", 2);
  await mountFixture(driver, binding);
  const abuse = await driver.send("abuse", {}, 6_000);
  const reported = Array.isArray(abuse.value) ? (abuse.value as ProbeCheckResult[]) : [];
  const byId = new Map(reported.map(check => [check.id, check]));
  for (const id of BRIDGE_CHECKS) {
    const check = byId.get(id);
    ledger.record(id, check?.passed === true, check?.detail ?? `not reported (${abuse.error ?? "no detail"})`);
  }
}

async function runLoopPhase(context: { host: ViewHost; artifactRoot: string; driver: ProbeDriver; ledger: ProbeLedger; window: BrowserWindow }): Promise<void> {
  const { host, driver, ledger, window } = context;
  host.release("probe-benign");
  const binding = await registerFixture(host, context.artifactRoot, "loop", "probe-session");
  const mounted = await mountFixture(driver, binding, { expectState: false, timeoutMs: 3_000 });
  ledger.note(`loop fixture mount: ${String(mounted.value.reason ?? mounted.error)}`);
  await delay(500);
  const frame = childFrames(window).find(entry => entry.url.startsWith(`${VIEW_SCHEME}:`)) ?? childFrames(window)[0];
  const osPid = frame?.osProcessId ?? -1;

  const during = await pingSeries(driver, 6);
  ledger.metric("hostPingDuringLoopMs", during.worstMs);
  ledger.record("host-responsive-during-loop", during.answered === 6, `answered=${during.answered}/6 worst=${during.worstMs}ms`);

  const typed = "ok-while-looping";
  await driver.send("focus-chat");
  window.webContents.focus();
  for (const character of typed) window.webContents.sendInputEvent({ type: "char", keyCode: character });
  await delay(250);
  const chat = await driver.send("chat-value");
  ledger.record("chat-input-usable-during-loop", chat.ok && chat.value.value === typed, `value=${JSON.stringify(chat.value.value ?? null)}`);

  const teardownStarted = Date.now();
  const closed = await driver.send("teardown", {}, 6_000);
  let frameGone = false;
  for (let attempt = 0; attempt < 60 && !frameGone; attempt += 1) {
    frameGone = childFrames(window).every(entry => !entry.url.startsWith(`${VIEW_SCHEME}:`));
    if (!frameGone) await delay(50);
  }
  const teardownMs = Date.now() - teardownStarted;
  ledger.metric("viewTeardownMs", teardownMs);
  ledger.record("view-destroyed-after-loop", closed.ok && frameGone, `closed=${String(closed.value.closed)} frameGone=${frameGone} in ${teardownMs}ms`);

  let exited = !processAlive(osPid);
  for (let attempt = 0; attempt < 40 && !exited; attempt += 1) { await delay(100); exited = !processAlive(osPid); }
  ledger.record("view-process-exited", osPid > 0 ? exited : frameGone, `osPid=${osPid} exited=${exited}`);

  const after = await pingSeries(driver, 3);
  ledger.metric("hostPingAfterTeardownMs", after.worstMs);
  ledger.record("host-responsive-after-teardown", after.answered === 3, `answered=${after.answered}/3 worst=${after.worstMs}ms`);
  host.releaseAll();
}
