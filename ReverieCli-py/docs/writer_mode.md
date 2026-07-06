# Writer Mode

Writer mode is Reverie's focused long-form fiction environment. Its tool surface intentionally excludes terminal execution, browser control, media generation, runtime plugins, arbitrary MCP tools, and general Skill discovery.

## Native Workflow

The `serial_novel` tool creates a resumable project under `novels/<novel-id>/` and mirrors reader-friendly TXT exports under `novel/<novel-id>/` with:

- project brief and delivery target
- world, cast, architecture, style, and roadmap documents
- one control card per chapter
- one committed Markdown file per chapter in the managed project
- one plain-text `.txt` file per committed chapter in the reader export folder
- one merged `manuscript.txt` in the reader export folder
- continuity, timeline, and foreshadowing ledgers
- machine-readable progress state

For novel and serial requests, `bootstrap` treats 100000 Chinese characters as the default floor unless the brief explicitly asks for a shorter form such as a short story or novella.

Every chapter must have a control card before it can be committed. The commit gate rejects drafts that cannot satisfy the total target within the planned chapter count, repeated-paragraph padding, 64-character passages copied from earlier chapters, generated-prose tic overuse, and placeholder text. Completion is separate from drafting: `audit` re-reads chapter files, verifies their hashes and character counts, checks sequence and active-draft state, verifies the mirrored TXT exports, and only then allows `complete`.

Later prompts can resume the same project by its stable `novel_id`; state is loaded from disk rather than reconstructed from chat history. One-shot Writer runs continue through `audit` and `complete`, and report failure if the persisted project status is not actually `complete`.

## SenseNova Flash Lite Validation

The live Writer acceptance profile uses `sensenova-6.7-flash-lite` through the OpenAI Chat transport. The provider documents that `max_tokens` includes hidden reasoning and that streamed responses may emit substantial `reasoning` before `content`. Flash Lite therefore uses the provider's instruction-mode sampling defaults (`temperature=0.7`, `top_p=0.8`, `top_k=20`, `min_p=0`, `presence_penalty=1.5`, and `repetition_penalty=1`), forwards configured `reasoning_effort` through the OpenAI-compatible request body, and does not send the undocumented `output_config.effort` field.

Legacy configurations that inherit the global 65536-token output budget are bounded to 6144 tokens for Flash Lite. Explicit user limits remain respected. Writer keeps long-form prose on the native tool-call path, where `prepare_chapter` exposes both the exact hard minimum and a 15% buffered recommended draft size.

When a chapter fails only because it is short, `serial_novel` preserves the rejected draft under the native project and returns a safe append amount. The next tool call sends only `data.append_content`; Reverie merges it locally and re-runs every quality gate. This prevents repeated multi-thousand-character API generations while preserving transactional counts and hashes. When a retry is blocked by non-length issues, Writer now explicitly requires a full rewrite instead of append mode. Test runs do not overwrite the user's selected provider.

Writer now reloads that preserved pending draft directly from the on-disk project state, trims overlap against the next continuation, auto-promotes short direct-prose retries back into a native `commit_chapter` call, and retries immediately when the model only repeats the preserved tail. This closes the failure mode where a valid continuation could stall as plain assistant prose instead of being committed transactionally.

`prepare_chapter` also lints the control card against its own negative continuity requirements. If the outline, hooks, or scene beats repeat phrases that the control card itself says must not reappear, the tool rejects the card before any new prose is generated.

Packaged `dist\reverie.exe` runs were re-validated against the long-form daily-novel acceptance task on `sensenova-6.7-flash-lite` through chapter 5. A real continuation run recovered from the chapter-4 and chapter-5 shortfall path, committed `chapter-0004.txt` and `chapter-0005.txt`, updated `manuscript.txt`, and completed without relying on outer auto-followup injection.

## Tool Surface

Writer receives Context Engine retrieval, WebSearch/WebFetch, project memory, clarification, mode switching, and the native Writer tools. Generic file-editing tools are intentionally hidden from the visible Writer tool surface so prose and project state stay on the transactional `serial_novel` path:

- `serial_novel`
- `novel_context_manager`
- `consistency_checker`
- `plot_analyzer`

Novel intent in another Reverie mode should switch to Writer before drafting.

## Design References

The native implementation is original Reverie code. Its document-first and continuity-control design was informed by these MIT-licensed community projects, reviewed at fixed commits on 2026-07-03:

- [Novel-Control-Station-Skill](https://github.com/jingtai123/Novel-Control-Station-Skill), commit `68d14aa6137efe60f93a4c87a0eccef8c654464b`
- [chinese-novelist-skill](https://github.com/PenglongHuang/chinese-novelist-skill), commit `eb1185649437f2aaaa765f02be024132ea83d82d`
- [oh-story-claudecode](https://github.com/worldwonderer/oh-story-claudecode), commit `e3cb89205b8078eb1d6fcfe2faf113ab64666a33`

Reverie adopts the general ideas of disk-backed truth, outline-before-prose, per-chapter state writeback, interruption recovery, and deterministic post-write checks without copying their prompt libraries or prose guidance.
