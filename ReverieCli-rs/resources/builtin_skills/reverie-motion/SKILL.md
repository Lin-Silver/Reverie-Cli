---
name: reverie-motion
description: >-
  Design, implement, run and verify production motion in any web project:
  real spring physics, shared-element (FLIP) transitions, frosted-glass panels,
  SVG path drawing, staggered choreography, particles, animated gradients,
  masks, filters, morphs, variants and style transfer. Works through a
  structured MotionSpec and a local runtime that previews motion in a real
  headless browser (keyframe screenshots, frame timing, layout work, layout
  shift, reduced-motion pass), critiques and auto-fixes it, and exports
  dependency-free CSS / Web Animations / React / Vue / Svelte code. Use when
  asked to add, build, polish, fix or verify animation or motion in a project.
  Not for MP4/GIF showcase exports (design-to-motion) or taste-only reviews
  (review-animations).
---

# Reverie Motion

You are the motion engineer. The job is finished only when the motion **runs in the target project, has been observed in a real browser, and passes the runtime checks** — not when code or advice has been written.

This skill owns the *executable pipeline*: structured spec → variants → native code → real-browser evidence → fixes → export. Taste decisions come from sibling skills when installed: `animate` (whether/what/how to animate), `apple-design` (springs, interruptibility, materials), `emil-design-eng` (polish), `review-animations` (strict review of existing code). Consult them for judgement; use this skill to build and prove the result. `design-to-motion` owns showcase loops and video/GIF export.

## 0. Runtime (once per session)

The runtime is plain Node ≥ 20.10, no npm install. Reverie's `command_exec` only runs scripts inside the workspace, so the runtime must live at

```
.agents/skills/reverie-motion/runtime/bin/reverie-motion.mjs      (relative to the workspace root)
```

1. Check it exists (`file_ops exists`). If it does not, this skill was installed outside the workspace. Use `userInput` to ask the user to run, once, the install command from the skill's own directory (shown by `skill_lookup inspect` as `path`):
   `node "<skill dir>/runtime/bin/reverie-motion.mjs" install --project "<workspace root>"`
   Do not copy the runtime by hand and do not continue with guessed paths.
2. Run `node .agents/skills/reverie-motion/runtime/bin/reverie-motion.mjs doctor --project . --launch`. It verifies Node, the vendored bundle hash and that a headless Chromium starts. If no browser launches, tell the user (they can set `REVERIE_MOTION_BROWSER` to a Chrome/Edge/Chromium executable). Static work can continue, but you must then state that runtime verification did not happen.

Below, `RM` means `node .agents/skills/reverie-motion/runtime/bin/reverie-motion.mjs`. Every command prints one JSON object `{ok, tool, result | error}`; read `error.code` on failure. Every command takes `--project .` and keeps all files inside it (working data in `.reverie-motion/`). Each `command_exec` is subject to Reverie's approval policy — never ask the user to lower it.

## 1. Required workflow

Track these as a checklist and do not skip steps. If a step cannot run, say which and why in the final report.

1. **Intent.** Purpose (entrance, exit, feedback, transition, ambient, attention, storytelling, loading), trigger, how often the user sees it, what it must communicate. Frequent keyboard/high-traffic interactions usually should not animate (see `animate`). Decide before designing.
2. **Stack.** `RM inspect --project .` → frameworks, existing motion libraries, reduced-motion coverage, HTML entries, `recommendedTargets`. If the project already uses Motion/Framer Motion/GSAP for this surface, follow that pattern; never run two engines on one element.
3. **Design.** Start from a template bound to the project's real selectors (`RM templates`, then `RM design --template ID --param selector=.real-class ...`), compose several (`--input` with `compose`), use storytelling (`--story-intent hero-entrance --selector .a --selector .b`), or author a spec (`references/spec-format.md`). Fix every validation error before continuing.
4. **Options.** Produce at least two candidates for anything non-trivial: `RM variants --spec ID` and/or `RM style --spec ID --archetype elegant`. Compare critique scores, then preview the strongest two and pick one with a stated reason.
5. **Implement.** `RM export --spec ID@N --targets css,waapi[,react|vue|svelte,dts] --out-dir <project motion dir>`, then wire it in following the project's conventions (`references/integration.md`). Edit project files with the normal editor tools.
6. **Preview — spec.** `RM preview --spec ID@N --action ...` (both viewports by default). Interactions need actions: `click:SELECTOR`, `toggle:ID`, `flip:ID`, `flip-reverse:ID`, `wait:MS`.
7. **Preview — integrated page.** Preview the real page: `--file path/to/index.html` for static or built output, or `--url http://localhost:PORT/route` when a dev server is already running (do not start long-running servers with `command_exec`; ask the user to start one). This is the evidence that the integration works.
8. **Evaluate.** Read `findings`, then per viewport: `errors`, `animations`, `perf.layoutsPerFrame`, `perf.p95FrameMs`, `perf.cls`, `visual.motionEnergy`, `reducedMotion`. Open the `contactSheet` PNG when you can view images; otherwise reason from the sampled element states in the report file. See `references/validation.md`.
9. **Fix.** `RM autofix --spec ID@N` for machine-fixable findings, edit the spec for the rest, or fix the integration code. Then `RM verify --spec ID@N [--action ...]` (critique → autofix → preview loop). Re-export and re-preview the integrated page after spec changes.
10. **Deliver.** Report: what moves and why, chosen candidate, files changed, final revision id, preview evidence directory and contact sheet paths, scores, and anything unverified. Never call it done while a `critical` finding is open or without a passing integrated-page preview (unless you explain exactly why it could not run).

## 2. Tools

| Command | Tool | Use |
|---|---|---|
| `inspect` | motion_inspect_project | stack & export targets |
| `templates` | motion_templates | templates, archetypes, narratives |
| `design` | motion_design | create/validate/save a spec revision |
| `variants` | motion_variants | alternative candidates (+ spring feels) |
| `style` | motion_style | style transfer, synthesis, DNA, compare |
| `critique` | motion_critique | static rules + OpenMotion analysers |
| `autofix` | motion_autofix | machine fixes → new revision |
| `preview` | motion_preview | real-browser evidence |
| `export` | motion_export | native code into the project |
| `verify` | motion_verify | critique → autofix → preview loop |
| `lineage` | motion_lineage | revision history |

Spec references: `ID` (latest), `ID@N` (exact revision) or a `.json` path. Complex inputs (selectors with spaces or `>`, `compose`, inline specs) go in a JSON file written with `create_file` and passed as `--input file.json`; the command policy rejects shell operators. Full parameters: `references/tools.md`, or `RM schema`.

## 3. Motion rules the runtime enforces (and you should design to)

- Animate `transform` and `opacity`; everything else costs layout or paint (RM001/RM002, RV002). Keep blur ≤ 10px and never animate `backdrop-filter` — make the glass static and move the panel.
- Durations: feedback 100–250ms, entrances 250–700ms, exits shorter than entrances (150–250ms), large transitions 300–600ms, ambient loops ≥ 8s.
- Ease-out family for anything that responds or arrives (`ease-out-quart`, `ease-out-expo`); never `ease-in` for UI response; `linear` only for constant loops.
- Springs: describe them as `{ "type": "spring", "response": s, "dampingFraction": d }` and set `durationMs: "auto"` so duration equals the solved settle time. Feedback ≈ 0.3/0.85, surfaces ≈ 0.42/0.86, playful ≈ 0.45/0.6. Springs compile to exact CSS `linear()` curves with a bezier fallback.
- Interactive motion must be interruptible: toggles use `toggle: true` (WAAPI reverses from the current position; CSS export uses transitions).
- Scale from the trigger (`transformOrigin`), never from 0 — start at 0.85–0.95 with opacity.
- Staggers: 30–60ms per item, whole cascade under ~500ms.
- Reduced motion is generated for every component: `final-state` (default), `first-frame` (default for loops), `fade` (150ms opacity only), `keep` (essential feedback only). Content must never stay hidden.
- Particles: ≤ 150 on phones, DPR capped at 2, paused off-screen.

Details and rationale: `references/easing-and-springs.md`, `references/validation.md`.

## 4. Safety and failure handling

- This skill grants no permissions. Every runtime call goes through `command_exec` and its approval policy; if the user or the policy denies a call, report it and stop that step — never retry it through another tool or a different command shape.
- Only local targets are previewed (`file:`, `localhost`, `127.0.0.1`, `[::1]`, `*.localhost`, `*.test`). A remote URL needs `--allow-remote` **and** the user's explicit request.
- The runtime installs nothing, deletes nothing, and refuses paths outside the project. `export` refuses to overwrite changed files unless `--overwrite true` after you have reviewed them.
- Do not edit `runtime/vendor/openmotion.mjs` (generated from OpenMotion; integrity checked by `doctor`).

| error.code | Do this |
|---|---|
| SPEC_INVALID / TEMPLATE_PARAMS | Read the listed paths, fix, re-run. |
| SPEC_NOT_FOUND | `RM lineage` to list revisions. |
| BROWSER_NOT_FOUND / BROWSER_LAUNCH_FAILED | Report it; ask the user for a browser path (`REVERIE_MOTION_BROWSER`). Do not claim runtime verification. |
| REMOTE_TARGET_REFUSED | Use a local URL or ask the user. |
| ACTION_TARGET_MISSING | Selector not on the page — check markup or wait with `wait:MS` first. |
| EXPORT_CONFLICT | Diff the listed files; re-run with `--overwrite true` only if replacing them is intended. |
| PATH_OUTSIDE_PROJECT | Keep paths relative to the workspace. |
| command rejected by Reverie policy | Move arguments into `--input file.json`; never use shell operators or inline code. |

## 5. References (load only what the step needs)

- `references/spec-format.md` — MotionSpec v1 fields, properties/units, kinds (keyframes, flip, particles), triggers, stagger, reduced-motion strategies. Load before authoring or editing a spec.
- `references/easing-and-springs.md` — presets, spring parameters and how they compile. Load when tuning feel.
- `references/templates.md` — template catalogue, parameters, composition. Load at the design step.
- `references/validation.md` — preview report fields, RM/RV finding codes, thresholds, how to read contact sheets. Load at evaluate/fix.
- `references/integration.md` — wiring exports into vanilla, React/Next, Vue/Nuxt, Svelte, TypeScript; coexisting with existing motion libraries. Load at implement.
- `references/style-and-variation.md` — variants, archetypes, style transfer policy, synthesis, storytelling, Motion DNA, lineage. Load at the options step.
- `references/tools.md` — every command, flag, JSON input example, MCP usage and exit codes.
