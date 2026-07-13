# Security Policy

## Supported version

Security fixes are applied to the latest code on `main`. Reverie CLI is alpha software and should not be treated as an operating-system sandbox.

## Reporting a vulnerability

Do not open a public issue for an unpatched vulnerability or include credentials, personal data, or exploit payloads in public reports. Contact the maintainer at `raiden@reverie.dev` with the affected version, impact, reproduction steps, and suggested remediation. You should receive an acknowledgement within seven days.

## Runtime boundary

Reverie enforces capability levels in software before tool execution. The default is `workspace_write`; shell, interactive browser, desktop control, runtime plugins, and SubAgents require explicit higher levels. Disk formatting, raw-disk writes, boot modification, and host shutdown are always blocked. Generic terminal deletion and directory deletion are disabled at every level.

Provider credentials should be supplied through environment variables where supported. Never commit `.reverie/`, `.env`, API keys, browser profiles, or command audit logs.
