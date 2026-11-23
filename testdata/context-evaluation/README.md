# Independent Context Engine evaluation corpus

This corpus was authored for Reverie CLI's Context Engine migration and is
covered by the repository's [MIT license](../../LICENSE). It contains no user
manuscripts, private sessions, third-party models, or copied game assets.

The code and documentation portion of evaluation comes from the complete,
fixed public Python release commit
`070fa25b07692c90c56a6b00a9a969ff2abb7804`. The supplemental corpus here contains
an original Chinese narrative and a small game's design, scene, asset and save
records. Freeze their Git blobs and byte digests separately from the Python
source. Do not add evaluation labels to the searchable corpus.

These are retrieval inputs. The game records are not a playable game, and the
narrative is not evidence of Writer model quality or complete literary
acceptance. Gamer's four complete works and the remaining product requirements
remain separate acceptance items.

## Narrative

`novel/` holds eight chapters of the original short narrative **潮汐档案**.
Facts emerge across chapters: a flood's timing, the ownership of a key, two
similar seals with different purposes, a lamp's signal, an altered tide record,
and the final disposition of the archive. Search must locate the actual
passages, not infer missing facts from file names or this overview.

## Game resources

`game/` describes **Tidelight**, a modest 2.5D harbor exploration game.
The design and data distinguish decorative objects, a puzzle's required
sequence, save compatibility, optional audio cues, collision layers, and
resource licensing. Similar objects and decoy states provide retrieval
distractors. The files are self-contained and include only original SVG
geometry and structured text.

## Frozen evaluation rules

- Annotate independently and cross-review before freezing the query set.
- Bind every required evidence span to file, inclusive line range, Git blob
  identity, complete-file digest, excerpt digest and exact UTF-8 bytes.
- Evaluate only evidence actually returned by the application.
- Each returned fragment has at most 72 lines and the total context has at
  most 12,000 tokens. Preserve order, remove exact duplicate fragments, then
  evaluate the first ten.
- A hit must completely cover the required evidence and match its content
  version. Supplementary passages do not enter the required Recall denominator.
- Keep development queries separate from independent acceptance labels.
- Freeze inputs before observing retrieval scores. Do not revise labels,
  relevance spans or applicability after seeing a candidate's failures.

Corpus authoring and validation may use ordinary tools. Evaluation itself must
not execute scripts contained in the indexed corpus.
