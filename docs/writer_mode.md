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

For novel and serial requests, `bootstrap` treats 100000 non-whitespace characters as the default floor unless the brief explicitly asks for a shorter form such as a short story or novella. New novels aim for 10000 characters per chapter with a 5000-character hard minimum. Explicit short-chapter targets and existing project settings retain their previous policy.

Every chapter must have a control card before it can be committed. The commit gate rejects short drafts, repeated-paragraph padding, 64-character passages copied from other chapters, generated-prose tic overuse, and placeholder text. Legacy projects retain their delivery-per-planned-chapter minimum. The new default keeps the 10000-character drafting goal separate from its 5000-character gate; more chapters can be necessary to reach the novel's total. Completion is separate from drafting: `audit` re-reads chapter files, verifies their hashes and character counts, checks sequence and active-draft state, verifies the mirrored TXT exports, and only then allows `complete`.

Later prompts can resume the same project by its stable `novel_id`; state is loaded from disk rather than reconstructed from chat history. One-shot Writer runs continue through `audit` and `complete`, and report failure if the persisted project status is not actually `complete`.

## WStyle Cards

`/wstyle` manages Markdown Cards under `<app_root>/.reverie/wstyles/`. Six bundled Cards install inactive. Application defaults are overridden by the current native novel; an absent field inherits and an empty novel list disables styles. Ordered composition changes each actual request's System Prompt, including direct prose and native recovery. Explicit incompatibilities reject activation, and same-layer combinations warn.

```text
/mode writer
/wstyle use delicate-prose dual-heroines gl-romance-beats --global
/wstyle current
/wstyle use commercial-serial-engagement --novel harbor
```

Switches preserve existing prose. Control cards, drafts and commits record Card IDs, content hashes and continuation segments. Explicit model-assisted review saves evidence without rewriting, and extraction creates disabled Cards from supplied samples. See [WStyle commands, format and scope](WSTYLE.md) and [Writer quality and evaluation](WRITER_QUALITY.md).

## Provider Budgets And Recovery

Use the current model catalog and configured output budget. The current SenseNova 6.8 Flash and Flash Lite entries use the Anthropic-compatible Messages transport. Provider-managed thinking and output limits can affect how much finished prose one request returns; historical Flash Lite acceptance results do not verify the current model or package. WStyle review and extraction use separate bounded text-only calls, while ordinary chapter generation retains the native workflow.

`prepare_chapter` returns both the hard minimum and recommended draft size. New default chapters recommend 10000 characters; explicit short or legacy projects retain the existing buffered recommendation. A planning target or Token budget is not evidence that the saved chapter meets its length contract.

When a chapter fails only because it is short, `serial_novel` preserves the rejected draft under the native project and returns a safe append amount. The next tool call sends only `data.append_content`; Reverie merges it locally and re-runs every quality gate. This prevents repeated multi-thousand-character API generations while preserving transactional counts and hashes. When a retry is blocked by non-length issues, Writer now explicitly requires a full rewrite instead of append mode. Test runs do not overwrite the user's selected provider.

Writer now reloads that preserved pending draft directly from the on-disk project state, trims overlap against the next continuation, auto-promotes short direct-prose retries back into a native `commit_chapter` call, and retries immediately when the model only repeats the preserved tail. This closes the failure mode where a valid continuation could stall as plain assistant prose instead of being committed transactionally.

`prepare_chapter` also lints the control card against its own negative continuity requirements. If the outline, hooks, or scene beats repeat phrases that the control card itself says must not reappear, the tool rejects the card before any new prose is generated.

Build and exercise the current standalone core and Desktop kernel separately when validating changes. Request-layer tests prove dynamic composition; original model samples and native multi-chapter audits provide separate evidence for generation and continuity.

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
