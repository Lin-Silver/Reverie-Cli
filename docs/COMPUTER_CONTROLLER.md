# Computer Controller

Computer Controller uses an embedded Python implementation of the
Open Computer Use MCP contract. It does not start an MCP child process, and the
legacy single-surface `computer_control` tool it replaced has been removed.

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

plus one Reverie addition:

- `launch_app` — start a program, document, or URL that is not running yet.

Call `get_app_state` once per assistant turn before acting on an app. The
result contains a screenshot and an indexed Windows UI Automation tree.
Prefer `element_index` and semantic actions. Screenshot-relative coordinates
are the fallback for canvas surfaces that do not expose useful accessibility
elements.

`launch_app` exists because the upstream contract can only act on windows that
already exist, which left "open Edge" solvable only by hunting for a desktop
icon. It resolves bare executable names (`msedge`, `notepad`) through the same
App Paths lookup the Run dialog uses, accepts full paths, documents, and URLs,
and takes an `arguments` string — so `launch_app(target="msedge",
arguments="https://www.youtube.com")` opens the browser directly on the page.

### Action verification

Every action tool observes the desktop before and after it acts and reports
what changed: new or closed windows, retitled windows, minimize/restore, the
foreground window, and the focused element. `set_value` reads the value back,
and `scroll` reports the scroll percentage it moved through.

This matters because unconditional success reports are indistinguishable from
no-ops. A single left click on a desktop icon only *selects* it, so a report of
"No window, title, or focus change was observed" is the signal to use
`perform_secondary_action(action="Invoke")`, `click_count=2`, or `launch_app`
instead of continuing as though the app had opened.

### Keyboard input

`type_text` sends literal text. Braces are escaped before they reach
`uiautomation`, which otherwise reads `{a}` as the key `a` and raises on
`{braces}`; parentheses, `+`, `^`, `%` and `~` are already literal because they
only group keys while a modifier is being held.

Keystrokes are delivered one Unicode event at a time and Windows can mistype
them under load, so `type_text` reads the focused field back and compares it
with what was sent. It reports `Typed N character(s)` only when the text is
actually there; otherwise it says the send is unverified and quotes what the
field really holds, because a silently mistyped URL is worse than a failure —
the model treats it as fact. `set_value` writes an exact string in one step and
is the better tool when the target exposes a value.

`press_key` diffs the focused value as well as the window list, so a key that
only edits text — Notepad's F5 timestamp, for instance — is reported as a real
change instead of "nothing happened".

### Coordinate space

Window captures larger than 1400px on the long edge are downscaled before they
are sent to the model. The accessibility-tree frames and the `x`/`y` arguments
of `click` and `drag` are expressed in that same downscaled screenshot space,
and `get_app_state` states the scale factor whenever it is not 1.0, so there is
only ever one coordinate system per observation.

### Window selection

`get_app_state` and the action tools rank candidate windows for an app: a
visible window beats a minimized one, the foreground window beats a background
one, then the largest window, then the window handle for stability. A target
that resolves only to a minimized window is restored first, because a minimized
window reports no accessible bounds at all.

Ranking happens once, in `get_app_state`. Every action then reuses the window
handle from that observation instead of resolving the app by name again, so an
app with two windows cannot move the target between the screenshot the model
read and the click or keystroke based on it.

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
