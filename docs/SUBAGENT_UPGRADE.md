# Reverie Subagent Upgrade

This note documents the base-Reverie Subagent capability introduced in v2.3.1.

## Scope

Subagents are enabled only when the active mode is `reverie`. They are disabled in `reverie-atlas`, `reverie-gamer`, `spec-driven`, `spec-vibe`, `writer`, `reverie-ant`, and `computer-controller`.

Each Subagent is intentionally small as configuration:

- `id`: the stable user-facing Subagent name, such as `subagent-001`
- `model_ref`: the default model selected by the user
- `color`: the stable log color for that Subagent
- `enabled`, `created_at`, `updated_at`: lifecycle metadata

The Subagent does not define a separate personality or tool profile. At runtime it inherits the same base Reverie system prompt, active rules, tools, MCP tools/resources, runtime plugins, skills, and workspace services as the main agent. The only task objective is the assignment supplied by the main agent.

## User Flow

Use `/mode reverie` before working with Subagents.

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
subagent(action="delegate", subagent_id="subagent-001", task="Inspect the CLI command parser and summarize risks.")
subagent(action="status", run_id="subagent-001-...")
```

Nested Subagent delegation is blocked so a delegated worker cannot spawn another delegated worker.

## Logging

Streamed tool events now include `agent_id` and `agent_color`. The TUI uses these fields to prefix live and completed tool rows with a colored Subagent ID, making it clear whether a log entry came from the main agent or a delegated Subagent.

## Runtime Notes

Subagent run logs are persisted under the current project cache:

```text
.reverie/project_caches/<project-key>/subagents/<subagent-id>/runs/<run-id>.json
```

The run log records the Subagent ID, resolved model, task assignment, status, summary, and error details if the run failed.

## Validation

The release includes a real local OpenAI-compatible test server that drives an actual Subagent run. The fake model calls Reverie's `create_file` tool, the Subagent writes a file inside the workspace, and the test verifies both the delegated run status and the produced file.
