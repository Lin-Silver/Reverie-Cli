# Permission Levels and Dangerous Operations

Reverie applies tool permissions in software, both when tools are advertised to the model and immediately before execution. Configure the level in `config.json`:

```json
{
  "security": {
    "permission_level": "full_control"
  }
}
```

| Level | Capabilities |
| --- | --- |
| `read_only` | Retrieval, inspection, and other non-mutating local tools |
| `workspace_write` | Read-only capabilities plus workspace file editing |
| `developer` | Workspace editing plus audited shell commands, web requests, and media generation |
| `full_control` | All registered tool classes, including interactive browser, desktop control, runtime plugins, and SubAgents; this is the default |

Higher levels include lower-level capabilities. Missing or invalid values fall back to `full_control`, so models receive the complete tool surface by default. Every tool call is still checked by the software policy immediately before execution.

When an interactive CLI session needs a tool above the configured level, Reverie presents a unified approval prompt with four answers: `once` (allow this call), `session` (allow this tool for the rest of the session), `deny`, and a free-form message. The default is `deny`. Typing a message denies the call and relays your words back to the model as the tool result, so you can redirect it ("use the staging table instead") without ending the turn. A one-time or session approval does not modify `config.json`; headless and SDK paths deny elevation unless the embedding host supplies an explicit approval handler.

No level permits disk formatting, raw-disk overwrite, boot configuration changes, host shutdown/restart, terminal-driven deletion/moves, inline interpreter code, or directory deletion. `delete_file` requires explicit confirmation and refuses files larger than 1 GiB. When that limit is reached, the AI is instructed to perform an in-depth review and confirm the target; cleanup must then be performed separately by the user.

## Approval modes

Permission *levels* above are a hard capability ceiling enforced in software. Layered on top is an approval *mode* that decides how much of the allowed surface still gets shown to you before it runs. Set it in the settings UI, with `/permission mode`, or directly:

```json
{
  "security": {
    "permission_mode": "auto_check",
    "strict_allow_read_only": false,
    "review": {
      "model_mode": "follow",
      "source": "",
      "model": "",
      "timeout": 45,
      "max_tokens": 900,
      "approve_risk_at": "medium",
      "fail_open": false,
      "review_read_only": false
    }
  }
}
```

| Mode | Behavior |
| --- | --- |
| `default` | Today's behavior: the built-in software policy decides, and only an above-level call raises a prompt |
| `auto_check` | After every model response, its tool calls are sent to a model in one extra stateless call that rates their risk; low-risk calls proceed and risky ones stop for you |
| `strict` | Every tool call waits for your explicit answer |

`default` is the default. Unknown values fall back to it.

### Auto Check

Each review is an independent API call with a fixed system prompt and no conversation history, so it stays cheap and cannot be steered by earlier turns. The reviewer must answer in a fixed JSON shape; Reverie parses it, tolerating fenced or partially truncated output. A batch of calls takes the highest risk any single call scored — review can only raise the verdict, never lower it. An unrecognized risk word is treated as `medium` rather than assumed safe.

`approve_risk_at` is the level at which Reverie stops and asks you; that level and everything above it pause. `fail_open` decides what happens when the reviewer *itself* fails (network error, unparseable reply): off (the default) denies the call, on lets it through. `review_read_only` includes provably read-only calls in review, which is off by default since reading cannot mutate the workspace.

By default the reviewer is the model you are chatting with (`model_mode: "follow"`). Pin a cheaper dedicated reviewer with `/permission model <source> <name>` — any configured source works, and `standard` accepts either a model name or its index in the `models` list.

### Strict

Strict asks for every call. `strict_allow_read_only` lets provably read-only tools run unprompted so the mode stays usable during exploration; it is off by default. Note this is a different switch from `review.review_read_only`, which only affects Auto Check.

### Commands

`/permission` with no argument prints the current policy and the full subcommand list. The family covers `mode`, `threshold` (alias `risk`), `model`, `readonly`, `review-read-only`, `timeout`, `max-tokens`, `fail-open`, and `level`. Friendly aliases are accepted for modes: `auto` → `auto_check`, `always_ask` → `strict`, `builtin` → `default`. Every change is validated, persisted to `config.json`, and reinitializes the agent; a rejected value leaves the stored policy untouched.

## Workspace checkpoints and deletion backups

Each executed AI tool call is bracketed by an internal shadow-Git checkpoint stored beside the executable at `.reverie/projects/<project-path-key>/git-checkpoints/`. This repository is bare and separate from the workspace's own `.git`; it does not create branches, commits, staged changes, or hooks in the user's repository. It protects ignored source/configuration files independently of the user's `.gitignore`, while excluding generated dependency trees, caches, build outputs, reference corpora, and large archive formats from the automatic whole-workspace snapshot. A changed checkpoint triggers an incremental Context Engine refresh.

Only `delete_file` may leave an existing workspace file deleted. Before deletion it force-checkpoints the target even when `.gitignore` excludes it, copies the file to `.reverie/projects/<project-path-key>/deleted-files/<timestamp>/<workspace-relative-path>`, and appends an audit record. If any other tool removes a checkpointed file, Reverie restores it and returns a policy failure. Directory deletion remains unavailable to AI tools.

All explicit path arguments of mutating tools must resolve within the active workspace. `command_exec` also rejects outside working directories, absolute or parent-traversing path arguments, direct delete/move commands, dangerous disk commands, opaque commands, and inline interpreter code. Reviewed workspace script files may still be executed at `developer` level; their known deletion APIs are scanned and any resulting deletion of checkpointed workspace files is restored.

This is capability isolation plus workspace outcome recovery, not an operating-system sandbox. A process allowed at `developer` level still runs under the current user account and can access networks. Software path checks reject explicit outside-workspace targets, but arbitrary third-party executables cannot be proven harmless without an OS sandbox. Full Control exposes all registered tools, while the software policy continues to block prohibited operations and enforce path, deletion, and approval rules.
