# O3DE Plugin Source

This directory contains the source code for the Reverie CLI `o3de` runtime plugin.

Current capabilities:

- Reverie CLI `-RC` handshake and `-RC-CALL` execution
- Official GitHub release/tag discovery
- Plugin-local O3DE source checkout under `.reverie/plugins/o3de/source`
- Plugin-local SDK/runtime manifest under `.reverie/plugins/o3de/runtime`
- O3DE-style project envelope validation support

The plugin intentionally does not install into global program folders or user-profile SDK paths. All generated state, downloads, source checkouts, and manifests stay inside the executable-root plugin depot.
