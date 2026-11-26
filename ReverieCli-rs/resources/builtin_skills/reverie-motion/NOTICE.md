# Notices

reverie-motion is MIT licensed (see `LICENSE`).

## OpenMotion

`runtime/vendor/openmotion.mjs` is a build of 16 unmodified source files from
[OpenMotion](https://github.com/Yuan-ManX/open-motion) at commit
`1c93d99b064e8674f244a8f24227358ec6f61618`, Copyright (c) 2026 Yuan-Man,
MIT License — full text in `LICENSES/OpenMotion-MIT.txt` and in the bundle header.
`PROVENANCE.json` lists every vendored file with its SHA-256, the bundler version
and the bundle hash; `reverie-motion doctor` re-checks the bundle hash.

Reused upstream modules: motion critique, accessibility, performance, analysis,
variant generator, style transfer (style DNA, archetypes, blending),
motion intelligence (component DNA), synthesis, storytelling,
lineage, genome, and the shared easing/transform/spec definitions.

Build-only additions (not shipped as source): `upstream/entry.ts` (re-exports)
and `upstream/shims/zod-inert.ts` (inert stand-in for zod schemas, which the
vendored analysis functions never call).

No other third-party code is included. The runtime has no npm dependencies;
browser validation drives an installed Chromium-family browser over the Chrome
DevTools Protocol pipe.
