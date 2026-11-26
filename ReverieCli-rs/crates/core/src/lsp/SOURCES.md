# Native LSP sources

This first-party adapter is under the repository MIT license. Its compatibility scope was reviewed against `ReverieCli-py/reverie/context_engine/lsp_manager.py`, `reverie/tools/codebase_retrieval.py`, the on-demand initialization in `reverie/cli/interface.py`, and LSP auxiliary evidence in `reverie/context_engine/retriever.py`. No Python plugin LSP execution or dedicated SDK LSP action was found in those reviewed sources.

The implementation follows the [Microsoft LSP 3.17 specification](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/): Content-Length framing, initialization/capabilities, cancellation, document synchronization, symbols/definitions and push diagnostics. The specification markdown was retrieved from the official `gh-pages` branch (blob `8911d56ea788e91a1774f1ab0104264e697e3081`) and the relevant included sections were read separately. Specification documents use CC BY 4.0 (`License.txt`); code uses MIT (`License-code.txt`). This adapter does not copy the upstream transport implementation.

Official Anthropic examples reviewed:

- [Pyright](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/pyright-lsp/.claude-plugin/plugin.json), blob `dda371eceb19164069e83f721927045a3fc73c1d`.
- [Rust Analyzer](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/rust-analyzer-lsp/.claude-plugin/plugin.json), blob `10b085dd3922d12c56c0ca00b98ac3aaafd879b4`.
- [TypeScript](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/typescript-lsp/.claude-plugin/plugin.json), blob `f1a2f31021c0e4641c33622897cfa8b257917001`.

These examples declare `lspServers`, `command`, optional `args`, and `extensionToLanguage`. The adapter also accepts an explicit `extensions` plus `language_id` pair to represent the existing six Python definitions. It does not infer a language from an arbitrary executable name. No external language-server binary is bundled or installed by this module; its binary, runtime and license remain managed dependencies of the host or extension.

No new dependencies are introduced. The adapter uses the workspace's existing Tokio, serde/serde_json, sha2, reqwest URL type and first-party ProcessTree. Their fixed identities and licenses remain governed by Cargo.lock and the existing distribution notice work.
