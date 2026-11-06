# Native engine provenance

Reverie bundles the unmodified Windows x64 executable from vercel-labs/agent-desktop v1.2.0, commit `2b0a7334fc111730454b726e6800aa41cdafc093`, under Apache-2.0.

Source: https://github.com/vercel-labs/agent-desktop/tree/v1.2.0

Release: https://github.com/vercel-labs/agent-desktop/releases/tag/v1.2.0

`native_manifest.json` pins the archive and executable SHA-256 values and protocol version. `scripts/prepare_computer_use.py` retrieves the executable and LICENSE at build time. The distributed `native/windows-x64/` directory contains `agent-desktop.exe`, `LICENSE`, and a receipt recording this provenance. No native dependency is installed from the network at runtime. The Python wrapper is maintained by Reverie and does not alter the upstream executable.
