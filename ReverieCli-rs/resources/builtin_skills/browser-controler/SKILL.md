---
name: browser-controler
description: Control and inspect embedded browser workflows with Browser Controler. Use when Reverie needs to open pages in its bundled Chromium runtime, operate a browser like a user without touching real Edge/Chrome profiles, import user-provided cookies/storage state, open DevTools, inspect page state, diagnose frontend behavior, check server endpoints, test forms/uploads/login flows, capture dynamic page text, or verify a web app beyond static HTTP fetches.
---

# Browser Controler

Use `browser_controler` when the task needs evidence from an embedded Chromium browser session or a web/server diagnostic pass. The skill is about browser control and inspection first; any web AI page is just another site to operate when the task specifically calls for it.

## Core Loop

1. Establish the target: URL, local dev server, route, form, upload, login flow, or endpoint.
2. Collect cheap evidence first: `active_window`/`list_browser_windows` for desktop state, `diagnose_page` for HTML/status/forms/assets, `check_endpoint` for API/server behavior, `extract_page` for static content, or `devtools_targets` when a DevTools-enabled browser is already open.
3. Open the browser with `open_page` for normal visible interaction. Use `browser_session_start` or `open_debug_page` when the task needs structured DevTools evidence such as live DOM content, screenshots, Console output, JavaScript execution, element interaction, uploads, or Network responses. Browser Controler launches Reverie's bundled Chromium runtime and stores every profile, cookie, import, backup, download, page artifact, and session under the app root `.reverie/browser` directory. For non-disruptive checks, prefer `browser_session_start(background=true, minimized=true, activate=false)` and then use `devtools_*` actions while the browser stays minimized. Use `private=true` only when logged-out state or privacy mode matters inside the embedded profile.
4. Use `activate_browser` before browser-specific shortcuts when the active window is not already an embedded Browser Controler browser window.
5. Use `observe` with a grid before coordinate actions. Then apply one small action at a time: `click`, `scroll`, `paste_text`, `key_press`, `hotkey`, `upload_file`, `wait`.
6. Re-observe, use `copy_page_text`, or use `devtools_snapshot` after each meaningful step. Report what was actually observed, not what you expected.

## DevTools And Diagnostics

- Prefer `open_debug_page` plus DevTools Protocol actions for structured evidence. DevTools sessions use the embedded open-source Chromium runtime; do not use the real Edge, Chrome, Brave, or Firefox executables for automation.
- DevTools actions only attach to ports recorded by Browser Controler sessions with safe `.reverie/browser/profiles` paths. Do not connect to arbitrary external DevTools ports.
- Use `browser_session_start` for reusable background automation sessions. Use `browser_session_list`, `browser_session_close`, and `browser_session_cleanup` to avoid stale embedded browser sessions/profiles.
- Use background mode for routine inspections: `browser_session_start(url=target_url, background=true, minimized=true, activate=false)`. This keeps the browser out of the foreground and lets the user keep working in other apps.
- Use `devtools_snapshot` to read the live rendered DOM text/HTML, including client-rendered content that static fetches miss.
- Use `devtools_screenshot(full_page=true)` for background screenshots; unlike `observe`, it works while the browser is minimized.
- Use `devtools_eval(expression="...")` to run JavaScript in the selected page, equivalent to entering a command in the browser Console. Good examples: inspect `document.title`, query DOM nodes, check app globals, localStorage, route state, or run a small diagnostic expression.
- Use `devtools_console` to read Console API events, browser log entries, and runtime exceptions. Pass `expression` when you need to deliberately emit or test a Console command.
- Use `devtools_network(url=..., include_bodies=true, include_request_body=true, export_har=true)` to enable Network, navigate or reload, filter by URL/method/status, capture request/response status, payload previews, failures, optional response bodies, WebSocket frames, and a HAR-style artifact.
- Use `devtools_dom_outline`, `devtools_find`, and `devtools_accessibility_snapshot` before interacting. Prefer selectors, roles, names, or visible text over coordinates.
- Use `devtools_click(selector=...)`, `devtools_type(selector=..., text=...)`, `devtools_upload(selector=..., file_path=...)`, and `devtools_wait_for(...)` for background page interaction.
- Background/minimized mode is for CDP actions. Do not use minimized windows for coordinate `click`, `scroll`, `observe`, file dialogs, or keyboard-driven UI automation; activate a visible browser window first when those are required.
- Use `open_devtools` when the user specifically wants the visual DevTools panel opened. For logs/responses, still prefer `devtools_console` and `devtools_network` because they return structured evidence.
- Use `diagnose_page(check_assets=true)` to find HTTP status, missing title/content, form structure, and broken scripts/styles/images.
- Use `check_endpoint(method="GET"|"POST"|...)` for server/API routes, health checks, auth callbacks, upload endpoints, and form actions.
- Prefer local command-line tests for code-level verification, then use Browser Controler for the final in-browser proof.

## Practical Patterns

- Background page smoke test: `browser_session_start(background=true, minimized=true, activate=false)`, then `devtools_snapshot`, `devtools_screenshot`, `devtools_console`, and `devtools_network`.
- Visible page smoke test: `diagnose_page`, `open_page`, `observe`, interact with the main path, `copy_page_text` or screenshot evidence.
- UI bug investigation: reproduce in a background debug browser when CDP evidence is enough; use visible interaction only for layout, pointer, upload, or focus behavior that truly needs the foreground.
- Form flow: `devtools_find` or `devtools_dom_outline`, then `devtools_type`, `devtools_click`, `devtools_wait_for`, and `devtools_network` to verify server behavior.
- Server feature check: identify endpoint or form action, call `check_endpoint`, compare response with UI behavior, then test through the browser.
- Upload flow: click the upload control, call `upload_file` for a workspace file, wait, observe the resulting UI state.
- Dynamic app content: use `devtools_snapshot` or `copy_page_text` after rendering or interaction because static `extract_page` may miss client-rendered state.
- Console command check: `open_debug_page(url=..., background=true, minimized=true, activate=false)`, then `devtools_eval(expression="document.body.innerText")` or `devtools_console(expression="console.log('probe', location.href)")`.
- Network response check: `open_debug_page(url="about:blank", background=true, minimized=true, activate=false)`, then `devtools_network(url=target_url, include_bodies=true)` and verify the relevant response status/body.
- Web AI engineering help: when explicitly useful, operate a web AI service as a browser page to ask for code ideas, OCR, or debugging suggestions, then verify any advice against the local codebase and tests before applying it.

## Embedded Profile Data

- Use `/browser runtime` or `browser_runtime_status` to inspect the embedded Chromium runtime and the `.reverie/browser` roots.
- Use `/browser status [profile]` to inspect an embedded profile. The default profile is `default`.
- Use `/browser import` or call `browser_profile_import` without `file_path` to open the transient arrow-key/Enter export-file picker. The user then chooses `Allow once`, `Always allow selected imports`, or `Cancel`; completed imports collapse to one log line.
- Use `/browser import <storage-state.json|cookies.txt> [profile]` or `browser_profile_import(file_path=...)` only for explicit workspace export paths. All accepted files are copied and normalized into `.reverie/browser/imports/<profile>`. This supports Playwright-style storage state JSON, cookie JSON arrays, and Netscape `cookies.txt`.
- Use `/browser backup [profile]`, `/browser backups [profile]`, and `/browser restore <profile> <backup_id> confirm` for embedded profile backups under `.reverie/browser/backups`.
- Imported credentials/cookies are copies selected or supplied by the user. The picker may list export-like files in the workspace, Desktop, Documents, and Downloads, but Browser Controler must not read browser databases or scan profile data from `%LOCALAPPDATA%`, `%APPDATA%`, Edge, Chrome, Brave, Firefox, or any real browser profile.

## Guardrails

- Do not treat Browser Controler as a replacement for reading the codebase. Use it to verify runtime behavior.
- Do not claim a UI state, console error, network result, or endpoint behavior unless `observe`, `copy_page_text`, `devtools_snapshot`, `devtools_eval`, `devtools_console`, `devtools_network`, `diagnose_page`, or `check_endpoint` produced evidence.
- Call `safety_policy` when unsure about credentials, imported cookies/storage state, uploads, external web AI services, or potentially destructive page actions.
- Do not control the user's existing logged-in browser. Use only Browser Controler windows launched from the embedded Chromium runtime.
- Do not use or back up a user's real Chrome/Edge/Firefox/Brave profile. If a custom profile is needed, use a relative embedded `profile` name so it is created under `.reverie/browser/profiles`.
- Upload only files inside the workspace or files the user explicitly provided.
- Avoid entering credentials unless the user explicitly asks and provides them in the current context.
- Keep external web AI/OCR use as an optional fallback for tasks that specifically require it; browser control and diagnostics are the default purpose.
