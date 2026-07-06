# Computer Controller

Computer Controller uses an embedded Python implementation of the
Open Computer Use MCP contract. It does not start an MCP child process and
does not call the legacy `computer_control` tool.

## Desktop tools

The mode exposes the nine upstream-compatible tools:

- `list_apps`
- `get_app_state`
- `click`
- `perform_secondary_action`
- `scroll`
- `drag`
- `type_text`
- `press_key`
- `set_value`

Call `get_app_state` once per assistant turn before acting on an app. The
result contains a screenshot and an indexed Windows UI Automation tree.
Prefer `element_index` and semantic actions. Screenshot-relative coordinates
are the fallback for canvas surfaces that do not expose useful accessibility
elements.

The Windows adapter runs in the Reverie Python process through
`uiautomation`; no Go executable or generated PowerShell runtime is required.
Attribution and the pinned upstream commit are recorded in
`reverie/computer_use/ATTRIBUTION.md`.

## Main Agent and SubAgents

The main Computer Controller owns desktop state. It does not receive Reverie's
file mutation or shell execution tools. Repository inspection, script writing,
code changes, and verification are delegated to a scoped `reverie` SubAgent.

SubAgents never receive desktop-control tools. Their session state is isolated
from the main Controller session, and their final response is returned to the
main Agent for the next decision. Use selective context keys rather than
copying the main conversation into a child.

## Observation storage

Screenshots are stored below the dedicated Computer Controller data root in
`computer_use/observations/`. Inline image data is relayed only to the current
model request. Persisted conversation history keeps the textual result and
image path, not the Base64 payload.
