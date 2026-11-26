// Minimal Chrome DevTools Protocol driver over --remote-debugging-pipe.
// Native Reverie Motion code; no npm dependencies (works on Node >= 20).
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

/** Candidate browser executables, most specific first. */
export function browserCandidates(env = process.env) {
  const list = [];
  for (const key of ["REVERIE_MOTION_BROWSER", "CHROME_PATH", "PUPPETEER_EXECUTABLE_PATH"]) if (env[key]) list.push(env[key]);
  const home = os.homedir();
  if (process.platform === "win32") {
    // Playwright's Chromium is an automation build; branded Chrome 158 refuses
    // headless startup on some machines (observed exit code 21), so it comes later.
    list.push(...playwrightChromium(path.join(env.LOCALAPPDATA || path.join(home, "AppData", "Local"), "ms-playwright"), "chrome-win", "chrome.exe"));
    const roots = [env.PROGRAMFILES || "C:\\Program Files", env["PROGRAMFILES(X86)"] || "C:\\Program Files (x86)", env.LOCALAPPDATA || path.join(home, "AppData", "Local")];
    for (const r of roots) {
      list.push(path.join(r, "Google", "Chrome", "Application", "chrome.exe"));
      list.push(path.join(r, "Microsoft", "Edge", "Application", "msedge.exe"));
      list.push(path.join(r, "Chromium", "Application", "chrome.exe"));
    }
  } else if (process.platform === "darwin") {
    list.push(...playwrightChromium(path.join(home, "Library", "Caches", "ms-playwright"), "chrome-mac", "Chromium.app/Contents/MacOS/Chromium"));
    list.push(
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      "/Applications/Chromium.app/Contents/MacOS/Chromium",
      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    );
  } else {
    list.push(...playwrightChromium(path.join(home, ".cache", "ms-playwright"), "chrome-linux", "chrome"));
    for (const dir of (env.PATH || "").split(path.delimiter)) {
      for (const name of ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"]) list.push(path.join(dir, name));
    }
  }
  return list;
}

function playwrightChromium(base, folder, exe) {
  try {
    return fs.readdirSync(base)
      .filter((d) => /^chromium-\d+$/.test(d))
      .sort((a, b) => Number(b.split("-")[1]) - Number(a.split("-")[1]))
      .flatMap((d) => [path.join(base, d, folder, exe), path.join(base, d, `${folder}64`, exe)]);
  } catch {
    return [];
  }
}

/** Existing browser executables in preference order (deduplicated). */
export function findBrowsers(preferred) {
  const all = preferred ? [preferred, ...browserCandidates()] : browserCandidates();
  const seen = new Set();
  const found = [];
  for (const candidate of all) {
    const key = candidate && path.resolve(candidate).toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    try {
      if (fs.statSync(candidate).isFile()) found.push(candidate);
    } catch {
      /* not installed */
    }
  }
  return found;
}

export function findBrowser(preferred) {
  return findBrowsers(preferred)[0] ?? null;
}

export class BrowserNotFoundError extends Error {
  constructor() {
    super("No Chromium-family browser found. Install Chrome/Edge/Chromium or set REVERIE_MOTION_BROWSER to its executable.");
    this.code = "BROWSER_NOT_FOUND";
  }
}

/**
 * Launch a headless browser. `profileDir` is reused between runs (never deleted)
 * so the tool performs no destructive filesystem operations.
 */
export async function launchBrowser({ executable, profileDir, headless = true, timeoutMs = 15000 } = {}) {
  const candidates = executable ? findBrowsers(executable).slice(0, 1) : findBrowsers();
  if (!candidates.length) throw new BrowserNotFoundError();
  const failures = [];
  for (const exe of candidates) {
    try {
      const browser = await launchOne(exe, path.join(profileDir, path.basename(path.dirname(exe)).replace(/[^\w.-]/g, "_")), headless, timeoutMs);
      browser.failedCandidates = failures;
      return browser;
    } catch (error) {
      failures.push({ executable: exe, error: error.message.slice(0, 300) });
    }
  }
  const err = new Error(`No browser candidate could be launched headless: ${failures.map((f) => `${f.executable}: ${f.error}`).join(" | ")}`);
  err.code = "BROWSER_LAUNCH_FAILED";
  err.failures = failures;
  throw err;
}

async function launchOne(exe, profileDir, headless, timeoutMs) {
  fs.mkdirSync(profileDir, { recursive: true });
  const args = [
    headless ? "--headless=new" : "",
    "--remote-debugging-pipe",
    `--user-data-dir=${profileDir}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--disable-sync",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--force-color-profile=srgb",
    "--hide-scrollbars",
    "--mute-audio",
    "about:blank",
  ].filter(Boolean);
  const child = spawn(exe, args, { stdio: ["ignore", "ignore", "pipe", "pipe", "pipe"], windowsHide: true });
  let stderr = "";
  child.stderr.on("data", (d) => {
    stderr = (stderr + d.toString()).slice(-4000);
  });
  const browser = new Browser(child, exe);
  const exited = new Promise((resolve) => child.once("exit", (code) => resolve(code)));
  try {
    await Promise.race([
      browser.send("Browser.getVersion"),
      exited.then((code) => {
        throw new Error(`Browser exited during startup (code ${code}). ${stderr.trim()}`);
      }),
      timeout(timeoutMs, "Browser did not answer the DevTools pipe in time."),
    ]);
  } catch (error) {
    child.kill();
    throw error;
  }
  browser.exited = exited;
  return browser;
}

function timeout(ms, message) {
  return new Promise((_, reject) => {
    const t = setTimeout(() => reject(new Error(message)), ms);
    t.unref?.();
  });
}

export class Browser {
  constructor(child, executable) {
    this.child = child;
    this.executable = executable;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map(); // sessionId|"" → Set<fn(method, params)>
    this.writer = child.stdio[3];
    this.reader = child.stdio[4];
    let buffer = Buffer.alloc(0);
    this.reader.on("data", (chunk) => {
      buffer = Buffer.concat([buffer, chunk]);
      let end;
      while ((end = buffer.indexOf(0)) !== -1) {
        const message = buffer.subarray(0, end).toString("utf8");
        buffer = buffer.subarray(end + 1);
        this.dispatch(JSON.parse(message));
      }
    });
    child.once("exit", () => {
      for (const { reject } of this.pending.values()) reject(new Error("Browser process exited."));
      this.pending.clear();
    });
  }

  dispatch(msg) {
    if (msg.id !== undefined) {
      const p = this.pending.get(msg.id);
      if (!p) return;
      this.pending.delete(msg.id);
      if (msg.error) p.reject(Object.assign(new Error(`${p.method}: ${msg.error.message}`), { cdp: msg.error }));
      else p.resolve(msg.result);
      return;
    }
    const set = this.listeners.get(msg.sessionId || "");
    if (set) for (const fn of set) fn(msg.method, msg.params);
  }

  send(method, params = {}, sessionId) {
    const id = this.nextId++;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject, method });
      this.writer.write(JSON.stringify(payload) + "\0");
    });
  }

  on(sessionId, fn) {
    const key = sessionId || "";
    if (!this.listeners.has(key)) this.listeners.set(key, new Set());
    this.listeners.get(key).add(fn);
    return () => this.listeners.get(key)?.delete(fn);
  }

  async newPage({ width = 1280, height = 800, deviceScaleFactor = 1, mobile = false, reducedMotion = false } = {}) {
    const { targetId } = await this.send("Target.createTarget", { url: "about:blank" });
    const { sessionId } = await this.send("Target.attachToTarget", { targetId, flatten: true });
    const page = new Page(this, targetId, sessionId);
    await Promise.all([page.send("Page.enable"), page.send("Runtime.enable"), page.send("Log.enable"), page.send("Performance.enable")]);
    await page.send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor, mobile });
    if (mobile) await page.send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
    await page.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: reducedMotion ? "reduce" : "no-preference" }] });
    return page;
  }

  async close() {
    try {
      await Promise.race([this.send("Browser.close"), timeout(3000, "close timeout")]);
    } catch {
      this.child.kill();
    }
    await Promise.race([this.exited, timeout(5000, "exit timeout")]).catch(() => this.child.kill());
  }
}

export class Page {
  constructor(browser, targetId, sessionId) {
    this.browser = browser;
    this.targetId = targetId;
    this.sessionId = sessionId;
    this.errors = [];
    this.console = [];
    this.waiters = [];
    browser.on(sessionId, (method, params) => {
      if (method === "Runtime.exceptionThrown") {
        const d = params.exceptionDetails;
        this.errors.push({ source: "exception", message: d.exception?.description || d.text, url: d.url, line: d.lineNumber });
      } else if (method === "Runtime.consoleAPICalled" && (params.type === "error" || params.type === "assert")) {
        this.errors.push({ source: "console", message: params.args.map((a) => a.value ?? a.description ?? "").join(" ") });
      } else if (method === "Runtime.consoleAPICalled") {
        this.console.push({ type: params.type, text: params.args.map((a) => a.value ?? a.description ?? "").join(" ") });
      } else if (method === "Log.entryAdded" && params.entry.level === "error") {
        // Network 404s for favicon etc. are noise for motion validation.
        if (!/favicon\.ico/.test(params.entry.url || "")) this.errors.push({ source: `log:${params.entry.source}`, message: params.entry.text, url: params.entry.url });
      }
      for (const w of this.waiters.slice()) {
        if (w.method === method) {
          this.waiters.splice(this.waiters.indexOf(w), 1);
          w.resolve(params);
        }
      }
    });
  }

  send(method, params) {
    return this.browser.send(method, params, this.sessionId);
  }

  waitFor(method, ms = 15000) {
    return Promise.race([
      new Promise((resolve) => this.waiters.push({ method, resolve })),
      timeout(ms, `Timed out waiting for ${method}`),
    ]);
  }

  async goto(url, { waitMs = 20000 } = {}) {
    // A navigation issued right after a tab opens can collide with the tab's initial about:blank commit and
    // come back net::ERR_ABORTED; that one error is retried. Every other navigation error fails immediately.
    for (let attempt = 0; ; attempt += 1) {
      const loaded = this.waitFor("Page.loadEventFired", waitMs);
      const result = await this.send("Page.navigate", { url });
      if (!result.errorText) return loaded;
      loaded.catch(() => {});
      if (result.errorText !== "net::ERR_ABORTED" || attempt >= 2) throw new Error(`Navigation failed: ${result.errorText}`);
      await sleep(100 * (attempt + 1));
    }
  }

  async evaluate(expression, { awaitPromise = true } = {}) {
    const r = await this.send("Runtime.evaluate", { expression, awaitPromise, returnByValue: true });
    if (r.exceptionDetails) throw new Error(`Page evaluation failed: ${r.exceptionDetails.exception?.description || r.exceptionDetails.text}`);
    return r.result.value;
  }

  async waitForExpression(expression, ms = 10000) {
    const end = Date.now() + ms;
    while (Date.now() < end) {
      if (await this.evaluate(`Boolean(${expression})`)) return true;
      await sleep(50);
    }
    return false;
  }

  async screenshot(clip) {
    const params = { format: "png", captureBeyondViewport: false };
    if (clip) params.clip = { ...clip, scale: 1 };
    const { data } = await this.send("Page.captureScreenshot", params);
    return Buffer.from(data, "base64");
  }

  async metrics() {
    const { metrics } = await this.send("Performance.getMetrics");
    return Object.fromEntries(metrics.map((m) => [m.name, m.value]));
  }

  async close() {
    await this.browser.send("Target.closeTarget", { targetId: this.targetId }).catch(() => {});
  }
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
