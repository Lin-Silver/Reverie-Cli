// Target-project technology inspection. Native Reverie Motion code.
// Bounded, read-only scan used to pick export formats that fit the existing stack.
import fs from "node:fs";
import path from "node:path";

const SKIP = new Set(["node_modules", ".git", ".hg", ".svn", "dist", "build", "out", ".next", ".nuxt", ".svelte-kit", ".turbo", ".cache", "coverage", "target", ".venv", "venv", "__pycache__", ".reverie-motion", ".agents"]);
const FRAMEWORKS = { react: "react", "react-dom": "react", next: "next", preact: "preact", vue: "vue", nuxt: "nuxt", svelte: "svelte", "@sveltejs/kit": "sveltekit", "solid-js": "solid", astro: "astro", "@angular/core": "angular", lit: "lit" };
const MOTION_LIBS = ["framer-motion", "motion", "gsap", "animejs", "@react-spring/web", "react-spring", "lottie-web", "@lottiefiles/dotlottie-web", "three", "@vueuse/motion", "popmotion", "@formkit/auto-animate", "velocity-animate", "@motionone/dom", "motion-v"];
const STYLE_LIBS = ["tailwindcss", "styled-components", "@emotion/react", "@emotion/styled", "sass", "less", "@vanilla-extract/css", "unocss", "postcss"];
const BUNDLERS = ["vite", "webpack", "parcel", "esbuild", "rollup", "@rspack/core", "turbopack"];

export function inspectProject(project, { maxFiles = 4000 } = {}) {
  const root = path.resolve(project);
  const pkgFile = path.join(root, "package.json");
  let pkg = null;
  try {
    pkg = JSON.parse(fs.readFileSync(pkgFile, "utf8"));
  } catch {
    /* not a node project */
  }
  const deps = { ...(pkg?.dependencies ?? {}), ...(pkg?.devDependencies ?? {}), ...(pkg?.peerDependencies ?? {}) };
  const has = (name) => Object.prototype.hasOwnProperty.call(deps, name);
  const frameworks = [...new Set(Object.entries(FRAMEWORKS).filter(([d]) => has(d)).map(([, f]) => f))];
  const motionLibraries = MOTION_LIBS.filter(has).map((n) => ({ name: n, version: deps[n] }));
  const styling = STYLE_LIBS.filter(has);
  const bundlers = BUNDLERS.filter(has);

  const ext = {};
  const signals = { keyframes: 0, reducedMotionQueries: 0, waapiCalls: 0, viewTransitions: 0, transitions: 0, htmlEntries: [] };
  let scanned = 0;
  let truncated = false;
  const walk = (dir, depth) => {
    if (truncated || depth > 8) return;
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      if (truncated) return;
      if (e.isDirectory()) {
        if (!SKIP.has(e.name) && !e.name.startsWith(".")) walk(path.join(dir, e.name), depth + 1);
        continue;
      }
      if (++scanned > maxFiles) {
        truncated = true;
        return;
      }
      const x = path.extname(e.name).toLowerCase();
      ext[x] = (ext[x] ?? 0) + 1;
      const full = path.join(dir, e.name);
      if (x === ".html" && signals.htmlEntries.length < 10) signals.htmlEntries.push(path.relative(root, full).replace(/\\/g, "/"));
      if ([".css", ".scss", ".sass", ".less", ".js", ".mjs", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".astro", ".html"].includes(x)) {
        let text = "";
        try {
          const stat = fs.statSync(full);
          if (stat.size > 512 * 1024) continue;
          text = fs.readFileSync(full, "utf8");
        } catch {
          continue;
        }
        signals.keyframes += (text.match(/@keyframes\s/g) ?? []).length;
        signals.reducedMotionQueries += (text.match(/prefers-reduced-motion/g) ?? []).length;
        signals.waapiCalls += (text.match(/\.animate\(\s*\[/g) ?? []).length;
        signals.viewTransitions += (text.match(/startViewTransition|view-transition-name/g) ?? []).length;
        signals.transitions += (text.match(/transition\s*:/g) ?? []).length;
      }
    }
  };
  walk(root, 0);

  const typescript = has("typescript") || (ext[".ts"] ?? 0) + (ext[".tsx"] ?? 0) > 0;
  const primary = frameworks.find((f) => ["react", "next", "preact"].includes(f)) ? "react"
    : frameworks.find((f) => ["vue", "nuxt"].includes(f)) ? "vue"
    : frameworks.find((f) => ["svelte", "sveltekit"].includes(f)) ? "svelte"
    : frameworks[0] ?? (signals.htmlEntries.length ? "vanilla" : "unknown");
  const targets = ["css", "waapi"];
  if (["react", "vue", "svelte"].includes(primary)) targets.push(primary);

  const notes = [];
  if (motionLibraries.length) {
    notes.push(`Project already uses ${motionLibraries.map((m) => m.name).join(", ")}. Prefer extending those patterns for new motion in the same surfaces; reverie-motion exports stay dependency-free and can coexist, but do not mix two engines on one element.`);
  }
  if (!signals.reducedMotionQueries) notes.push("No prefers-reduced-motion handling found; exported code adds it per component.");
  if (primary === "unknown") notes.push("No framework or HTML entry detected; export css + waapi and wire them where the UI is rendered.");
  const scripts = pkg?.scripts ?? {};
  const preview = scripts.build && (has("vite") || has("parcel")) ? { suggestion: "Build, then preview the built index.html with motion_preview --file, or ask the user to run the dev server and preview its localhost URL." }
    : signals.htmlEntries.length ? { suggestion: `Preview ${signals.htmlEntries[0]} directly with motion_preview --file.` }
    : { suggestion: "Use motion_preview on the generated spec preview; integrate after verification." };

  return {
    schema: "reverie-motion.stack.v1",
    project: root,
    packageName: pkg?.name ?? null,
    frameworks,
    primary,
    typescript,
    motionLibraries,
    styling,
    bundlers,
    scripts: Object.keys(scripts),
    fileTypes: Object.fromEntries(Object.entries(ext).sort((a, b) => b[1] - a[1]).slice(0, 12)),
    signals,
    scanned: { files: Math.min(scanned, maxFiles), truncated },
    recommendedTargets: targets,
    moduleExtension: typescript ? ".js + generated .d.ts (export adds typings for TypeScript projects)" : ".js",
    preview,
    notes,
  };
}
