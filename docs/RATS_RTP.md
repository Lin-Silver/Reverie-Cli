# Reverie RATS / RTP

RATS is Reverie's local agentic-tool service layer. RTP (`reverie.rtp/1`) is
the versioned wire protocol used between Reverie CLI and a running Reverie
Engine. The Engine starts its loopback service with the editor; Reverie CLI
does not enable any native tool until the user explicitly enables that Engine
in the desktop RATS page.

## Local data and trust boundary

Both products keep their state beside their own executable:

```text
<engine-exe-root>/ReverieLocal/RATS/Services/*.json
<engine-exe-root>/ReverieLocal/RATS/Audit/*.jsonl
<cli-exe-root>/.reverie/rats/settings.json
```

The CLI accepts only discovery descriptors that declare the exact
`reverie.rats.discovery/1` schema, `reverie.rtp/1`, an absolute Engine path, a
valid service id and token, and an endpoint exactly matching
`http://127.0.0.1:<port>/rtp`. Control and session tokens remain only in the
Python core process. Renderer responses and settings contain neither token.

`REVERIE_RATS_DISCOVERY_ROOTS` can add local discovery directories for a
development/test process. Its value is not copied into the settings file. The
desktop file picker registers an Engine by deriving
`ReverieLocal/RATS/Services` from the selected executable.

## Desktop workflow

1. Start Reverie Engine. Its RATS service publishes an executable-local
   descriptor while the process is alive.
2. Open **RATS** in Reverie Desktop and add the Engine executable if its
   discovery directory is not already known.
3. Select the exact permission set and enable the service. This opens one RTP
   session owned by the Python core.
4. Inspect the compact catalog, connection state, PID, endpoint, permission
   policy, and individual full definitions.
5. Disable the service to close the session and immediately remove its native
   tools from the model-facing catalog.

Selections persist by stable Engine executable path. A saved offline Engine is
reconnected after it starts and the CLI core next refreshes its local catalog.
Changing permissions closes the old session and opens a new one, rotating the
session token.

## Token-efficient tool exposure

The compact RTP catalog is visible in the RATS page, but Reverie does not inject
all native schemas into every model request. On session open, only `ping`,
`version`, `get_status`, and `project.status` are described when their schemas
are available. These become model-safe names such as
`rats_reverie_engine_project_status`.

The always-available `rats_catalog` tool searches the Engine's compact catalog
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

The implemented slice covers local discovery, descriptor validation, persisted
selection, permission-controlled session open/rotation/close, live status,
compact catalog display, progressive definition loading, dynamic native tool
calls, desktop integration, and graceful shutdown. Unit tests use only
repository-local test directories. The real end-to-end test places its project,
CLI state, logs, and temporary files under the selected Engine executable's
`ReverieLocal` directory.

Third-party RATS package discovery, signature/trust metadata, download/update,
and installation are not implemented by this slice. Multi-client sessions,
streamed RTP events, and remote transports also remain open. They must not be
presented as complete in the UI or roadmap.
