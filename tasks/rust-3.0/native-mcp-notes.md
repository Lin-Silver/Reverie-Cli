# Rust 3.0 native MCP / Connector handoff

The native MCP/Connector module is implemented and its source is frozen for root integration. This is a module handoff, not a declaration that Reverie CLI 3.0.0 or its final release assets have passed acceptance. Python sources, branches, tags and releases were not modified by this module task.

## Owned files

- ReverieCli-rs/crates/core/src/mcp.rs and mcp/config.rs, privacy.rs, runtime.rs, sse.rs, transport.rs, tests.rs, SOURCES.md.
- ReverieCli-rs/crates/core/src/credentials.rs.
- ReverieCli-rs/crates/core/src/connectors.rs and connectors/callback.rs, metadata.rs, oauth.rs, store.rs, tests.rs.
- scripts/verification/rust-mcp-smoke.mjs and scripts/verification/rust-oauth-smoke.mjs.
- scripts/verification/rust-mcp-sdk-smoke.mjs for the targeted SDK integration regressions requested by root.
- This handoff document.

root owns host/lib/SDK integration, Cargo manifests and lockfile, platform ProcessTree export, GUI/TUI, CI, commits and pushes.

## Implemented behavior

Manual and trusted plugin MCP configurations share discovery and transport machinery. Config parsing preserves duplicate argv, environment expansion, transport aliases, include/exclude rules and namespaces; updates preserve unknown configuration, back up original bytes and check revisions. Untrusted configurations are displayed without starting a process or an MCP handshake.

stdio, POST JSON/SSE HTTP and legacy SSE perform real JSON-RPC initialization, discovery pagination, roots replies, resources/templates, prompts, tool calls and cancellation notifications. Discovery has a total per-server budget and at most four servers run concurrently. Requests with unknown delivery are not replayed; catalogues and task leases carry generations, and retired clients remain available to existing leases until their owners release them. Normal shutdown closes active and retained clients and their process trees.

Tool inputSchema is compiled offline with jsonschema and cached by content in the client and lease. Required fields, types and internal references are enforced before transmission. External file/HTTP/relative references are rejected. Public MCP metadata omits private _meta and reflected known credential values; tool errors retain their text and delivery classification.

Connectors discover protected-resource and OAuth/OIDC metadata without sending configured credentials. Authorization binds the endpoint, resource, issuer, client, scopes, callback, state and PKCE S256. Registration or code exchange begins only after explicit confirmation. OAuth tokens, applicable client secrets and API keys use system storage, including the Windows long-value treatment documented in mcp/SOURCES.md.

Refresh, restart restoration, explicit reauthorization, revocation and API keys are implemented. A disconnected refresh is recorded as uncertain and requires explicit recovery instead of automatic replay. A 403/401 challenge can provide the actual required scope without expanding an existing grant. Public status is separate from MCP connection health.

## Integration contract

~~~rust
McpRuntime::new()
runtime.discover(servers, project, authorization_headers, notify, cancel).await
runtime.retain_configurations(project, all_configurations)
runtime.authorization_challenge(project, server_id) // private String, never SDK/model data
runtime.invalidate(project, optional_server_id)
runtime.close().await

snapshot.public()
snapshot.prepare_tool(name) // resolution only, no execution
lease.configuration() // private config, not an activity/log payload
lease.call_approved(arguments, private_headers, cancel).await
snapshot.read_resource(server_id, uri, private_headers, cancel).await
snapshot.get_prompt(server_id, name, arguments, private_headers, cancel).await

ConnectorManager::new(app)
manager.list()
manager.status(server)
manager.discover(server, cancel).await // returns OAuthDiscovery { id(), public() }
manager.discover_with_challenge(server, captured_challenge.as_deref(), cancel).await
manager.begin_authorization(server, discovery_id, choice, notify, cancel).await
manager.complete_authorization(server, authorization_id, cancel).await
manager.cancel_authorization(authorization_id)
manager.headers(server, cancel).await // private BTreeMap; never publish it
manager.set_api_key(server, header, complete_header_value, confirmed, cancel).await
manager.revoke(server, cancel).await
manager.close().await
~~~

AuthorizationChoice requires an explicit issuer and confirmed scopes; optional client_id, client_secret, client_auth_method, redirect_uri and registration_token allow applicable registration variants. confirmed defaults to false. An Authorization API key value includes its scheme, such as Bearer. Manager headers are bound by server identity and the original endpoint, so credential_ref need not be inserted into mcp.json.

root must route MCP tool calls through the ordinary permission, approval and task-journal path before call_approved; resource/prompt actions require their corresponding host ownership and permission checks. retain_configurations receives complete configurations before mode filtering. OAuth/admin actions belong to explicit GUI/TUI control, and raw challenges, private configuration, authorization codes, client secrets and token headers must not be serialized to model/activity logs.

## Executed verification

Host: Windows, rustc 1.96.0 and Cargo 1.96.0. The following records the initial module verification; newer integrated native-fixture evidence is recorded separately below. The targeted tests compiled actual native Rust integration executables. No release/LTO build was launched by this module task.

~~~text
cargo test --manifest-path ReverieCli-rs/Cargo.toml -p reverie-core mcp:: --locked
cargo test --manifest-path ReverieCli-rs/Cargo.toml -p reverie-core connectors:: --locked
node scripts/verification/rust-mcp-smoke.mjs
node scripts/verification/rust-oauth-smoke.mjs
~~~

The basic MCP tests passed 4 tests; its Node-dependent ignored test was separately executed and passed. The basic OAuth tests passed 3 tests; its OS-vault/Node-dependent ignored test was separately executed and passed.

- Earlier MCP runtime evidence: .runtime/rust-3.0/mcp-smoke/case-SI9kzt/report.json. Actual stdio/HTTP/SSE, pagination, roots, resources, prompts, trust blocking, private fields, error text, input validation without server transmission, generation invalidation, timeout and shutdown passed.
- Earlier OAuth/storage evidence: .runtime/rust-3.0/oauth-smoke/case-YMNOzC/report.json. Actual Windows vault handling of a 20,014-byte value, large/small replacement/removal, metadata/PKCE/registration/callback, refresh/restart, authenticated MCP, a private 403 scope challenge, target binding, revocation/API keys, confidential Basic client and no replay after an uncertain refresh passed. Counts: 3 registrations, 3 exchanges, 3 refresh attempts, 6 revocations, 1 successful MCP call, 1 scope challenge.
- The source was formatted. The last strict Clippy run found three items in concurrently edited Writer/plugins and a test-module placement in this module. schema_tests was then moved to the runtime.rs end. root performs the unified final fmt/Clippy/build checks; this handoff does not declare the prior failed workspace check passed.

## Management boundary increment

The MCP/Connector management fixes are source-complete and frozen for root integration. Rustfmt, Node syntax checking and a scoped git diff check passed at handoff. The new native tests had not run at that initial handoff; the integrated rerun below now includes the actual OAuth/Windows-vault management checks. root owns the unified Cargo/build window.

`McpConfigStore::read_all(plugins)` returns `ConfigRead`: a private `document: Option<Value>`, all valid `servers` before enabled/mode filtering, public `diagnostics`, and `revision: Option<u64>`. An unreadable/invalid full JSON file is represented by a document diagnostic, no executable servers, and an unknown revision. Its original bytes remain intact. A bad individual entry does not remove the valid entries from management or execution reads.

`ConfigRead::effective(mode, global_override)` applies either file policy or an explicit application policy. Malformed global policy does not activate servers and adds a diagnostic. `read_effective(plugins, mode)` is the file-policy convenience. `public_read(&read)` adds the actual selected current/legacy path; host code must not serialize the private raw document/configuration fields.

All manual public rows carry a fingerprint. Valid rows use the normalized execution-configuration fingerprint; invalid rows use the raw entry SHA-256 and explicitly identify `fingerprint_kind=raw_entry`. Errors omit environment/header values and endpoint queries. Per-entry repair only validates its explicit replacement; deleting a bad entry works even when another bad entry remains. Unsupported full JSON/server-table shapes are preserved rather than replaced. MCP/Connector metadata locks return busy immediately, and existing per-server Connector mutation leases have a 15-second bound. MCP edits also check original bytes before replacing the file and retain byte-exact backups.

`ConnectorManager::list_configured(&all_valid_configurations)` computes current status. Missing/removed configuration, changed endpoint, disabled entry and untrusted entry no longer inherit an old `authorized` status. The legacy no-configuration `list()` reports `configuration_unverified`; pending authorizations also expose whether their original target still matches. The host supplies the complete configuration set and applies any source-level activation policy before projection.

`clear_local_credentials(server_id, confirmed, cancel)` requires explicit confirmation, accepts an identity after its source is disabled/deleted, cancels matching pending authorization, removes stored metadata and cleans the OS vault through the retirement/recovery path. It makes no remote request and reports `server_revocation=not_attempted_local_only`. Remaining native cleanup is reported as pending. Normal remote `revoke` remains separate.

Vault persistence now records a recoverable retirement intent before starting a blocking native write. A cancelled native worker may still finish; the intent lets local cleanup find and serialize removal of that entry. Successful activation removes its own intent and keeps the prior credential retirement behavior.

Added focused coverage includes four MCP configuration tests, two Connector metadata tests and two additional checks inside the actual OAuth/vault fixture. The fixture counts all non-audit HTTP requests so confirmed local cleanup can prove that authorization cancellation, real vault removal and an idempotent repeat caused no remote request. These were prepared tests at the initial handoff; the integrated OAuth run below subsequently passed those two actual-protocol checks. root records the unified pure-test results separately.

## SDK boundary regressions (2026-11-23, debug verified)

root accepted four integration review findings: isolate individual Connector credential failures, preserve typed MCP read delivery, reject non-object prompt arguments, and edit MCP trust/enabled fields while holding the configuration write lock. root owns those implementation changes and the new debug executable.

The SDK smoke script retains its existing stdio discovery, trust, schema, approval, identity-change and cancellation checks. It now adds a loopback HTTP read fixture and these actual-process regression scenarios:

1. Create a trusted HTTP MCP configuration through the SDK, then place a schema-valid Connector metadata record with a deliberately wrong binding into the isolated application folder. Its credential identifier has no real vault entry. Verify public status is target_changed, listTools diagnoses/excludes the server, the unrelated stdio tools and runPrompt remain usable, and the blocked endpoint receives no MCP request. This is an authorization-binding/error-isolation fixture, not proof of a real OAuth or vault workflow.
2. Submit explicit string and array prompt arguments through both SDK and model tool calls. Verify the tool reports the argument error and the HTTP fixture receives no prompts/get RPC; empty-object substitution must not make the test pass.
3. Wait until the HTTP fixture observes resources/read and prompts/get before Stop. Verify the emitted tool result keeps delivery=unknown, the cancellation notification refers to the transmitted request ID, and later discovery restores control without replaying the read.

The fixture enables strict_allow_read_only for built-in read helpers; the existing stdio echo/hang tools still require their ordinary strict approvals. It creates only isolated project-local fixture metadata and does not add OS-vault or external-login prerequisites. Reports retain the executable hash, blocked-endpoint request count and read delivery observations; failures also retain the safe read-RPC audit.

Preparation status: Node syntax checking and the scoped diff check passed. The first execution against debug SHA-256 A0B9FA5B04BC2BA67FE29ADA2CACFE1F83FC5A4D8F759B02641B469DAB50F1F9 stopped at a test-field mismatch: the implementation returns authorization diagnostics in authorization_diagnostics, while the test checked mcp_diagnostics. The failed report is .runtime/rust-3.0/mcp-sdk-smoke/case-Zhz28A/report.json; its blocked endpoint count was 0 and its fixture server had no failure. root authorized changing only that assertion, preserving server_id binding and zero blocked requests.

The corrected full SDK run passed all 9 checks with exit 0 against that same debug executable (70,466,560 bytes). Evidence: .runtime/rust-3.0/mcp-sdk-smoke/case-aw6gZy/report.json, recorded at 2026-11-24T05:19:57.731Z. The executable hash was checked before and after the run and matches the report. The blocked Connector endpoint received 0 requests. The transmitted resources/read request ID 6 and prompts/get request ID 12 both retained delivery=unknown with status=error; cancellation IDs matched and later discovery did not replay either read. Five actual loopback model tool-result turns were recorded. This is native debug SDK/Agent/MCP evidence with isolated fixtures, not external-account OAuth/vault or final four-platform/release acceptance. No Cargo or Rust/runtime-source changes were performed for this regression increment; new compaction or release executable identities require their own runtime verification.

### Basic fixture commands and boundaries

root initially deferred the two basic library fixtures while integrating compaction/tokenizer dependencies and owning the workspace Cargo window. That pause ended for the serialized integrated rerun below. They do not accept a CLI executable argument: their first argument is the project-local report directory. Their Node wrappers create the isolated directory and live 127.0.0.1 fixture before setting the required test environment.

~~~text
node scripts/verification/rust-mcp-smoke.mjs .runtime/rust-3.0/mcp-smoke
node scripts/verification/rust-oauth-smoke.mjs .runtime/rust-3.0/oauth-smoke
~~~

The wrappers invoke these exact Cargo filters; the integrated rerun executed them sequentially after root released the build window:

~~~text
cargo test --manifest-path ReverieCli-rs/Cargo.toml -p reverie-core mcp::tests::native_protocol_rpc --locked -- --ignored --nocapture
cargo test --manifest-path ReverieCli-rs/Cargo.toml -p reverie-core connectors::tests::native_oauth_authorization_and_vault --locked -- --ignored --nocapture
~~~

Running those filtered commands alone does not prepare a fixture: MCP requires REVERIE_MCP_SMOKE_ROOT, REVERIE_MCP_FIXTURE_URL and REVERIE_MCP_NODE; OAuth requires REVERIE_OAUTH_SMOKE_ROOT and REVERIE_OAUTH_FIXTURE_URL. The wrappers provide them. These are native reverie-core test executables, not the CLI debug binary, so their results must record their own build/test identity rather than inherit the SDK SHA above.

The two scripts are first-party sources covered by the root MIT LICENSE; reverie-core inherits workspace license=MIT. Their JavaScript imports are Node built-ins, with no added npm packages or copied external marketplace fixtures. Existing Rust dependency/native-backend licenses remain separate, as described in mcp/SOURCES.md and the lockfile; this command review is not a new complete dependency-license audit.

MCP uses only generated fixture credentials, its temporary workspace and owned stdio/HTTP/SSE peers. OAuth constructs application and workspace directories beneath its temporary root, uses a local authorization/registration/token service, and reads/writes only fixture account IDs under CredentialStore's application-path-derived service namespace. It exercises a real OS credential backend when run, but does not authorize an external account. Both wrappers retain JSON evidence inside the repository and close their own loopback server. Neither basic fixture was rerun in this debug SDK verification window.

## Integrated native library fixtures (2026-11-24, passed)

root released one serialized Cargo window after integrating the core source tree. MCP, OAuth and the additional LSP wrapper ran in that order with separate project-local fixture directories. All three Node wrappers exited 0, and each filtered Rust test reported 1 passed, 0 failed. No Rust, Host, GUI, terminal or verification-script source was changed during these executions. The Cargo window was returned immediately after LSP finished.

The source identity is main HEAD 881e3f14a1e4b79bc405cab7daa26fd32059aea0 plus its captured uncommitted source tree, not that committed HEAD alone. The source-before.json evidence records 92 SHA-256 inputs covering the workspace manifest/lockfile, core and its first-party crate sources/manifests, and the three Node wrappers. All 92 hashes remained unchanged at the end of each fixture. The source snapshot, command logs, individual run-evidence.json records and round-summary.json are under .runtime/rust-3.0/native-fixtures-round-20261124T053815Z-ab0171.

Cargo's actual Running paths selected the same native test executable for all three filters: ReverieCli-rs/target/debug/deps/reverie_core-807e544c9a24723a.exe, 69,999,616 bytes, SHA-256 64AF0DCD4D127075B38E25E771F61C90FFDF3BE7163680B50FE3124BADF6F1FA. Each post-run hash matched the pre-run executable snapshot. This is the reverie-core native test executable; it is not the SDK debug program identity above.

Node was C:/Program Files/nodejs/node.exe v24.18.0, SHA-256 9A4EB5F1C29C6A2E93852EAD46B999E284A6A5CA8BAB4D4E241D587D025A52DE. Cargo was 1.96.0 (30a34c682 2026-05-25), and rustc was 1.96.0 (ac68faa20 2026-05-25). All three scripts passed Node syntax checking before execution.

| Wrapper | Rust filter | Rust test elapsed | JSON report beneath the round directory |
|---|---|---|---|
| rust-mcp-smoke.mjs | mcp::tests::native_protocol_rpc | 3.98 seconds | mcp/case-j2Yg1o/report.json |
| rust-oauth-smoke.mjs | connectors::tests::native_oauth_authorization_and_vault | 1.07 seconds | oauth/case-Lw0Uqi/report.json |
| rust-lsp-smoke.mjs | lsp::tests::native_stdio_lifecycle_and_evidence | 1.85 seconds | lsp/case-OLLFZz/report.json |

These durations are the filtered Rust test timings from the Cargo logs, not a performance-baseline result. Each wrapper's first argument was its isolated report directory under the round directory; the LSP wrapper used Cargo, with no REVERIE_LSP_TEST_BINARY override.

MCP passed three transport groups: real stdio, HTTP and SSE initialization/discovery, pagination, roots, resources, prompts, trust, private-field handling, errors, configuration generations and timeout/shutdown checks. OAuth passed 11 reported checks, including the new configured-status projection and confirmed server_id-only local cleanup. That cleanup cancelled pending authorization and removed actual Windows-vault fixture credentials without any remote request. The complete run recorded 4 registrations, 3 exchanges, 3 refresh attempts, 6 revocations, 24 metadata requests, 1 successful MCP call, 1 scope challenge and 56 total non-audit requests.

LSP passed eight reported checks covering fragmented Content-Length framing, read-only client replies, Unicode/UTF-16 positions and source evidence, incremental revisions, stale and unversioned diagnostics, retained configuration generations, cancellation/timeout without replay, private-data redaction, document deletion and shutdown. It recorded 4 starts, 2 opens, 1 change, 2 cancellations, 4 shutdowns and 4 exits; no fixture PID remained alive.

The OAuth service and MCP/LSP peers were generated local fixtures. Only the fixture's application-path-derived Windows-vault namespace was accessed; no real account credentials were read. These passes do not establish external-service interoperability, real external-account consent/refresh/revocation, non-Windows vault behavior, GUI/TUI/Context Engine integration, long-running failure injection or final four-platform/release acceptance. The earlier SDK run remains evidence for its own captured debug identity; a newer SDK or release program needs its own run.

## Remaining work and unverified evidence

1. Final GUI/TUI/SDK integration through ordinary permission, approval, cancellation and task journals has not been exercised by this module's library fixtures.
2. External MCP service interoperability and real external OAuth account authorization/refresh/revocation have not been verified.
3. macOS Keychain and Linux Secret Service runtime behavior, unavailable/locked vault states and headless Linux setup have not been verified.
4. Windows vault fragment recovery under process termination, corrupt/missing entries, failed writes/deletes and concurrent cross-process failure injection has not been verified.
5. Streamable HTTP independent GET event streams, Last-Event-ID reconnection/resumption and server-side session expiry recovery are not implemented or verified.
6. MCP sampling and elicitation client requests are not implemented; current capability declarations only advertise roots.
7. MCP Apps UI protocol, private view metadata, app-only tool dispatch and full view lifecycle/permission integration are not implemented in this module.
8. Tool outputSchema validation and the broader protocol conformance/error/cancellation matrix have not been implemented or verified.
9. Resource subscriptions, roots-list-change notifications and server resource-update notifications have not been implemented or verified.
10. OAuth client-ID metadata documents, device/enterprise extensions, client_secret_post and authenticated dynamic registration have not been exercised; automatic hosting of client metadata is not implemented.
11. Final four-platform CLI/desktop assets, installers, signed/dependency license materials and same-package end-to-end runtime behavior have not been verified by this module.
12. Long-running external-service workloads, memory/handle/process leakage, rate limiting and adversarial transport/credential failure matrices remain unverified.

For cloud handoff, run the pure MCP/Connector tests followed by their Node wrappers above using main and the locked dependencies; rust-lsp-smoke.mjs provides the separate LSP native fixture. The Node scripts retain JSON reports under the project .runtime directory. A missing OS vault, unavailable dependency or network limitation is an explicit failed/blocked environment result; use the pure tests for their narrow evidence and report the integration gap. Do not substitute fake token storage, remove assertions, create branches, change versions/tags/releases or claim real external login from the loopback fixture.
