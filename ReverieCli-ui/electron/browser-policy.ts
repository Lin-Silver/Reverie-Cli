import path from "node:path";
import type { BrowserElement, BrowserRequest, Rectangle, Viewport } from "../src/generated/core-types";

export const BROWSER_PROTOCOL = "reverie.browser.v1";
const KEYS = new Set(["enter", "tab", "escape", "backspace", "delete", "space", "arrow_up", "arrow_down", "arrow_left", "arrow_right", "home", "end", "page_up", "page_down"]);

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid browser data.");
  return value as Record<string, unknown>;
}

function fields(value: unknown, names: string[]): Record<string, unknown> {
  const result = object(value);
  const keys = Object.keys(result);
  if (keys.length !== names.length || keys.some(key => !names.includes(key))) throw new Error("Invalid browser fields.");
  return result;
}

export function browserId(value: unknown): value is string {
  return typeof value === "string" && /^[A-Za-z0-9_.-]{1,256}$/.test(value);
}

export function browserUrl(value: unknown): value is string {
  if (value === "about:blank") return true;
  if (typeof value !== "string" || Buffer.byteLength(value, "utf8") > 8192 || /[\u0000-\u001f\u007f-\u009f]/u.test(value)) return false;
  try {
    const url = new URL(value);
    return (url.protocol === "http:" || url.protocol === "https:") && !!url.hostname && !url.username && !url.password;
  } catch { return false; }
}

function text(value: unknown, limit: number): value is string {
  return typeof value === "string" && Buffer.byteLength(value, "utf8") <= limit && !value.includes("\0");
}

function target(value: unknown): void {
  const result = fields(value, ["tab_id", "observation_id", "revision"]);
  if (!browserId(result.tab_id) || !browserId(result.observation_id) || !Number.isSafeInteger(result.revision) || Number(result.revision) < 1) throw new Error("Invalid browser target.");
}

/** Validate the generated protocol at the trusted-host boundary, then detach caller references. */
export function browserRequest(value: unknown): BrowserRequest {
  const result = fields(value, ["protocol", "request_id", "host", "scope", "profile", "action"]);
  const host = fields(result.host, ["host_id", "generation"]);
  const scope = fields(result.scope, ["project_root", "session_id", "run_id"]);
  const profile = fields(result.profile, ["mode", "profile_id"]);
  if (result.protocol !== BROWSER_PROTOCOL || !browserId(result.request_id) || !browserId(host.host_id) || !browserId(host.generation)
    || typeof scope.project_root !== "string" || scope.project_root.includes("\0") || !path.isAbsolute(scope.project_root)
    || !browserId(scope.session_id) || !browserId(scope.run_id) || !browserId(profile.profile_id)
    || profile.mode !== "ephemeral" && profile.mode !== "persistent") throw new Error("Invalid browser identity.");
  const action = object(result.action);
  switch (action.action) {
    case "open": fields(action, ["action", "url"]); if (!browserUrl(action.url)) throw new Error("Invalid browser URL."); break;
    case "list": fields(action, ["action"]); break;
    case "observe": fields(action, ["action", "tab_id"]); if (!browserId(action.tab_id)) throw new Error("Invalid browser tab."); break;
    case "click": fields(action, ["action", "target", "element_id"]); target(action.target); if (!browserId(action.element_id)) throw new Error("Invalid browser element."); break;
    case "type":
      fields(action, ["action", "target", "element_id", "text", "replace"]); target(action.target);
      if (!browserId(action.element_id) || !text(action.text, 65536) || typeof action.replace !== "boolean") throw new Error("Invalid browser input.");
      break;
    case "scroll":
      fields(action, ["action", "target", "element_id", "delta_x", "delta_y"]); target(action.target);
      if (action.element_id !== null && !browserId(action.element_id) || !Number.isInteger(action.delta_x) || !Number.isInteger(action.delta_y)
        || Math.abs(Number(action.delta_x)) > 10000 || Math.abs(Number(action.delta_y)) > 10000) throw new Error("Invalid browser scroll.");
      break;
    case "key":
      fields(action, ["action", "target", "key", "shift"]); target(action.target);
      if (typeof action.key !== "string" || !KEYS.has(action.key) || typeof action.shift !== "boolean") throw new Error("Invalid browser key.");
      break;
    case "navigate": fields(action, ["action", "target", "url"]); target(action.target); if (!browserUrl(action.url)) throw new Error("Invalid browser URL."); break;
    case "close": fields(action, ["action", "target"]); target(action.target); break;
    default: throw new Error("Unsupported browser action.");
  }
  return structuredClone(result) as BrowserRequest;
}

function dimension(value: unknown, max: number): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0 && value <= max;
}

function rectangle(value: unknown, viewport: Viewport): Rectangle {
  const result = fields(value, ["x", "y", "width", "height"]);
  if (typeof result.x !== "number" || !Number.isFinite(result.x) || result.x < 0
    || typeof result.y !== "number" || !Number.isFinite(result.y) || result.y < 0
    || !dimension(result.width, viewport.width) || !dimension(result.height, viewport.height)
    || result.x + result.width > viewport.width || result.y + result.height > viewport.height) throw new Error("Invalid browser bounds.");
  return result as unknown as Rectangle;
}

export interface ObservedElement { element: BrowserElement; point: { x: number; y: number } }
export interface ObservedPage { viewport: Viewport; elements: ObservedElement[] }

export function observedPage(value: unknown, frameId: string): ObservedPage {
  const result = fields(value, ["viewport", "elements"]);
  const viewport = fields(result.viewport, ["width", "height", "device_scale_factor"]);
  if (!browserId(frameId) || !dimension(viewport.width, 65536) || !dimension(viewport.height, 65536)
    || !dimension(viewport.device_scale_factor, 16) || !Array.isArray(result.elements) || result.elements.length > 256) throw new Error("Invalid browser observation.");
  const typedViewport = viewport as unknown as Viewport;
  const ids = new Set<string>();
  let bytes = 0;
  const elements = result.elements.map(value => {
    const item = fields(value, ["element_id", "role", "name", "text", "editable", "bounds", "point"]);
    if (!browserId(item.element_id) || ids.has(item.element_id) || !text(item.role, 128) || !text(item.name, 2048) || !text(item.text, 16384)
      || typeof item.editable !== "boolean") throw new Error("Invalid browser element.");
    ids.add(item.element_id);
    bytes += Buffer.byteLength(item.role) + Buffer.byteLength(item.name) + Buffer.byteLength(item.text);
    if (bytes > 524288) throw new Error("Browser observation is too large.");
    const bounds = rectangle(item.bounds, typedViewport);
    const point = fields(item.point, ["x", "y"]);
    if (typeof point.x !== "number" || !Number.isFinite(point.x) || point.x < bounds.x || point.x >= bounds.x + bounds.width
      || typeof point.y !== "number" || !Number.isFinite(point.y) || point.y < bounds.y || point.y >= bounds.y + bounds.height) throw new Error("Invalid browser hit point.");
    return {
      element: { element_id: item.element_id, frame_id: frameId, role: item.role, name: item.name, text: item.text, editable: item.editable, bounds },
      point: { x: point.x, y: point.y },
    };
  });
  return { viewport: typedViewport, elements };
}

export function browserSummaryUrl(value: string): string {
  if (value === "about:blank") return value;
  try { const url = new URL(value); if (url.protocol !== "http:" && url.protocol !== "https:") return ""; url.username = ""; url.password = ""; url.search = ""; url.hash = ""; return url.href; }
  catch { return ""; }
}

export function browserTitle(value: string): string {
  const clean = value.replace(/[\u0000-\u001f\u007f-\u009f]/gu, " ");
  const bytes = Buffer.from(clean, "utf8");
  if (bytes.length <= 4096) return clean;
  let end = 4096;
  while (end && (bytes[end] & 0xc0) === 0x80) end--;
  return bytes.subarray(0, end).toString("utf8");
}

export function pngDimensions(png: Buffer): { width: number; height: number } {
  if (png.length < 33 || !png.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
    || png.readUInt32BE(8) !== 13 || png.toString("ascii", 12, 16) !== "IHDR") throw new Error("Invalid browser screenshot.");
  const width = png.readUInt32BE(16), height = png.readUInt32BE(20);
  if (!dimension(width, 16384) || !dimension(height, 16384)) throw new Error("Browser screenshot is too large.");
  return { width, height };
}
