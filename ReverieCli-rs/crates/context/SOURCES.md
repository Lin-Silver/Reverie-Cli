# Context Engine implementation sources

The initial `catalog.rs`, `parsing.rs`, `scan.rs`, `search.rs`, `text.rs` and SQL schema were recovered from this repository's MIT-licensed Rust indexer at commit [`f029496d19138176b857bedb54f7eeb225973471`](https://github.com/Lin-Silver/Reverie-Cli/tree/f029496d19138176b857bedb54f7eeb225973471/ReverieCli-py/native/context-engine). The original source remains in Git history and the historical mixed Python release. The final Python 2.5.5 archive does not depend on this implementation.

The 3.0 implementation uses an in-process library, Git directory exclusion, a separate versioned database with source identities and persisted evidence text, bounded evidence fragments and a shared query API. These changes are Reverie CLI changes under the repository MIT license. No legacy worker or Python adapter is included. Parser, SQLite and ignore dependencies remain separately licensed; Cargo.lock records their exact versions.
