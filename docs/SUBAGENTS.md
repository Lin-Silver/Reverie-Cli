# Managed SubAgents

This guide documents Reverie's managed SubAgent runtime.

## Scope

SubAgents are managed by a main Agent in `reverie` or `computer-controller` mode. NVIDIA-backed main Agents can use them. A child can use a selected non-desktop workflow mode, but `computer-controller` is normalized to `reverie` so the main Agent remains the only desktop actor.

Each Subagent is intentionally small as configuration:

- `id`: the stable user-facing Subagent name, such as `subagent-001`
- `model_ref`: the default model selected by the user
- `color`: the stable log color for that Subagent
- `mode`: the child workflow mode, defaulting to `reverie`
- `enabled`, `created_at`, `updated_at`: lifecycle metadata

At runtime the child receives its mode prompt, active rules, tools, MCP resources, runtime plugins, skills, and workspace services. It does not inherit the main conversation, `SessionManager`, operation history, or rollback manager. Read access is bounded by `read_scope`; writes are blocked unless an explicit `write_scope` is assigned.

## User Flow

Use `/mode reverie` or `/mode computer-controller` before working with SubAgents.

| Command | Purpose |
| --- | --- |
| `/subagent` | Open the Subagent roster TUI |
| `/subagent create` | Open the model selector and create a Subagent |
| `/subagent list` | Show configured Subagents, colors, and model sources |
| `/subagent model <id>` | Change one Subagent's default model |
| `/subagent run <id> <task>` | Run a direct delegated task |
| `/subagent delete <id>` | Delete one Subagent |

During normal chat, the main agent can call the `subagent` tool:

```text
subagent(action="list")
subagent(action="create", subagent_id="coder", mode="reverie")
subagent(action="delegate", subagent_id="subagent-001", task="Inspect the CLI command parser and summarize risks.")
subagent(action="start", subagent_id="coder", task="Write the scoped script.", write_scope=["scripts"])
subagent(action="status", run_id="subagent-001-...")
subagent(action="wait", run_id="subagent-001-...", timeout=30)
subagent(action="cancel", run_id="subagent-001-...")
```

Nested Subagent delegation is blocked so a delegated worker cannot spawn another delegated worker.

## Logging

Streamed tool events now include `agent_id` and `agent_color`. The TUI uses these fields to prefix live and completed tool rows with a colored Subagent ID, making it clear whether a log entry came from the main agent or a delegated Subagent.

## Runtime Notes

Subagent run logs are persisted under the current project cache:

```text
.reverie/projects/<project-path-key>/subagents/<subagent-id>/runs/<run-id>.json
```

The run log records the Subagent ID, resolved model, task assignment, status, summary, and error details if the run failed.

Each SubAgent also owns an isolated selective-memory file:

```text
.reverie/projects/<project-path-key>/subagents/<subagent-id>/context.json
```

Use `remember`, `context`, `forget`, and `clear_context` to curate it. `delegate` and `start` inject only the requested `context_keys`; `retain_summary=true` stores the completed response as `last_summary`.

Background runs support `start`, `status`, `wait`, and cooperative `cancel`. Completed run status can be restored from its persisted JSON log after a CLI restart.

## Validation

Tests cover model-backed delegation, scoped writes, isolated parent/child sessions, background lifecycle, cancellation, selective context injection, retained summaries, NVIDIA/Computer Controller visibility, and read-scope query enforcement.
