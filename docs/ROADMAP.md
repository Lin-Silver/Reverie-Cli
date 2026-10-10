# Reverie CLI Roadmap

This is the single source of truth for planned product work. Current behavior belongs in the relevant guide; completed work belongs in the changelog.

Last reconciled with the repaired local worktree: **2026-10-05**. See [Feature Status](FEATURE_STATUS.md) for the current capability matrix and gap IDs, and the [repair report](VERIFICATION_HISTORY.md#reverie-cli-feature-repairs-2026-10-05) for evidence. The [audit](VERIFICATION_HISTORY.md#reverie-cli-feature-audit-2026-10-05) preserves the earlier baseline; the [MCP scope addendum](VERIFICATION_HISTORY.md#reverie-cli-feature-audit-addendum-2026-10-05) and the [cross-platform identity and language coverage addendum](VERIFICATION_HISTORY.md#reverie-cli-platform-language-audit-2026-10-05) record the later source passes. A gap recorded here is not authorization to implement all optional product extensions.

## Current Baseline

2026-10-08 documentation update: historical reports and specifications are consolidated in [Verification History](VERIFICATION_HISTORY.md) and [Development History](DEVELOPMENT_HISTORY.md). The new [Intelligent UI specification](INTELLIGENT_UI_SPEC.md) is a proposal based on current source inspection, not a completed implementation or a new full regression run.

Reverie CLI provides a multi-provider coding agent, Context Engine retrieval and memory, sessions and rollback, scoped managed SubAgents, explicit handoff and recovery surfaces, desktop control, Writer workflows, runtime plugins, cross-platform CI, and packaged SDK bridge verification.

The CLI's built-in Python Reverie Engine runtime supports deterministic headless gameplay execution, scene and component data, physics queries, navigation, input, animation, UI state, localization, save data, telemetry, video export, and a ModernGL renderer with reusable mesh resources, basic textures, blending, framebuffer readback and PNG capture. Native window presentation, input, resize and close now have Windows runtime evidence. G19–G21 concern this runtime/Gamer surface, not the external Engine editor registered as a RATS provider.

## Product Completion Priorities

### P1: Real model compatibility

| Gap | Required completion | Verification gate |
| --- | --- | --- |
| G12 — Model compatibility | Maintain per-provider/model evidence for text, complete SSE, native tool round trips, thinking signatures and vision | Actual named client surface and provider tested separately; empty SSE, dropped tools and billing-only responses cannot count as success |

### P1: Cross-platform provider trust boundary

| Gap | Required completion | Verification gate |
| --- | --- | --- |
| G28 — Non-Windows RATS identity | Decide explicitly between a per-platform executable/process identity check and refusing to enable providers on hosts where identity cannot be established. An existence check and a liveness probe that treats `PermissionError` as a match must not be presented as identity validation | Run the identity suite on a non-Windows host with a deliberately mismatched executable and a reused PID; a descriptor pointing at an existing but wrong binary must be rejected rather than enabled |

### P2: Scale and completion evidence

| Gaps | Completion gate |
| --- | --- |
| G07 — Skill workflow compliance | Full main-body loading is enforced per turn; actual model use of referenced resources and prescribed workflows still needs representative model runs |
| G08 / G09 — Residual scale limits | Memory/IPC bounds and cached history search are implemented and measured; investigate cancellation and random byte paging without losing exact hash/line counts, and measure first history-index construction and short queries |
| G13 / G14 — Native input and notifications | Command keyboard selection and composition guards are implemented; actual Windows IME candidate windows, screen-reader/focus checks, notification click ownership and OS-disabled behavior still need host evidence |
| G15 — Authorized integrations | Real plugin/MCP/RATS connect, permission, call, revoke, disconnect and restart paths; unconfigured E2E remains skipped rather than accepted |
| G16 — Retrieval quality | Reproduce the complete benchmark with frozen data and broader languages; publish methods and distributions, keeping hidden-prompt/media estimates separate from API usage |
| G17 / G18 — Packaging and platforms | Build identity and actual launch path are visible; this turn's portable first-launch action was blocked by automatic approval review, so first extraction remains unverified. Test it through an allowed run, and test native Linux/macOS GUI, PTY, notifications and prolonged sessions on those hosts |
| G24 — MCP client feature scope | Document the supported MCP client profile; add only explicitly selected prompt/resource/client-request features, and report unsupported requests clearly. Current dynamic tool and resource paths remain available |
| G26 — Remote MCP authorization | Choose between static-header-only support and managed OAuth. If OAuth is added, verify resource/authorization discovery, PKCE, 401 challenge handling, token storage and refresh against an authorized server |
| G27 — MCP multimodal acceptance | Typed image/audio relay, structured/resource metadata and bounded rejection are implemented; verify real media servers and each supported model, and complete binary embedded-resource handling |
| G29 — Platform test gating | Keep the Windows-only assertions, but report the per-platform skip count alongside any published regression total, and add non-Windows equivalents for the paths that are only asserted under `os.name == "nt"` |
| G30 / G31 — Multi-language parsing dependency | Decide whether tree-sitter is required or optional. If required, add it to the installed and packaged dependency set and pin the grammar imports in the PyInstaller spec; if optional, surface the active parsing mode so a regex fallback is visible rather than silent. Either way, remove `zig` from the claimed language set or implement both its grammar dependency and a parse path |
| G32 — LSP coverage | Add server definitions only for languages with an actual parser or grammar path, and report a configured-but-missing server distinctly from an unsupported language |

G01–G06, G10–G11, G22–G23, G25 and Windows G19 have been repaired; their current behavior belongs in the guides and dated repair reports. G07–G09, G13, G17, G24, G26 and G27 retain the limits above. G28–G32 were newly registered by the [cross-platform identity and language coverage addendum](VERIFICATION_HISTORY.md#reverie-cli-platform-language-audit-2026-10-05); that pass changed documentation only, so none of them has been repaired. API cancellation, output-mode latency and profile/crop improvements are recorded in the [request repair report](VERIFICATION_HISTORY.md#reverie-cli-request-profile-repairs-2026-10-05). Keep links, examples, current status and local-evidence labels checked in future changes. Do not turn every incomplete experiment into a new UI module.

## Desktop Coding Workflow and UI/UX

<a id="intelligent-ui"></a>

### Intelligent UI — G33, proposed

Implement the public experience described in [INTELLIGENT_UI_SPEC](INTELLIGENT_UI_SPEC.md): model-generated interactive views and a declared MCP Apps compatibility profile. The specification includes file-level integration points, contracts, acceptance tests and copyable AI prompts. The current request authorizes documentation and planning; implementation begins with a subsequent development request.

| Order | Deliverable | Current state / completion gate |
| --- | --- | --- |
| P0 | Isolated renderer and trusted bridge prototype | Not implemented. Prove navigation/IPC/network restrictions and recovery from an infinite loop in packaged Electron; select the rendering container from that evidence |
| P1 | `render_view`, durable artifacts, timeline, restart and TUI fallback | Not implemented. Verify the complete tool-to-view flow, provenance, old-client fallback and absence of duplicate HTML in model results |
| P2 | User actions, approval routing and session state | Not implemented. Verify existing executor/session locks, cancellation, replay protection, fork/rewind/delete and private state separation |
| P3 | MCP Apps interoperability | Not implemented. Freeze a tested protocol profile; preserve UI metadata and result `_meta`; run an unchanged standard example plus negative fixtures |
| P4 | Inline/fullscreen/pip, accessibility and delivery | Not implemented. Verify actual packaged behavior, keyboard/theme/layout/state, lazy mounting and measured latency |

P1 is an MVP; full RIU requires P0–P4. Standard card/carousel content does not create extra protocol display modes. Full Plugin Extensions, cloud hosting, OAuth and every `window.openai` extension remain separate scope. Closing G33 must not automatically close the broader MCP gaps G24/G26.

Product decision: 2026-09-30. The detailed specification is [Reverie CLI feature additions](DEVELOPMENT_HISTORY.md#reverie-cli-feature-additions-2026-09-30); it defines the default implementation scope S01–S21, UI states, dependencies, acceptance checks, and a complete mapping from the [Codex gap analysis](DEVELOPMENT_HISTORY.md#codex-gap-analysis-2026-09-29). The [implementation prompt](DEVELOPMENT_HISTORY.md#reverie-cli-implementation-prompt-2026-09-30) is the handoff for a new coding chat.

- R1 — Input and execution control: deliver the shared desktop shell, independent structured drafts/attachments, image paste and preview, explicit queue/steer/stop, workspace result isolation, sidebar states, and accurate approval scope.
- R2 — Single-repository review and publication: deliver full Git diffs, file/hunk staging and revert, commit/ordinary push, branch preflight, line feedback/read-only review, and local artifact previews.
- R3 — Validation and long-running feedback: deliver a session-bound terminal, project actions, run records/recovery, lightweight plan/goal controls, notifications, and effective plugin/skill/connection states.
- R4 — Local parallel work: deliver managed local worktrees and independent session executors together with checkout write coordination and correctly routed events/approvals.

Each feature requires its working UI/UX and real runtime evidence before completion. Existing customizable message names, branch selection, file drops, and text drafts are the baseline to extend. Conditional items T01–T05 and deferred items X01–X08 in the specification are excluded from the default scope. In particular, no Local/Cloud selector or hosted cloud service is planned in this track. This desktop track does not change the Engine priorities below.

Implementation update, 2026-09-30: S01–S21 now have code and UI entry points across R1–R4. All stages have Windows packaged runtime evidence. Completion remains conditional for the model/authorization/native-IME checks listed in the [implementation and acceptance report](VERIFICATION_HISTORY.md#reverie-cli-implementation-report-2026-09-30); code implementation, interface delivery, passed checks and missing evidence are tracked separately there. No project commit or push was performed.

Validation update, 2026-10-01: the user authorized local submission after deeper checks. Photo preview focus/resolution, failed-card controls, queued workspace ownership, draft isolation, model capability identity, loopback transport, and sent-photo transcript previews were corrected. Final build, runtime screenshots, test results and remaining service/IME evidence are recorded in the [deep validation report](VERIFICATION_HISTORY.md#reverie-cli-deep-validation-2026-10-01). No push was requested.

User revision, 2026-10-02: remove conversation up/down, manual ordering and the sidebar status filter. Retain pins, native recent order and per-conversation states. Context usage must update during draft edits, attachments and generation, with API usage calibration and local estimates for new content. Popup clipping, error presentation and custom-provider photo input are covered by the [context and GUI validation report](VERIFICATION_HISTORY.md#reverie-cli-context-gui-validation-2026-10-02).

Further user revision, 2026-10-02: remove the Message context summary and reuse the original token counters. Review introduced regressions and correct runtime send-mode styling and error layout across window sizes. Findings and final evidence are tracked in the [token/context review](VERIFICATION_HISTORY.md#reverie-cli-token-context-review-2026-10-02).

User revision, 2026-10-03: expose the existing streaming output preference in the conversation composer and improve restrained feedback, scrolling, cancellation and narrow layouts. Packaged inspection also corrected attachment preview clipping under the existing workspace background. Implementation and packaged evidence are tracked in the [output-mode and UX validation](VERIFICATION_HISTORY.md#reverie-cli-streaming-ux-validation-2026-10-03).

User revision, 2026-10-04: install and bundle all 14 Emil Kowalski Skills, move mode selection to the composer, use top-layer menus, compact reasoning, repair Workbench directory handling and read-only file-list overhead, persist Desktop pins and tool results. Actual Windows package/theme/restart evidence is in the [UI repair report](VERIFICATION_HISTORY.md#reverie-cli-ui-repair-2026-10-04). Native non-streaming compatibility and the separately sampled JDW upstream failures are in the [compatibility report](VERIFICATION_HISTORY.md#reverie-cli-jdw-compatibility-2026-10-04).

Audit and repairs, 2026-10-05: the paths above exist; confirmed software defects and verification limits are separated in [Feature Status](FEATURE_STATUS.md). The S01–S21 implementation label must not be used to restore removed manual sorting, status filters, Message context summaries or redundant trace bars. The current guides supersede those historical UI details.

## Engine Priority 1: Rendering, Audio, and Live2D (G20)

- Add lighting, normal/ORM materials, shadows, skeletal GPU skinning, batching, post-processing, and asset streaming in measured increments.
- Add real-device audio integration tests, spatial playback, and a defined effects/bus processing contract.
- Add verified Live2D expression, motion, lip-sync, and scene-command execution; keep browser-bridge readiness distinct from native rendering readiness.
- Add resource lifetime and long-run leak tests for graphics, audio, and media backends.

Completion requires runtime evidence from actual backend devices, not dependency imports or manifest validation alone.

## Engine Priority 2: Reverie-Gamer Production Depth (G21)

- Extend deterministic vertical slices into multi-milestone playtests with progression, region transitions, save migration, and repeatable performance budgets.
- Improve generated asset review gates without presenting procedural candidates as final production art.
- Expand supported migration coverage while keeping unsupported native scripts and scene semantics visible for manual review.
- Add Galgame samples combining dialogue, generated media, save/load, and Live2D character manifests.

AAA/3A production and unrestricted 3D open worlds remain outside the supported scope until the runtime and evidence gates above are complete.

## Maintenance Rules

- Keep public engine imports consolidated under `reverie.engine`.
- Add planned product work only to this file; current guides and dated reports should link here instead of maintaining competing roadmaps.
- Remove completed items from this file in the same change that records them under the changelog's unreleased section.
- Keep capability reports conservative: `implemented`, `available`, and `production-ready` are different states.
- Update `FEATURE_STATUS.md` and the relevant guide when closing a gap; retain the dated reproduction and its verification scope.
