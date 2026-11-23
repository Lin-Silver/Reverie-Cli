# Reverie CLI 3.0.0 Rust workspace

This workspace implements the native first-party kernel and terminal migration. Development is on `main`; the final Python 2.5.5 project is frozen on `Reverie-Cli-py`. The full product scope is in [the migration plan](../tasks/rust-3.0/plan.md); [unverified items](../tasks/rust-3.0/UNVERIFIED.md) and [the cloud validation prompt](../tasks/rust-3.0/CLOUD_VALIDATION_PROMPT.md) track remaining evidence.

Rust/Cargo 1.96.0 and Edition 2024 are fixed. Build with `cargo build --manifest-path ReverieCli-rs/Cargo.toml --release --locked` from the repository root. The output is `ReverieCli-rs/target/release/reverie` (`reverie.exe` on Windows).

The native program provides version/help, `--kernel-info`, and UTF-8 JSONL `--sdk-bridge`. Configuration and session actions support bootstrap/state, existing manual-model profiles, settings, independent conversation snapshots, durable SQLite transcripts, paging, naming, archiving and confirmed deletion. The bridge preserves string/number request IDs, reports malformed input, and closes on `shutdown` or EOF. Capabilities declare implemented actions; unsupported actions return explicit errors. Conversation schema 7 and the stored `Reverie`/wire `assistant` role convention remain compatible. Existing databases are backed up through SQLite before Rust writes, and configuration edits preserve unknown fields with an original-byte backup. Provider execution, Context Engine, the scrolling terminal, and Electron integration continue in subsequent increments.

Run `node scripts/verification/rust-smoke.mjs` and `node scripts/verification/rust-session-smoke.mjs` against the built release program for basic actual-process checks. These checks do not establish complete product, legacy data, performance, model, DPI, game, or release acceptance.

All first-party crates use the repository's MIT license. Serde 1.0.229 and serde_json 1.0.154 were verified against Crates.io metadata as available and not yanked, under MIT OR Apache-2.0. Cargo.lock pins the complete dependency graph; final binary notices and dependency license auditing remain part of the release work.
