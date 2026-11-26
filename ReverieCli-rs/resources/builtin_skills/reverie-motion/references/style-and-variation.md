# Variants, style transfer, synthesis, storytelling, DNA, lineage

All engines below are OpenMotion modules vendored unmodified; Reverie adds the product-UI policy noted for each.

## Variants — `RM variants --spec ID [--count 3] [--strategies easing,timing,...] [--seed N]`

OpenMotion strategies: `easing`, `timing`, `choreography`, `intensity`, `direction`, `palette` (off by default — it recolours). Spring components also get three native spring-feel variants (`snappy`, `smooth`, `bouncy`). Each variant is saved as its own spec (`<id>-v1`, `<id>-snappy`, …) with lineage parent and a critique summary. Pick by: critique passing → preview contact sheets → intent fit. Delete nothing; unused variants stay as history.

## Style transfer — `RM style --spec ID --archetype NAME [--strength 0.8]` or `--from OTHER_ID`

Archetypes: minimalist, energetic, cinematic, playful, corporate, organic, mechanical, elegant (`RM style --mode archetypes`). Policy:

- Only `durationMs`, `delayMs`, `easing`, `keyframes` are transferred by default. Colours are kept (`--keep-colors false` to allow recolouring) and one-shot motion never becomes a loop (`--allow-loops true` to permit `iterationCount`/`direction` changes).
- Spring components stay springs, retuned to the archetype's feel (e.g. elegant → response 0.55, dampingFraction 0.9); `mechanical` switches them to bezier timing. Transferring from another spec copies that spec's spring feel.
- Result reports `similarityToSource.before/after` (OpenMotion style-DNA similarity to the archetype or source) and a critique. Style transfer can legitimately make motion worse for its role (e.g. a cinematic feedback press) — critique will say so; preview before adopting.

## Synthesis — `RM style --mode synthesize --spec TARGET --input sources.json`

`{"mode":"synthesize","spec":"target","sources":["a@1","b@2"],"strategy":"blend","seed":1}` blends component DNA from the sources (`blend`, `dominant`, `crossover`, `mutation`) and applies it to the target's first animated component. Seeded, so repeatable.

## Storytelling — `RM design --story-intent hero-entrance --selector .eyebrow --selector .title --selector .cta`

OpenMotion's five-act planner (exposition → rising action → climax → falling action → resolution) produces beats with timing, easing and intensity for the intent (`hero-entrance`, `celebration`, `dramatic-reveal`, `conflict`, `transformation`, `journey`, `resolution`). Each beat is bound to a selector (cycled) and realised as translate/opacity keyframes scaled by intensity, with a small overshoot at the climax. Use for landing heroes and onboarding sequences; critique still applies (long beats get RM003).

## Motion DNA — `RM style --mode dna --spec ID` / `--mode compare --spec A --from B`

Style DNA: easing profile, tempo, energy, axis preferences, palette, complexity, iteration and staging patterns, plus a natural-language description; per-component DNA (easing family, timing bucket, transform signature, trigger, intensity). Use DNA to keep a product's motion language consistent: compare new specs against an approved reference spec and aim for high similarity.

## Lineage — `RM lineage [--spec ID@N]`

Every saved revision records its operation (`template`, `original`, `variation`, `style-transfer`, `story-beat`, and `autofix`/`synthesis` stored as `import` with the real label) and parents in `.reverie-motion/lineage.json`; OpenMotion's lineage engine computes generations, trees and ancestor chains. Cite the final revision id and its chain in the delivery report.
