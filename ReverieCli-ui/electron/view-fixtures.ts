/**
 * Minimal offline HTML fixtures for the packaged isolation probe.
 *
 * They are string constants rather than shipped files so the packaged application can
 * materialise them inside its own repo-local artifact root at probe time, which also
 * exercises the real `ViewHost.register` path instead of a hand-built binding.
 */

import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";

/** Shared inline handshake. The view only ever talks to its embedder, and only after the host issues a capability. */
const HANDSHAKE = `
    var capability = null;
    function post(message) { parent.postMessage(message, "*"); }
    function report(checks) { post({ jsonrpc: "2.0", id: "state-1", method: "reverie/view-state", capability: capability, params: { checks: checks } }); }
    function check(id, run) { try { return { id: id, passed: run() === true, detail: "evaluated" }; } catch (error) { return { id: id, passed: false, detail: "threw: " + String(error && error.name || error) }; } }
    function throws(run) { try { run(); return false; } catch (error) { return true; } }
    addEventListener("message", function (event) {
      if (event.source !== parent || !event.data || typeof event.data !== "object") return;
      if (typeof event.data.capability === "string") { capability = event.data.capability; post({ jsonrpc: "2.0", method: "ui/notifications/initialized", capability: capability }); if (typeof ready === "function") ready(); }
    });
    post({ jsonrpc: "2.0", id: "init", method: "ui/initialize", params: { protocolVersion: "1" } });
`;

const BENIGN = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Reverie view fixture</title>
<style>body{margin:0;font:13px system-ui;background:#101014;color:#e6e6ef}main{padding:14px}b{color:#8ab4ff}</style>
</head><body><main><b id="state">offline fixture</b><p id="echo">waiting for the host</p></main>
<script>${HANDSHAKE}
    function ready() {
      document.getElementById("state").textContent = "bridge ready";
      report([check("fixture-rendered", function () { return document.getElementById("echo") !== null; })]);
    }
    addEventListener("message", function (event) {
      if (event.source !== parent || !event.data || event.data.method !== "ui/message") return;
      document.getElementById("echo").textContent = String(event.data.params && event.data.params.text || "");
      post({ jsonrpc: "2.0", method: "ui/notifications/initialized", capability: capability });
    });
</script></body></html>
`;

/** Runs the escape battery the spec requires and reports each outcome over the restricted channel. */
const HOSTILE = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Reverie hostile fixture</title></head>
<body><p>probing</p>
<script>${HANDSHAKE}
    // Fired early so the trusted main process has recorded every decision before it is read.
    function requestPermissions() {
      try { navigator.geolocation.getCurrentPosition(function () {}, function () {}); } catch (error) { /* unavailable */ }
      try { if (window.Notification) Notification.requestPermission(); } catch (error) { /* unavailable */ }
      try { navigator.mediaDevices.getUserMedia({ audio: true }).catch(function () {}); } catch (error) { /* unavailable */ }
      try { navigator.clipboard.readText().catch(function () {}); } catch (error) { /* unavailable */ }
      try { var promise = document.documentElement.requestFullscreen(); if (promise) promise.catch(function () {}); } catch (error) { /* unavailable */ }
      try { navigator.permissions.query({ name: "geolocation" }).catch(function () {}); } catch (error) { /* unavailable */ }
    }

    function ready() {
      requestPermissions();
      var checks = [
        check("node-api-absent", function () {
          return typeof require === "undefined" && typeof process === "undefined" && typeof module === "undefined"
            && typeof global === "undefined" && typeof Buffer === "undefined" && typeof __dirname === "undefined";
        }),
        check("preload-bridge-absent", function () {
          var leaked = Object.keys(window).filter(function (key) { return /reverie|electron|ipc|node/i.test(key); });
          return leaked.length === 0 && typeof window.reverie === "undefined" && typeof window.electron === "undefined";
        }),
        check("parent-dom-blocked", function () {
          return throws(function () { return parent.document.body.innerHTML; })
            && throws(function () { parent.document.title = "owned"; })
            && throws(function () { return parent.location.href; });
        }),
        check("top-window-access-blocked", function () {
          return throws(function () { return top.location.href; }) && throws(function () { return top.document.cookie; });
        }),
        (function () {
          // allow-scripts without allow-same-origin yields an opaque origin: window.origin serialises
          // to "null". document.origin is a deprecated, non-standard alias (undefined in modern
          // Chromium), so it is rejected only if it leaks a concrete origin; window.origin is the
          // authoritative signal, corroborated by storage access throwing SecurityError.
          var win = String(window.origin), doc = document.origin, proto = String(location.protocol);
          var docOpaque = doc === undefined || doc === null || String(doc) === "null";
          return { id: "opaque-origin-enforced", passed: win === "null" && docOpaque && proto === "reverie-view:", detail: "window=" + win + " document=" + String(doc) + " protocol=" + proto };
        })(),
        check("storage-apis-blocked", function () {
          // An opaque origin denies DOM storage and cookies: reads throw SecurityError (or cookie is empty).
          return throws(function () { return window.localStorage.length; })
            && throws(function () { return window.sessionStorage.length; })
            && (throws(function () { return document.cookie; }) || document.cookie === "");
        }),
        check("window-open-blocked", function () {
          var opened = null;
          try { opened = window.open("https://example.invalid/", "_blank"); } catch (error) { return true; }
          return opened === null;
        }),
      ];
      var pending = [
        new Promise(function (resolve) {
          fetch("https://example.invalid/probe").then(
            function () { resolve({ id: "network-fetch-blocked", passed: false, detail: "fetch resolved" }); },
            function (error) { resolve({ id: "network-fetch-blocked", passed: true, detail: String(error && error.name || error) }); },
          );
        }),
        new Promise(function (resolve) {
          // The constructor does not throw synchronously; a blocked socket must simply never open.
          var socket = null, opened = false, settled = false;
          var finish = function (passed, detail) { if (settled) return; settled = true; try { if (socket) socket.close(); } catch (error) { /* already gone */ } resolve({ id: "websocket-blocked", passed: passed, detail: detail }); };
          try {
            socket = new WebSocket("wss://example.invalid/probe");
            socket.onopen = function () { opened = true; finish(false, "socket opened"); };
            socket.onerror = function () { finish(!opened, "error without open"); };
            socket.onclose = function () { finish(!opened, opened ? "opened then closed" : "closed without opening"); };
          } catch (error) {
            finish(true, "threw: " + String(error && error.name || error));
          }
          setTimeout(function () { finish(!opened, opened ? "opened" : "never opened"); }, 1200);
        }),
        new Promise(function (resolve) {
          var image = new Image();
          var settled = false;
          var finish = function (passed, detail) { if (!settled) { settled = true; resolve({ id: "remote-subresource-blocked", passed: passed, detail: detail }); } };
          image.onload = function () { finish(false, "remote image loaded"); };
          image.onerror = function () { finish(true, "blocked"); };
          setTimeout(function () { finish(true, "never loaded"); }, 1200);
          image.src = "https://example.invalid/pixel.png";
        }),
        new Promise(function (resolve) {
          var before = location.href;
          var form = document.createElement("form");
          form.method = "POST";
          form.action = "https://example.invalid/submit";
          document.body.appendChild(form);
          try { form.submit(); } catch (error) { /* blocked synchronously */ }
          setTimeout(function () { resolve({ id: "form-submission-blocked", passed: location.href === before, detail: "href unchanged" }); }, 400);
        }),
      ];
      Promise.all(pending).then(function (resolved) {
        report(checks.concat(resolved));
        // Navigation and download attempts are judged by the trusted main process, not by this frame.
        var anchor = document.createElement("a");
        anchor.href = location.href.replace(/[^/]*$/, "") + "payload.txt";
        anchor.download = "escape.txt";
        document.body.appendChild(anchor);
        anchor.click();
        setTimeout(function () { try { location.href = "https://example.invalid/escape"; } catch (error) { /* blocked */ } }, 50);
        setTimeout(function () { try { location.replace("about:blank"); } catch (error) { /* blocked */ } }, 150);
      });
    }
</script></body></html>
`;

/** Floods the embedder with well-formed messages so the host-side rate limit is measured, not assumed. */
const FLOOD = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Reverie flood fixture</title></head>
<body><p>flooding</p>
<script>${HANDSHAKE}
    function ready() {
      report([check("fixture-rendered", function () { return true; })]);
      for (var round = 0; round < 12; round += 1) {
        setTimeout(function () {
          for (var index = 0; index < 250; index += 1) {
            post({ jsonrpc: "2.0", method: "ui/message", capability: capability, params: { index: index, filler: "f" } });
          }
        }, round * 25);
      }
    }
</script></body></html>
`;

/** Announces itself, then never yields again. The host must stay usable and be able to close it. */
const LOOP = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Reverie loop fixture</title></head>
<body><p>looping</p>
<script>${HANDSHAKE}
    function ready() {
      post({ jsonrpc: "2.0", method: "ui/notifications/initialized", capability: capability, params: { stage: "loop-start" } });
      setTimeout(function () {
        var spin = 0;
        for (;;) { spin = (spin + 1) % 2147483647; if (spin === -1) break; }
      }, 60);
    }
</script></body></html>
`;

export const VIEW_FIXTURES = { benign: BENIGN, hostile: HOSTILE, flood: FLOOD, loop: LOOP } as const;
export type ViewFixtureName = keyof typeof VIEW_FIXTURES;

/** Writes one fixture bundle under `root` and returns its directory. */
export async function writeViewFixture(root: string, name: ViewFixtureName): Promise<string> {
  const directory = path.join(root, name);
  await rm(directory, { recursive: true, force: true });
  await mkdir(directory, { recursive: true });
  await writeFile(path.join(directory, "index.html"), VIEW_FIXTURES[name], "utf8");
  await writeFile(path.join(directory, "payload.txt"), "fixture payload\n", "utf8");
  await writeFile(path.join(directory, "payload.js"), "// never mappable\n", "utf8");
  return directory;
}
