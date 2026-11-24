# Character track

For humans, humanoids, creatures, and anything with a face or a skeleton. Insert these stages between pass 3 (form) and pass 4 (material) of the main pipeline; the eight numbered passes still govern the run.

A character fails differently from an object: proportion errors read as "wrong person", and asymmetry errors read as "broken". Both gates below are fail-closed.

## C1. Landmarks

Mark the anatomical points on the reference before any character geometry:

- Head: eye line, pupil centres, nose base, mouth line, chin, ear top and lobe, hairline.
- Torso: shoulder points, sternum, waist, hip points, navel.
- Limbs: elbow, wrist, knuckle line, knee, ankle.

Express everything in head-heights, not pixels: total height, shoulder width, leg-to-torso ratio, head-to-shoulder. Head-heights survive an unknown camera; pixels do not.

**Gate**: every landmark listed above has a value, and the head-height total is stated.

## C2. Camera pose solve

A photo is a projection. Before trusting any measurement, solve for the camera:

1. Estimate focal length from the perspective compression across known-parallel features.
2. Estimate yaw, pitch, and roll from the landmark asymmetry — a 15° yaw makes a symmetric face measure asymmetric.
3. Set the harness `front` camera to the solved pose so pass renders are compared against the photo on equal terms.
4. Record focal length and rotation in `state.json` under a `camera_solve` key.

**Gate**: measurements are corrected for the solved pose, not read flat off the image.

## C3. De-lighting

Do this before pass 4, because a character's skin and clothing colours are the most light-contaminated part of any photo.

- Identify the key light direction from the shadow terminator across the face.
- Remove its tint and falloff from sampled colours; a warm key makes pale skin read tan.
- Discard specular pixels entirely — forehead, nose bridge, cheekbone highlights are the light, not the skin.
- Sample skin in at least three regions (forehead, cheek, jaw) and keep them as separate values; skin is not one colour.

**Gate**: sampled colours are recorded post-correction, with the removed key tint noted.

## C4. Texture projection

Only when the user supplied the photo for use as texture:

- Project the reference through the solved camera onto the front-facing geometry; never wrap a photo as an equirect or a flat UV.
- Mirror across the median plane only where the subject is genuinely symmetric, and never across an asymmetric feature (a parting, a scar, a logo).
- Fill occluded regions by inpainting from adjacent projected colour, and mark those regions in `state.json`; they are inferred, not observed.
- With no supplied photo, use procedural materials from [materials.md](materials.md) instead. Do not generate a face texture with an image model.

## C5. Skeleton and skinning

- Build the bone hierarchy to match the structural pass tree: root → hips → spine chain → neck → head, and hips → leg chains, chest → arm chains.
- Place joints at the C1 landmark positions, not at mesh-segment midpoints.
- Bind with geodesic weights (distance measured over the surface, not through space), so an arm bone does not drag the ribcage.
- Cap influences at 4 bones per vertex and normalise the weights.
- Test each joint through its real range in the harness and screenshot the extremes. Candy-wrapper twisting at the wrist and forearm is the usual failure.

**Gate**: a screenshot per tested joint at its range limit, with no surface collapse or inverted normal.

## C6. Hair

Five stages, in order. Skipping to strands produces a wig floating above a bald head.

1. **Scalp** — the cap surface hair grows from, matching the skull.
2. **Volume** — the overall hair mass as low-poly shells; this is what the silhouette is judged on.
3. **Clumps** — major locks and partings as extruded or lathed groups following the volume.
4. **Strands** — card or tube detail on the outer surface only, never on hidden interior.
5. **Flyaways** — a sparse set of individual curves that break the silhouette's hard edge.

Judge stage 2 against the reference silhouette before any strand work.

## Chirality gates

Check after every character stage, and again before pass 8:

- Left and right limbs mirror in position and rotation, and are named `.L`/`.R` consistently.
- No mesh has a negative determinant transform — mirroring by negative scale inverts normals and breaks lighting.
- Hands: thumbs point inward on both sides; fingers curl the same direction.
- Feet point forward with the arch on the inside of each foot.
- Any asymmetry present in the output is present in the reference. Unintended asymmetry blocks the pass.
