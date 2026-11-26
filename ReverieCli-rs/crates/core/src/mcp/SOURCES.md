# Native MCP / Connector sources and licensing

This module is a first-party Rust implementation under the repository license. Python compatibility was reviewed against ReverieCli-py/reverie/mcp.py, reverie/tools/mcp_dynamic.py and reverie/tools/mcp_resource_tools.py. Connector OAuth is newly implemented; no existing Python OAuth implementation was identified in those reviewed paths.

## Protocol references consulted

- [MCP 2025-06-18 transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports): stdio, streamable HTTP and legacy SSE compatibility.
- [MCP 2025-06-18 authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization): protected-resource discovery, resource indicators, client registration and HTTP token use.
- [MCP 2025-11-25 authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization): OAuth/OpenID Connect metadata discovery order, explicit issuer/scopes and advertised PKCE support.
- [RFC 7636](https://www.rfc-editor.org/rfc/rfc7636): the S256 example values in Appendix B are used as a numeric test vector. The Rust hashing, callback and HTTP implementations are independently written.

The supported default MCP handshake is 2025-06-18; 2025-11-25 negotiation is also accepted. Client capability declarations currently cover roots only. Sampling, elicitation and MCP Apps require further implementation and validation; protocol references do not establish that those capabilities are present.

## Dependency evidence

The fixed registry releases and their Cargo.toml license declarations were read locally. keyring, reqwest and jsonschema license files were also read. Cargo.lock is the dependency identity authority; native backend licenses must be included in distribution notices alongside wrapper licenses.

| Package | Fixed version | Declared license | Declared minimum Rust |
|---|---|---|---|
| keyring | 4.2.0 | MIT OR Apache-2.0 | 1.88.0 |
| windows-native-keyring-store | 1.1.0 | MIT OR Apache-2.0 | 1.88 |
| apple-native-keyring-store | 1.0.3 | MIT OR Apache-2.0 | 1.85 |
| zbus-secret-service-keyring-store | 1.0.1 | MIT OR Apache-2.0 | 1.88 |
| reqwest | 0.13.5 | MIT OR Apache-2.0 | 1.85.0 |
| base64 | 0.23.1 | MIT OR Apache-2.0 | 1.71.0 |
| jsonschema | 0.63.1 | MIT | 1.85.0 |

The downloaded keyring 4.2.0 crate was independently hashed:

~~~text
SHA-256 2270074a3d26bcac93c1dc5d2845eb4c089e8d761ccf6e0ea266a16004640627
~~~

That digest agrees with Cargo.lock. Its local review material is in .runtime/rust-3.0/mcp-sources/keyring-4.2.0; the source archive is not a distributable product asset.

The default keyring v1 feature selects Windows Credential Manager, macOS Keychain and Linux Secret Service backends. Actual Windows write/read/delete behavior was exercised; the other backends have not been run in this task.

## Windows storage boundary

windows-native-keyring-store 1.1.0 checks secret byte length against CRED_MAX_CREDENTIAL_BLOB_SIZE in src/utils.rs. windows-sys 0.61.2 declares that limit as 2560 bytes. A real 20,014-byte test credential failed against the original single-entry implementation.

credentials.rs now divides Windows values exceeding 2000 bytes into OS-vault entries. A versioned root identifies the generation, length, count and SHA-256; the root is written after all fragments. An OS-vault recovery journal records the old/new generations, while empty per-entry filesystem locks serialize writers/readers across processes. Secrets and fragment data remain inside the OS vault. Existing small JSON entries continue to load.

Successful large/small replacement and removal were actually exercised. Process-crash, corruption and failure-injection recovery remain additional verification work. Temporary byte buffers are filled with zero; compiler-resistant erasure of all memory copies has not been established.

## Scope of execution evidence

The Node scripts use local protocol fixtures and real Rust library integration executables. OAuth identity and consent are fixture behavior; these results do not establish successful login to an external account or final packaged GUI/TUI behavior. The implementation notes in tasks/rust-3.0/native-mcp-notes.md enumerate those remaining checks.
