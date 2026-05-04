# Reverie UI

Reverie UI is a Windows desktop GUI for Reverie built with C# WinForms and WebView2.
The UI treats the compiled `reverie.exe` as the preferred local SDK and talks to it
through Reverie's JSONL bridge.

## Runtime Resolution

Startup resolves `reverie.exe` in this order:

1. The system `PATH` environment variable, looking for `reverie.exe`, `reverie.cmd`, `reverie.bat`, or `reverie`.
2. The latest GitHub Release asset from `Lin-Silver/Reverie-Cli` named `reverie.exe`.
3. Bundled/local development fallbacks, including `runtime/reverie.exe` and repository `dist/reverie.exe`.
4. Python source bridge fallback through `runtime/reverie_ui_bridge.py`.

If the exe must be downloaded, it is stored at `%USERPROFILE%\.reverie\bin\reverie.exe`.
Set `REVERIE_RELEASE_REPOSITORY=owner/repo` to use another release source.

Configuration follows the selected exe when the exe is discovered from `PATH`.
For the downloaded exe fallback, configuration is created under `%USERPROFILE%\.reverie`.

## Architecture

- `src/Reverie.UI`: WebView2 host, exe/Python bridge launcher, window lifecycle.
- `src/Reverie.UI/wwwroot`: Codex-style workspace with chats, projects, models, tools,
  context indexing, Git status, diagnostics, settings, and runtime logs.
- `runtime/reverie_ui_bridge.py`: compatibility launcher for the Python fallback bridge.
- `reverie.sdk_bridge`: the canonical JSONL SDK bridge shared by CLI exe and UI.

## Run

```powershell
cd ".\Reverie UI\src\Reverie.UI"
dotnet run
```

Useful environment overrides:

```powershell
$env:REVERIE_RELEASE_REPOSITORY = "Lin-Silver/Reverie-Cli"
$env:REVERIE_UI_PYTHON = "G:\Reverie\Reverie-Cli\venv\Scripts\python.exe"
dotnet run
```

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
