# Upstream attribution

- Source: https://github.com/zhaoxuya520/reverse-skill
- Revision: `7e2097fd90d25c2f976f6eba26d6c00aa88051df`
- Imported: 2026-09-04
- Main license: `upstream/LICENSE` (MIT, Copyright 2026 zhaoxuya520).
- CTF sidecar: `upstream/CTF-Sandbox-Orchestrator/LICENSE` (GPL-3.0).
- Upstream files retain their original layout and license notices.
- External tools are not included as installed tools.

The Reverie adapter is the adjacent SKILL.md. Nested upstream skills are
supporting resources, not separate auto-discovered entries.

Windows antivirus blocked these upstream reference documents during import.
They are omitted; protection was not disabled or bypassed:

- `skills/pentest-tools/src-hunter/references/payloader/waf-bypass.md`
- `skills/pentest-tools/src-hunter/references/payloader/by-category/web/xss跨站脚本.md`
- `skills/pentest-tools/src-hunter/references/payloader/tools/系统命令.md`
- `skills/pentest-tools/src-hunter/references/playbooks/xss.md`
- `skills/pentest-tools/src-hunter/references/playbooks/path-traversal.md`

If a scenario references an omitted document, report it as unavailable.

## Python 2.5.5 clean installation

Clean Windows package verification with Microsoft Defender engine 1.1.26100.4
and security intelligence 1.463.398.0 quarantined two further reference documents
during standalone CLI extraction and desktop installation. They are omitted
from the Python 2.5.5 distribution:

- `skills/pentest-tools/src-hunter/references/playbooks/rce.md`
- `skills/pentest-tools/src-hunter/references/payloader/by-category/web/文件漏洞.md`

Their original content remains in Reverie's Git history through commit
`e5468fc2327d711d8c547933579f9a4a105b37c4`. References to these omitted documents
must be reported as unavailable, following the same rule above. The remaining
bundled resources, upstream revision, and license notices are unchanged.
