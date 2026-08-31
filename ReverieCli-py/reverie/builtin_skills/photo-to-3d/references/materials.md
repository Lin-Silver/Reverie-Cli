# Materials

Pass 4 assigns one material per distinct real material, not one per mesh. A grinder with a painted body, a smoked hopper, and a steel burr ring has three materials however many meshes exist.

## Sampling colour from the photo

The photo's pixels are lit; a material's `color` is not. Sample, then correct:

1. Pick 3–5 pixels from a mid-tone, non-specular, non-shadowed region of the part.
2. Take the median, not the mean — one stray specular pixel skews the mean badly.
3. Divide out the key light's tint and intensity. A white object under warm light samples warm; the material is still white.
4. Convert to linear-sRGB the way the renderer expects, and set `outputColorSpace`/`toneMapping` before judging the result.
5. Write the final hex into `state.json` under `materials` so pass 5 and any later audit can check it.

Never state a colour from memory of what the object "usually" is.

## Physical starting points

| surface | material | roughness | metalness | extras |
| --- | --- | --- | --- | --- |
| matte painted metal | `MeshPhysicalMaterial` | 0.55–0.7 | 1.0 | thin `clearcoat` 0.1 |
| glossy car paint | `MeshPhysicalMaterial` | 0.25–0.35 | 0.0 | `clearcoat` 1.0, `clearcoatRoughness` 0.05 |
| bare aluminium | `MeshStandardMaterial` | 0.3–0.45 | 1.0 | anisotropic roughness if brushed |
| polished steel | `MeshStandardMaterial` | 0.08–0.15 | 1.0 | needs an environment map to read |
| injection-moulded ABS | `MeshPhysicalMaterial` | 0.4–0.6 | 0.0 | slight `sheen` for the mould finish |
| rubber / TPU | `MeshStandardMaterial` | 0.85–0.95 | 0.0 | very dark, near-black base is common |
| clear glass | `MeshPhysicalMaterial` | 0.02–0.06 | 0.0 | `transmission` 1.0, `ior` 1.5, `thickness` |
| smoked plastic | `MeshPhysicalMaterial` | 0.15–0.3 | 0.0 | `transmission` 0.6–0.85, tinted `attenuationColor` |
| unfinished wood | `MeshStandardMaterial` | 0.7–0.85 | 0.0 | procedural grain in pass 5 |
| fabric / canvas | `MeshPhysicalMaterial` | 0.9 | 0.0 | `sheen` 0.5, `sheenColor` lighter than base |
| skin | `MeshPhysicalMaterial` | 0.45–0.6 | 0.0 | `sheen`, plus the character track's subsurface note |
| ceramic glaze | `MeshPhysicalMaterial` | 0.1–0.2 | 0.0 | `clearcoat` 0.8 |

Treat these as starting values to be corrected against the render, not as answers.

## Procedural surface in pass 5

Prefer roughness variation over colour variation — most real surface reads as breakup in specular response, not as painted-on colour.

- **Noise**: build a small value/simplex noise function in an `onBeforeCompile` patch or a full `ShaderMaterial`; feed it `roughnessMap`-equivalent variation.
- **Edge wear**: drive exposure by `abs(dot(normal, viewDir))` plus curvature approximated from the derivative of the normal; paint metal through worn paint.
- **Panel lines**: cheap and convincing as a dark line in the roughness and normal channels, generated from UV or object-space distance functions. Real geometry only when the line must catch a highlight.
- **Weave and grain**: two crossed sine/noise bands with different frequency, then a slight normal perturbation.
- **Logos and text**: generate a `CanvasTexture` at runtime with `2d` drawing calls. That is authored, not downloaded.
- Keep every shader patch parameterised and commented; an opaque GLSL block cannot be reviewed.

## Rules

- No downloaded textures and no image-model-generated textures. Bitmaps only when the user supplied them.
- Share materials across parts made of the same thing so pass 8 has less to merge.
- Set `envMapIntensity` deliberately once pass 6 exists; metals are unreadable without an environment.
- If a material needs an environment map to look right, say so in `state.json` — a consumer of the factory has to know.
