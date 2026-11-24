# Marketplace sources

This module is an independent Rust implementation of source discovery and catalog reading. It does not copy marketplace installer code or execute a catalog's command sources.

Official source documents inspected on 2026-11-23:

- [Anthropic official plugins](https://github.com/anthropics/claude-plugins-official/blob/main/.claude-plugin/marketplace.json): Git blob `d72a89dd7021669899587d7dd8f9296c5d684b9d`; 317 entries using relative, `url`, `git-subdir` and `command` sources.
- [Anthropic Skills](https://github.com/anthropics/skills/blob/main/.claude-plugin/marketplace.json): Git blob `1969092344b3405a5459f82c1dd252d30b335a6e`; five plugin entries pointing at the repository root. Components declared by each entry must be handled when installing, rather than assuming each directory is one Skill.
- [OpenAI Plugins](https://github.com/openai/plugins/blob/main/.agents/plugins/marketplace.json): Git blob `ea8a0c4bc4530ea9a5ddafcd5937da58c0e33ac9`; 65 entries with local, URL and Git-subdirectory sources. Installation/product/authentication policies remain visible as metadata; they do not confer platform-specific connector access.
- [MCP Registry API](https://registry.modelcontextprotocol.io/docs): the built-in catalog uses `/v0.1/servers`, server name/version identities and `metadata.nextCursor`. Current endpoint availability and package installation have separate runtime checks.

Counts and public catalogs may change. Each native refresh records the actual Git commit where applicable and SHA-256 of the returned catalog. These hashes bind the fetched content; they do not constitute a publisher signature or plugin trust grant.

Marketplace listing does not grant a common license to its plugins, models, scripts or assets. Installation must retain and evaluate the selected package's own license and applicable third-party notices. A metadata-only listing is not a redistribution-permission check.
