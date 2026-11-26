# Rust browser control core

Status: standalone library source and 14 behavior/contract tests are prepared for root integration. Rustfmt parsing/formatting is verified; Cargo compilation and all browser tests remain unexecuted. No Host/lib/protocol registration, Electron browser host, GUI, CLI host packaging or final browser acceptance is included in this module task. Cargo is reserved by root; prepared Rust tests are not passed evidence.

## Current process boundary

The reviewed source tree is main HEAD 881e3f14a1e4b79bc405cab7daa26fd32059aea0 plus the current uncommitted work. The relevant local sources are ReverieCli-ui/electron/core-bridge.ts, electron/main.ts, ReverieCli-rs/crates/cli/src/sdk.rs and core/src/host.rs.

CoreBridge owns the core child stdin/stdout JSONL connection. It routes prompt.event while the originating request is still pending and can submit another request concurrently. Rust EventSink is Arc<dyn Fn(serde_json::Value) + Send + Sync>; the SDK wraps each event as prompt.event and preserves the originating request ID. This permits the same event/completion contract for Electron main and a future explicitly selected CLI browser adapter.

Electron main currently journals and forwards every task event to the trusted application renderer. The future integration must intercept browser.request/browser.cancel before those generic paths. The full control payload goes only to the registered main-process adapter; the task journal and model receive a safe action/host/tab/request summary. Adapter credentials must never be added to an EventSink payload, remote page preload, renderer state, tool arguments or logs.

The existing core:request IPC guard checks both the application webContents and its exact mainFrame. Remote browser pages must not receive that preload/IPC capability. Registration/completion/invalidation are trusted-adapter control operations, not model tools or ordinary renderer-selectable actions. The core runtime verifies an opaque registration credential in addition to host generation, request ID and scope.

## Small stable contract

The new standalone Rust types live under core/src/browser/types.rs; they do not modify reverie-protocol or generated TypeScript. Their public serialized DTOs/enums derive ts_rs::TS; browser::typescript_types() emits 24 export declarations directly from their decl() methods. AdapterKey is excluded, and the two u64 revision fields explicitly map to TypeScript number. Root owns the core ts-rs workspace dependency, module registration and CLI --protocol-types concatenation into the shared generated/core-types.d.ts; no hand-written authority or separate generated file is introduced. The protocol identifier is reverie.browser.v1. Unknown fields and unsupported actions are rejected instead of forwarded as arbitrary CDP or JavaScript.

| Type | Fields / responsibility |
|---|---|
| BrowserScope | Canonical existing project_root, session_id, run_id; exact ownership for every request and completion |
| BrowserProfile | Required mode (ephemeral or persistent) and explicit opaque profile_id; no Default, no user-data path, no sharing or packaging policy |
| BrowserHostRef / AdapterDescriptor / BrowserHost | Descriptor supplies host_id, engine/version and explicit capabilities; public BrowserHost pairs it with the kernel-generated host reference/generation |
| AdapterKey | Opaque registration credential, private and Debug-redacted; transport access is explicit and separate from public host information |
| BrowserAction | open/list/observe/click/type/scroll/key/navigate/close; URLs, finite keys and opaque observed element references, no selector expressions or script/command fields |
| BrowserTarget | tab_id, observation_id and document revision; required for mutations, navigation and close |
| BrowserTab / PageObservation | Bound tab identity, current revision, URL/title, bounded visible elements and optional screenshot reference/coordinate metadata |
| BrowserCompletion / BrowserReply | Exact request/host/scope/profile binding and a typed action result; reply carries a kernel-issued observation identity when observing |
| BrowserFailure / Delivery | Stable failure code and not_started/unknown/completed delivery; cancellation after dispatch remains unknown and is never replayed |

Observed element IDs are opaque references from one observation, not CSS/XPath/JavaScript. Click/type and any supplied scroll target must refer to an element in that observation. Key input is a finite page-key enum; it does not expose arbitrary OS or DevTools shortcuts. Core operations target registered browser tabs, never the application window.

The adapter maintains a monotonic document revision for navigation and relevant page/viewport changes. It reports invalidation to the core and also checks the expected revision immediately before executing an input. This second check is necessary because the page can change after Rust dispatches an action. Core invalidation and successful mutations retire old observations; cancelled/uncertain mutations require a new observation. Neither simulated revisions nor coordinate metadata prove actual DPI correctness.

The profile mode and profile ID are always supplied explicitly. The library does not choose a persistent default, share external Chrome cookies, install a browser runtime or select an independent CLI host. Profile isolation uses the explicit ownership tuple; any future cross-run/profile adoption requires an explicit trusted integration decision.

## Proposed library entry points

~~~rust
BrowserRuntime::new() -> BrowserRuntime
browser::typescript_types() -> String
runtime.register_adapter(AdapterDescriptor, trusted: bool) -> BrowserResult<AdapterKey>
runtime.adapters() -> BrowserResult<Vec<BrowserHost>>
runtime.authenticate_adapter(&BrowserHostRef, token: &str) -> BrowserResult<AdapterKey>
runtime.unregister_adapter(&AdapterKey) -> BrowserResult<()>

BrowserScope::new(project: &Path, session: &str, run: &str) -> BrowserResult<BrowserScope>
runtime.begin_request(BrowserScope, BrowserProfile, BrowserHostRef, BrowserAction)
    -> BrowserResult<PendingBrowserRequest>
pending.request_id() -> &str
pending.wait(EventSink, &CancellationToken, Duration) -> BrowserResult<BrowserReply>

runtime.complete(&AdapterKey, BrowserCompletion) -> BrowserResult<()>
runtime.complete_json(&AdapterKey, serde_json::Value) -> BrowserResult<()>
runtime.invalidate_tab(&AdapterKey, &BrowserScope, &BrowserProfile, tab_id: &str, revision: u64)
    -> BrowserResult<()>
runtime.cancel_request(&BrowserScope, request_id: &str) -> BrowserResult<()>
runtime.cancel_scope(&BrowserScope) -> BrowserResult<usize>
runtime.close() -> BrowserResult<()>
~~~

Request registration is atomic. One request per host/scope/profile is allowed in flight, so open/list reconciliation and tab actions cannot race within that ownership tuple. All host, profile, tab and observation checks run before emission; a prepared request is checked again when dispatched. A failed preparation or cancellation before dispatch is not_started. Once browser.request has been emitted, timeout, caller-future drop, cancellation, adapter disconnect and runtime close preserve unknown delivery and send a bound browser.cancel when possible.

The private sender state is Prepared -> Emitting -> Sent. Cancellation during Emitting commits unknown to the waiter but retains the ownership slot and defers browser.cancel until the browser.request callback returns. No global or per-request mutex is held across EventSink; synchronous completion/cancellation callbacks remain usable. An internal emission guard finalizes the slot on return and removes it without another callback during panic unwinding. An already committed cancellation rejects late completion; a completion committed first keeps its known result. Failed or uncertain operations are never automatically replayed.

Completion validates the credential and every ownership field before removing a pending request. Wrong IDs, wrong host generations, cross-scope/profile callbacks, unsent callbacks, incompatible result shapes, stale revisions and duplicate/late callbacks cannot satisfy another waiter. The first committed completion/cancellation wins. No operation is automatically retried, including reads.

## JSONL adapter draft

The module draft is separate from sdk-bridge.v1 action registration. Rust emits an event through the existing EventSink; the bridge still supplies its normal outer prompt.event/request ID.

~~~json
{"type":"browser.request","protocol":"reverie.browser.v1","request_id":"kernel-request-id","host":{"host_id":"registered-host","generation":"kernel-generation"},"scope":{"project_root":"canonical-project","session_id":"session","run_id":"run"},"profile":{"mode":"ephemeral","profile_id":"explicit-profile"},"action":{"action":"observe","tab_id":"owned-tab"}}
~~~

A private control channel supplies the registration token to the trusted adapter. The adapter returns a separate completion control request containing the same protocol/request/host/scope/profile and a typed result. A JSONL-facing caller first authenticates the private token and then invokes complete; public browser events contain no token. Root will choose and guard the actual SDK action names during integration.

BrowserAction uses a strict action tag. Its finite payloads are open(url), list, observe(tab_id), click(target, element_id), type(target, element_id, text, replace), scroll(target, optional element_id, delta_x, delta_y), key(target, finite key, shift), navigate(target, url) and close(target). BrowserTarget contains tab_id, observation_id and revision. URLs permit HTTP(S) without embedded user credentials and the exact initial about:blank value; arbitrary schemes, selectors, CDP commands and scripts have no executable path.

BrowserCompletion carries protocol, request_id, host, scope, profile and outcome. Outcome is either {status: completed, result: ...} or {status: failed, delivery: not_started/unknown/completed}. Result uses a strict type tag: opened(tab), listed(tabs), observed(observation), changed(tab) or closed(tab_id), and must match the original action. A valid completed response returns BrowserReply with delivery=completed. An observation reply's observation_id is issued by the core; BrowserReply::target() constructs its bound BrowserTarget. Failure text is generated from stable codes and does not reflect raw adapter or malformed-input strings.

browser.cancel contains only protocol/request/host/scope/profile binding and the delivery classification. The adapter must cancel only that owned request, must not replay it and must report later unsolicited tab/document changes through the trusted invalidation path. A reconnect obtains a new host generation; old tabs/observations/credentials are unusable.

## Prepared verification scope

1. Explicit registration trust and profile mode; unsupported actions/profiles cause no adapter request.
2. Actual async request/event/oneshot completion for open, list, observe and the finite tab actions.
3. Bad request IDs, forged credentials, wrong host generation, cross-scope/profile, unsent and duplicate completion rejection.
4. Observed element binding and stale revision rejection before dispatch and at completion.
5. Cancellation before dispatch is not_started; transmitted cancellation/timeout/drop/disconnect is unknown and is never replayed.
6. Same-scope in-flight serialization, caller-drop cleanup and safe runtime shutdown.
7. Strict JSON decoding, bounded output and refusal of arbitrary CDP/JavaScript/selector fields.

The 14 standalone Rust tests are now in browser/tests.rs. They exercise the actual EventSink/oneshot paths with an in-process trusted test adapter, including reentrant cancellation, Barrier-controlled concurrent cancellation, immediate completion, unsupported controls, bad completion bindings, unknown read timeout/cancellation/drop, scope/disconnect/close cancellation, stale observations, invalid/cross-scope tab results, emission-panic cleanup, retired generations and generated type/wire-enum consistency without credentials. Fixture directories are created beneath this repository's .runtime/rust-3.0/browser-library-tests; no real browser profile or credential store is accessed.

rustfmt --edition 2024 ReverieCli-rs/crates/core/src/browser.rs parsed and formatted the standalone module. It does not prove name/type resolution or test results. Root must register the module before running cargo test --manifest-path ReverieCli-rs/Cargo.toml -p reverie-core browser:: --locked, followed by its unified checks. A later Node adapter fixture may test real JSONL routing after root integrates the runtime; passing an in-memory adapter is not an Electron browser or website result.

## Remaining product work

1. Trusted Host and SDK control registration, permission/approval routing, run journaling and model tool catalogue integration are not implemented by this module.
2. Electron WebContentsView creation, isolated browser partitions, visible sidebar tabs and renderer interaction are not implemented by this module.
3. The maintainer selected a dedicated persistent profile with an ephemeral option and the same on-demand Electron component for CLI. Product wiring and packaging remain pending.
4. Actual webpage navigation, observation, element input, manual changes, redirection, downloads/uploads and popup handling remain unverified.
5. Real single-display 100/125/150/200 percent DPI, capture/crop/resize coordinates and input-effect readback remain unverified.
6. Browser process/debugger/session cleanup, crash recovery and four-platform final assets remain unverified.
7. External service login, personal browser state, real credentials and Chrome extension/sync compatibility are not established by this library.

This task adds only first-party MIT source and uses existing Rust dependencies. It does not add a fifth market, a complete IDE, copied browser automation code or a new browser engine dependency.
