# Reverie Desktop

Reverie Desktop is the Electron GUI for the existing Reverie CLI. It does not reimplement providers or tools in JavaScript: the desktop process starts the platform-native compiled kernel with `--sdk-bridge` and communicates with it over a versioned JSONL protocol.

Current stable version: `v2.5.0` (released 2026-07-17).

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

For complete local builds, use `build.bat` on Windows or `build.sh` on Linux. They build and sanity-check the core first, install locked desktop dependencies, build the GUI packages, and verify the expected filenames.

The rolling `latest` GitHub Release is rebuilt from every `main` push and is marked as a prerelease. Its downloads are grouped Windows → Linux → macOS Apple Silicon → macOS Intel, and its four platform kernel records are consolidated into `reverie-kernels.json`.

Every package contains a fast-starting PyInstaller directory kernel. The build also records the SHA-256 of the separately released one-file core inside the ASAR-integrity-protected application package. A portable sibling `reverie.exe`/`reverie` is used only when that protected hash is trusted and its `reverie.kernel.v1` handshake matches; otherwise the desktop logs the reason and uses its internal kernel. The terminal contract is:

- `reverie`: TUI/core in the current directory.
- `reverieui`: GUI in the current directory.
- `Reverie-Portable-*.exe --tui`: explicit portable convenience route to the bundled TUI; no double-click heuristic is used.

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

The conversation display can independently show or hide model reasoning records, tool calls, tool results, expanded reasoning and result bodies, and live run activity. **Clean chat**, **Calls first**, **Results first**, and **Full trace** presets are available under **Settings → Conversation display**. Sessions that contain technical history also expose the same reasoning/call/result controls directly above the transcript, together with the number of persisted records.

The Tools page reads the live flattened catalog from the CLI core, including descriptions, categories, aliases, supported modes, required arguments, MCP tools, and runtime-plugin tools.

The desktop appearance supports **Follow system**, **Dark**, and **Light** themes, five accent palettes, three reading scales, configurable answer width, three bundled Reverie backgrounds, and optional imported workspace backgrounds with strength, blur, and dimming controls. A selected image is the full application base behind the sidebar, toolbar, conversation, and inspector; those surfaces become translucent glass instead of replacing the photo with a solid theme color. Imported images are copied into `.reverie/desktop/backgrounds` so the original file can move or be deleted safely. Preferences are stored in `.reverie/desktop/desktop-settings.json`, update the native Windows title bar together with the renderer, and can be changed from either the top toolbar or **Settings → Appearance**.

In the composer, the two file controls have distinct roles:

- `@` asks Context Engine for the most likely workspace files and symbols using the current draft, recent conversation, semantic index, Git state, and file recency.
- The paperclip opens the native file chooser for any file, copies it to `<project>/.reverie/attachments`, and inserts a removable attachment reference into the draft.

Project changes reuse the existing `reverie.exe --sdk-bridge` child process. Only workspace-scoped Python services are replaced, avoiding a visible kernel disconnect/reconnect cycle.

The renderer has no Node.js access. It reaches the core only through the small, context-isolated preload API in `electron/preload.ts`.
