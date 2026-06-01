---
name: browser-controler
description: Control and inspect real browser workflows with Browser Controler. Use when Reverie needs to open pages, operate a browser like a user, use private windows, open DevTools, inspect page state, diagnose frontend behavior, check server endpoints, test forms/uploads/login flows, capture dynamic page text, or verify a web app beyond static HTTP fetches.
---

# Browser Controler

Use `browser_controler` when the task needs evidence from a real browser session or a web/server diagnostic pass. The skill is about browser control and inspection first; any web AI page is just another site to operate when the task specifically calls for it.

## Core Loop

1. Establish the target: URL, local dev server, route, form, upload, login flow, or endpoint.
2. Collect cheap evidence first: `active_window`/`list_browser_windows` for desktop state, `diagnose_page` for HTML/status/forms/assets, `check_endpoint` for API/server behavior, or `extract_page` for static content.
3. Open the browser with `open_page`; use `private=true` only when isolation, logged-out state, or privacy mode matters.
4. Use `activate_browser` before browser-specific shortcuts when the active window is not already a browser.
5. Use `observe` with a grid before coordinate actions. Then apply one small action at a time: `click`, `scroll`, `paste_text`, `key_press`, `hotkey`, `upload_file`, `wait`.
6. Re-observe or use `copy_page_text` after each meaningful step. Report what was actually observed, not what you expected.

## DevTools And Diagnostics

- Use `open_devtools` when visual browser evidence is not enough and the user asks for browser/developer inspection.
- Use DevTools manually through browser controls: focus panels, search console/network text, copy visible errors, and re-observe.
- Use `diagnose_page(check_assets=true)` to find HTTP status, missing title/content, form structure, and broken scripts/styles/images.
- Use `check_endpoint(method="GET"|"POST"|...)` for server/API routes, health checks, auth callbacks, upload endpoints, and form actions.
- Prefer local command-line tests for code-level verification, then use Browser Controler for the final in-browser proof.

## Practical Patterns

- Page smoke test: `diagnose_page`, `open_page`, `observe`, interact with the main path, `copy_page_text` or screenshot evidence.
- UI bug investigation: reproduce in browser, open DevTools, copy console/network clues, inspect related source files, patch, rebuild, retest.
- Server feature check: identify endpoint or form action, call `check_endpoint`, compare response with UI behavior, then test through the browser.
- Upload flow: click the upload control, call `upload_file` for a workspace file, wait, observe the resulting UI state.
- Dynamic app content: use `copy_page_text` after rendering or interaction because static `extract_page` may miss client-rendered state.
- Web AI engineering help: when explicitly useful, operate a web AI service as a browser page to ask for code ideas, OCR, or debugging suggestions, then verify any advice against the local codebase and tests before applying it.

## Guardrails

- Do not treat Browser Controler as a replacement for reading the codebase. Use it to verify runtime behavior.
- Do not claim a UI state, console error, network result, or endpoint behavior unless `observe`, `copy_page_text`, `diagnose_page`, or `check_endpoint` produced evidence.
- Upload only files inside the workspace or files the user explicitly provided.
- Avoid entering credentials unless the user explicitly asks and provides them in the current context.
- Keep external web AI/OCR use as an optional fallback for tasks that specifically require it; browser control and diagnostics are the default purpose.
