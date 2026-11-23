# Reverie CLI 3.0.0 Rust workspace

This workspace implements the native first-party kernel and terminal migration. Development is on `main`; the final Python 2.5.5 project is frozen on `Reverie-Cli-py`. The full product scope is in [the migration plan](../tasks/rust-3.0/plan.md); [unverified items](../tasks/rust-3.0/UNVERIFIED.md) and [the cloud validation prompt](../tasks/rust-3.0/CLOUD_VALIDATION_PROMPT.md) track remaining evidence.

Rust/Cargo 1.96.0 and Edition 2024 are fixed. Build with `cargo build --manifest-path ReverieCli-rs/Cargo.toml --release --locked` from the repository root. The output is `ReverieCli-rs/target/release/reverie` (`reverie.exe` on Windows).

The first increment provides the actual native version/help entry, `--kernel-info`, and UTF-8 JSONL `--sdk-bridge`. The bridge preserves string/number request IDs, reports malformed input, responds to `hello`, and closes on `shutdown` or EOF. Capabilities declare implemented actions; unsupported actions return explicit errors. The Context Engine is not available in this increment, as recorded by the kernel identity. Configuration, sessions, Provider execution, context retrieval, the scrolling terminal, and Electron integration follow in the next increments.

Run `node scripts/verification/rust-smoke.mjs` against the built release program for the basic actual-process checks. These checks do not establish complete product, performance, model, DPI, game, or release acceptance.

All first-party crates use the repository's MIT license. Serde 1.0.229 and serde_json 1.0.154 were verified against Crates.io metadata as available and not yanked, under MIT OR Apache-2.0. Cargo.lock pins the complete dependency graph; final binary notices and dependency license auditing remain part of the release work.
