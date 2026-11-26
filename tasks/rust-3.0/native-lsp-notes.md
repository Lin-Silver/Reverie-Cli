# Rust 3.0 native LSP increment

This increment migrates the existing five read-only language-service actions. It does not declare final GUI/TUI integration, external language-server interoperability or product acceptance complete.

## Scope and verification plan

1. Review Python discovery, tool actions, SDK and task-retrieval behavior; verify public plugin configuration against official examples.
2. Add project/version-bound LSP configurations and UTF-16 positions; check trust is caller-controlled and paths remain inside the project.
3. Add stdio framing, initialization, document revisions, push diagnostics, symbols/definitions, cancellation and process-tree shutdown; exercise an actual Rust client against a Node protocol fixture.
4. Give root explicit registration/query/lifecycle APIs and evidence boundaries; root alone changes lib/Host/Cargo/protocol/UI, compiles the workspace, commits and pushes.

## Current status

Source review and configuration preparation are in progress. No Cargo build has been run by this increment. Builtin PATH discovery does not decide activation or trust; both are assigned by the caller after the user's startup-policy decision. Parsed configuration alone is never approval.

Existing Python actions are `workspace_symbols`, `document_symbols`, `definitions`, `diagnostics`, `status`. Positions are zero-based; the Rust boundary explicitly uses UTF-16 code units. LSP evidence remains separate from the static index, binds its project/server/configuration revision and records document content identity. Server-requested edits/commands cannot grant execution or workspace permissions.
