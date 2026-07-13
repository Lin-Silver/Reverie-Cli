# Permission Levels and Dangerous Operations

Reverie applies tool permissions in software, both when tools are advertised to the model and immediately before execution. Configure the level in `config.json`:

```json
{
  "security": {
    "permission_level": "workspace_write"
  }
}
```

| Level | Capabilities |
| --- | --- |
| `read_only` | Retrieval, inspection, and other non-mutating local tools |
| `workspace_write` | Read-only capabilities plus workspace file editing; this is the default |
| `developer` | Workspace editing plus audited shell commands, web requests, and media generation |
| `full_control` | Developer capabilities plus interactive browser, desktop control, runtime plugins, and SubAgents |

Higher levels include lower-level capabilities. Invalid values fall back to `workspace_write`.

When an interactive CLI session needs a tool above the configured level, Reverie presents a unified approval prompt: `once`, `session`, or `deny`. The default is `deny`. A one-time or session approval does not modify `config.json`; headless and SDK paths deny elevation unless the embedding host supplies an explicit approval handler.

No level permits disk formatting, raw-disk overwrite, boot configuration changes, host shutdown/restart, terminal-driven deletion/moves, or directory deletion. `delete_file` requires explicit confirmation and refuses files larger than 1 GiB. When that limit is reached, the AI is instructed to perform an in-depth review and confirm the target; cleanup must then be performed separately by the user.

This is capability isolation, not an operating-system sandbox. A process allowed at `developer` level can execute project code and access networks under the current user account. Use `workspace_write` unless command execution is needed, and enable `full_control` only for a reviewed task.
