# Reverie CLI Roadmap

2026-10-31: 2.5.3 integrates Cloud RIU and Liquid Glass, fixes light-theme opaque accessibility materials, and shows user avatars without message names. The user authorized main publication. See [2.5.3 verification](verification/2026-10-31-v2.5.3/README.md) for current checks and remaining model/platform acceptance limits.


2026-10-30：本地 Liquid Glass 与云端 dev `894fe6e` 已整合，保留经典界面和 RIU 富格式路线。Windows 联合目录包与本轮回归证据见[本地整合记录](verification/2026-10-30-desktop-integration/README.md)。此记录不关闭历史模型质量及跨平台安装验收缺口。

2026-10-28 GitHub 接续更新：用户已明确授权将本轮全部仓库改动提交到新的 `dev` 分支；本轮授权覆盖此前禁止提交/推送的限制，不含版本升级或 Release。[接续说明](CONTINUE_RIU.md)与[可克隆 goal/关键证据](verification/2026-10-28-dev-handoff/README.md)已补齐。**最新源码还包含保留 v12 之后的 Linux 安装链接启动器修复；它的回归测试已有覆盖，但包含此修复的新安装包尚未验收，优先完成此项。** 此前 v12 通过记录仅对应原包；整体 RIU 仍未完成。实际提交 SHA 与远端推送结果以交付消息及 GitHub 分支为准。

2026-10-27 最新补充：当前源码 v12 Linux x64 build `fcce0356b0365178` 的 AppImage 在真实 FUSE 挂载下通过富格式86/86、P2 24/24；提取程序 P3/P4/隔离26/31/36通过；P4另以60次合成循环完成31/31，注册交互/输入 P95 为286.16/47ms。当前源码本地 Qwen3.5-4B 合成应用请求精确显示四项指标、两行表格、带徽标/来源/链接的推荐卡，并通过深浅主题×1280/460px布局。Deb 使用 rootless Bubblewrap 隔离根和当前 Debian 13 依赖数据库，未用 `--force-depends` 完成 v11 安装、v12 升级与卸载，宿主机状态未变化；另有只读 APT 依赖模拟通过。仓库打包脚本的干净重试对deb/AppImage均exit0，原始exit1仍留档。正式模型质量样本仍为0，跨平台和设备验收未关闭；隔离生命周期不等于宿主系统安装或桌面启动。见[实施清单](RIU_COMPLETION_PLAN.md)、[结构化包与原生证据](verification/2026-10-27-static-rich-routing/package-rebuilds.json)。

当前完整 RIU 尚未验收达标。最新源码 Linux x64 的确定性 UI、交互生命周期、隔离及本地包检查已有证据；第二正式组60个位置中59份完成评测、1份中断，原始自动31项合格但4项被人工复核否定，其余27项也不等于完整人工验收。模型质量、Windows/macOS实际系统、物理输入与辅助技术、长时稳定性仍未验收。见[实施清单](RIU_COMPLETION_PLAN.md)与[当前原生证据](verification/2026-10-27-static-rich-routing/package-rebuilds.json)。



上一阶段（2026-10-25）：已按用户参考图实现**回答 UI/UX 与格式样式**：统计卡片、状态表格、图文推荐、来源与链接，支持深浅主题、窄容器、流式输出和会话重开。[格式说明](RICH_ANSWER_UI.md)与[实际原生截图和验证](verification/2026-10-25-rich-answer-ui/README.md)已记录。当时 Linux 包 **c9df6ba5417e0851**；Desktop **407/1**、Python **2314/24**、类型检查通过，最终包原生 P2/P3/隔离 **24/26/36** 通过。真实模型回答及两张远程图片实际显示成功，完整 27 工具和采样设置保留。旧正式矩阵依最新优先级停在 15 项，不宣称完成 36 项或整体模型质量验收。

This is the single source of truth for planned product work. Current behavior belongs in the relevant guide; completed work belongs in the changelog.

2026-10-27 RIU status: the screenshot-driven rich-answer UI is implemented and verified in the current-source Linux x64 package candidate, build `fcce0356b0365178`. On the retained AppImage, actual FUSE-mounted rich UI passed **86/86** and P2 **24/24**; the extracted packaged desktop passed P3 **26/26**, P4 **31/31**, and isolation **36/36**. A supplementary 60-cycle synthetic P4 stress run also passed **31/31** (registration P95 286.16ms; local input P95 47ms). The current-source Qwen3.5-4B in-app synthetic smoke matched all four metrics, two table rows, and the numbered recommendation card with badge/source/link; dark/light × 1280/460 containment passed with zero browser errors. The deb passed an isolated Bubblewrap v11→v12 install/upgrade/removal lifecycle against the current Debian 13 dependency inventory, without forced dependency checks or host writes. This does not verify installation into the host package database or launching the installed desktop. The repository package-validation wrapper later returned 0 for fresh deb and AppImage targets using the verified v12 prepackaged payload; initial exit-1 evidence remains preserved. Formal model quality is still 0 accepted samples, and the two-cohort cap bars another formal cohort. Windows/macOS real-host, physical accessibility, and long-duration evidence remain open. See [RIU completion plan](RIU_COMPLETION_PLAN.md), [package and native evidence](verification/2026-10-27-static-rich-routing/package-rebuilds.json), and [goal](../.runtime/riu-completion-20261021/goal.json).

RIU roadmap status last reconciled against the current-source v12 Linux x64 evidence: **2026-10-27**. The broader [Feature Status](FEATURE_STATUS.md) matrix retains its 2026-10-05 audit baseline and separately dated follow-up checks; those dates do not supersede the RIU status above. See the [verification history](VERIFICATION_HISTORY.md) for dated evidence. A gap recorded here is not authorization to implement all optional product extensions.

## Current Baseline

2026-10-08 documentation update: historical reports and specifications are consolidated in [Verification History](VERIFICATION_HISTORY.md) and [Development History](DEVELOPMENT_HISTORY.md). The new [Intelligent UI specification](INTELLIGENT_UI_SPEC.md) is a proposal based on current source inspection, not a completed implementation or a new full regression run.

Reverie CLI provides a multi-provider coding agent, Context Engine retrieval and memory, sessions and rollback, scoped managed SubAgents, explicit handoff and recovery surfaces, desktop control, Writer workflows, runtime plugins, cross-platform CI, and packaged SDK bridge verification.

The CLI's built-in Python Reverie Engine runtime supports deterministic headless gameplay execution, scene and component data, physics queries, navigation, input, animation, UI state, localization, save data, telemetry, video export, and a ModernGL renderer with reusable mesh resources, basic textures, blending, framebuffer readback and PNG capture. Native window presentation, input, resize and close now have Windows runtime evidence. G19–G21 concern this runtime/Gamer surface, not the external Engine editor registered as a RATS provider.

## Product Completion Priorities

### P1: Real model compatibility

2026-10-23 继续执行两模型 **30 个完整生成通过 + 6 个文本对照** 的质量门。Python 全量 **2214/24**、验证器 **114**、六组重点检查 **244**；Desktop **387/1**、类型、文档和 diff 检查通过，源码哈希一致。Linux **3824bc06ee6c6e24** 完成源码核对和消费者检查；P4 两次输入超限、释放闲置旧包缓存后的第三轮通过均保留，不宣称稳定性或根因已解决。GPT-OSS native6 完整开发为生成 **0/5**、文本 **1/1**，实际页面复核失败保留；当前先做同模型构建对照，再冻结两个 Qwen 模型执行完整正式矩阵，见[当前进展](verification/2026-10-21-riu-completion/progress.md)。

2026-10-20–21 Cloud：基于 `350c5ba` 完成匿名 Chat、冷却等待、未完成工具参数/空调用 ID 和 OpenCode 新目录路由修复；Linux 冻结包、P2/P3/P4 及隔离已验证。OpenCode 服务端拒绝 Reverie 的真实匿名身份；Pollinations Classic 实测模型为 GPT-OSS 20B。最终五类自然任务各三次独立 profile 完成，生成质量 0/15，文本对照 3/3；正常修改与重启恢复的质量门仍未通过。官方 MiniCPM5-2B Gradio/SSE 接口已匿名调用成功，但不暴露 tools，未计为第二个工具闭环模型。不同来源、构建与负载的延迟不得合并成改善率。见 [本轮证据](VERIFICATION_HISTORY.md#riu-cloud-runtime-2026-10-20)与[免费接口核对](verification/2026-10-20-riu-cloud/free-api-search.md)。

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

### Intelligent UI — G33, implementation and remaining scope

RIU status reconciled on **2026-10-17**; this does not re-date the broader product audit.

Implement the public experience described in [INTELLIGENT_UI_SPEC](INTELLIGENT_UI_SPEC.md): model-generated interactive views and a declared MCP Apps compatibility profile. P0–P2 provide the local generated-view host, durable artifacts, worker-owned approvals, private state and no-replay receipts. P3 adds the pinned offline MCP Apps profile and unchanged official-component interoperability. P4 is implemented and locally verified on Windows (2026-10-17). The prompt/runtime follow-up repairs actual mode/tool mismatches and evaluates real model output separately from host correctness. See the specification's protocol matrix and [current follow-up](VERIFICATION_HISTORY.md#riu-prompt-quality-2026-10-17) for exact regression, model and package evidence.

| Order | Deliverable | Current state / completion gate |
| --- | --- | --- |
| P0 | Isolated renderer and trusted bridge prototype | Verified on Windows 2026-10-11 (packaged Electron 41.2.1, isolation probe 34/34). `reverie-view:` + sandboxed iframe (opaque origin) selected from measured evidence; navigation/IPC/network/permission/traversal restrictions proven and the host stayed responsive through an infinite sync loop and message flood with the view torn down. Linux/macOS NOT verified. See [VERIFICATION_HISTORY](VERIFICATION_HISTORY.md#riu-p0-isolation-2026-10-11) and [probe report](verification/2026-10-11-riu-p0-isolation.json) |
| P1 | `render_view`, durable artifacts, timeline, restart and TUI fallback | Verified on Windows 2026-10-11 (packaged Electron 41.2.1, build `03c991ccd69a9a3c`). Full tool→store→host-dereference→restart/fork/rewind/delete→TUI chain proven by Python e2e on the two mandated fixtures and the renderer rebuild pipeline test; identity kernel-bound, persist-before-display, forged model text cannot mint a view, resolved reference is an opaque `reverie-view:` allow-list with no filesystem path. HTML/`<script>` markers absent from tool results, events, parsed rows, resolved refs and restored history — zero-token HTML NOT claimed, only no re-addition to model requests. RIU focused Python 41/1, renderer pipeline 6; regressions npm test 342/1, typecheck PASS, full Python 1912/2 (one unrelated timing flake, isolated rerun passes); packaged isolation probe re-run 34/34. Linux/macOS and live packaged model-driven view generation NOT verified. See [VERIFICATION_HISTORY](VERIFICATION_HISTORY.md#riu-p1-pipeline-2026-10-11) and [probe report](verification/2026-10-11-riu-p1-pipeline.json) |
| P2 | User actions, approval routing and session state | Implemented and verified locally on Windows 2026-10-15: production packaged Electron + loopback model, 24/24 interaction checks; existing worker/coordinator/security_policy/permission_review approval chain, Stop, busy, duplicate/stale/cross-session rejection, crash/unknown write no-replay, private state recovery and fork/rewind/delete. Standard method subset is pinned to ext-apps v1.2.0 / 2026-01-26; MCP server callbacks remain fail-closed for P3. Full Python 1941/2, Desktop 363/1; typecheck/build and packaged isolation 34/34 passed. No external model, non-Windows or installer acceptance claimed. See [VERIFICATION_HISTORY](VERIFICATION_HISTORY.md#riu-p2-interactions-2026-10-15) and [evidence](verification/2026-10-15-riu-p2.json) |
| P3 | MCP Apps interoperability | Implemented: ext-apps 2.0.3 / UI 2026-01-26; tool visibility, UI resource identity/MIME/offline CSP, private result metadata, standard initialization/input/result/call/message/model-context/teardown, unchanged official vanilla example and hostile fixtures. Windows package evidence and measured regressions: [P3 verification](VERIFICATION_HISTORY.md#riu-p3-interop-2026-10-16). Network permissions, broad host extensions and persistent connection ownership are outside this profile; expired callbacks fail closed |
| P4 | Inline/fullscreen/pip, accessibility and delivery | Windows host implemented: stable iframe state, live host context, keyboard/focus, reduced motion, narrow layout, 100-view lazy history and measured local latency. Historical build `6198938667318762`: 28/28 checks and a recorded Writer regression. Prompt/runtime repairs, larger controls, expandable summaries and current package/regression results are tracked in the [follow-up](VERIFICATION_HISTORY.md#riu-prompt-quality-2026-10-17); no release/version bump |
| Quality gate | Real model authoring and visual usability | Mode-accurate prompts, runtime identity/configuration, offline host integration and advisory authoring feedback are implemented. A real Step 5 authored comparator passes arithmetic, controls, three modes, theme and private-state checks after packaged continuation; GPT OSS 20B discovers the official app and completes a host-approved callback. Generation and continuation provenance is recorded. Visible-reasoning recitation, weaker-model sandbox API errors and cross-template visual quality remain open; registration or keywords do not establish OpenAI parity |
| Visual QA | Host controls and generated content | Host buttons and long summaries have targeted polish. Continue reviewing hierarchy, user-facing copy, spacing, contrast, empty/error states and density in inline/workbench/pip with real generated content; theme switching alone is not visual acceptance. Cross-template visual quality remains open |

The 2026-10-18 continuation adds a fixed [task corpus](../scripts/verification/fixtures/riu-quality-tasks.json) and [packaged real-model runner](../scripts/verification/riu_quality_benchmark.py). The remaining quality gate requires two available configured models, three independent fresh sessions per calculator/table/chart/form/comparison combination (30 generation attempts), separate text controls, semantic interaction and natural-language revision checks, unchanged-instance display moves, theme and restart recovery, and manual visual review. Preserve all failed and repaired attempts and compare actual full request sizes and timing boundaries. Prompt deduplication and passing host regressions alone do not close this gate.

2026-10-20 shutdown handoff: the [natural-language corpus](../scripts/verification/fixtures/riu-natural-tasks.json), version 2026-10-20.2, tests automatic format selection without asking for HTML. The old NVIDIA run stopped at 10/36 samples on user source steering. Local SenseNova baselines were generation-only and remain registered/unvalidated. Cloud should extend the runner for legitimate OpenCode anonymous/free models, refresh live availability and protocol metadata, and fix observed source client errors without impersonation or bypassing denials. The latest Harness/Markdown changes still need rebuilding; the Python full-suite paste-input failure passes alone but remains unresolved. See the [complete continuation prompt](CLOUD_CODEX_RIU_HANDOFF.md).

P1/P2 provide the local generated-view MVP; P3 adds a declared offline interoperability profile; P4 completes the implemented local display experience. Overall acceptance also requires current regressions and model-quality evidence, while retaining explicit unverified platform/service limits. Standard card/carousel content does not create extra protocol display modes. Full Plugin Extensions, cloud hosting, OAuth and every `window.openai` extension remain separate scope. Closing G33 must not automatically close the broader MCP gaps G24/G26.

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
