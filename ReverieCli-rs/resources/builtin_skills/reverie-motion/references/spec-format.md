# MotionSpec v1 (`reverie-motion/spec@1`)

A spec is framework-neutral JSON describing *what* moves, *when*, *how* and *what happens under reduced motion*. It is a superset of OpenMotion's `MotionSpec`, so the vendored OpenMotion analysers run on it unchanged. Validate by saving it with `RM design --spec file.json` (or `--input`), which returns precise `path: message` errors.

```json
{
  "schema": "reverie-motion/spec@1",
  "id": "card-entrance",
  "name": "Card entrance",
  "intent": { "purpose": "entrance" },
  "components": [
    {
      "id": "cards",
      "selector": ".product-card",
      "trigger": "onScroll",
      "durationMs": 420,
      "easing": "ease-out-quart",
      "stagger": { "eachMs": 45, "from": "start", "count": 6 },
      "keyframes": [
        { "offset": 0, "properties": { "translateY": 16, "opacity": 0 } },
        { "offset": 1, "properties": { "translateY": 0, "opacity": 1 } }
      ]
    }
  ],
  "stage": { "html": "<div class=\"product-card\">…</div>", "css": ".product-card{…}" }
}
```

## Top level

| Field | Type | Notes |
|---|---|---|
| `id` | string | `[A-Za-z0-9][A-Za-z0-9-_]{0,63}`; revisions are `id@N` |
| `name`, `description` | string | |
| `intent.purpose` | enum | `entrance` `exit` `feedback` `transition` `ambient` `attention` `storytelling` `loading` — drives duration rules |
| `tokens` | object | free-form design tokens (kept for reuse) |
| `components` | array | ≥ 1 |
| `stage` | object | preview only: `html`, `css`, `script`, `background`, `colorScheme`; also emitted by `export --targets scaffold` |
| `meta` | object | written by the runtime: `template`, `params`, `version`, `revisionId`, `parent`, `operation` |

## Component

| Field | Default | Notes |
|---|---|---|
| `id` | `c<n>` | unique in the spec |
| `kind` | `keyframes` | `keyframes`, `flip` (shared element), `particles` (canvas) |
| `selector` | — | CSS selector in the target markup (required except `flip`); all matches animate |
| `trigger` | `onLoad` | `onLoad`, `onClick` (element or `triggerSelector`), `onHover` (pointer devices only), `onScroll` (enters viewport; CSS uses `animation-timeline: view()` when supported), `manual`/`onState` (call the controller or add the play class) |
| `triggerSelector` | — | element that receives the click/hover |
| `toggle` | false | click toggles open/closed; reversible mid-flight |
| `durationMs` | 400 / `"auto"` | `"auto"` with a spring = solved settle time |
| `delayMs` | 0 | ≥ 0 |
| `iterationCount` | 1 | integer or `"infinite"` |
| `direction` | `normal` | `reverse`, `alternate`, `alternate-reverse` |
| `fillMode` | `both` | keep `both` for delayed entrances (RM010) |
| `easing` | `ease-out` | preset name, `cubic-bezier(...)`, or object (see easing reference) |
| `keyframes` | — | ≥ 2 frames, offsets ascending, first `0`, last `1`; optional per-frame `easing` |
| `transformOrigin` | — | e.g. `"top left"` — scale from the trigger |
| `stagger` | — | `{eachMs, from: start|center|end, count}`; `count` is used for analysis/preview only, runtime uses real matches. Negative `eachMs` only for infinite loops (out-of-phase loops) |
| `reducedMotion` | `final-state` (`first-frame` for loops) | `final-state`, `first-frame`, `fade`, `keep` |
| `style` | {} | static styles used in previews (`includeStyles` exports them) |
| `flip` | — | kind `flip`: `{from, to, crossfade}` selectors |
| `particles` | — | kind `particles`: `{count, colors[], sizeMin, sizeMax, speed, seed, drift, twinkle, maxDpr}` |

## Animatable properties

Numbers get the unit shown; strings pass through verbatim (`"10%"`, `"2rem"`).

| Group | Properties | Unit | Cost |
|---|---|---|---|
| transform | `translateX` `translateY` `translateZ` | px | composited |
| | `scale` `scaleX` `scaleY` | — | composited |
| | `rotate` `rotateX` `rotateY` `rotateZ` `skewX` `skewY` | deg | composited |
| opacity | `opacity` | — | composited |
| filter | `blur` (px) `brightness` `saturate` `contrast` `hueRotate` (deg) | | paint |
| glass | `backdropBlur` | px | very expensive — keep static |
| mask | `clipPath` (string, e.g. `inset(…)`, `circle(…)`) | | paint |
| svg | `strokeDashoffset` (use with `pathLength="1"` + `stroke-dasharray: 1`) | — | paint |
| paint | `color` `backgroundColor` `boxShadow` `borderRadius` `backgroundPosition` | | paint |
| layout | `width` `height` `top` `left` `right` `bottom` `margin` `padding` `fontSize` `letterSpacing` | px | layout every frame — avoid |

Transform properties in a frame are combined in a fixed order: translate → scale → rotate → skew.

## Kinds

- **keyframes** — compiles to `@keyframes` (CSS) and `element.animate()` (WAAPI).
- **flip** — First/Last/Invert/Play: the runtime measures `from` and `to`, then animates `to` from the old geometry. Needs the JS module (`controller.flip(id, mutate)`; `mutate` performs the DOM change, default: show `to`, hide `from`). Reverse with `{ reverse: true }`.
- **particles** — seeded deterministic canvas field appended to each `selector` match; pauses off-screen and on hidden tabs; draws one static frame under reduced motion.

## Reduced-motion strategies

| Strategy | Behaviour |
|---|---|
| `final-state` | no animation; element shows its final keyframe |
| `first-frame` | no animation; element stays at the first keyframe (loops) |
| `fade` | 150ms opacity-only change into the final state |
| `keep` | unchanged — only for essential feedback with small travel (RM012 warns otherwise) |
