# RIU P3 interoperability fixture

The manifest and lockfile pin `@modelcontextprotocol/ext-apps` and the official
`@modelcontextprotocol/server-basic-vanillajs` example to **2.0.3**. The UI
protocol is **2026-01-26**. The official example is installed and run as shipped;
neither its component source nor its bundled HTML is patched for Reverie.

Upstream source: [ext-apps v2.0.3 vanilla example](https://github.com/modelcontextprotocol/ext-apps/tree/v2.0.3/examples/basic-server-vanillajs).
The verification script compares the resource stored by the packaged kernel
byte-for-byte with the package's `dist/mcp-app.html` and records its SHA-256.
The SDK is a verification dependency; the product host implements the declared
JSON-RPC subset without injecting a component adapter.

Install under the repository, using PowerShell from its root:

```powershell
New-Item -ItemType Directory -Force .runtime/riu-p3-sdk
Copy-Item scripts/verification/fixtures/mcp-apps/package*.json .runtime/riu-p3-sdk/
npm ci --prefix .runtime/riu-p3-sdk --ignore-scripts --no-audit --no-fund
cd ReverieCli-ui
npm run pack
cd ..
python scripts/verification/riu_p3_electron.py --exe ReverieCli-ui/release/win-unpacked/ReverieUI.exe --sdk-root .runtime/riu-p3-sdk
```

The loopback model, isolated app profile, fixtures, logs, screenshots and side
effects stay in the script's repository-local `--output` directory. No external
model credential or real user conversation is used. A `passed: false` report
is a failed attempt, never an acceptance record.

The separate [negative stdio server](../../../../ReverieCli-py/tests/fixtures/riu_p3/server.py)
and [component](../../../../ReverieCli-py/tests/fixtures/riu_p3/standard.html)
exercise app-only writes, duplicate IDs, model-only rejection, private metadata,
model-context, message proposals, forbidden host/Node/network access, missing
resources, invalid MIME/URI, requested network CSP, oversized HTML and teardown.
They are test fixtures, not upstream example modifications.
