# Reverie Desktop

Reverie Desktop is the Electron GUI for the existing Reverie CLI. It does not reimplement providers or tools in JavaScript: the desktop process starts the platform-native compiled kernel with `--sdk-bridge` and communicates with it over a versioned JSONL protocol.

Current stable version: `v2.5.0` (released 2026-07-17).

The current user flow is documented in the [Desktop guide](../docs/DESKTOP_GUIDE.md). The [2026-10-05 feature status](../docs/FEATURE_STATUS.md) and [audit](../docs/VERIFICATION_HISTORY.md#reverie-cli-feature-audit-2026-10-05) supersede outdated completeness claims below; implementation and acceptance remain separate.

The 2026-09-30 desktop workflow has an [S01–S21 implementation and acceptance report](../docs/VERIFICATION_HISTORY.md#reverie-cli-implementation-report-2026-09-30) with packaged evidence and remaining model, authorization and native-IME checks. Dated reports describe their own build/worktree state; current uncommitted changes and published releases must be assessed separately.

The [2026-10-06 Workbench repair](../docs/VERIFICATION_HISTORY.md#reverie-cli-workbench-repairs-2026-10-06) combines the inspector and Workbench into one resizable panel, adds a lazy file tree and guarded UTF-8 editor, and exposes persisted display presets directly in the conversation header. Unchanged recovery snapshots reuse Git objects. The report distinguishes local preparation time from provider response time.

The [2026-10-10 memory update](../docs/VERIFICATION_HISTORY.md#desktop-memory-2026-10-10) removes idle-startup worker preparation and postpones automatic indexing until use. One completed worker can be reused for 30 seconds, then is released; up to four active runs remain isolated. Desktop's internal `ui-onedir` kernel is separate from the public one-file CLI/TUI download, which runs without Electron or a companion runtime directory. See the [CLI/TUI/GUI relationship](../README.md#cli-tui-and-desktop-gui).

The composer supports structured attachment drafts, image clipboard input, file references, Queue/Steer/Stop and a goal summary. The Workbench contains full Git scopes, guarded file/hunk operations, whole-index commit, reviewed ordinary push, read-only review, local previews (including locally rendered PDF pages), session-owned real PTYs, explicit project actions, durable run records, notifications and effective capabilities. Managed local worktrees use detached HEAD and recoverable byte-preserving archive/restore. Independent cores coordinate writers with identical project roots; parent/child roots in the same checkout remain a known gap. Saved idle goals are not yet reliably supplied to the next model run. No Local/Cloud selector is added.

Project initialization commands run only after explicit action confirmation. Closing the app with active runs or terminals explains which processes will end. A prior incomplete run is shown for review and never automatically replays unknown writes. Worktree archive defaults to preserving ignored files; inspect every choice before removal.

## Development

Requirements:

- A current `../dist/reverie.exe`, built from `../ReverieCli-py`
- Node.js and npm

```powershell
npm install
npm run typecheck
npm run start
```

Create an unpacked application or platform package:

```powershell
npm run pack
npm run dist:win
# Linux x64: AppImage + deb
npm run dist:linux
# macOS host architecture: DMG
npm run dist:mac
```

For complete local builds, use `build.bat` on Windows or `build.sh` on Linux. They build and sanity-check the core first, install locked desktop dependencies, build the GUI packages, and verify the expected filenames. If a user-level npm proxy is configured but unavailable, dependency installation automatically retries without the user-level `.npmrc`. Electron and electron-builder tool archives use checksum-verified mirrors by default; set `ELECTRON_MIRROR` or `ELECTRON_BUILDER_BINARIES_MIRROR` before invoking the script to override them. Automated Windows builds can pass `--no-pause`.

The rolling `latest` GitHub Release is rebuilt from every `main` push and is marked as a prerelease. Its downloads are grouped Windows → Linux → macOS Apple Silicon → macOS Intel, and its four platform kernel records are consolidated into `reverie-kernels.json`.

Every desktop package contains a fast-starting PyInstaller directory kernel, which both the GUI and terminal startup routes use directly so portable startup never hashes, probes, and unpacks the one-file core first. The installer and portable EXE remain unified products: choose the default startup interface under **Settings → General → Default startup mode**, or override it for one launch with `--gui` or `--tui`. The build also records the SHA-256 of the separately released one-file core inside the ASAR-integrity-protected application package. The terminal contract is:

- `reverie`: TUI/core in the current directory.
- `reverieui`: the configured desktop interface in the current directory.
- `Reverie-Portable-*.exe --gui`: open the GUI regardless of the saved default.
- `Reverie-Portable-*.exe --tui`: open the bundled TUI regardless of the saved default.

The embedded CLI supports one-shot commands such as:

```powershell
reverie -P "Explain this project" -source codex -model gpt-5.6-sol -reasoning high
```

## Local data boundaries

Development state and Chromium caches stay under `ReverieCli-ui/.runtime`. A packaged build stores configuration and history in `.reverie` beside the original portable executable; Electron-only caches and logs stay under `.reverie/desktop`. The custom portable wrapper keeps its verified application cache in `.reverie/desktop/app-runtime` beside the portable executable and reuses it on later launches, so it does not unpack hundreds of megabytes into the system drive on every start. `REVERIE_APP_ROOT` always points the CLI core back to the original executable directory.

The final repository build therefore shares `../dist/.reverie` with the standalone `../dist/reverie.exe`. The active root can be inspected or changed under **Settings → General → CLI data and history**; Reverie always creates the actual configuration folder as `.reverie` below that root.

Conversation history is workspace-scoped. Recent workspaces are shown as project groups, with the active project's sessions nested below it. The desktop UI restores the last active session, keeps unsent drafts per session, and exposes rename, archive, unarchive, fork, rewind, delete, and full-history search actions. Rename and delete are backed directly by the CLI session manager; archive state is a non-destructive desktop preference.

The button beside the Reverie mark at the top of the project/session sidebar hides it and expands the agent workspace. While hidden, a restore button remains in the main toolbar. The layout choice is kept locally across application restarts.

The complete desktop interface supports Simplified Chinese and English. **Settings → General → Interface language** switches the renderer and native file-picker titles immediately, and the choice is persisted with the other desktop preferences.

Every project row also has a management menu. **Delete project and records** removes the project from the recent list and deletes its Reverie sessions, transcripts, memory, checkpoints, Context Engine cache, security/audit data, and imported attachments. It never deletes ordinary project files, workspace configuration, or project rules. Deleting the active project first selects a valid fallback workspace.

The conversation display can independently show or hide model reasoning records, tool calls, tool results, expanded reasoning and result bodies, and live run activity. **Clean chat**, **Calls first**, **Results first**, and **Full trace** presets are available under **Settings → Conversation display**. Reasoning is a compact expandable summary with hover/focus feedback. The redundant transcript-wide record counter and trace toolbar have been removed.

The Tools page reads the live flattened catalog from the CLI core, including descriptions, categories, aliases, supported modes, required arguments, MCP tools, runtime-plugin tools, and progressively loaded RATS tools.

The RATS page registers executable-local providers, supports explicit custom provider definitions, and verifies a live RTP identity before enabling tools. Engine remains the sole built-in official provider. Settings persist provider identity/path/permission data; the Python core exclusively owns control/session tokens and native RTP calls. The page shows a compact catalog and retrieves definitions on demand. Registration or configuration is not proof of authorization; third-party package download/install is not part of this surface.

The desktop appearance supports **Follow system**, **Dark**, and **Light** themes, five accent palettes, three reading scales, configurable answer width, three bundled Reverie backgrounds, and optional imported workspace backgrounds with strength, blur, and dimming controls. A selected image is the full application base behind the sidebar, toolbar, conversation, and inspector; those surfaces become translucent glass instead of replacing the photo with a solid theme color. Imported images are copied into `.reverie/desktop/backgrounds` so the original file can move or be deleted safely. Preferences are stored in `.reverie/desktop/desktop-settings.json`, update the native Windows title bar together with the renderer, and can be changed from either the top toolbar or **Settings → Appearance**.

In the composer, the two file controls have distinct roles:

- `@` asks Context Engine for the most likely workspace files and symbols using the current draft, recent conversation, semantic index, Git state, and file recency.
- The paperclip opens the native file chooser and adds ordered attachment cards. Workspace files retain references; external files and clipboard images get fixed copies in `<project>/.reverie/attachments`. Cards show the source version, preview, reorder, remove, and retry controls.
- Dropping up to 20 local files uses the same structured attachment path. The input surface shows the drop target; native image paste and photo-only messages are supported when the selected model accepts images. Unsent text and attachments persist together per conversation, including failed sends. Sent local images retain preview buttons in the transcript.

**Settings → Conversation display → User display name** changes the name shown above user messages, including existing conversation history. Empty restores the default label. For Git workspaces, a branch control at the bottom of the conversation lists local and fetched remote-only branches, shows the current branch and uncommitted file count, and can switch or create a branch. Branch switching is unavailable while a session is running, and Git itself decides whether working-tree changes permit a switch.

Project changes reuse the existing `reverie.exe --sdk-bridge` child process. Only workspace-scoped Python services are replaced, avoiding a visible kernel disconnect/reconnect cycle.

That child is the management bridge. Task execution uses separate session-owned cores, with at most four active slots. Mode selection is at the lower left of the composer, `@` and `/` use top-layer candidate menus, and `/skill` pins a mandatory prompt workflow. The `/` catalog includes reference-only terminal commands; see the Desktop guide before assuming every listed command is locally executable.

The renderer has no Node.js access. It reaches the core only through the small, context-isolated preload API in `electron/preload.ts`.
