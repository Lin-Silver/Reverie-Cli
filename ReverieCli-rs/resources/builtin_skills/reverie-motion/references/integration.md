# Integrating exports into a project

`RM export --spec ID@N --targets ... --out-dir DIR` writes dependency-free files. Pick targets from `RM inspect` → `recommendedTargets`.

| Target | File | Contents |
|---|---|---|
| `css` | `<id>.motion.css` | `@keyframes`, trigger rules, spring `linear()` + fallback, reduced-motion block |
| `waapi` | `<id>.motion.js` | ES module: `motionSpec` data + runtime; `mount(root?, options?)` → controller |
| `dts` | `<id>.motion.d.ts` | typings for the module (TypeScript projects) |
| `react` / `vue` / `svelte` | `<id>.<fw>.js` | hook / composable / action around `mount` (imports only the framework itself) |
| `html` | `<id>.preview.html` | standalone preview page |
| `scaffold` | `<id>.scaffold.html` | the template's markup + CSS, for projects that lack the elements |

## Contracts

**CSS only** — onLoad components animate when the stylesheet applies. Click/manual/state components play while the element has class `rm-<specId>-<componentId>-play` (re-add it to replay: remove, force reflow, add). Toggles are CSS transitions between the first and last keyframe, so toggling the class mid-flight reverses smoothly. Hover rules are wrapped in `@media (hover: hover) and (pointer: fine)`. onScroll uses `animation-timeline: view()` where supported; elsewhere the element animates when you add class `rm-in-view` (e.g. from an IntersectionObserver) — or use the module, which handles scroll triggers itself. Staggered items read `--rm-i` (their index) in CSS-only setups: set `style="--rm-i: N"` in the markup. The module computes stagger delays itself. Flip and particles need the module.

**Module (WAAPI)** —

```js
import { mount } from "./motion/hero.motion.js";
const motion = mount(document.querySelector(".hero"));   // scope (the element itself and its descendants); default document
// motion.play("id") · motion.reverse("id") · motion.toggle("id")
// motion.flip("id", ({ from, to, reverse }) => { /* change the DOM */ }, { reverse })
// motion.finished() · motion.pause() · motion.resume() · motion.destroy()
```

It binds triggers itself (click, hover on hover-capable pointers, IntersectionObserver for scroll), reads `prefers-reduced-motion` once at mount (`options.reducedMotion` overrides), and cleans up listeners and animations in `destroy()`.

Use **either** the CSS file **or** the module for a given keyframes component — loading both runs the animation twice. Typical choice: CSS for static-site entrances, module for anything interactive, flip or particles.

## Frameworks

- **Vanilla / static** — `<link rel="stylesheet" href="motion/x.motion.css">` and/or `<script type="module">import { mount } from "./motion/x.motion.js"; mount();</script>`.
- **React** — `const { ref } = useXMotion();` then `<section ref={ref}>…`. Mount happens in `useEffect`, so it is client-only; in Next.js App Router put it in a `"use client"` component. Pass options once; the hook does not re-mount on prop changes.
- **Vue / Nuxt** — `const { root } = useXMotion();` `<section ref="root">`. In Nuxt use it in a client-only component or `onMounted` path (the composable already mounts in `onMounted`).
- **Svelte / SvelteKit** — `<section use:xMotion>`; actions run only in the browser.
- **TypeScript** — export `dts` next to the module; import the `.js` file as usual (`allowJs` not required).
- **Existing motion libraries** — when the project uses Motion/Framer Motion/GSAP/React Spring for the same surface, translate the spec values into that library instead of adding a second engine: durations, keyframes, and for springs `stiffness`/`damping`/`mass` from the spec (or `critique` → `springs`). Keep the exported CSS reduced-motion behaviour equivalent.

## Verify the integration, not just the spec

After wiring, run `RM preview --file <built or static html>` or `--url http://localhost:PORT/route` (server started by the user), with the same `--action`s a user would perform, and require `passed: true`. The spec preview proves the design; the integrated preview proves the code works in the product (selectors match, styles do not fight, no runtime errors, reduced motion holds).
