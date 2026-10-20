import { mkdir, mkdtemp, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  MAX_VIEW_BUNDLE_BYTES,
  MAX_VIEW_ENTRY_BYTES,
  VIEW_CONTENT_SECURITY_POLICY,
  VIEW_IFRAME_SANDBOX,
  VIEW_SCHEME,
  ViewHost,
  trustedHostFrame,
  viewFrameNavigation,
  viewMimeType,
  viewPermissionDecision,
  viewRequestPath,
  viewResponseHeaders,
} from "./view-host";

const roots: string[] = [];
afterEach(async () => { for (const root of roots.splice(0)) { const actual = path.resolve(root); if (!actual.startsWith(path.resolve(tmpdir()) + path.sep)) throw new Error("Unsafe test cleanup"); await rm(actual, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 }); } });
async function artifactRoot(): Promise<string> { const root = await mkdtemp(path.join(tmpdir(), "reverie-view-")); roots.push(root); return root; }
async function viewDirectory(root: string, name: string, html = "<!doctype html><title>fixture</title>"): Promise<string> { const directory = path.join(root, name); await mkdir(directory, { recursive: true }); await writeFile(path.join(directory, "index.html"), html, "utf8"); return directory; }
const registration = (directory: string, overrides: Partial<{ viewId: string; revision: number; sessionId: string; entry: string }> = {}) => ({ viewId: "view-a", revision: 1, sessionId: "session-a", directory, ...overrides });

describe("reverie-view host policy", () => {
  it("serves a validated MCP App MIME without widening the offline CSP", async () => {
    const root = await artifactRoot();
    const directory = await viewDirectory(root, "mcp-app");
    const host = new ViewHost({ root });
    const binding = await host.register({ ...registration(directory), mimeType: "text/html;profile=mcp-app" });
    const response = await host.respond(binding.url);
    expect(response.status).toBe(200);
    expect(response.headers["Content-Type"]).toBe("text/html;profile=mcp-app; charset=utf-8");
    expect(response.headers["Content-Security-Policy"]).toBe(VIEW_CONTENT_SECURITY_POLICY);
    await expect(host.register({ ...registration(directory), mimeType: "application/javascript" })).rejects.toThrow("MIME");
  });

  it("keeps the offline response policy, sandbox flags and host-frame identity contract", () => {
    expect(VIEW_SCHEME).toBe("reverie-view");
    expect(VIEW_IFRAME_SANDBOX).toBe("allow-scripts");
    for (const directive of ["default-src 'none'", "script-src 'unsafe-inline'", "style-src 'unsafe-inline'", "img-src data: blob:", "font-src 'none'", "media-src data: blob:", "connect-src 'none'", "frame-src 'none'", "worker-src 'none'", "object-src 'none'", "base-uri 'none'", "form-action 'none'"]) expect(VIEW_CONTENT_SECURITY_POLICY).toContain(directive);
    expect(VIEW_CONTENT_SECURITY_POLICY).not.toMatch(/allow-same-origin|allow-popups|'unsafe-eval'|\bhttps?:/);
    const headers = viewResponseHeaders("text/html");
    expect(headers["Content-Type"]).toBe("text/html; charset=utf-8");
    expect(headers["Content-Security-Policy"]).toBe(VIEW_CONTENT_SECURITY_POLICY);
    expect(headers["X-Content-Type-Options"]).toBe("nosniff");
    expect(headers["Cache-Control"]).toBe("no-store");
    expect(headers["Referrer-Policy"]).toBe("no-referrer");
    expect(headers["Cross-Origin-Resource-Policy"]).toBe("same-origin");
    expect(headers["Permissions-Policy"]).toMatch(/camera=\(\)/);
    expect(viewMimeType("index.html")).toBe("text/html");
    expect(viewMimeType("style.css")).toBe("text/css");
    expect(viewMimeType("data.json")).toBe("application/json");
    expect(viewMimeType("payload.svg")).toBe("image/svg+xml");
    expect(viewMimeType("tool.exe")).toBeNull();
    expect(viewMimeType("script.mjs")).toBeNull();
    const host = { webContents: { id: 1 }, mainFrame: { id: 10 } };
    expect(trustedHostFrame({ sender: host.webContents, senderFrame: host.mainFrame }, host)).toBe(true);
    expect(trustedHostFrame({ sender: host.webContents, senderFrame: { id: 11 } }, host)).toBe(false);
    expect(trustedHostFrame({ sender: { id: 2 }, senderFrame: host.mainFrame }, host)).toBe(false);
    expect(trustedHostFrame({ sender: host.webContents, senderFrame: null }, host)).toBe(false);
    expect(trustedHostFrame({ sender: host.webContents, senderFrame: host.mainFrame }, null)).toBe(false);
  });

  it("grants the host page only its existing clipboard permissions and never answers a view frame", () => {
    const hostPage = { isMainFrame: true, requestingUrl: "file:///C:/app/dist/index.html", requestingOrigin: "file://" };
    expect(viewPermissionDecision("clipboard-read", hostPage)).toBe(true);
    expect(viewPermissionDecision("clipboard-sanitized-write", hostPage)).toBe(true);
    expect(viewPermissionDecision("fullscreen", hostPage)).toBe(true);
    for (const permission of ["media", "geolocation", "notifications", "midi", "midiSysex", "pointerLock", "openExternal", "display-capture", "hid", "serial", "usb", "idle-detection", "window-management", "fileSystem", "storage-access", "speaker-selection"]) expect(viewPermissionDecision(permission, hostPage), permission).toBe(false);
    expect(viewPermissionDecision("clipboard-read", { isMainFrame: false, requestingUrl: `reverie-view://${"a".repeat(32)}/index.html`, requestingOrigin: "null" })).toBe(false);
    expect(viewPermissionDecision("clipboard-read", { isMainFrame: true, requestingOrigin: "null" })).toBe(false);
    expect(viewPermissionDecision("clipboard-read", { isMainFrame: true, requestingUrl: `reverie-view://${"a".repeat(32)}/index.html` })).toBe(false);
    expect(viewPermissionDecision("clipboard-read")).toBe(false);
  });

  it("allows only the first commit of a bound view URL and blocks every other frame navigation", () => {
    const bound = (token: string) => token === "a".repeat(32);
    const entry = `reverie-view://${"a".repeat(32)}/index.html`;
    expect(viewFrameNavigation({ frameUrl: "", targetUrl: entry, isBound: bound })).toBe("allow");
    expect(viewFrameNavigation({ frameUrl: "about:blank", targetUrl: entry, isBound: bound })).toBe("allow");
    expect(viewFrameNavigation({ frameUrl: entry, targetUrl: entry, isBound: bound })).toBe("block");
    expect(viewFrameNavigation({ frameUrl: entry, targetUrl: "https://example.invalid/", isBound: bound })).toBe("block");
    expect(viewFrameNavigation({ frameUrl: "", targetUrl: "https://example.invalid/", isBound: bound })).toBe("block");
    expect(viewFrameNavigation({ frameUrl: "", targetUrl: "file:///C:/Windows/win.ini", isBound: bound })).toBe("block");
    expect(viewFrameNavigation({ frameUrl: "", targetUrl: `reverie-view://${"b".repeat(32)}/index.html`, isBound: bound })).toBe("block");
    expect(viewFrameNavigation({ frameUrl: "", targetUrl: "data:text/html,<script>1</script>", isBound: bound })).toBe("block");
    expect(viewFrameNavigation({ frameUrl: "", targetUrl: "not a url", isBound: bound })).toBe("block");
  });

  it("rejects traversal, device paths, encoded escapes and foreign tokens before touching the disk", () => {
    const binding = { token: "a".repeat(32), entry: "index.html" };
    expect(viewRequestPath(binding, `reverie-view://${binding.token}/`)).toBe("index.html");
    expect(viewRequestPath(binding, `reverie-view://${binding.token}/assets/app.css?v=2#top`)).toBe("assets/app.css");
    for (const target of [
      `reverie-view://${binding.token}/../secret.txt`,
      `reverie-view://${binding.token}/assets/../../secret.txt`,
      `reverie-view://${binding.token}/%2e%2e/secret.txt`,
      `reverie-view://${binding.token}/%2E%2E%2Fsecret.txt`,
      `reverie-view://${binding.token}/%2fsecret.txt`,
      `reverie-view://${binding.token}/..%5csecret.txt`,
      `reverie-view://${binding.token}/assets%5c..%5c..%5csecret.txt`,
      `reverie-view://${binding.token}/C:/Windows/win.ini`,
      `reverie-view://${binding.token}//server/share/secret.txt`,
      `reverie-view://${binding.token}/CON`,
      `reverie-view://${binding.token}/index.html%00.png`,
      `reverie-view://${binding.token}/.git/config`,
      `reverie-view://${"b".repeat(32)}/index.html`,
      `reverie-view://${binding.token.toUpperCase()}/index.html`,
      `file://${binding.token}/index.html`,
      `reverie-view:///index.html`,
    ]) expect(() => viewRequestPath(binding, target), target).toThrow();
  });
});

describe("reverie-view resource protocol", () => {
  it("maps only the bound entry and declared resources with the offline policy headers", async () => {
    const root = await artifactRoot();
    const host = new ViewHost({ root });
    const directory = await viewDirectory(root, "view-a");
    await mkdir(path.join(directory, "assets"));
    await writeFile(path.join(directory, "assets", "app.css"), ":root{color:#fff}", "utf8");
    const binding = await host.register(registration(directory));
    expect(binding.token).toMatch(/^[0-9a-f]{32}$/);
    expect(binding.entry).toBe("index.html");
    expect(binding.url).toBe(`reverie-view://${binding.token}/index.html`);
    expect(host.binding(binding.token)).toEqual(binding);

    const entry = await host.respond(binding.url);
    expect(entry.status).toBe(200);
    expect(entry.headers["Content-Security-Policy"]).toBe(VIEW_CONTENT_SECURITY_POLICY);
    expect(entry.body?.toString("utf8")).toContain("<title>fixture</title>");
    expect((await host.respond(`reverie-view://${binding.token}/`)).status).toBe(200);
    expect((await host.respond(`reverie-view://${binding.token}/assets/app.css`)).headers["Content-Type"]).toBe("text/css; charset=utf-8");
    expect((await host.respond(binding.url, "POST")).status).toBe(405);
    expect((await host.respond(`reverie-view://${binding.token}/missing.html`)).status).toBe(404);
    expect((await host.respond(`reverie-view://${binding.token}/assets`)).status).toBe(404);
    expect((await host.respond(`reverie-view://${binding.token}/../secret.txt`)).status).toBe(400);
    expect((await host.respond(`reverie-view://${"c".repeat(32)}/index.html`)).status).toBe(404);
    await writeFile(path.join(directory, "payload.bin"), "binary", "utf8");
    expect((await host.respond(`reverie-view://${binding.token}/payload.bin`)).status).toBe(415);
  });

  it("refuses link escapes, directories, oversized bundles and unknown roots at registration", async () => {
    const root = await artifactRoot();
    const host = new ViewHost({ root });
    const outside = path.join(root, "outside");
    await mkdir(outside, { recursive: true });
    await writeFile(path.join(outside, "secret.txt"), "classified", "utf8");

    await expect(host.register(registration(path.join(root, "absent")))).rejects.toThrow(/directory/i);
    await expect(host.register(registration(path.join(root, "view-missing-entry", "..", "outside")))).rejects.toThrow();
    const noEntry = path.join(root, "view-empty");
    await mkdir(noEntry, { recursive: true });
    await expect(host.register(registration(noEntry))).rejects.toThrow(/entry/i);
    const traversalEntry = await viewDirectory(root, "view-entry");
    await expect(host.register(registration(traversalEntry, { entry: "../outside/secret.txt" }))).rejects.toThrow();
    await expect(host.register(registration(traversalEntry, { entry: "index.html", sessionId: "" }))).rejects.toThrow();

    const external = path.join(await artifactRoot(), "external");
    await mkdir(external, { recursive: true });
    await writeFile(path.join(external, "index.html"), "<!doctype html>", "utf8");
    await expect(host.register(registration(external))).rejects.toThrow(/root/i);

    const linked = await viewDirectory(root, "view-linked");
    let junctions = true;
    try { await symlink(outside, path.join(linked, "escape"), "junction"); } catch { junctions = false; }
    const linkedBinding = await host.register(registration(linked, { viewId: "view-linked" }));
    if (junctions) expect((await host.respond(`reverie-view://${linkedBinding.token}/escape/secret.txt`)).status).toBe(403);

    const oversized = await viewDirectory(root, "view-oversized");
    await writeFile(path.join(oversized, "index.html"), "x".repeat(MAX_VIEW_ENTRY_BYTES + 1), "utf8");
    await expect(host.register(registration(oversized, { viewId: "view-oversized" }))).rejects.toThrow(/2 MiB|size|large/i);
    const bulky = await viewDirectory(root, "view-bulky");
    for (let index = 0; index < 5; index += 1) await writeFile(path.join(bulky, `blob-${index}.json`), "0".repeat(Math.ceil(MAX_VIEW_BUNDLE_BYTES / 4)), "utf8");
    await expect(host.register(registration(bulky, { viewId: "view-bulky" }))).rejects.toThrow(/total|bundle|large/i);
  });

  it("scopes bindings to one session and revision and revokes them on release", async () => {
    const root = await artifactRoot();
    const host = new ViewHost({ root });
    const first = await host.register(registration(await viewDirectory(root, "a"), { viewId: "view-a", sessionId: "session-a" }));
    const second = await host.register(registration(await viewDirectory(root, "b"), { viewId: "view-b", sessionId: "session-b" }));
    expect(second.token).not.toBe(first.token);
    expect((await host.respond(`reverie-view://${first.token}/index.html`)).status).toBe(200);

    const replaced = await host.register(registration(await viewDirectory(root, "a2"), { viewId: "view-a", revision: 2, sessionId: "session-a" }));
    expect(replaced.token).not.toBe(first.token);
    expect((await host.respond(first.url)).status).toBe(404);
    expect(host.binding(first.token)).toBeNull();

    expect(host.releaseSession("session-a")).toBe(1);
    expect((await host.respond(replaced.url)).status).toBe(404);
    expect((await host.respond(second.url)).status).toBe(200);
    expect(host.release("view-b")).toBe(1);
    expect(host.release("view-b")).toBe(0);
    expect((await host.respond(second.url)).status).toBe(404);
    expect(host.bindings()).toEqual([]);
  });

  it("re-reads bytes through the opened handle so a swapped entry cannot be served", async () => {
    const root = await artifactRoot();
    const host = new ViewHost({ root });
    const directory = await viewDirectory(root, "view-toctou", "<!doctype html><title>trusted</title>");
    const binding = await host.register(registration(directory));
    const target = path.join(directory, "index.html");
    await rm(target);
    await symlink(path.join(root, "outside-secret.txt"), target).catch(async () => { await writeFile(target, "<!doctype html><title>swapped</title>", "utf8"); });
    const response = await host.respond(binding.url);
    expect(response.body?.toString("utf8") ?? "").not.toContain("classified");
    expect([200, 403, 404]).toContain(response.status);
    if (response.status === 200) expect(response.body?.toString("utf8")).toContain("swapped");
  });
});

// The kernel's ViewStore persists managed views under <project_data_dir>/views,
// which is a DIFFERENT directory from the host's own default artifact root. The
// host must be able to bind a view the core already resolved there -- but only
// after the core hands it that root, and never a directory outside every root it
// trusts. allowRoot is the one widening seam; the forged-event defense lives one
// layer up (a forged view id never resolves to a directory to allow).
describe("reverie-view host trusted roots", () => {
  it("binds a view inside a root allowed after construction, outside the default root", async () => {
    const root = await artifactRoot();
    const host = new ViewHost({ root });
    const managed = await artifactRoot();
    const directory = await viewDirectory(managed, "v-ext");
    await expect(host.register(registration(directory, { viewId: "v-ext" }))).rejects.toThrow(/root/i);
    const trusted = await host.allowRoot(managed);
    expect(path.resolve(trusted)).toBe(path.resolve(await realpath(managed)));
    const binding = await host.register(registration(directory, { viewId: "v-ext" }));
    expect(binding.url).toBe(`reverie-view://${binding.token}/index.html`);
    expect((await host.respond(binding.url)).status).toBe(200);
  });

  it("still refuses a directory outside every trusted root", async () => {
    const root = await artifactRoot();
    const host = new ViewHost({ root });
    await host.allowRoot(await artifactRoot());
    const stranger = await viewDirectory(await artifactRoot(), "stranger");
    await expect(host.register(registration(stranger, { viewId: "stranger" }))).rejects.toThrow(/root/i);
  });

  it("rejects allowRoot for a path that is not an existing directory", async () => {
    const root = await artifactRoot();
    const host = new ViewHost({ root });
    await expect(host.allowRoot(path.join(root, "does-not-exist"))).rejects.toThrow();
  });

  it("keeps serving views registered under the default root after trusting another", async () => {
    const root = await artifactRoot();
    const host = new ViewHost({ root });
    await host.allowRoot(await artifactRoot());
    const binding = await host.register(registration(await viewDirectory(root, "default-view"), { viewId: "default-view" }));
    expect((await host.respond(binding.url)).status).toBe(200);
  });
});
