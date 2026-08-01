# Reverie RATS / RTP

RATS is the Reverie ecosystem's multi-provider agentic-tool runtime and service
layer. RTP (`reverie.rtp/1`) is its versioned tool protocol. Explicitly
supported Reverie/Rilance applications can each be RATS providers; Reverie CLI
is the client, management center, active-provider selector, and AI scheduling
environment. Together they form the Reverie Agentic Developer Environment
(RADE). RATS is not an Engine-only protocol.

The current production allowlist and user-selectable provider list contain one
implemented entry: `reverie.engine` (Reverie Engine). This describes present
product availability, not a protocol limitation or permanent uniqueness rule.
The Engine starts its loopback service with the editor, but Reverie CLI does not
show it until a registered executable-local descriptor passes a live identity
handshake and does not enable any native tool until the user explicitly turns
that provider on in the desktop RATS page.

## Local data and trust boundary

Both products keep their state beside their own executable:

```text
<provider-exe-root>/<provider-defined-local-root>/Services/*.json
<provider-exe-root>/<provider-defined-local-root>/Audit/*.jsonl
<cli-exe-root>/.reverie/rats/settings.json
<cli-exe-root>/.reverie/rats/diagnostics.jsonl
```

Settings use schema version 2 with `enabledProviders` entries keyed by
`providerId` plus executable and permissions. Older `enabledEngines` settings
are migrated deterministically and idempotently; the state response also keeps
a deprecated Engine-only mirror until packaged Desktop clients migrate to
`ratsRegisterProvider` and `ratsSetProviderEnabled`.

The CLI accepts only discovery descriptors that declare the exact
`reverie.rats.discovery/1` schema, `reverie.rtp/1`, an allowlisted provider
identity, an absolute provider executable path, a valid service id and token,
an endpoint exactly matching `http://127.0.0.1:<port>/rtp`, and a descriptor
parent matching that provider's registry-defined discovery root. It then
requires live `hello` values to match the descriptor. Unknown, mismatched, or
offline entries are omitted from the service list. Control and session tokens
remain only in the Python core process. Renderer responses, settings, and
diagnostics contain neither token nor tool arguments.

`REVERIE_RATS_DISCOVERY_ROOTS` can add local discovery directories for a
development/test process. Its value is not copied into the settings file. The
desktop file picker registers a supported provider through its provider
adapter; the current adapter derives `ReverieLocal/RATS/Services` for
Reverie Engine.
There is no port scan, network broadcast, or arbitrary local-server catalog.

Anonymous presence probes have a 350 ms deadline, normal session/catalog
requests use 1.5 seconds, and native tool calls use a separate 12-second bound.
The diagnostic log is capped and rotated locally; the GUI drawer shows recent
discovery, rejection, handshake, timeout, operation, and timing records so a
missing or unexpected provider can be audited without waiting for MCP-style
configuration timeouts.

## Desktop workflow

1. Start a supported Reverie/Rilance provider application. Its RATS service
   publishes a registry-compatible executable-local descriptor while alive.
2. Open **RATS** in Reverie Desktop and register the provider executable if its
   discovery directory is not already known.
3. Select the exact permission set and enable the service. This opens one RTP
   session owned by the Python core.
4. Inspect the compact catalog, provider identity, handshake latency, PID,
   endpoint, permission policy, and individual full definitions. Toggle
   **RTP log** to audit discovery and request timing.
5. Disable the service to close the session and immediately remove its native
   tools from the model-facing catalog.

Selections persist by stable provider ID plus executable path. A saved offline
provider is reconnected after it starts and the CLI core next refreshes its
local catalog.
Changing permissions closes the old session and opens a new one, rotating the
session token.

## Token-efficient tool exposure

The compact RTP catalog is visible in the RATS page, but Reverie does not inject
all native schemas into every model request. On session open, only `ping`,
`version`, `get_status`, and `project.status` are described when their schemas
are available. These become model-safe names such as
`rats_reverie_engine_project_status`.

The always-available `rats_catalog` tool searches enabled providers' compact catalogs
and requests full definitions only for relevant matches. Loaded definitions are
registered in `ToolExecutor` on the next agent step, so the normal provider tool
schema channel carries the exact request schema without duplicating it in the
system prompt. The Tools page reads that same live catalog and labels RATS tools
separately from built-ins, MCP tools, and runtime plugins.

Tools without an RTP request schema remain visible in the compact catalog but
are not promoted to direct model functions. This is intentional: guessing an
argument contract would be less reliable than leaving the tool unavailable
until the Engine publishes a versioned schema.

## Verified scope and remaining work

The provider-neutral client covers typed allowlisted provider specs,
descriptor/root and live identity validation, fast-fail deadlines, bounded
sanitized diagnostics, versioned persisted selections, permission-controlled
session open/rotation/close, live status, compact catalog display, progressive
definition loading, dynamic native tool calls, the toggleable desktop log
drawer, and graceful shutdown. Unit tests use only repository-local test
directories. The real end-to-end test places its project, CLI state, logs, and
temporary files under the selected Engine executable's `ReverieLocal`
directory.

Focused provider tests pass 8/8. The Python suite passes 831/831; the desktop
suite passes 53 tests with 1 existing skip (54 total), with TypeScript
typecheck and production build passing; and real desktop-core→RTP E2E passes
against exact Engine binary `0.1.dev.custom_build.36888aaf3`. The RATS page and
log drawer are interaction-tested but have not received a current real-window
visual inspection.

RATS is designed for multiple explicitly supported Reverie/Rilance providers,
but Reverie Engine is the only provider currently implemented, verified, and
shown in the active selection list. Each additional provider needs a versioned
identity/capability contract, an explicit client allowlist entry, and real
cross-product E2E before it can appear. Arbitrary third-party package discovery,
download, or installation is outside the current RATS model. Multi-client
sessions, streamed RTP task events, and remote transports also remain open and
must not be presented as complete.

The provider-neutral client cleanup task and its acceptance criteria are in
[`RATS_PROVIDER_GENERALIZATION_HANDOFF.md`](RATS_PROVIDER_GENERALIZATION_HANDOFF.md).
