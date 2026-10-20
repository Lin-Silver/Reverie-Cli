/**
 * Trusted host page for the packaged isolation probe.
 *
 * It only ever sets `iframe.src` to a bound `reverie-view:` URL — view markup is never
 * parsed, inlined or injected into this document. Every inbound `message` event goes
 * through the real `ViewChannel` validator before anything acts on it.
 */

import { BRIDGE_RATE_LIMIT, MAX_BRIDGE_MESSAGE_BYTES, ViewChannel, type BridgeVerdict } from "./view-bridge";

type ProbeCommand = { id: string; name: string; args?: Record<string, unknown> };
type ProbeBridge = {
  onCommand(handler: (command: ProbeCommand) => void): void;
  reply(id: string, value: unknown): void;
  failed(id: string, message: string): void;
};
type ProbeCheck = { id: string; passed: boolean; detail?: string };

const bridge = (window as unknown as { riuProbe?: ProbeBridge }).riuProbe;
const stage = document.getElementById("stage") as HTMLParagraphElement;
const chat = document.getElementById("chat") as HTMLTextAreaElement;
const slot = document.getElementById("slot") as HTMLDivElement;

const VIEW_SANDBOX = "allow-scripts";
let frame: HTMLIFrameElement | null = null;
let channel: ViewChannel | null = null;
let verdicts: BridgeVerdict[] = [];
let viewChecks: ProbeCheck[] = [];
let handshake: ((capability: string) => void) | null = null;
let echoed: ((text: string) => void) | null = null;
let stateReported: (() => void) | null = null;

function announce(text: string): void { stage.textContent = text; }

function post(message: Record<string, unknown>): void {
  // Targeting "*" is unavoidable for an opaque origin, but the recipient is the window
  // object this page created, and the host blocks every navigation of that frame.
  frame?.contentWindow?.postMessage(message, "*");
}

window.addEventListener("message", event => {
  if (!channel) return;
  const verdict = channel.accept(event);
  verdicts.push(verdict);
  if (!verdict.accepted) return;
  if (verdict.method === "ui/initialize") {
    post({ jsonrpc: "2.0", id: verdict.id, result: { protocolVersion: "1", capability: channel.capability }, capability: channel.capability });
    channel.settle(String(verdict.id));
    handshake?.(channel.capability);
    return;
  }
  const params = (verdict.params ?? {}) as Record<string, unknown>;
  if (verdict.method === "reverie/view-state") {
    const reported = Array.isArray(params.checks) ? (params.checks as ProbeCheck[]) : [];
    viewChecks = viewChecks.concat(reported.filter(check => check && typeof check.id === "string"));
    if (verdict.id !== null) channel.settle(verdict.id);
    stateReported?.();
    return;
  }
  if (verdict.method === "ui/notifications/initialized") { echoed?.(String(params.stage ?? "initialized")); return; }
  if (verdict.id !== null) channel.settle(verdict.id);
});

function mount(args: Record<string, unknown>): Promise<unknown> {
  teardown();
  const url = String(args.url ?? "");
  const element = document.createElement("iframe");
  element.setAttribute("sandbox", VIEW_SANDBOX);
  element.setAttribute("referrerpolicy", "no-referrer");
  element.title = "generative view";
  element.width = "640";
  element.height = "180";
  slot.appendChild(element);
  frame = element;
  // The WindowProxy of a frame survives its navigations, so it is the stable identity the
  // channel binds to. It is read only after the element is in the document.
  channel = new ViewChannel({
    source: element.contentWindow,
    sessionId: String(args.sessionId ?? ""),
    viewId: String(args.viewId ?? ""),
    revision: Number(args.revision ?? 1),
    capability: String(args.capability ?? ""),
  });
  element.src = url;
  announce(`mounted ${String(args.viewId ?? "")}`);

  return new Promise(resolve => {
    const expectState = args.expectState !== false;
    let settled = false;
    const finish = (reason: string) => {
      if (settled) return;
      settled = true;
      handshake = null;
      stateReported = null;
      resolve({ reason, handshaken: channel?.initialized === true, checks: viewChecks, stats: channel?.stats, pending: channel?.pending });
    };
    handshake = () => { if (!expectState) finish("handshake"); };
    stateReported = () => finish("state");
    window.setTimeout(() => finish("timeout"), Number(args.timeoutMs ?? 4_000));
  });
}

function teardown(): void {
  channel?.revoke();
  if (frame?.parentNode) frame.parentNode.removeChild(frame);
  frame = null;
  channel = null;
  verdicts = [];
  viewChecks = [];
  handshake = null;
  echoed = null;
  stateReported = null;
  announce("view closed");
}

/** Real `message` events and real validator calls; only the envelopes are hostile. */
async function abuse(): Promise<ProbeCheck[]> {
  const live = channel;
  const target = frame?.contentWindow;
  if (!live || !target) return [{ id: "forged-bridge-source-rejected", passed: false, detail: "no live view" }];
  const seen = () => live.stats.byReason;
  const results: ProbeCheck[] = [];

  const before = seen()["unknown-source"] ?? 0;
  window.postMessage({ jsonrpc: "2.0", method: "ui/message", capability: live.capability, params: { stolen: true } }, "*");
  await new Promise(resolve => window.setTimeout(resolve, 60));
  results.push({ id: "forged-bridge-source-rejected", passed: (seen()["unknown-source"] ?? 0) > before, detail: "window.postMessage with a valid capability" });

  const dispatch = (data: unknown) => {
    const count = verdicts.length;
    window.dispatchEvent(new MessageEvent("message", { source: target as unknown as Window, data }));
    const verdict = verdicts[count];
    return verdict && !verdict.accepted ? verdict.reason : "accepted";
  };
  results.push({ id: "missing-capability-rejected", passed: dispatch({ jsonrpc: "2.0", method: "ui/message", params: {} }) === "missing-capability", detail: "no capability" });
  results.push({ id: "stale-instance-rejected", passed: dispatch({ jsonrpc: "2.0", method: "ui/message", capability: live.capability, revision: 99 }) === "stale-instance", detail: "revision 99" });
  results.push({ id: "unsupported-method-rejected", passed: dispatch({ jsonrpc: "2.0", method: "files/delete", capability: live.capability }) === "unsupported-method", detail: "files/delete" });
  const oversize = dispatch({ jsonrpc: "2.0", method: "ui/message", capability: live.capability, params: { filler: "x".repeat(MAX_BRIDGE_MESSAGE_BYTES) } });
  results.push({ id: "oversize-message-rejected", passed: oversize === "oversize", detail: `${MAX_BRIDGE_MESSAGE_BYTES + 1} bytes` });
  return results;
}

const commands: Record<string, (args: Record<string, unknown>) => unknown | Promise<unknown>> = {
  ping: () => ({ at: Date.now(), stage: stage.textContent }),
  mount: args => mount(args),
  abuse: () => abuse(),
  stats: () => ({ stats: channel?.stats, pending: channel?.pending, checks: viewChecks, rateLimit: BRIDGE_RATE_LIMIT }),
  echo: args => new Promise(resolve => {
    const text = String(args.text ?? "hello");
    echoed = value => resolve({ echoed: value });
    post({ jsonrpc: "2.0", method: "ui/message", capability: channel?.capability, params: { text } });
    window.setTimeout(() => resolve({ echoed: null }), Number(args.timeoutMs ?? 1_500));
  }),
  "focus-chat": () => { chat.value = ""; chat.focus(); return { focused: document.activeElement === chat }; },
  "chat-value": () => ({ value: chat.value, focused: document.activeElement === chat }),
  "flood-report": () => {
    const stats = channel?.stats ?? { accepted: 0, rejected: 0, byReason: {} };
    return { stats, rateLimited: stats.byReason["rate-limited"] ?? 0, accepted: stats.accepted };
  },
  teardown: () => { teardown(); return { closed: frame === null }; },
};

bridge?.onCommand(async command => {
  try {
    const handler = commands[command.name];
    if (!handler) throw new Error(`Unknown probe command: ${command.name}`);
    bridge.reply(command.id, await handler(command.args ?? {}));
  } catch (error) {
    bridge.failed(command.id, error instanceof Error ? error.message : String(error));
  }
});

announce(bridge ? "probe host ready" : "probe bridge missing");
