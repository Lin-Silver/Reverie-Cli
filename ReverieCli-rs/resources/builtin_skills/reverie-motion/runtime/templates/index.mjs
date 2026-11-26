// Parameterised, composable motion templates. Native Reverie Motion code.
// Each template returns a Reverie MotionSpec input (validated by normalizeSpec).
// Stage markup/CSS is for previews and for scaffolding when the target project
// has no matching elements yet; selectors are parameters so templates bind to
// existing markup.

import { staggerOrder } from "../lib/spec.mjs";

const P = (type, def, description, extra = {}) => ({ type, default: def, description, ...extra });
// CSS-only exports read the stagger order from --rm-i; preview markup sets it like an integrator would.
const rmi = (i, count, from = "start") => `--rm-i:${staggerOrder(count, from)[i]}`;

const DARK = `body { min-height: 100vh; display: grid; place-items: center; color: #f5f7fb; }`;

export const TEMPLATES = [
  {
    id: "spring-pop",
    title: "Spring pop entrance",
    purpose: "entrance",
    capabilities: ["spring-physics", "keyframes"],
    description: "Element scales up from a smaller size with a real damped spring (Apple-style response/dampingFraction).",
    params: {
      selector: P("string", ".rm-pop", "Element to animate."),
      fromScale: P("number", 0.85, "Starting scale (0.8–0.95 reads natural; avoid 0).", { min: 0, max: 1 }),
      response: P("number", 0.45, "Spring response in seconds (period of the undamped oscillation).", { min: 0.1, max: 2 }),
      dampingFraction: P("number", 0.62, "1 = no bounce, 0.5–0.8 = lively.", { min: 0.1, max: 2 }),
      delayMs: P("number", 0, "Start delay."),
      trigger: P("string", "onLoad", "onLoad | onClick | onScroll | manual"),
    },
    build: (p) => ({
      id: "spring-pop",
      name: "Spring pop",
      intent: { purpose: "entrance" },
      components: [{
        id: "pop", name: "Pop", selector: p.selector, trigger: p.trigger, delayMs: p.delayMs,
        easing: { type: "spring", response: p.response, dampingFraction: p.dampingFraction }, durationMs: "auto",
        keyframes: [
          { offset: 0, properties: { scale: p.fromScale, opacity: 0 } },
          { offset: 1, properties: { scale: 1, opacity: 1 } },
        ],
        reducedMotion: "fade",
      }],
      stage: {
        html: `<button class="${cls(p.selector)}" type="button">New message</button>`,
        css: `${DARK}
.${cls(p.selector)} { font: 600 17px/1 system-ui, sans-serif; color: #fff; border: 0; padding: 18px 28px; border-radius: 999px;
  background: linear-gradient(180deg, #4f8cff, #2f6bf0); box-shadow: 0 10px 30px rgba(47,107,240,.35), inset 0 1px 0 rgba(255,255,255,.25); }`,
      },
    }),
  },
  {
    id: "shared-element",
    title: "Shared-element card → detail (FLIP)",
    purpose: "transition",
    capabilities: ["spring-physics", "flip", "layers"],
    description: "A card morphs into its detail view by animating the measured geometry difference (First-Last-Invert-Play) with a spring; reverse on close.",
    params: {
      from: P("string", ".rm-card", "Source element (thumbnail/card)."),
      to: P("string", ".rm-detail", "Destination element (expanded view)."),
      response: P("number", 0.42, "Spring response (s)."),
      dampingFraction: P("number", 0.86, "Damping fraction; ~0.85 for large surfaces (no visible wobble)."),
      trigger: P("string", "onClick", "onClick (click source to open, again to close) | manual"),
    },
    build: (p) => ({
      id: "shared-element",
      name: "Shared element",
      intent: { purpose: "transition" },
      components: [{
        id: "hero", name: "Card to detail", kind: "flip", trigger: p.trigger,
        flip: { from: p.from, to: p.to, crossfade: true },
        easing: { type: "spring", response: p.response, dampingFraction: p.dampingFraction }, durationMs: "auto",
        reducedMotion: "fade",
      }],
      stage: {
        html: `<main class="rm-grid">
  <article class="${cls(p.from)}" tabindex="0"><div class="rm-art"></div><h3>Aurora</h3><p>Northern lights field guide</p></article>
  <article class="rm-tile"><div class="rm-art b"></div><h3>Tides</h3><p>Coastal almanac</p></article>
  <article class="rm-tile"><div class="rm-art c"></div><h3>Dunes</h3><p>Desert notes</p></article>
</main>
<section class="${cls(p.to)}" hidden><div class="rm-art"></div><h2>Aurora</h2><p>Charged particles meet the upper atmosphere and glow. Best seen between 22:00 and 02:00 on clear nights.</p></section>`,
        css: `body { min-height: 100vh; color: #f5f7fb; display: grid; place-items: center; }
.rm-grid { display: grid; grid-template-columns: repeat(3, 180px); gap: 16px; }
.${cls(p.from)}, .rm-tile { border-radius: 18px; background: #171a21; padding: 10px 10px 14px; cursor: pointer; box-shadow: 0 1px 0 rgba(255,255,255,.06) inset; }
.rm-art { height: 110px; border-radius: 12px; background: linear-gradient(135deg, #3ee0b0, #4f6bff 60%, #a23cff); }
.rm-art.b { background: linear-gradient(135deg, #3fa9ff, #1b3d8f); } .rm-art.c { background: linear-gradient(135deg, #ffb35c, #c2410c); }
h3 { margin: 10px 4px 2px; font: 600 15px system-ui; } p { margin: 0 4px; font: 13px/1.45 system-ui; color: #a6adbb; }
.${cls(p.to)} { position: fixed; inset: 40px; max-width: 720px; margin: auto; height: fit-content; border-radius: 28px; background: #171a21; padding: 18px 18px 28px; box-shadow: 0 30px 80px rgba(0,0,0,.5); }
.${cls(p.to)} .rm-art { height: 260px; border-radius: 18px; } .${cls(p.to)} h2 { margin: 16px 6px 6px; font: 700 26px system-ui; } .${cls(p.to)} p { font-size: 15px; }
@media (max-width: 640px) { .rm-grid { grid-template-columns: repeat(2, 1fr); width: calc(100vw - 32px); } .${cls(p.to)} { inset: 16px; } .${cls(p.to)} .rm-art { height: 180px; } }`,
        script: `// close by clicking the detail view
document.querySelector(${JSON.stringify(p.to)})?.addEventListener("click", () => {
  const motion = window.__reverieMotion.controller;
  // reverse: "from" is the open detail view, "to" is the card it collapses back into
  motion.flip("hero", ({ from, to }) => { from.hidden = true; to.style.visibility = ""; }, { reverse: true });
});`,
      },
    }),
  },
  {
    id: "glass-window",
    title: "Frosted-glass window expand / collapse",
    purpose: "transition",
    capabilities: ["spring-physics", "filters", "keyframes", "interruptible"],
    description: "A translucent panel (static backdrop blur) springs open from its trigger and collapses on the next click; mid-flight clicks reverse from the current position.",
    params: {
      selector: P("string", ".rm-glass", "Panel element."),
      triggerSelector: P("string", ".rm-glass-toggle", "Element whose click toggles the panel."),
      origin: P("string", "top left", "transform-origin, i.e. where the trigger sits relative to the panel."),
      response: P("number", 0.38, "Spring response (s)."),
      dampingFraction: P("number", 0.82, "Damping fraction."),
      fromScale: P("number", 0.9, "Collapsed scale."),
    },
    build: (p) => ({
      id: "glass-window",
      name: "Glass window",
      intent: { purpose: "transition" },
      components: [{
        id: "panel", name: "Glass panel", selector: p.selector, trigger: "onClick", triggerSelector: p.triggerSelector, toggle: true,
        transformOrigin: p.origin,
        easing: { type: "spring", response: p.response, dampingFraction: p.dampingFraction }, durationMs: "auto",
        keyframes: [
          { offset: 0, properties: { scale: p.fromScale, translateY: -8, opacity: 0 } },
          { offset: 1, properties: { scale: 1, translateY: 0, opacity: 1 } },
        ],
        reducedMotion: "fade",
      }],
      stage: {
        background: "radial-gradient(60% 80% at 20% 20%, #4f46e5 0%, transparent 60%), radial-gradient(50% 70% at 80% 70%, #db2777 0%, transparent 60%), #0b0d12",
        html: `<div class="rm-desk">
  <button class="${cls(p.triggerSelector)}" type="button" aria-label="Toggle panel">⌘ Panel</button>
  <div class="${cls(p.selector)}" role="dialog" aria-label="Quick settings">
    <h2>Quick settings</h2>
    <label><span>Focus</span><input type="checkbox" checked></label>
    <label><span>Night shift</span><input type="checkbox"></label>
    <label><span>AirDrop</span><input type="checkbox" checked></label>
  </div>
</div>`,
        css: `body { min-height: 100vh; color: #fff; }
.rm-desk { position: relative; box-sizing: border-box; width: 100%; padding: 28px; }
.${cls(p.triggerSelector)} { font: 600 14px system-ui; color: #fff; padding: 10px 16px; border-radius: 12px; border: 1px solid rgba(255,255,255,.18); background: rgba(255,255,255,.08); -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px); cursor: pointer; }
.${cls(p.selector)} { position: absolute; top: 76px; left: 28px; width: min(320px, calc(100vw - 56px)); padding: 18px; border-radius: 22px; opacity: 0;
  background: rgba(28, 30, 38, .45); border: 1px solid rgba(255,255,255,.14); box-shadow: 0 20px 60px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.12);
  -webkit-backdrop-filter: blur(24px) saturate(160%); backdrop-filter: blur(24px) saturate(160%); }
.${cls(p.selector)} h2 { margin: 0 0 10px; font: 600 15px system-ui; color: rgba(255,255,255,.85); }
.${cls(p.selector)} label { display: flex; justify-content: space-between; padding: 10px 2px; font: 14px system-ui; border-top: 1px solid rgba(255,255,255,.08); }`,
      },
    }),
  },
  {
    id: "svg-path-draw",
    title: "SVG path draw-on",
    purpose: "entrance",
    capabilities: ["svg", "path", "keyframes", "stagger"],
    description: "Strokes draw themselves using pathLength=\"1\" + stroke-dashoffset (no length measurement), staggered per path.",
    params: {
      selector: P("string", ".rm-path", "SVG <path>/<line>/<circle> elements with pathLength=\"1\" and stroke-dasharray: 1."),
      durationMs: P("number", 900, "Per-path draw time."),
      eachMs: P("number", 120, "Stagger between paths."),
      easing: P("string", "ease-in-out-cubic", "Draw easing."),
    },
    build: (p) => ({
      id: "svg-path-draw",
      name: "Path draw",
      intent: { purpose: "entrance" },
      components: [{
        id: "draw", name: "Draw stroke", selector: p.selector, durationMs: p.durationMs, easing: p.easing,
        stagger: { eachMs: p.eachMs, from: "start", count: 3 },
        keyframes: [
          { offset: 0, properties: { strokeDashoffset: 1, opacity: 0.2 } },
          { offset: 0.15, properties: { opacity: 1 } },
          { offset: 1, properties: { strokeDashoffset: 0, opacity: 1 } },
        ],
      }],
      stage: {
        html: `<svg viewBox="0 0 240 160" width="420" role="img" aria-label="Signature">
  <path class="${cls(p.selector)}" style="--rm-i:0" pathLength="1" d="M20 110 C 40 30, 70 30, 80 100 S 120 150, 140 70" />
  <path class="${cls(p.selector)}" style="--rm-i:1" pathLength="1" d="M140 70 C 150 40, 175 40, 180 80 C 185 120, 205 120, 220 60" />
  <circle class="${cls(p.selector)}" style="--rm-i:2" pathLength="1" cx="196" cy="34" r="8" />
</svg>`,
        css: `${DARK}
svg { max-width: calc(100vw - 32px); height: auto; }
.${cls(p.selector)} { fill: none; stroke: #8ab4ff; stroke-width: 4; stroke-linecap: round; stroke-linejoin: round; stroke-dasharray: 1; }`,
      },
    }),
  },
  {
    id: "stagger-list",
    title: "Staggered list entrance",
    purpose: "entrance",
    capabilities: ["stagger", "keyframes", "choreography"],
    description: "Items rise and fade in one after another; total cascade stays short so the last item is not late.",
    params: {
      selector: P("string", ".rm-item", "Repeated item selector."),
      eachMs: P("number", 45, "Delay step between items (30–60ms for lists)."),
      distance: P("number", 14, "Rise distance in px."),
      durationMs: P("number", 420, "Per-item duration."),
      from: P("string", "start", "start | center | end"),
      count: P("number", 6, "Item count in the preview stage."),
    },
    build: (p) => ({
      id: "stagger-list",
      name: "Stagger list",
      intent: { purpose: "entrance" },
      components: [{
        id: "items", name: "List items", selector: p.selector, durationMs: p.durationMs, easing: "ease-out-quart",
        stagger: { eachMs: p.eachMs, from: p.from, count: p.count },
        keyframes: [
          { offset: 0, properties: { translateY: p.distance, opacity: 0 } },
          { offset: 1, properties: { translateY: 0, opacity: 1 } },
        ],
      }],
      stage: {
        html: `<ul class="rm-list">${Array.from({ length: p.count }, (_, i) => `<li class="${cls(p.selector)}" style="${rmi(i, p.count, p.from)}"><span class="dot" style="--h:${(i * 47) % 360}"></span><b>Item ${i + 1}</b><small>Updated just now</small></li>`).join("")}</ul>`,
        css: `${DARK}
.rm-list { list-style: none; margin: 0; padding: 0; width: min(420px, calc(100vw - 32px)); display: grid; gap: 8px; }
.${cls(p.selector)} { display: grid; grid-template-columns: 36px 1fr; grid-template-rows: auto auto; column-gap: 12px; padding: 12px 14px; border-radius: 14px; background: #171a21; }
.${cls(p.selector)} .dot { grid-row: span 2; width: 36px; height: 36px; border-radius: 10px; background: hsl(var(--h) 80% 60%); }
.${cls(p.selector)} b { font: 600 15px system-ui; } .${cls(p.selector)} small { font: 13px system-ui; color: #a6adbb; }`,
      },
    }),
  },
  {
    id: "particle-field",
    title: "Particle field (canvas)",
    purpose: "ambient",
    capabilities: ["particles", "canvas"],
    description: "Deterministic seeded particles drift and twinkle on a DPR-capped canvas; pauses off-screen and when the tab is hidden; one static frame under reduced motion.",
    params: {
      selector: P("string", ".rm-particles", "Container element (canvas is appended, absolutely positioned)."),
      count: P("number", 90, "Particle count (≤ 150 recommended for phones)."),
      colors: P("array", ["#ffffff", "#a5c8ff", "#ffd6f5"], "Particle colors."),
      speed: P("number", 22, "Drift speed in px/s."),
      seed: P("number", 7, "Random seed (deterministic output)."),
    },
    build: (p) => ({
      id: "particle-field",
      name: "Particle field",
      intent: { purpose: "ambient" },
      components: [{
        id: "particles", name: "Particles", kind: "particles", selector: p.selector, trigger: "onLoad",
        particles: { count: p.count, colors: p.colors, speed: p.speed, seed: p.seed, sizeMin: 0.8, sizeMax: 2.2, drift: 0.6, twinkle: true, maxDpr: 2 },
        reducedMotion: "first-frame",
      }],
      stage: {
        html: `<section class="${cls(p.selector)}"><h1>Night sky</h1></section>`,
        css: `body { margin: 0; } .${cls(p.selector)} { position: relative; width: 100%; height: 100vh; display: grid; place-items: center; overflow: hidden; background: radial-gradient(120% 90% at 50% 100%, #1d2a5a 0%, #0b0d12 60%); }
.${cls(p.selector)} h1 { position: relative; z-index: 1; color: #fff; font: 700 clamp(28px, 6vw, 56px) system-ui; letter-spacing: -0.02em; }`,
      },
    }),
  },
  {
    id: "gradient-drift",
    title: "Dynamic gradient background",
    purpose: "ambient",
    capabilities: ["gradient", "layers", "filters", "keyframes"],
    description: "Blurred color blobs drift on long, offset loops. Only transform animates (compositor); the blur is static.",
    params: {
      selector: P("string", ".rm-blob", "Blob elements inside a clipped container."),
      durationMs: P("number", 14000, "Loop length (ambient loops ≥ 8s read as calm)."),
      distance: P("number", 80, "Travel in px."),
      colors: P("array", ["#5b6cff", "#ff5fa2", "#2ee6c5"], "Blob colors (preview stage)."),
    },
    build: (p) => ({
      id: "gradient-drift",
      name: "Gradient drift",
      intent: { purpose: "ambient" },
      components: [{
        id: "blobs", name: "Gradient blobs", selector: p.selector, durationMs: p.durationMs, iterationCount: "infinite", direction: "alternate", easing: "ease-in-out",
        stagger: { eachMs: -Math.round(p.durationMs / 3), from: "start", count: 3 }, // negative step = loops start out of phase
        keyframes: [
          { offset: 0, properties: { translateX: 0, translateY: 0, scale: 1 } },
          { offset: 0.5, properties: { translateX: p.distance, translateY: -p.distance * 0.6, scale: 1.15 } },
          { offset: 1, properties: { translateX: -p.distance * 0.5, translateY: p.distance * 0.4, scale: 0.95 } },
        ],
        reducedMotion: "first-frame",
      }],
      stage: {
        html: `<section class="rm-hero"><div class="rm-blobs">${p.colors.map((c, i) => `<span class="${cls(p.selector)}" style="--rm-i:${i};--c:${c};--x:${[15, 55, 35][i % 3]}%;--y:${[20, 30, 60][i % 3]}%"></span>`).join("")}</div><h1>Calm, alive</h1></section>`,
        css: `body { margin: 0; }
.rm-hero { position: relative; width: 100%; height: 100vh; overflow: hidden; display: grid; place-items: center; background: #0b0d12; }
.rm-blobs { position: absolute; inset: 0; filter: blur(60px) saturate(140%); }
.${cls(p.selector)} { position: absolute; left: var(--x); top: var(--y); width: 46vmax; height: 46vmax; border-radius: 50%; background: var(--c); opacity: .55; }
.rm-hero h1 { position: relative; color: #fff; font: 700 clamp(28px, 6vw, 56px) system-ui; letter-spacing: -0.02em; }`,
      },
    }),
  },
  {
    id: "mask-reveal",
    title: "Mask (clip-path) reveal",
    purpose: "entrance",
    capabilities: ["mask", "keyframes"],
    description: "Content is revealed by an expanding inset clip-path with a slight settle.",
    params: {
      selector: P("string", ".rm-reveal", "Element to reveal."),
      durationMs: P("number", 700, "Duration."),
      edge: P("string", "bottom", "bottom | left | center"),
    },
    build: (p) => {
      const start = { bottom: "inset(100% 0 0 0 round 24px)", left: "inset(0 100% 0 0 round 24px)", center: "inset(50% 50% 50% 50% round 24px)" }[p.edge] ?? "inset(100% 0 0 0 round 24px)";
      return {
        id: "mask-reveal",
        name: "Mask reveal",
        intent: { purpose: "entrance" },
        components: [{
          id: "reveal", name: "Reveal", selector: p.selector, durationMs: p.durationMs, easing: "ease-out-expo",
          keyframes: [
            { offset: 0, properties: { clipPath: start, scale: 1.04 } },
            { offset: 1, properties: { clipPath: "inset(0% 0 0 0 round 24px)", scale: 1 } },
          ],
        }],
        stage: {
          html: `<figure class="${cls(p.selector)}"><figcaption>Revealed</figcaption></figure>`,
          css: `${DARK} .${cls(p.selector)} { margin: 0; width: min(520px, calc(100vw - 32px)); aspect-ratio: 16/10; border-radius: 24px; background: linear-gradient(135deg, #ff9a5a, #ff4f7b 50%, #6a5cff); display: grid; place-items: end start; padding: 20px; }
figcaption { font: 600 18px system-ui; color: #fff; }`,
        },
      };
    },
  },
  {
    id: "blur-in",
    title: "Blur-in text",
    purpose: "entrance",
    capabilities: ["filters", "keyframes", "stagger"],
    description: "Words sharpen from a soft blur while rising slightly; small blur radius keeps paint cost low.",
    params: {
      selector: P("string", ".rm-word", "Word/line elements."),
      eachMs: P("number", 60, "Stagger step."),
      blur: P("number", 8, "Start blur in px (keep ≤ 10)."),
    },
    build: (p) => ({
      id: "blur-in",
      name: "Blur in",
      intent: { purpose: "entrance" },
      components: [{
        id: "words", name: "Words", selector: p.selector, durationMs: 600, easing: "ease-out-quart",
        stagger: { eachMs: p.eachMs, from: "start", count: 4 },
        keyframes: [
          { offset: 0, properties: { blur: p.blur, translateY: 8, opacity: 0 } },
          { offset: 1, properties: { blur: 0, translateY: 0, opacity: 1 } },
        ],
      }],
      stage: {
        html: `<h1 class="rm-title">${["Design", "that", "feels", "alive"].map((w, i) => `<span class="${cls(p.selector)}" style="--rm-i:${i}">${w}</span>`).join(" ")}</h1>`,
        css: `${DARK} .rm-title { font: 700 clamp(32px, 7vw, 72px) system-ui; letter-spacing: -0.03em; margin: 0 16px; } .${cls(p.selector)} { display: inline-block; }`,
      },
    }),
  },
  {
    id: "morph-blob",
    title: "Organic shape morph",
    purpose: "ambient",
    capabilities: ["morph", "keyframes"],
    description: "A shape morphs via border-radius keyframes while slowly rotating (border-radius repaints; keep the element small).",
    params: {
      selector: P("string", ".rm-morph", "Shape element."),
      durationMs: P("number", 8000, "Loop length."),
    },
    build: (p) => ({
      id: "morph-blob",
      name: "Morph blob",
      intent: { purpose: "ambient" },
      components: [{
        id: "morph", name: "Morph", selector: p.selector, durationMs: p.durationMs, iterationCount: "infinite", easing: "ease-in-out",
        keyframes: [
          { offset: 0, properties: { borderRadius: "42% 58% 70% 30% / 45% 45% 55% 55%", rotate: 0 } },
          { offset: 0.33, properties: { borderRadius: "70% 30% 46% 54% / 30% 29% 71% 70%", rotate: 30 } },
          { offset: 0.66, properties: { borderRadius: "28% 72% 44% 56% / 49% 40% 60% 51%", rotate: 60 } },
          { offset: 1, properties: { borderRadius: "42% 58% 70% 30% / 45% 45% 55% 55%", rotate: 90 } },
        ],
        reducedMotion: "first-frame",
      }],
      stage: {
        html: `<div class="${cls(p.selector)}"></div>`,
        css: `${DARK} .${cls(p.selector)} { width: 220px; height: 220px; background: linear-gradient(135deg, #7c5cff, #2ee6c5); }`,
      },
    }),
  },
  {
    id: "layer-parallax",
    title: "Layered depth entrance",
    purpose: "entrance",
    capabilities: ["layers", "choreography", "keyframes"],
    description: "Foreground, midground and background layers settle with different travel distances and timings, creating depth.",
    params: {
      back: P("string", ".rm-layer-back", "Background layer."),
      mid: P("string", ".rm-layer-mid", "Midground layer."),
      front: P("string", ".rm-layer-front", "Foreground layer."),
      distance: P("number", 40, "Foreground travel in px."),
    },
    build: (p) => ({
      id: "layer-parallax",
      name: "Layer parallax",
      intent: { purpose: "entrance" },
      components: [
        { id: "back", name: "Back", selector: p.back, durationMs: 900, easing: "ease-out-expo", keyframes: [{ offset: 0, properties: { translateY: p.distance * 0.3, scale: 1.06, opacity: 0 } }, { offset: 1, properties: { translateY: 0, scale: 1, opacity: 1 } }] },
        { id: "mid", name: "Mid", selector: p.mid, durationMs: 800, delayMs: 80, easing: "ease-out-expo", keyframes: [{ offset: 0, properties: { translateY: p.distance * 0.6, opacity: 0 } }, { offset: 1, properties: { translateY: 0, opacity: 1 } }] },
        { id: "front", name: "Front", selector: p.front, durationMs: 700, delayMs: 160, easing: { type: "spring", response: 0.5, dampingFraction: 0.85 }, keyframes: [{ offset: 0, properties: { translateY: p.distance, opacity: 0 } }, { offset: 1, properties: { translateY: 0, opacity: 1 } }] },
      ],
      stage: {
        html: `<div class="rm-scene"><div class="${cls(p.back)}"></div><div class="${cls(p.mid)}"></div><div class="${cls(p.front)}">Depth</div></div>`,
        css: `${DARK} .rm-scene { position: relative; width: min(560px, calc(100vw - 32px)); aspect-ratio: 16/10; border-radius: 24px; overflow: hidden; }
.${cls(p.back)} { position: absolute; inset: 0; background: linear-gradient(180deg, #1e3a8a, #0f172a); }
.${cls(p.mid)} { position: absolute; inset: 45% -10% -20%; background: #1f2937; border-radius: 50% 50% 0 0; }
.${cls(p.front)} { position: absolute; left: 8%; bottom: 10%; font: 800 clamp(28px, 7vw, 56px) system-ui; color: #fff; }`,
      },
    }),
  },
  {
    id: "press-feedback",
    title: "Press feedback",
    purpose: "feedback",
    capabilities: ["keyframes", "micro-interaction"],
    description: "A quick scale-down/settle on press (≈160ms) to acknowledge input without delaying it.",
    params: {
      selector: P("string", ".rm-press", "Pressable element."),
      scale: P("number", 0.96, "Pressed scale."),
    },
    build: (p) => ({
      id: "press-feedback",
      name: "Press feedback",
      intent: { purpose: "feedback" },
      components: [{
        id: "press", name: "Press", selector: p.selector, trigger: "onClick", durationMs: 160, easing: "ease-out",
        keyframes: [
          { offset: 0, properties: { scale: 1 } },
          { offset: 0.4, properties: { scale: p.scale } },
          { offset: 1, properties: { scale: 1 } },
        ],
        reducedMotion: "keep",
      }],
      stage: {
        html: `<button class="${cls(p.selector)}" type="button">Press me</button>`,
        css: `${DARK} .${cls(p.selector)} { font: 600 16px system-ui; padding: 14px 24px; border-radius: 14px; border: 0; color: #0b0d12; background: #f5f7fb; }`,
      },
    }),
  },
];

const byId = new Map(TEMPLATES.map((t) => [t.id, t]));

export function listTemplates() {
  return TEMPLATES.map(({ id, title, purpose, capabilities, description, params }) => ({ id, title, purpose, capabilities, description, params }));
}

/** Resolve params (defaults + type coercion + range checks) and build the spec input. */
export function buildTemplate(id, params = {}) {
  const t = byId.get(id);
  if (!t) {
    const error = new Error(`Unknown template "${id}". Available: ${TEMPLATES.map((x) => x.id).join(", ")}`);
    error.code = "TEMPLATE_NOT_FOUND";
    throw error;
  }
  const resolved = {};
  const problems = [];
  for (const [name, def] of Object.entries(t.params)) {
    let v = params[name] ?? def.default;
    if (def.type === "number") v = Number(v);
    if (def.type === "number" && !Number.isFinite(v)) problems.push(`${name} must be a number`);
    if (def.type === "number" && def.min !== undefined && v < def.min) problems.push(`${name} must be >= ${def.min}`);
    if (def.type === "number" && def.max !== undefined && v > def.max) problems.push(`${name} must be <= ${def.max}`);
    if (def.type === "array" && typeof v === "string") v = v.split(",").map((s) => s.trim()).filter(Boolean);
    if (def.type === "string") v = String(v);
    resolved[name] = v;
  }
  for (const name of Object.keys(params)) if (!(name in t.params)) problems.push(`unknown parameter "${name}" for ${id}`);
  if (problems.length) {
    const error = new Error(`Invalid template parameters: ${problems.join("; ")}`);
    error.code = "TEMPLATE_PARAMS";
    throw error;
  }
  const spec = t.build(resolved);
  spec.meta = { ...(spec.meta ?? {}), template: id, params: resolved };
  return spec;
}

/**
 * Compose several spec inputs into one (ids prefixed when they collide,
 * stage markup/CSS concatenated). Lets templates combine, e.g. a gradient
 * background + particles + a staggered list.
 */
export function composeSpecs(specs, { id, name } = {}) {
  if (!specs.length) throw new Error("composeSpecs needs at least one spec");
  const seen = new Set();
  const components = [];
  for (const s of specs) {
    for (const c of s.components) {
      const cid = seen.has(c.id) ? `${s.id}-${c.id}` : c.id;
      seen.add(cid);
      components.push({ ...c, id: cid });
    }
  }
  return {
    id: id ?? specs.map((s) => s.id).join("+").slice(0, 64).replace(/\+/g, "-"),
    name: name ?? specs.map((s) => s.name).join(" + "),
    intent: specs[0].intent,
    components,
    stage: {
      background: specs.find((s) => s.stage?.background)?.stage.background,
      html: specs.map((s) => s.stage?.html ?? "").join("\n"),
      css: specs.map((s) => s.stage?.css ?? "").join("\n"),
      script: specs.map((s) => s.stage?.script ?? "").join("\n"),
    },
    meta: { composedFrom: specs.map((s) => s.meta?.template ?? s.id) },
  };
}

function cls(selector) {
  // ".rm-card" → "rm-card" for stage markup; complex selectors fall back to the last class.
  const m = String(selector).match(/\.([A-Za-z0-9_-]+)\s*$/);
  return m ? m[1] : String(selector).replace(/[^A-Za-z0-9_-]/g, "");
}
