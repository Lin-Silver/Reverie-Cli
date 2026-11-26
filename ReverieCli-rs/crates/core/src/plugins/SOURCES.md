# Native extension installation and activation

This is a first-party implementation under the repository MIT license. Compatibility was reviewed against the archived Python plugin manager and the fixed marketplace records in `tasks/rust-3.0`. No Codex or ZCode source was copied into these modules.

The implementation handles local directories, ZIP archives, Git trees and recorded market entries. Component discovery keeps Skills, commands, agents, Hooks, MCP, LSP, configuration, platform Apps and `-RC` runtime entries distinct. Discovery and approval of a component do not establish that its execution adapter is complete.

Version directories preserve the candidate bytes. A single revisioned activation record binds active content, provenance and the approved execution profile; running tasks retain leases to their selected version. Source, permissions, connection configuration, dependencies, license material and terms enter the profile. An expanded profile requires explicit approval, and enabling Hooks requires separate confirmation. Untrusted or disabled content is not supplied to Agent Skills or MCP discovery.

Package validation rejects path traversal, links, reparse points, platform path aliases, malformed manifests, incompatible runtime protocols, content changes and invalid signatures. Ed25519 signatures bind the declared inventory; directory content hashes are not publisher signatures. A user-supplied expected hash proves the supplied content expectation, not publisher ownership. Automatic checking and switching of trusted updates, runtime health checks and the remaining execution adapters still require implementation and verification.

## Fixed dependencies checked locally

`cargo metadata --locked --offline` resolved the versions below. Their registry `Cargo.toml` declarations were read during integration; this table is source evidence, not a complete binary distribution notice.

| Dependency | Version | Declared license | Use |
|---|---|---|---|
| zip | 8.6.0 | MIT | Bounded archive extraction |
| ed25519-dalek | 3.0.0 | BSD-3-Clause | Publisher signature verification |
| sha2 | 0.11.1 | MIT OR Apache-2.0 | Content identity |
| base64 | 0.23.1 | MIT OR Apache-2.0 | Signature encoding |
| serde-saphyr | 2.2.0 | MIT OR Apache-2.0 | Skill and command front matter |
| toml | 0.9.8 | MIT OR Apache-2.0 | Common plugin configuration |
| semver | 1.0.28 | MIT OR Apache-2.0 | Kernel compatibility requirements |
| unicode-normalization | 0.1.26 | (MIT OR Apache-2.0) AND Unicode-3.0 | Portable path identity |

The lockfile remains authoritative for transitive dependencies. Final packages must carry the applicable dependency license and notice material. The native MCP, system credential and Connector dependencies are separately recorded in `../mcp/SOURCES.md`; built-in WStyle cards retain their original Git blobs and license evidence in `../../../../resources/wstyle_cards/SOURCES.md`.

## Verification boundary

Unit and integration checks exercise actual file copying, ZIP extraction, Git export, signatures, immutable task leases, revision conflicts, activation, profile expansion and rollback. GUI and PTY probes use the actual Rust executable with isolated first-party fixtures and loopback services. They do not certify public plugin publishers, external accounts, complete component execution, four-platform release packages or the product's performance gates.
