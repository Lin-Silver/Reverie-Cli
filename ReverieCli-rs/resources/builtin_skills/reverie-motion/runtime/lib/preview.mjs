// Real-browser preview & validation. Native Reverie Motion code.
// Loads a page (generated preview, local file or local dev-server URL) in a
// headless Chromium over CDP and produces evidence: runtime errors, frame
// timing, layout/style recalculation counts, layout shift, deterministic
// keyframe samples (screenshots + computed element state), visual motion
// metrics, a contact sheet, and a reduced-motion pass.
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { launchBrowser, sleep } from "./cdp.mjs";
import { finalProperties } from "./spec.mjs";

export const DEFAULT_VIEWPORTS = [
  { name: "desktop", width: 1280, height: 800, deviceScaleFactor: 1, mobile: false },
  { name: "mobile", width: 390, height: 844, deviceScaleFactor: 2, mobile: true },
];

const MIME = {
  ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".webp": "image/webp", ".gif": "image/gif", ".avif": "image/avif", ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf",
  ".otf": "font/otf", ".wasm": "application/wasm", ".txt": "text/plain; charset=utf-8", ".mp4": "video/mp4", ".webm": "video/webm", ".map": "application/json",
};

/**
 * Ephemeral read-only static server for local files. Browsers refuse ES module
 * scripts from file:// (CORS), so local pages are served over
 * http://127.0.0.1:<random port> for the duration of one preview. GET/HEAD
 * only, confined to `root`, closed afterwards.
 */
export async function serveStatic(root) {
  const base = path.resolve(root);
  const server = http.createServer((req, res) => {
    if (req.method !== "GET" && req.method !== "HEAD") {
      res.writeHead(405).end();
      return;
    }
    let rel;
    try {
      rel = decodeURIComponent(new URL(req.url, "http://127.0.0.1").pathname);
    } catch {
      res.writeHead(400).end();
      return;
    }
    let file = path.resolve(base, `.${rel}`);
    const inside = path.relative(base, file);
    if (inside.startsWith("..") || path.isAbsolute(inside)) {
      res.writeHead(403).end();
      return;
    }
    try {
      if (fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
      const body = fs.readFileSync(file);
      res.writeHead(200, { "content-type": MIME[path.extname(file).toLowerCase()] ?? "application/octet-stream", "cache-control": "no-store" });
      res.end(req.method === "HEAD" ? undefined : body);
    } catch {
      res.writeHead(404).end();
    }
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const { port } = server.address();
  return {
    origin: `http://127.0.0.1:${port}`,
    urlFor(file) {
      const rel = path.relative(base, path.resolve(file)).split(path.sep).map(encodeURIComponent).join("/");
      if (rel.startsWith("..")) throw Object.assign(new Error(`File is outside the served root: ${file}`), { code: "PATH_OUTSIDE_PROJECT" });
      return `http://127.0.0.1:${port}/${rel}`;
    },
    close: () => new Promise((resolve) => { server.closeAllConnections?.(); server.close(() => resolve()); }),
  };
}

const LOCAL_HOST = /^(localhost|127\.0\.0\.1|\[::1\]|[^/]+\.localhost|[^/]+\.test)$/i;

/** Only local targets are opened unless the caller explicitly allows remote URLs. */
export function checkTarget(url, allowRemote = false) {
  const u = new URL(url);
  if (u.protocol === "file:" || u.protocol === "data:" || u.protocol === "about:") return u.href;
  if ((u.protocol === "http:" || u.protocol === "https:") && (LOCAL_HOST.test(u.hostname) || allowRemote)) return u.href;
  const error = new Error(`Refusing to open ${u.protocol}//${u.hostname}: only file:, localhost, 127.0.0.1, [::1], *.localhost and *.test targets are allowed without allowRemote.`);
  error.code = "REMOTE_TARGET_REFUSED";
  throw error;
}

const PROBE = `(() => {
  if (window.__rmProbe) return;
  const rm = window.__rmProbe = { frames: [], cls: 0, shifts: 0, longTasks: 0, longTaskMs: 0, errors: [], recording: false };
  try { new PerformanceObserver((l) => { for (const e of l.getEntries()) { if (!e.hadRecentInput) { rm.cls += e.value; rm.shifts++; } } }).observe({ type: "layout-shift", buffered: true }); } catch (e) {}
  try { new PerformanceObserver((l) => { for (const e of l.getEntries()) { rm.longTasks++; rm.longTaskMs += e.duration; } }).observe({ type: "longtask", buffered: true }); } catch (e) {}
  let last = 0;
  rm.startFrames = () => { rm.frames = []; last = 0; rm.recording = true; const loop = (t) => { if (!rm.recording) return; if (last) rm.frames.push(t - last); last = t; requestAnimationFrame(loop); }; requestAnimationFrame(loop); };
  rm.stopFrames = () => { rm.recording = false; return rm.frames; };
  rm.resetLayoutShift = () => { rm.cls = 0; rm.shifts = 0; };
  addEventListener("error", (e) => rm.errors.push(String(e.message || e.error)));
  addEventListener("unhandledrejection", (e) => rm.errors.push("unhandledrejection: " + String(e.reason)));
})();`;

const ELEMENT_STATE = `((selectors) => selectors.map((sel) => {
  let nodes = [];
  try { nodes = Array.from(document.querySelectorAll(sel)).slice(0, 4); } catch (e) { return { selector: sel, error: String(e) }; }
  return { selector: sel, count: document.querySelectorAll(sel).length, nodes: nodes.map((el) => {
    const cs = getComputedStyle(el); const r = el.getBoundingClientRect();
    const m = cs.transform; let sx = 1, sy = 1, tx = 0, ty = 0;
    if (m && m !== "none") {
      const v = m.match(/matrix(3d)?\\(([^)]+)\\)/); const n = v ? v[2].split(",").map(Number) : [];
      if (v && !v[1]) { sx = Math.hypot(n[0], n[1]); sy = Math.hypot(n[2], n[3]); tx = n[4]; ty = n[5]; }
      else if (v) { sx = Math.hypot(n[0], n[1], n[2]); sy = Math.hypot(n[4], n[5], n[6]); tx = n[12]; ty = n[13]; }
    }
    let clipped = false;
    for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) { const o = getComputedStyle(p); if (/hidden|clip/.test(o.overflowX) || /hidden|clip/.test(o.overflow)) { clipped = true; break; } }
    return { x: r.x, y: r.y, width: r.width, height: r.height, opacity: Number(cs.opacity), clipped, visibility: cs.visibility, display: cs.display,
      transform: m, scaleX: sx, scaleY: sy, translateX: tx, translateY: ty, filter: cs.filter, clipPath: cs.clipPath, strokeDashoffset: cs.strokeDashoffset };
  }) };
}))`;

const TIMELINE = `(() => {
  const anims = document.getAnimations();
  let end = 0, infinite = 0;
  for (const a of anims) {
    const t = a.effect && a.effect.getComputedTiming ? a.effect.getComputedTiming() : null;
    if (!t) continue;
    const timing = a.effect.getTiming();
    const delay = timing.delay || 0;
    const dur = typeof t.duration === "number" ? t.duration : 0;
    // 1.5 loop periods: with evenly spaced samples (both ends included) the first two samples always land on
    // different loop phases, so a sample count can never alias every frame onto the loop boundary.
    if (t.iterations === Infinity) { infinite++; end = Math.max(end, delay + dur * 1.5); }
    else end = Math.max(end, t.endTime);
  }
  return { count: anims.length, infinite, endTime: Math.round(end),
    animations: anims.slice(0, 40).map((a) => ({ id: a.id, name: a.animationName || null, playState: a.playState,
      target: a.effect && a.effect.target ? (a.effect.target.id ? "#" + a.effect.target.id : a.effect.target.tagName.toLowerCase() + (a.effect.target.classList.length ? "." + Array.from(a.effect.target.classList).join(".") : "")) : null,
      duration: a.effect ? a.effect.getTiming().duration : null, delay: a.effect ? a.effect.getTiming().delay : null, iterations: a.effect ? String(a.effect.getTiming().iterations) : null,
      easing: a.effect ? a.effect.getTiming().easing.slice(0, 80) : null })) };
})()`;

async function ready(page, timeoutMs) {
  // Module scripts execute before the load event, so a complete document means
  // a reverie preview has already mounted (it sets __rmReady at the end).
  await page.waitForExpression("document.readyState === 'complete'", timeoutMs);
  await page.evaluate("new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))");
  return page.evaluate("window.__rmReady === true ? 'reverie-preview' : 'document-complete'");
}

async function runActions(page, actions = []) {
  for (const action of actions) {
    if (action.delayMs) await sleep(action.delayMs);
    if (action.type === "click" || action.type === "hover") {
      const box = await page.evaluate(`(() => { const el = document.querySelector(${JSON.stringify(action.selector)}); if (!el) return null; const r = el.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
      if (!box) throw Object.assign(new Error(`Action target not found: ${action.selector}`), { code: "ACTION_TARGET_MISSING" });
      await page.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: box.x, y: box.y });
      if (action.type === "click") {
        await page.send("Input.dispatchMouseEvent", { type: "mousePressed", x: box.x, y: box.y, button: "left", clickCount: 1 });
        await page.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: box.x, y: box.y, button: "left", clickCount: 1 });
      }
    } else if (["play", "reverse", "toggle", "flip"].includes(action.type)) {
      const ok = await page.evaluate(`(() => { const rm = window.__reverieMotion; if (!rm) return false; const c = rm.controller; ${action.type === "play" ? `rm.play(${JSON.stringify(action.id)})` : `c.${action.type}(${JSON.stringify(action.id)}${action.type === "flip" && action.reverse ? ", null, { reverse: true }" : ""})`}; return true; })()`);
      if (!ok) throw Object.assign(new Error(`Action ${action.type} needs a reverie-motion preview page.`), { code: "ACTION_UNSUPPORTED" });
    } else if (action.type === "wait") {
      await sleep(action.ms ?? 100);
    } else {
      throw Object.assign(new Error(`Unknown action type "${action.type}".`), { code: "ACTION_UNKNOWN" });
    }
  }
}

function stats(frames) {
  if (!frames.length) return { frames: 0 };
  const sorted = [...frames].sort((a, b) => a - b);
  const mean = frames.reduce((a, b) => a + b, 0) / frames.length;
  const q = (p) => sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))];
  return {
    frames: frames.length,
    meanMs: round(mean, 2),
    p95Ms: round(q(0.95), 2),
    maxMs: round(sorted[sorted.length - 1], 2),
    fps: round(1000 / mean, 1),
    droppedFrames: frames.filter((f) => f > 25).length,
  };
}

const round = (n, d = 3) => Number(Number(n).toFixed(d));

/**
 * @param {object} o
 * @param {string} [o.htmlFile]  generated preview or local html file (served over http://127.0.0.1)
 * @param {string} [o.serveRoot] directory served for htmlFile (default: its folder; tools pass the project root)
 * @param {string} [o.url]       local dev server URL
 * @param {object} [o.spec]      normalized spec (enables spec-aware checks)
 * @param {string} o.outDir      evidence directory
 */
export async function runPreview(o) {
  const outDir = path.resolve(o.outDir);
  fs.mkdirSync(outDir, { recursive: true });
  const server = o.url ? null : await serveStatic(o.serveRoot ?? path.dirname(path.resolve(o.htmlFile)));
  let browser;
  try {
    const targetUrl = checkTarget(o.url ?? server.urlFor(o.htmlFile), o.allowRemote);
    browser = await launchBrowser({ executable: o.browser, profileDir: o.profileDir ?? path.join(outDir, "..", "..", "browser-profile") });
    return await previewWith(browser, targetUrl, o, outDir);
  } finally {
    if (browser) await browser.close();
    if (server) await server.close();
  }
}

async function previewWith(browser, targetUrl, o, outDir) {
  const viewports = o.viewports ?? DEFAULT_VIEWPORTS;
  const track = o.track ?? (o.spec ? [...new Set(o.spec.components.filter((c) => c.selector && c.kind !== "particles").map((c) => c.selector))] : []);
  const report = {
    schema: "reverie-motion.preview.v1",
    created_at: new Date().toISOString(),
    target: targetUrl,
    ...(o.htmlFile ? { file: path.resolve(o.htmlFile), servedBy: "ephemeral 127.0.0.1 static server (closed after the preview)" } : {}),
    browser: { executable: browser.executable, version: (await browser.send("Browser.getVersion")).product, skipped: browser.failedCandidates },
    track,
    viewports: [],
    findings: [],
  };
  for (const vp of viewports) report.viewports.push(await runViewport(browser, targetUrl, vp, o, track, outDir));
  const analysis = await browser.newPage({ width: 400, height: 300 });
  try {
    for (const v of report.viewports) {
      v.visual = await analyzeFrames(analysis, v.samples.map((s) => path.join(outDir, s.file)), v.samples.map((s) => `${v.name} · ${s.t}ms`));
      if (v.visual.contactSheet) {
        const file = `contact-${v.name}.png`;
        fs.writeFileSync(path.join(outDir, file), Buffer.from(v.visual.contactSheet.split(",")[1], "base64"));
        v.visual.contactSheet = file;
      }
    }
  } finally {
    await analysis.close();
  }
  report.findings = findingsFor(report, o.spec);
  const penalty = { critical: 30, warning: 10, info: 2 };
  report.score = Math.max(0, 100 - report.findings.reduce((s, f) => s + (penalty[f.severity] ?? 0), 0));
  report.passed = !report.findings.some((f) => f.severity === "critical") && report.score >= (o.passScore ?? 70);
  fs.writeFileSync(path.join(outDir, "preview-report.json"), JSON.stringify(report, null, 2) + "\n");
  return report;
}

async function runViewport(browser, url, vp, o, track, outDir) {
  const result = { name: vp.name, width: vp.width, height: vp.height, deviceScaleFactor: vp.deviceScaleFactor ?? 1 };
  const readyTimeout = o.readyTimeoutMs ?? 10000;

  // 1) Live run: errors, frame timing, layout/style work, layout shift.
  const live = await browser.newPage({ ...vp, reducedMotion: false });
  try {
    await live.send("Page.addScriptToEvaluateOnNewDocument", { source: PROBE });
    await live.goto(url);
    result.ready = await ready(live, readyTimeout);
    await live.evaluate("window.__rmProbe && window.__rmProbe.resetLayoutShift()");
    const before = await live.metrics();
    await live.evaluate("window.__rmProbe.startFrames()");
    await runActions(live, o.actions);
    const timeline = await live.evaluate(TIMELINE);
    const liveMs = Math.min(o.maxLiveMs ?? 2500, Math.max(600, timeline.endTime + 150));
    await sleep(liveMs);
    const frames = await live.evaluate("window.__rmProbe.stopFrames()");
    const after = await live.metrics();
    const probe = await live.evaluate("({ cls: window.__rmProbe.cls, shifts: window.__rmProbe.shifts, longTasks: window.__rmProbe.longTasks, longTaskMs: window.__rmProbe.longTaskMs, errors: window.__rmProbe.errors, pageErrors: window.__rmErrors || [] })");
    const frameStats = stats(frames);
    const layouts = (after.LayoutCount ?? 0) - (before.LayoutCount ?? 0);
    const recalcs = (after.RecalcStyleCount ?? 0) - (before.RecalcStyleCount ?? 0);
    result.timeline = timeline;
    result.perf = {
      liveMs,
      ...frameStats,
      layoutCount: layouts,
      recalcStyleCount: recalcs,
      layoutsPerFrame: frameStats.frames ? round(layouts / frameStats.frames, 3) : 0,
      layoutDurationMs: round(((after.LayoutDuration ?? 0) - (before.LayoutDuration ?? 0)) * 1000, 2),
      recalcStyleDurationMs: round(((after.RecalcStyleDuration ?? 0) - (before.RecalcStyleDuration ?? 0)) * 1000, 2),
      scriptDurationMs: round(((after.ScriptDuration ?? 0) - (before.ScriptDuration ?? 0)) * 1000, 2),
      cumulativeLayoutShift: round(probe.cls, 4),
      layoutShifts: probe.shifts,
      longTasks: probe.longTasks,
      longTaskMs: round(probe.longTaskMs, 1),
    };
    result.errors = dedupe([...live.errors.map((e) => e.message), ...probe.errors, ...probe.pageErrors]);
    result.overflow = await live.evaluate("({ scrollWidth: document.documentElement.scrollWidth, innerWidth: innerWidth })");
  } finally {
    await live.close();
  }

  // 2) Deterministic keyframe sampling: pause every Animation and seek it.
  const sampler = await browser.newPage({ ...vp, reducedMotion: false });
  try {
    await sampler.send("Page.addScriptToEvaluateOnNewDocument", { source: PROBE });
    await sampler.goto(url);
    await ready(sampler, readyTimeout);
    await runActions(sampler, o.actions);
    const timeline = await sampler.evaluate(TIMELINE);
    // Pages with only rAF/canvas motion have no Animation end time; sample 2s.
    const end = o.sampleEndMs ?? (timeline.endTime > 0 ? timeline.endTime : 2000);
    const count = Math.max(2, o.sampleCount ?? 8);
    const times = o.samples ?? [...Array(count).keys()].map((i) => Math.round((end * i) / (count - 1)));
    const seekable = timeline.count > 0 || (await sampler.evaluate("Boolean(window.__reverieMotion && window.__reverieMotion.seek)"));
    result.sampling = { mode: seekable ? "seek" : "realtime", endMs: end, times };
    result.samples = [];
    const started = Date.now();
    for (const t of times) {
      if (seekable) {
        await sampler.evaluate(`(() => { const rm = window.__reverieMotion; if (rm && rm.seek) { rm.seek(${t}); } else { for (const a of document.getAnimations()) { a.pause(); a.currentTime = ${t}; } } return new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))); })()`);
      } else {
        const wait = t - (Date.now() - started);
        if (wait > 0) await sleep(wait);
      }
      const file = `frame-${vp.name}-${String(t).padStart(5, "0")}.png`;
      fs.writeFileSync(path.join(outDir, file), await sampler.screenshot());
      const elements = track.length ? await sampler.evaluate(`${ELEMENT_STATE}(${JSON.stringify(track)})`) : [];
      result.samples.push({ t, file, elements });
    }
    if (o.fineTrack) {
      // Dense numeric sampling (no screenshots) to verify curves such as spring overshoot.
      result.fineSamples = [];
      for (let t = 0; t <= end; t += o.fineStepMs ?? 16) {
        await sampler.evaluate(`(() => { const rm = window.__reverieMotion; if (rm && rm.seek) rm.seek(${t}); else for (const a of document.getAnimations()) { a.pause(); a.currentTime = ${t}; } })()`);
        result.fineSamples.push({ t, elements: await sampler.evaluate(`${ELEMENT_STATE}(${JSON.stringify(o.fineTrack)})`) });
      }
    }
  } finally {
    await sampler.close();
  }

  // 3) Reduced motion: no long-running motion, nothing left hidden.
  if (o.reducedMotion !== false) {
    const rmPage = await browser.newPage({ ...vp, reducedMotion: true });
    try {
      await rmPage.send("Page.addScriptToEvaluateOnNewDocument", { source: PROBE });
      await rmPage.goto(url);
      await ready(rmPage, readyTimeout);
      await runActions(rmPage, o.actions);
      await sleep(o.reducedSettleMs ?? 450);
      const matches = await rmPage.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches");
      const motion = await rmPage.evaluate(`(() => document.getAnimations().filter((a) => a.playState === "running").map((a) => { const t = a.effect.getTiming(); return { duration: t.duration, iterations: String(t.iterations), target: a.effect.target ? a.effect.target.tagName.toLowerCase() + (a.effect.target.className && typeof a.effect.target.className === "string" ? "." + a.effect.target.className.trim().split(/\\s+/).join(".") : "") : null }; }).filter((a) => a.iterations === "Infinity" || Number(a.duration) > 200))()`);
      const file = `reduced-${vp.name}.png`;
      fs.writeFileSync(path.join(outDir, file), await rmPage.screenshot());
      const elements = track.length ? await rmPage.evaluate(`${ELEMENT_STATE}(${JSON.stringify(track)})`) : [];
      const particleFrames = await rmPage.evaluate("document.querySelectorAll('canvas[data-rm-particles]').length");
      result.reducedMotion = { mediaMatched: matches, longRunning: motion, elements, file, particleCanvases: particleFrames, errors: rmPage.errors.map((e) => e.message) };
    } finally {
      await rmPage.close();
    }
  }
  return result;
}

/** Visual metrics computed with <canvas> in a separate blank tab (no image libraries). */
async function analyzeFrames(page, files, labels) {
  if (!files.length) return { frames: [] };
  const images = files.map((f) => `data:image/png;base64,${fs.readFileSync(f).toString("base64")}`);
  const fn = `(async (images, labels) => {
    const load = (src) => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; });
    const imgs = await Promise.all(images.map(load));
    const W = 320; const H = Math.round(imgs[0].height * W / imgs[0].width);
    const c = document.createElement("canvas"); c.width = W; c.height = H; const g = c.getContext("2d", { willReadFrequently: true });
    const px = imgs.map((img) => { g.clearRect(0, 0, W, H); g.drawImage(img, 0, 0, W, H); return g.getImageData(0, 0, W, H).data; });
    const corner = (d) => { const pts = [0, (W - 1) * 4, (H - 1) * W * 4, ((H - 1) * W + W - 1) * 4]; const s = [0, 0, 0]; for (const p of pts) { s[0] += d[p]; s[1] += d[p + 1]; s[2] += d[p + 2]; } return s.map((v) => v / 4); };
    const frames = px.map((d, i) => {
      const bg = corner(d); let cov = 0, lum = 0; const n = W * H;
      for (let p = 0; p < d.length; p += 4) { const diff = Math.abs(d[p] - bg[0]) + Math.abs(d[p + 1] - bg[1]) + Math.abs(d[p + 2] - bg[2]); if (diff > 24) cov++; lum += 0.2126 * d[p] + 0.7152 * d[p + 1] + 0.0722 * d[p + 2]; }
      let diffPrev = null, changedPrev = null;
      if (i > 0) { const q = px[i - 1]; let sum = 0, ch = 0; for (let p = 0; p < d.length; p += 4) { const dd = Math.abs(d[p] - q[p]) + Math.abs(d[p + 1] - q[p + 1]) + Math.abs(d[p + 2] - q[p + 2]); sum += dd; if (dd > 24) ch++; } diffPrev = sum / (n * 765); changedPrev = ch / n; }
      return { label: labels[i], coverage: cov / n, luminance: lum / n / 255, diffPrev, changedPrev };
    });
    const first = px[0], last = px[px.length - 1]; let fl = 0; for (let p = 0; p < first.length; p += 4) fl += Math.abs(first[p] - last[p]) + Math.abs(first[p + 1] - last[p + 1]) + Math.abs(first[p + 2] - last[p + 2]);
    const cols = Math.min(4, imgs.length), rows = Math.ceil(imgs.length / cols), cw = 300, ch = Math.round(imgs[0].height * cw / imgs[0].width), pad = 8, lh = 20;
    const sheet = document.createElement("canvas"); sheet.width = cols * (cw + pad) + pad; sheet.height = rows * (ch + lh + pad) + pad;
    const s = sheet.getContext("2d"); s.fillStyle = "#111"; s.fillRect(0, 0, sheet.width, sheet.height); s.font = "12px sans-serif";
    imgs.forEach((img, i) => { const x = pad + (i % cols) * (cw + pad), y = pad + Math.floor(i / cols) * (ch + lh + pad); s.drawImage(img, x, y + lh, cw, ch); s.fillStyle = "#ddd"; s.fillText(labels[i], x, y + 14); s.strokeStyle = "#333"; s.strokeRect(x, y + lh, cw, ch); });
    return { frames, firstToLast: fl / (W * H * 765), motionEnergy: frames.reduce((a, f) => a + (f.diffPrev || 0), 0), contactSheet: sheet.toDataURL("image/png") };
  })`;
  const r = await page.evaluate(`${fn}(${JSON.stringify(images)}, ${JSON.stringify(labels)})`);
  r.frames = r.frames.map((f) => ({ ...f, coverage: round(f.coverage, 4), luminance: round(f.luminance, 4), diffPrev: f.diffPrev == null ? null : round(f.diffPrev, 5), changedPrev: f.changedPrev == null ? null : round(f.changedPrev, 4) }));
  r.firstToLast = round(r.firstToLast, 5);
  r.motionEnergy = round(r.motionEnergy, 5);
  return r;
}

function dedupe(list) {
  return [...new Set(list.filter(Boolean).map(String))];
}

function findingsFor(report, spec) {
  const out = [];
  const add = (code, severity, viewport, message, extra = {}) => out.push({ code, severity, dimension: "runtime", viewport, message, ...extra });
  for (const v of report.viewports) {
    if (v.errors.length) add("RV001", "critical", v.name, `Runtime errors: ${v.errors.slice(0, 3).join(" | ")}`);
    if (!v.timeline.count && (!spec || spec.components.some((c) => c.kind === "keyframes" && c.trigger === "onLoad"))) {
      const canvases = spec && spec.components.some((c) => c.kind === "particles");
      if (!canvases) add("RV010", "critical", v.name, "No running Animation objects were found after load/actions.");
    }
    const p = v.perf;
    if (p.frames > 10 && p.layoutsPerFrame > 0.5) add("RV002", "warning", v.name, `Layout ran ${p.layoutCount} times over ${p.frames} frames (${p.layoutsPerFrame}/frame): a layout-triggering property is animated.`, { fix: "animate transform/opacity instead of size or position properties" });
    if (p.cumulativeLayoutShift > 0.1) add("RV003", "critical", v.name, `Cumulative layout shift ${p.cumulativeLayoutShift} (> 0.1 is poor).`);
    else if (p.cumulativeLayoutShift > 0.02) add("RV003", "warning", v.name, `Cumulative layout shift ${p.cumulativeLayoutShift}.`);
    if (p.frames > 10 && (p.p95Ms > 25 || p.longTasks > 0)) add("RV004", "warning", v.name, `Frame pacing: p95 ${p.p95Ms}ms, ${p.droppedFrames} frames > 25ms, ${p.longTasks} long tasks.`);
    if (v.overflow.scrollWidth > v.overflow.innerWidth + 1) add("RV006", "warning", v.name, `Horizontal overflow: document is ${v.overflow.scrollWidth}px wide in a ${v.overflow.innerWidth}px viewport.`);
    // Element-level overflow only counts when no ancestor clips it (clipped blobs are intentional).
    const flagged = new Set();
    for (const s of v.samples) {
      for (const e of s.elements) for (const n of e.nodes ?? []) {
        if (flagged.has(e.selector) || n.clipped) continue;
        if (n.opacity > 0.05 && n.visibility !== "hidden" && (n.x + n.width > v.width + 8 || n.x < -8) && n.width < v.width) {
          add("RV006", "warning", v.name, `${e.selector} leaves the viewport horizontally at ${s.t}ms (x=${Math.round(n.x)}, w=${Math.round(n.width)}).`, { t: s.t, selector: e.selector });
          flagged.add(e.selector);
        }
      }
    }
    const changed = Math.max(0, ...(v.visual?.frames ?? []).map((f) => f.changedPrev ?? 0));
    const expectsMotion = v.timeline.count > 0 || (spec && spec.components.some((c) => c.kind === "particles"));
    if (v.visual?.frames?.length > 1 && v.visual.motionEnergy < 0.0005 && changed < 0.0005 && expectsMotion) {
      add("RV007", "critical", v.name, `Sampled frames are visually identical (motion energy ${v.visual.motionEnergy}); the animation is not visible.`);
    }
    const frames = v.visual?.frames ?? [];
    for (let i = 1; i < frames.length - 1; i += 1) {
      if (frames[i].coverage < 0.002 && frames[i - 1].coverage > 0.01 && frames[i + 1].coverage > 0.01) add("RV009", "warning", v.name, `Blank frame at ${v.samples[i].t}ms between visible frames.`);
    }
    if (spec) {
      const last = v.samples[v.samples.length - 1];
      for (const c of spec.components) {
        if (c.kind !== "keyframes" || c.iterationCount === "infinite" || c.trigger !== "onLoad") continue;
        const expect = finalProperties(c);
        const state = last?.elements.find((e) => e.selector === c.selector);
        const node = state?.nodes?.[0];
        if (!node || expect.opacity === undefined) continue;
        if (Math.abs(node.opacity - Number(expect.opacity)) > 0.05 && last.t >= c.delayMs + c.durationMs) {
          add("RV008", "warning", v.name, `${c.id}: final opacity ${node.opacity} != expected ${expect.opacity}.`, { component: c.id });
        }
      }
    }
    const rm = v.reducedMotion;
    if (rm) {
      if (!rm.mediaMatched) add("RV005", "warning", v.name, "prefers-reduced-motion emulation did not apply.");
      if (rm.longRunning.length) add("RV005", "warning", v.name, `${rm.longRunning.length} animation(s) still run under prefers-reduced-motion: ${rm.longRunning.slice(0, 3).map((a) => a.target).join(", ")}.`);
      const finalSample = v.samples[v.samples.length - 1];
      for (const e of rm.elements) for (const [i, n] of (e.nodes ?? []).entries()) {
        const normal = finalSample?.elements.find((x) => x.selector === e.selector)?.nodes?.[i];
        const shown = (x) => x.opacity > 0.5 && x.visibility !== "hidden" && x.display !== "none";
        const hidden = (x) => x.opacity < 0.05 || x.visibility === "hidden" || x.display === "none";
        if (normal && shown(normal) && hidden(n)) {
          add("RV005", "critical", v.name, `${e.selector} is hidden under prefers-reduced-motion but visible otherwise.`, { selector: e.selector });
        }
      }
      if (rm.errors.length) add("RV001", "critical", v.name, `Runtime errors with reduced motion: ${rm.errors.slice(0, 2).join(" | ")}`);
    }
  }
  return out;
}
