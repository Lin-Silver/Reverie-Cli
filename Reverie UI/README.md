# Reverie UI

Reverie UI is a Windows desktop GUI for Reverie built with C# WinForms and WebView2.
It does not call the compiled `reverie.exe` as a kernel SDK. Instead, this project
contains an embedded source runtime under `runtime/` and talks to it through
`runtime/reverie_ui_bridge.py`.

## Architecture

- `src/Reverie.UI`: WebView2 host, process bridge, window lifecycle.
- `src/Reverie.UI/wwwroot`: Codex-style chat workspace, sessions, models, tools,
  context indexing, diagnostics, and runtime logs.
- `runtime/reverie`: copied Reverie Python source used directly by the bridge.
- `runtime/reverie_ui_bridge.py`: JSONL command bridge for chat streaming,
  configuration, sessions, tools, and Context Engine indexing.

## Run

```powershell
cd ".\Reverie UI\src\Reverie.UI"
dotnet run
```

If Python is not on `PATH`, set `REVERIE_UI_PYTHON` to the Python executable that
has Reverie's dependencies installed.

```powershell
$env:REVERIE_UI_PYTHON = "G:\Reverie\Reverie-Cli\venv\Scripts\python.exe"
dotnet run
```

Runtime configuration and secrets are stored outside the repository in the local
application-data directory selected by the desktop host.

## Build And Verify

Run the full build, bridge smoke tests, mock chat streaming test, and a brief GUI
launch check from the repository root:

```powershell
.\Reverie UI\build-gui.ps1
```

Useful options:

```powershell
.\Reverie UI\build-gui.ps1 -Configuration Debug
.\Reverie UI\build-gui.ps1 -Publish
.\Reverie UI\build-gui.ps1 -SkipLaunch
.\Reverie UI\build-gui.ps1 -PythonPath "G:\Reverie\Reverie-Cli\venv\Scripts\python.exe"
```

The script writes smoke-test output under `Reverie UI/artifacts/`.
