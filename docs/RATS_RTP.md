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
requires live `hello` values to match the descriptor. On Windows, the current
`reverie.engine` adapter additionally requires PE VersionInfo `ProductName` to
be exactly `Reverie Engine` or `Reverie Engine (Console)`, queries the live PID
with `QueryFullProcessImageNameW`, and requires that process image to match the
descriptor executable. Unknown, mismatched, dead, or offline entries are
omitted from the service list.

The control token is a bearer capability stored in the Engine's live discovery
descriptor; it is not confined to the Python process. On the client side, the
independent session token is returned only to the Python core; the Engine keeps
the current token in memory to validate requests. Neither token is written to
CLI settings, diagnostics, or renderer responses, and diagnostics also omit
tool arguments. Windows ProductName and PID-image matching prevent ordinary
accidental or text-file impersonation, but an unsigned local binary can copy
version metadata, and PID-image matching does not prove that the PID owns the
advertised TCP port. Any same-user process able to read the Engine descriptor
remains inside the current local trust boundary.

For every parsed RTP response, the Python client requires an exact echoed
request ID and verifies `result_sha256` against the response's raw canonical
`result` or `error` value span. This deliberately preserves Godot's float
formatting. The Engine contract serializes both the hashed value and outer
envelope with `JSON::stringify(value, "", true, false)`. The unkeyed hash detects
inconsistency and supports audit correlation; it does not authenticate the
server.

`REVERIE_RATS_DISCOVERY_ROOTS` can add local discovery directories for a
development/test process. Its value is not copied into the settings file. The
desktop file picker registers a supported provider through its provider
adapter; the current adapter derives `ReverieLocal/RATS/Services` for
Reverie Engine. Windows editor builds also provide a small
`reverie.windows.editor.x86_64.terminal.exe` console host. The picker accepts
that file only when its PE ProductName is exactly `Reverie Engine Terminal`
and the adjacent main executable independently passes the normal Engine
ProductName check; settings, discovery, and live PID-image validation then use
the adjacent real Engine executable. The terminal wrapper itself is never
treated as the RTP service process.
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
descriptor/root and live PID-image identity validation, exact response-ID and
canonical result/error-hash checks, fast-fail deadlines, bounded sanitized
diagnostics, versioned persisted selections, permission-controlled session
open/rotation/close, live status, compact catalog display, progressive
definition loading, schema-sensitive dynamic-tool regeneration, native task
calls, the toggleable desktop log drawer, and graceful shutdown. Socket I/O is
serialized per session without holding the global state lock. Automatic task
synchronization skips terminal tasks; each session retains every active task
and at most 64 terminal records. The renderer keeps at most 128 task events and
the latest 64 Ki characters of logs for the selected task.

Unit tests use only repository-local test directories. The real end-to-end
test creates a UUID-named, owner-marked project, CLI state, log, and temporary
tree under the selected Engine executable's `ReverieLocal` directory. It binds
the new descriptor to the exact launched PID and executable and revalidates
those ownership fields before deleting only that test descriptor.

Working-tree revalidation on 2026-08-12 passed the RATS runtime file with 34
tests and 1 conditional skip, the real Engine E2E with 10 tests, and the complete
Python suite with 939 tests and 2 conditional skips. The focused RTP desktop
interaction selection passed 16/16; the complete desktop suite passed 63 tests
with 1 conditional skip. TypeScript typecheck and the production build passed.
The verified Windows terminal wrapper normalization is included in the runtime
file. A direct cross-repository check selected the real terminal executable,
persisted its verified sibling main Engine executable, connected the
`reverie.engine` service, and loaded 19 tools under `read`. The real provider
tests used the current working-tree Engine binary reporting
`0.1.dev.custom_build.8917976f3`; that version string identifies the baseline
HEAD and does not encode the uncommitted Engine fixes compiled into the binary.
The RATS page and task workspace are interaction-tested but have not received a
current real-window visual inspection.

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
