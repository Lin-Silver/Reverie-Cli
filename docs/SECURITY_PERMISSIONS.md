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

When an interactive CLI session needs a tool above the configured level, Reverie presents a unified approval prompt: `once`, `session`, or `deny`. The default is `deny`. A one-time or session approval does not modify `config.json`; headless and SDK paths deny elevation unless the embedding host supplies an explicit approval handler.

No level permits disk formatting, raw-disk overwrite, boot configuration changes, host shutdown/restart, terminal-driven deletion/moves, inline interpreter code, or directory deletion. `delete_file` requires explicit confirmation and refuses files larger than 1 GiB. When that limit is reached, the AI is instructed to perform an in-depth review and confirm the target; cleanup must then be performed separately by the user.

## Workspace checkpoints and deletion backups

Each executed AI tool call is bracketed by an internal shadow-Git checkpoint stored beside the executable at `.reverie/projects/<project-path-key>/git-checkpoints/`. This repository is bare and separate from the workspace's own `.git`; it does not create branches, commits, staged changes, or hooks in the user's repository. It protects ignored source/configuration files independently of the user's `.gitignore`, while excluding generated dependency trees, caches, build outputs, reference corpora, and large archive formats from the automatic whole-workspace snapshot. A changed checkpoint triggers an incremental Context Engine refresh.

Only `delete_file` may leave an existing workspace file deleted. Before deletion it force-checkpoints the target even when `.gitignore` excludes it, copies the file to `.reverie/projects/<project-path-key>/deleted-files/<timestamp>/<workspace-relative-path>`, and appends an audit record. If any other tool removes a checkpointed file, Reverie restores it and returns a policy failure. Directory deletion remains unavailable to AI tools.

All explicit path arguments of mutating tools must resolve within the active workspace. `command_exec` also rejects outside working directories, absolute or parent-traversing path arguments, direct delete/move commands, dangerous disk commands, opaque commands, and inline interpreter code. Reviewed workspace script files may still be executed at `developer` level; their known deletion APIs are scanned and any resulting deletion of checkpointed workspace files is restored.

This is capability isolation plus workspace outcome recovery, not an operating-system sandbox. A process allowed at `developer` level still runs under the current user account and can access networks. Software path checks reject explicit outside-workspace targets, but arbitrary third-party executables cannot be proven harmless without an OS sandbox. Full Control exposes all registered tools, while the software policy continues to block prohibited operations and enforce path, deletion, and approval rules.
