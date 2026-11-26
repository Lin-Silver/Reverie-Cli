# Rust MCP / Connector control surfaces

This increment adds an independent Connectors page, its state controller, and a terminal module. It does not claim complete Reverie CLI 3.0.0 delivery or acceptance. Root owns the App/navigation/i18n mount, generated protocol, native host, coordinated build, staging and publication.

## Files and integration

- `ReverieCli-ui/src/ConnectorsView.tsx`, `connector-state.ts`, `connectors.css`, and `ConnectorsView.test.tsx`.
- `ReverieCli-rs/crates/cli/src/terminal/connectors.rs`, with Connector routing, secret masking and cancellation integration in `terminal/mod.rs` and `terminal/screen.rs`.
- `scripts/verification/rust-connector-fixture.mjs`, `rust-connectors-tui-smoke.mjs`, `rust-connectors-electron-smoke.mjs`, and `rust-connectors-electron-probe.cjs`.

Mount `useConnectors(view === 'connectors', projectRoot)` once in App, alongside the existing extension controllers, so navigation keeps the pending operation and public authorization state. Render `<ConnectorsView controller={connectors} onOpenPlugin={...} />`. The plugin callback receives the plugin ID with the `plugin:` origin prefix removed; it should select the existing Plugins page/record.

The controller deliberately keeps only the name, filter and selected service ID as drafts. It never publishes a Connector authorization URL, password, client secret, registration token or complete MCP configuration into App snapshots. Configuration and prompt JSON are temporary uncontrolled textareas. Secret controls are uncontrolled password inputs; sending clears them before awaiting the request, and unmounting discards them.

Manual configuration saves are explicitly complete replacements and save without trust. Trust is approved separately against the exact inspected fingerprint and revision. Enable state is independent. Plugin MCP delegates its controls to Plugins. Disabled/out-of-mode valid servers remain visible; malformed entries remain visible in diagnostics.

OAuth discovery is distinct from authorization: issuer, resource, scopes, supported client authentication, preregistration/dynamic registration and callback are reviewed before `confirmed:true`. Only the immediate returned authorization URL is passed to the external launcher. Public pending IDs/status survive page navigation, and completion is a cancellable background operation. Remote revocation and local credential clearing are separate actions, including clearing an orphaned or changed target.

API Key submission binds `expected_fingerprint` to the reviewed server. A changed target is rejected by the native host; a failed submission does not preserve its secret in the page. Runtime/authorization diagnostics remain separate from configuration diagnostics, so a later status reload cannot hide a service excluded for a credential failure.

## Terminal integration checklist

All nine integration items below are implemented and frozen for root's coordinated build. The shared terminal edits preserve the pre-existing Markets/Plugins routing. Runtime results remain pending.

1. Register `mod connectors` and a `ConnectorUiState` field initialized with `Default::default()`.
2. Add the `ConnectorChoice`, `ConnectorInput`, `ConnectorSecret`, and `ConnectorConfirmation` panel kinds and route their submission to `submit_connector_panel`.
3. Route `/mcp` and `/connectors`/`/connector`; add their help entries.
4. Render `connectors::masked_input` for secret panels before calculating rows, wrapping and cursor position.
5. Typing/pasting into Connector input/secret panels selects their explicit Continue option; preserve pasted secret bytes rather than applying `display_text` whitespace changes.
6. Esc/Ctrl+C and empty Ctrl+D cancel a Connector panel and restore the ordinary draft, without exiting or writing the secret to history.
7. Mask API Key slash commands, exclude them from history and do not restore a rejected private command into the normal editor, including a command with leading whitespace.
8. Route Connector-owned background replies, including errors, to `print_connector_reply`; route Connector stop through the targeted authorization and operation cancellation helper.
9. Surface `mcp.notification` authorization status and `extension.progress` by their bound public IDs without printing payloads or authorization URLs.

The terminal rejects opening private/review panels while its own conversation run is active. This prevents a model question/approval event from overwriting a secret panel and restoring its input as a normal prompt. Read-only status and background capability operations remain available. Normal exit cancels tasks, waits for them, and closes the native MCP/Connector resources before restoring the terminal.

## Executed checks so far

`npm test -- src/ConnectorsView.test.tsx` passed 11 focused interaction tests: configuration visibility, plugin delegation, exact fingerprint trust, full replacement/temp input, OAuth review/private inputs, navigation and completion cancellation, API Key target approval, changed-target refusal, orphan cleanup, resource/prompt routing, retained authorization diagnostics, and old-workspace response isolation. Some tests cover more than one behavior.

`rustfmt --edition 2024 ReverieCli-rs/crates/cli/src/terminal/connectors.rs` parsed and formatted the standalone module. This is not a Rust compilation or runtime result.

`terminal/screen.rs` was also formatted directly. `terminal/mod.rs` and its modules passed a read-only `rustfmt --emit stdout` parse/preview; adjacent existing terminal code was not reformatted. `git diff --check` passed for the shared terminal edits.

All four new Node probe files passed `node --check`. This verifies syntax only. The actual probes wait for root's coordinated native program and production desktop build; they do not invoke Cargo or rebuild/deploy another agent's program.

The current generated API Key type still needs root regeneration with the required `expected_fingerprint` field before full frontend typecheck can pass. Native compilation, App/i18n integration, real ConPTY and production Electron results must be recorded against the new coordinated program identity. The older plugin increment's executable and build cannot serve as Connector evidence.

## Coordinated basic runtime checks

```text
cargo test --manifest-path ReverieCli-rs/Cargo.toml -p reverie-cli terminal::connectors::tests --locked
npm --prefix ReverieCli-ui test -- src/ConnectorsView.test.tsx
npm --prefix ReverieCli-ui run typecheck
node scripts/verification/rust-connectors-tui-smoke.mjs <coordinated-rust-program>
node scripts/verification/rust-connectors-electron-smoke.mjs <coordinated-rust-program>
```

Probe artifacts and failures stay under `.runtime/rust-3.0/connectors-tui-smoke` and `connectors-electron-smoke`. The TUI probe includes an actual bracketed-paste/vault/HTTP round trip with a literal tab in a header value to detect secret whitespace rewriting. Each actual run records program size/SHA-256; the Electron run additionally verifies the program loaded by the production host and records the desktop build identity/screenshots. A changed program is a failure, not an implicit update to the accepted evidence.

The Electron probe instruments the production `shell.openExternal` boundary and follows only the local OAuth fixture. This proves the production IPC chooses the returned URL and exercises native discovery, PKCE callback, exchange and system vault; it does not prove OS browser startup or real external account consent.

## Not yet verified

1. New terminal module compilation and coordinated native executable integration.
2. App navigation, translations and generated-type integration in the production desktop build.
3. New actual ConPTY management and masked-input probe against the coordinated executable.
4. New actual production Electron Connector probe and visual screenshots against that executable/build.
5. OS default browser startup from GUI and TUI.
6. Successful TUI browser authorization and pending completion cancellation with its own host registry.
7. Public MCP services and real external OAuth account login, refresh, restoration and revocation.
8. Third-party connector registration variants beyond the local fixture.
9. Windows/Linux/macOS credential backends outside the host actually exercised by the native probe.
10. Non-Windows terminal behavior, CJK/IME/paste behavior across terminal emulators and desktop layouts.
11. Physical DPI, multimonitor, window movement and package installation validation.
12. Final release assets, performance, long-running stability and complete product acceptance.
