---
name: reverse-skill
description: 逆向工程与安全分析。Use for binary EXE/DLL/ELF, APK/Android/iOS, .NET, JavaScript signatures and obfuscation, firmware, protocol/PCAP analysis, malware analysis, CTF and authorized security testing. Routes to the bundled reverse-skill specialist workflows and toolchain scripts.
---

# Reverse Skill for Reverie

This built-in skill bundles the reverse-skill project. Resolve every path below
relative to this SKILL.md, regardless of the user's current working directory.
Read `UPSTREAM.md` for the source revision and licenses.

## Workflow

1. Read `upstream/RULES.md` and `upstream/skills/MASTER-ROUTING.md` using
   `skill_lookup(operation="read_resource", skill_name="reverse-skill", resource_path="<relative-path>")`.
   Read every chunk using `body_offset` until `complete=true`. The same operation
   reads all nested scenario SKILL.md files, references and script source below.
2. Run the bundled platform router with the user's task:
   - Windows: `pwsh -NoProfile -File "<skill-dir>/upstream/skills/scripts/master-route.ps1" -Hint "<task>" -ProjectRoot "<workspace>"`
   - Linux/macOS: `bash "<skill-dir>/upstream/skills/scripts/master-route.sh" --hint "<task>" --project-root "<workspace>"`
   Read the script's usage if the installed shell requires different arguments.
3. Read the selected PRIMARY's `SKILL.md` under `upstream/skills/`, plus the
   references it requires using `skill_lookup` with `read_resource`. Discover
   Reverie's available command tools and inspect their actual schemas before use.
4. Follow `upstream/skills/ops/scope-contract.md` and the platform `case-init`
   script to record the user's authorized scope in `<workspace>/work/<case>`.
   Reuse authorization already supplied in the conversation. For local sample
   analysis, use the offline-sample preset and explicitly name the sample.
5. Inspect the actual local toolchain before choosing commands. The upstream
   tool index is a reference snapshot, not proof that a tool or MCP server is
   installed on this computer. Discover available Reverie tools/MCPs first.
6. Perform the selected analysis workflow and support findings with file
   offsets, addresses, traces, or reproducible observations. Clearly distinguish
   confirmed behavior from hypotheses and unavailable tooling.

## Runtime paths

The bundled upstream tree is read-only reference material, including in packaged
builds. Keep cases, reports, generated tool indexes, downloads and new journal
entries under the user's workspace, never inside the installed skill. If an
upstream bootstrap or refresh script needs to modify its own tree, first copy
the bundled upstream tree to `<workspace>/.reverie/reverse-skill/<revision>` and
run that working copy. Preserve its directory layout and licensing notices.

External reverse-engineering tools are not bundled or implicitly running.
Install/start only tools needed for the user's requested workflow, using the
upstream pinned manifests and Reverie's existing permission controls. Do not
register external MCP servers merely because the skill was loaded.

Load only the selected scenario and needed references, not the entire tree into
the conversation. Generic GUI work or ordinary coding does not trigger this skill.
