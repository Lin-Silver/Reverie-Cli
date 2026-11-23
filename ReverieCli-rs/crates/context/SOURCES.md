# Context Engine implementation sources

The initial `catalog.rs`, `parsing.rs`, `scan.rs`, `search.rs`, `text.rs` and SQL schema were recovered from this repository's MIT-licensed Rust indexer at commit [`f029496d19138176b857bedb54f7eeb225973471`](https://github.com/Lin-Silver/Reverie-Cli/tree/f029496d19138176b857bedb54f7eeb225973471/ReverieCli-py/native/context-engine). The original source remains in Git history and the historical mixed Python release. The final Python 2.5.5 archive does not depend on this implementation.

The 3.0 implementation uses an in-process library, Git directory exclusion, a separate versioned database with source identities and persisted evidence text, bounded evidence fragments and a shared query API. These changes are Reverie CLI changes under the repository MIT license. No legacy worker or Python adapter is included. Parser, SQLite and ignore dependencies remain separately licensed; Cargo.lock records their exact versions.

The symbol, file, search, dependency, outline, exploration and task request fields follow the actual Python tool and index contracts in the fixed final Python source [`070fa25b07692c90c56a6b00a9a969ff2abb7804`](https://github.com/Lin-Silver/Reverie-Cli/tree/070fa25b07692c90c56a6b00a9a969ff2abb7804/ReverieCli-py/reverie/context_engine) and its `tools/codebase_retrieval.py`. The new Rust graph and lookup are independent implementations under the same repository license. Grammar tag queries come from the pinned Tree-sitter crates; inference is explicitly labelled and is not an LSP or compiler resolution claim. `tests/fixtures/rust-schema-v2.sql` preserves the development schema from `9ca0212` for actual backup, migration and restoration checks.

The additional grammars below were checked against Crates.io metadata, their packaged source commit and actual license text on 2026-11-23. Each declares MIT. Copies of their applicable copyright and permission texts are retained in [licenses](licenses); final packages must include these texts with the other binary dependency notices. The six licenses not found at their crate roots were retrieved from the fixed upstream revisions, including Lua's `LICENSE.md`.

| Grammar | Fixed crate | Source revision and license |
|---|---|---|
| C | tree-sitter-c 0.24.2 | [b780e47](https://github.com/tree-sitter/tree-sitter-c/blob/b780e47fc780ddc8da13afa35a3f4ed5c157823d/LICENSE) |
| C++ | tree-sitter-cpp 0.23.4 | [f41e1a0](https://github.com/tree-sitter/tree-sitter-cpp/blob/f41e1a044c8a84ea9fa8577fdd2eab92ec96de02/LICENSE) |
| C# | tree-sitter-c-sharp 0.24.0 | [d4bbe18](https://github.com/tree-sitter/tree-sitter-c-sharp/blob/d4bbe18103c3380c6454085e589d2610938da142/LICENSE) |
| Go | tree-sitter-go 0.25.0 | [1547678](https://github.com/tree-sitter/tree-sitter-go/blob/1547678a9da59885853f5f5cc8a99cc203fa2e2c/LICENSE) |
| Java | tree-sitter-java 0.23.5 | [94703d5](https://github.com/tree-sitter/tree-sitter-java/blob/94703d5a6bed02b98e438d7cad1136c01a60ba2c/LICENSE) |
| Zig | tree-sitter-zig 1.1.2 | [b670c8d](https://github.com/tree-sitter-grammars/tree-sitter-zig/blob/b670c8df85a1568f498aa5c8cae42f51a90473c0/LICENSE) |
| HTML | tree-sitter-html 0.23.2 | [5a5ca85](https://github.com/tree-sitter/tree-sitter-html/blob/5a5ca8551a179998360b4a4ca2c0f366a35acc03/LICENSE) |
| CSS | tree-sitter-css 0.25.0 | [dda5cfc](https://github.com/tree-sitter/tree-sitter-css/blob/dda5cfc5722c429eaba1c910ca32c2c0c5bb1a3f/LICENSE) |
| Lua | tree-sitter-lua 0.5.0 | [10fe005](https://github.com/tree-sitter-grammars/tree-sitter-lua/blob/10fe0054734eec83049514ea2e718b2a56acd0c9/LICENSE.md) |
| GDScript | tree-sitter-gdscript 6.1.0 | [d2a0ee9](https://github.com/prestonknopp/tree-sitter-gdscript/blob/d2a0ee914d297b873a40dd4596bd1f7157ebc52b/LICENSE) |

The small Zig, HTML, CSS and GDScript definition queries in `src/queries` are Reverie's own queries based on these crates' actual `NODE_TYPES` and grammar structure. The native lexer, parser and bundled upstream tag queries remain upstream code. Actual basic definitions, source evidence and selected calls have been exercised; this does not establish complete language constructs, import/alias/type resolution or compiler equivalence.
