// Compiler: Reverie MotionSpec → native target code. Native Reverie Motion code.
//   compileCss(spec)      plain CSS (@keyframes, triggers, reduced-motion, spring linear())
//   compileModule(spec)   self-contained ES module (WAAPI runtime + spec data)
//   compileFramework(spec, framework, moduleFile)  thin React/Vue/Svelte wrappers (no extra deps)
//   compilePreviewHtml(spec, {engine})  standalone page used by preview/validation
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { springToLinear, settleTimeMs } from "./spring.mjs";
import { REVERIE_BEZIER, finalProperties, firstProperties } from "./spec.mjs";

const RUNTIME_SOURCE = fs.readFileSync(fileURLToPath(new URL("./client-runtime.js", import.meta.url)), "utf8");

const NATIVE = ["linear", "ease", "ease-in", "ease-out", "ease-in-out"];
// Same values as OpenMotion PRESET_BEZIER (shared/motion/easing.ts) plus Reverie additions.
const PRESET_BEZIER = {
  "ease-in-quad": [0.11, 0, 0.5, 0], "ease-out-quad": [0.5, 1, 0.89, 1], "ease-in-out-quad": [0.45, 0, 0.55, 1],
  "ease-in-cubic": [0.32, 0, 0.67, 0], "ease-out-cubic": [0.33, 1, 0.68, 1], "ease-in-out-cubic": [0.65, 0, 0.35, 1],
  bounce: [0.68, -0.6, 0.32, 1.6], back: [0.34, 1.56, 0.64, 1], elastic: [0.5, -0.6, 0.1, 1.4],
  snappy: [0.2, 0.8, 0.2, 1], smooth: [0.45, 0, 0.15, 1], soft: [0.4, 0, 0.6, 1],
  ...REVERIE_BEZIER,
};

const TRANSFORM_ORDER = ["translateX", "translateY", "translateZ", "scale", "scaleX", "scaleY", "rotate", "rotateX", "rotateY", "rotateZ", "skewX", "skewY"];
const UNITS = {
  translateX: "px", translateY: "px", translateZ: "px", rotate: "deg", rotateX: "deg", rotateY: "deg", rotateZ: "deg",
  skewX: "deg", skewY: "deg", blur: "px", backdropBlur: "px", borderRadius: "px", width: "px", height: "px",
  fontSize: "px", letterSpacing: "px", hueRotate: "deg", top: "px", left: "px", right: "px", bottom: "px", margin: "px", padding: "px",
};
const FILTERS = { blur: "blur", brightness: "brightness", saturate: "saturate", contrast: "contrast", hueRotate: "hue-rotate" };

const kebab = (s) => s.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`);
const value = (prop, v) => (typeof v === "number" ? `${v}${UNITS[prop] ?? ""}` : String(v));
const pct = (o) => `${Number((o * 100).toFixed(3))}%`;

/** Easing → {css, linear?, fallback?}. Springs become a real `linear()` curve. */
export function compileEasing(easing, durationMs) {
  if (!easing) return { css: "ease-out" };
  if (easing.type === "preset") {
    if (NATIVE.includes(easing.name)) return { css: easing.name };
    const b = PRESET_BEZIER[easing.name];
    return { css: b ? `cubic-bezier(${b.join(", ")})` : "ease-out" };
  }
  if (easing.type === "bezier") return { css: `cubic-bezier(${easing.p1[0]}, ${easing.p1[1]}, ${easing.p2[0]}, ${easing.p2[1]})` };
  if (easing.type === "spring") {
    const settle = settleTimeMs(easing);
    const lin = springToLinear(easing, { durationMs: durationMs ?? settle });
    const zeta = easing.damping / (2 * Math.sqrt(easing.stiffness * (easing.mass ?? 1)));
    return { linear: lin.css, css: lin.css, fallback: zeta < 1 ? "cubic-bezier(0.34, 1.4, 0.64, 1)" : "cubic-bezier(0.22, 1, 0.36, 1)", settleMs: settle };
  }
  return { css: "ease-out" };
}

function frameDecls(props) {
  const decls = [];
  const transform = TRANSFORM_ORDER.filter((p) => props[p] !== undefined).map((p) => `${p}(${value(p, props[p])})`);
  if (transform.length) decls.push(`transform: ${transform.join(" ")}`);
  const filter = Object.keys(FILTERS).filter((p) => props[p] !== undefined).map((p) => `${FILTERS[p]}(${value(p, props[p])})`);
  if (filter.length) decls.push(`filter: ${filter.join(" ")}`);
  for (const [p, v] of Object.entries(props)) {
    if (TRANSFORM_ORDER.includes(p) || FILTERS[p]) continue;
    if (p === "backdropBlur") {
      const b = `blur(${value(p, v)})`;
      decls.push(`-webkit-backdrop-filter: ${b}`, `backdrop-filter: ${b}`);
    } else decls.push(`${kebab(p)}: ${p === "opacity" || p === "strokeDashoffset" ? v : value(p, v)}`);
  }
  return decls;
}

const animName = (spec, c) => `rm-${spec.id}-${c.id}`.replace(/[^a-zA-Z0-9_-]/g, "");
const playClass = (spec, c) => `rm-${spec.id}-${c.id}-play`.replace(/[^a-zA-Z0-9_-]/g, "");

/** Plain CSS export. Click/manual/state triggers play when `.rm-<spec>-<id>-play` is added. */
export function compileCss(spec, { includeStyles = false } = {}) {
  const blocks = [`/* reverie-motion: ${spec.name} (${spec.id}) — generated, edit the spec instead. */`];
  const reduced = [];
  const fallbacks = [];
  for (const c of spec.components) {
    if (c.kind !== "keyframes") {
      if (c.kind === "particles") blocks.push(`/* ${c.id}: particle field is drawn by the JS module (canvas). */`);
      if (c.kind === "flip") blocks.push(`/* ${c.id}: shared-element (FLIP) transition needs the JS module — CSS cannot measure layout. */`);
      continue;
    }
    const name = animName(spec, c);
    const easing = compileEasing(c.easing, c.durationMs);
    if (c.toggle && c.keyframes.length === 2) {
      // Toggles compile to transitions: CSS transitions retarget mid-flight, so a
      // second click reverses from the current position (interruptible).
      blocks.push(toggleCss(spec, c, easing, reduced, fallbacks));
      continue;
    }
    const frames = c.keyframes
      .map((k) => {
        const decls = frameDecls(k.properties);
        if (k.easing) decls.push(`animation-timing-function: ${compileEasing(k.easing).css}`);
        return `  ${pct(k.offset)} { ${decls.join("; ")}; }`;
      })
      .join("\n");
    blocks.push(`@keyframes ${name} {\n${frames}\n}`);
    const delay = c.stagger ? `calc(${c.delayMs}ms + var(--rm-i, 0) * ${c.stagger.eachMs}ms)` : `${c.delayMs}ms`;
    const iter = c.iterationCount === "infinite" ? "infinite" : c.iterationCount;
    const anim = [
      `animation-name: ${name}`,
      `animation-duration: ${c.durationMs}ms`,
      `animation-timing-function: ${easing.css}`,
      `animation-delay: ${delay}`,
      `animation-iteration-count: ${iter}`,
      `animation-direction: ${c.direction}`,
      `animation-fill-mode: ${c.fillMode}`,
    ];
    if (c.transformOrigin) anim.push(`transform-origin: ${c.transformOrigin}`);
    const styles = includeStyles ? styleDecls(c.style) : [];
    if (styles.length) blocks.push(`${c.selector} { ${styles.join("; ")}; }`);
    const sel = c.selector;
    if (c.trigger === "onLoad") blocks.push(`${sel} { ${anim.join("; ")}; }`);
    else if (c.trigger === "onHover") blocks.push(`@media (hover: hover) and (pointer: fine) {\n  ${hoverSelector(sel)} { ${anim.join("; ")}; }\n}`);
    else if (c.trigger === "onScroll") {
      blocks.push(`@supports (animation-timeline: view()) {\n  ${sel} { ${anim.join("; ")}; animation-timeline: view(); animation-range: entry 0% cover 35%; }\n}`);
      blocks.push(`@supports not (animation-timeline: view()) {\n  ${sel}.rm-in-view { ${anim.join("; ")}; }\n}`);
    } else blocks.push(`${sel}.${playClass(spec, c)} { ${anim.join("; ")}; }`);
    if (easing.linear) {
      fallbacks.push(`  ${sel}${c.trigger === "onLoad" || c.trigger === "onScroll" ? "" : `.${playClass(spec, c)}`} { animation-timing-function: ${easing.fallback}; }`);
    }
    // Reduced motion — never leave content stuck in a hidden first frame.
    if (c.reducedMotion === "keep") continue;
    if (c.reducedMotion === "fade") {
      const fin = finalProperties(c);
      const fadeName = `${name}-rm-fade`;
      const start = c.keyframes[0].properties.opacity ?? 1;
      reduced.push(`  @keyframes ${fadeName} { from { opacity: ${start}; } to { opacity: ${fin.opacity ?? 1}; } }`);
      reduced.push(`  ${sel}, ${sel}.${playClass(spec, c)} { animation: ${fadeName} 150ms linear 0ms 1 both !important; ${frameDecls(withoutOpacity(fin)).map((d) => `${d} !important`).join("; ")}; }`);
    } else {
      const props = c.reducedMotion === "first-frame" ? firstProperties(c) : finalProperties(c);
      const target = c.trigger === "onLoad" || c.trigger === "onScroll" ? sel : `${sel}.${playClass(spec, c)}`;
      reduced.push(`  ${target} { animation: none !important; ${frameDecls(props).map((d) => `${d} !important`).join("; ")}; }`);
    }
  }
  if (fallbacks.length) blocks.push(`@supports not (animation-timing-function: linear(0, 1)) {\n${fallbacks.join("\n")}\n}`);
  if (reduced.length) blocks.push(`@media (prefers-reduced-motion: reduce) {\n${reduced.join("\n")}\n}`);
  return blocks.join("\n\n") + "\n";
}

function toggleCss(spec, c, easing, reduced, fallbacks) {
  const sel = c.selector;
  const play = `${sel}.${playClass(spec, c)}`;
  const first = frameDecls(c.keyframes[0].properties);
  const last = frameDecls(c.keyframes[1].properties);
  const props = [...new Set([...first, ...last].map((d) => d.split(":")[0].trim()))];
  const origin = c.transformOrigin ? `; transform-origin: ${c.transformOrigin}` : "";
  const rule = `${sel} { ${first.join("; ")}; transition-property: ${props.join(", ")}; transition-duration: ${c.durationMs}ms; transition-timing-function: ${easing.css}; transition-delay: ${c.delayMs}ms${origin}; }
${play} { ${last.join("; ")}; }`;
  if (easing.linear) fallbacks.push(`  ${sel} { transition-timing-function: ${easing.fallback}; }`);
  if (c.reducedMotion === "fade") {
    const fin = frameDecls(withoutOpacity(c.keyframes[1].properties)).map((d) => `${d} !important`);
    reduced.push(`  ${sel} { transition: opacity 150ms linear !important;${fin.length ? ` ${fin.join("; ")};` : ""} }`);
  } else if (c.reducedMotion !== "keep") {
    reduced.push(`  ${sel} { transition: none !important; }`);
  }
  return `/* ${c.id}: toggle — add/remove class "${playClass(spec, c)}" */
${rule}`;
}

function withoutOpacity(props) {
  const { opacity, ...rest } = props;
  void opacity;
  return rest;
}

function hoverSelector(sel) {
  return sel.split(",").map((s) => `${s.trim()}:hover`).join(", ");
}

function styleDecls(style = {}) {
  return Object.entries(style)
    .filter(([k]) => !k.startsWith("_"))
    .map(([k, v]) => `${kebab(k)}: ${typeof v === "number" && !["opacity", "zIndex", "fontWeight", "lineHeight", "flexGrow"].includes(k) ? `${v}px` : v}`);
}

/** Runtime data: normalized spec + precomputed easing strings (no solver shipped to the browser). */
export function runtimeSpec(spec) {
  return {
    id: spec.id,
    name: spec.name,
    components: spec.components.map((c) => {
      const out = {
        id: c.id, kind: c.kind, selector: c.selector, durationMs: c.durationMs, delayMs: c.delayMs,
        iterationCount: c.iterationCount, direction: c.direction, fillMode: c.fillMode, trigger: c.trigger,
        easing: { type: c.easing.type }, compiledEasing: compileEasing(c.easing, c.durationMs),
        keyframes: c.keyframes.map((k) => ({ offset: k.offset, properties: k.properties, ...(k.easing ? { easing: { type: k.easing.type }, compiledEasing: compileEasing(k.easing) } : {}) })),
        reducedMotion: c.reducedMotion,
      };
      for (const key of ["transformOrigin", "triggerSelector", "toggle", "stagger", "flip", "particles"]) if (c[key] !== undefined) out[key] = c[key];
      return out;
    }),
  };
}

/** Self-contained ES module: `import { mount } from "./x.motion.js"; const motion = mount(rootEl);` */
export function compileModule(spec) {
  const data = JSON.stringify(runtimeSpec(spec), null, 2);
  const runtime = RUNTIME_SOURCE.replace("export function mount(", "function mountSpec(");
  return [
    `// reverie-motion: ${spec.name} (${spec.id}) — generated module, no dependencies.`,
    "// Usage: import { mount } from \"./this-file.js\"; const motion = mount(rootElement); … motion.destroy();",
    `export const motionSpec = ${data};`,
    runtime,
    "export function mount(root, options) {",
    "  return mountSpec(motionSpec, root, options);",
    "}",
    "",
  ].join("\n");
}

/** Thin framework adapters around the generated module. They add no dependencies beyond the framework itself. */
export function compileFramework(spec, framework, moduleImport) {
  const pascal = spec.id.replace(/(^|[-_])(\w)/g, (_, __, ch) => ch.toUpperCase());
  if (framework === "react") {
    return `// reverie-motion React hook for ${spec.id}. Uses only React's own hooks.
import { useEffect, useRef } from "react";
import { mount } from "${moduleImport}";

export function use${pascal}Motion(options) {
  const ref = useRef(null);
  const controller = useRef(null);
  useEffect(() => {
    if (!ref.current) return undefined;
    controller.current = mount(ref.current, options);
    return () => controller.current && controller.current.destroy();
    // options are read once on mount by design
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return { ref, controller };
}
`;
  }
  if (framework === "vue") {
    return `// reverie-motion Vue composable for ${spec.id}.
import { onMounted, onBeforeUnmount, ref, shallowRef } from "vue";
import { mount } from "${moduleImport}";

export function use${pascal}Motion(options) {
  const root = ref(null);
  const controller = shallowRef(null);
  onMounted(() => { if (root.value) controller.value = mount(root.value, options); });
  onBeforeUnmount(() => controller.value && controller.value.destroy());
  return { root, controller };
}
`;
  }
  if (framework === "svelte") {
    return `// reverie-motion Svelte action for ${spec.id}: <div use:${camel(pascal)}Motion>
import { mount } from "${moduleImport}";

export function ${camel(pascal)}Motion(node, options) {
  const controller = mount(node, options);
  return { destroy() { controller.destroy(); } };
}
`;
  }
  throw new Error(`Unsupported framework "${framework}" (react, vue, svelte).`);
}

const camel = (s) => s.charAt(0).toLowerCase() + s.slice(1);

/** Standalone preview page. engine "waapi" uses the module runtime; "css" uses compileCss + class toggles. */
export function compilePreviewHtml(spec, { engine = "waapi", manualClock = false } = {}) {
  const css = engine === "css" ? compileCss(spec, { includeStyles: true }) : stylesheetFromStyles(spec);
  const module = compileModule(spec).replace(/<\/script/gi, "<\\/script");
  const boot = engine === "css"
    ? `
// CSS engine: animations come from the stylesheet; JS only drives non-CSS kinds and play classes.
const controller = mount(document, { manualClock: ${manualClock} });
window.__reverieMotion = {
  engine: "css",
  controller,
  animations: () => document.getAnimations(),
  seek(ms) { for (const a of document.getAnimations()) { a.pause(); a.currentTime = ms; } controller.seek(ms); },
  play(id) { const c = fullSpec.components.find((x) => x.id === id); document.querySelectorAll(c.selector).forEach((el) => { el.classList.remove("rm-${spec.id}-" + id + "-play"); void el.offsetWidth; el.classList.add("rm-${spec.id}-" + id + "-play"); }); },
  toggle(id) { const c = fullSpec.components.find((x) => x.id === id); document.querySelectorAll(c.selector).forEach((el) => el.classList.toggle("rm-${spec.id}-" + id + "-play")); },
};
// What an integrator does with the CSS export: add the play class on click.
for (const c of fullSpec.components.filter((x) => x.kind === "keyframes" && x.trigger === "onClick")) {
  const targets = c.triggerSelector ? document.querySelectorAll(c.triggerSelector) : document.querySelectorAll(c.selector);
  targets.forEach((t) => t.addEventListener("click", () => (c.toggle ? window.__reverieMotion.toggle(c.id) : window.__reverieMotion.play(c.id))));
}`
    : `
const controller = mount(document, { manualClock: ${manualClock} });
window.__reverieMotion = {
  engine: "waapi",
  controller,
  animations: () => document.getAnimations(),
  seek(ms) { for (const a of document.getAnimations()) { a.pause(); a.currentTime = ms; } controller.seek(ms); },
  play: (id) => controller.play(id),
};`;
  // In the CSS engine the module must not also start keyframe animations.
  const moduleForEngine = engine === "css"
    ? module.replace("export const motionSpec = ", "const fullSpec = ").replace("export function mount(root, options) {\n  return mountSpec(motionSpec, root, options);\n}", "export const motionSpec = { ...fullSpec, components: fullSpec.components.filter((c) => c.kind !== \"keyframes\") };\nexport function mount(root, options) {\n  return mountSpec(motionSpec, root, options);\n}")
    : module;
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(spec.name)} · reverie-motion preview</title>
<script>
  window.__rmErrors = [];
  addEventListener("error", (e) => window.__rmErrors.push(String(e.message || e.error)));
  addEventListener("unhandledrejection", (e) => window.__rmErrors.push("unhandledrejection: " + String(e.reason)));
</script>
<style>
  :root { color-scheme: ${spec.stage.colorScheme}; }
  *, *::before, *::after { box-sizing: border-box; }
  html, body { margin: 0; min-height: 100%; }
  body { background: ${spec.stage.background}; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
${indent(spec.stage.css)}
${indent(css)}
</style>
</head>
<body>
${spec.stage.html}
<script type="module">
${moduleForEngine}
${boot}
${spec.stage.script}
window.__rmReady = true;
</script>
</body>
</html>
`;
}

function stylesheetFromStyles(spec) {
  return spec.components
    .filter((c) => c.selector && Object.keys(c.style).length)
    .map((c) => `${c.selector} { ${styleDecls(c.style).join("; ")}; }`)
    .join("\n");
}

function indent(s) {
  return s ? s.split("\n").map((l) => `  ${l}`).join("\n") : "";
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** TypeScript declarations for the generated module. */
export function compileTypes(spec) {
  const ids = spec.components.map((c) => JSON.stringify(c.id)).join(" | ") || "string";
  return `// reverie-motion: typings for ${spec.id}
export type MotionComponentId = ${ids};
export interface MotionController {
  readonly reducedMotion: boolean;
  play(id: MotionComponentId): Animation[];
  reverse(id: MotionComponentId): Animation[];
  toggle(id: MotionComponentId): Animation[];
  flip(id: MotionComponentId, mutate?: ((ctx: { from: Element; to: Element; reverse: boolean }) => void) | null, options?: { reverse?: boolean }): Animation[];
  animations(): Animation[];
  seek(ms: number): void;
  pause(): void;
  resume(): void;
  finished(): Promise<unknown[]>;
  destroy(): void;
}
export interface MountOptions { reducedMotion?: boolean; manualClock?: boolean }
export declare const motionSpec: { id: string; name: string; components: unknown[] };
export declare function mount(root?: ParentNode, options?: MountOptions): MotionController;
`;
}
