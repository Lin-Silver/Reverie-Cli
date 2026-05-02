param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",

    [switch]$SkipTests,
    [switch]$SkipLaunch,
    [switch]$Publish,
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectPath = Join-Path $ScriptRoot "src\Reverie.UI\Reverie.UI.csproj"
$RuntimeRoot = Join-Path $ScriptRoot "runtime"
$BridgePath = Join-Path $RuntimeRoot "reverie_ui_bridge.py"
$PublishDir = Join-Path $ScriptRoot "artifacts\publish"
$TestRoot = Join-Path $ScriptRoot "artifacts\test"
$ReportPath = Join-Path $TestRoot "gui-smoke-report.json"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "OK  $Message" -ForegroundColor Green
}

function Resolve-Python {
    param([string]$Requested)

    if ($Requested) {
        return $Requested
    }

    if ($env:REVERIE_UI_PYTHON) {
        return $env:REVERIE_UI_PYTHON
    }

    $RepoRoot = Split-Path -Parent $ScriptRoot
    $VenvPython = Join-Path $RepoRoot "venv\Scripts\python.exe"
    if (Test-Path $VenvPython) {
        return $VenvPython
    }

    return "python"
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory = $ScriptRoot
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $FilePath $($Arguments -join ' ')"
    }
}

function Get-FreeTcpPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try {
        return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    }
    finally {
        $listener.Stop()
    }
}

function Stop-ProcessSafe {
    param([System.Diagnostics.Process]$Process)

    if (-not $Process -or $Process.HasExited) {
        return
    }

    try {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
    catch {
        try {
            $Process.Kill()
        }
        catch {
        }
    }
}

function Read-JsonLine {
    param(
        [System.Diagnostics.Process]$Process,
        [int]$TimeoutMs = 30000
    )

    $task = $Process.StandardOutput.ReadLineAsync()
    if (-not $task.Wait($TimeoutMs)) {
        throw "Timed out waiting for bridge output."
    }

    $line = $task.Result
    if (-not $line) {
        $stderr = $Process.StandardError.ReadToEnd()
        throw "Bridge closed stdout unexpectedly. stderr: $stderr"
    }

    return $line | ConvertFrom-Json
}

function Send-JsonLine {
    param(
        [System.Diagnostics.Process]$Process,
        [hashtable]$Payload
    )

    $json = $Payload | ConvertTo-Json -Depth 20 -Compress
    $Process.StandardInput.WriteLine($json)
    $Process.StandardInput.Flush()
}

function Wait-ForType {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$Type,
        [int]$TimeoutMs = 45000
    )

    $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMs)
    while ([DateTime]::UtcNow -lt $deadline) {
        $remaining = [int]([Math]::Max(1000, ($deadline - [DateTime]::UtcNow).TotalMilliseconds))
        $message = Read-JsonLine -Process $Process -TimeoutMs $remaining
        if ($message.type -eq "error" -or $message.type -eq "host.error") {
            throw "Bridge error while waiting for '$Type': $($message.error)"
        }
        if ($message.type -eq $Type) {
            return $message
        }
    }

    throw "Timed out waiting for bridge message type '$Type'."
}

function Start-MockOpenAiServer {
    param(
        [string]$Python,
        [int]$Port
    )

    $MockServerPath = Join-Path $TestRoot "mock_openai_server.py"
    @'
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1])

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_POST(self):
        length = int(self.headers.get("content-length", "0") or "0")
        if length:
            self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        chunks = [
            {"id": "reverie-ui-smoke", "object": "chat.completion.chunk", "created": 1, "model": "mock-reverie", "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Reverie UI smoke chat ok."}, "finish_reason": None}]},
            {"id": "reverie-ui-smoke", "object": "chat.completion.chunk", "created": 1, "model": "mock-reverie", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
        for chunk in chunks:
            self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
print(f"READY {PORT}", flush=True)
server.serve_forever()
'@ | Set-Content -LiteralPath $MockServerPath -Encoding UTF8

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $Python
    $startInfo.Arguments = "`"$MockServerPath`" $Port"
    $startInfo.WorkingDirectory = $TestRoot
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true

    $process = [System.Diagnostics.Process]::Start($startInfo)
    $lineTask = $process.StandardOutput.ReadLineAsync()
    if (-not $lineTask.Wait(10000)) {
        $process.Kill($true)
        throw "Mock OpenAI server did not start."
    }
    if (-not ($lineTask.Result -like "READY*")) {
        $stderr = $process.StandardError.ReadToEnd()
        $process.Kill($true)
        throw "Mock OpenAI server failed to report ready. stderr: $stderr"
    }
    return $process
}

function Invoke-BridgeSmokeTests {
    param([string]$Python)

    Write-Step "Running Python bridge smoke tests"

    $TestAppRoot = Join-Path $TestRoot "appdata"
    $Workspace = Join-Path $TestRoot "workspace"
    New-Item -ItemType Directory -Force -Path $TestAppRoot, $Workspace | Out-Null
    Set-Content -LiteralPath (Join-Path $Workspace "hello.py") -Value "def hello():`n    return 'reverie-ui-smoke'`n" -Encoding UTF8

    $port = Get-FreeTcpPort
    $mockServer = Start-MockOpenAiServer -Python $Python -Port $port
    $bridge = $null
    try {
        $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
        $startInfo.FileName = $Python
        $startInfo.Arguments = "`"$BridgePath`""
        $startInfo.WorkingDirectory = $RuntimeRoot
        $startInfo.UseShellExecute = $false
        $startInfo.RedirectStandardInput = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $startInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
        $startInfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8
        $startInfo.Environment["PYTHONUNBUFFERED"] = "1"
        $startInfo.Environment["PYTHONPATH"] = $RuntimeRoot
        $startInfo.Environment["REVERIE_APP_ROOT"] = $TestAppRoot
        $startInfo.Environment["NO_PROXY"] = "127.0.0.1,localhost"
        $startInfo.Environment["no_proxy"] = "127.0.0.1,localhost"
        $startInfo.Environment.Remove("HTTP_PROXY") | Out-Null
        $startInfo.Environment.Remove("HTTPS_PROXY") | Out-Null
        $startInfo.Environment.Remove("http_proxy") | Out-Null
        $startInfo.Environment.Remove("https_proxy") | Out-Null

        $bridge = [System.Diagnostics.Process]::Start($startInfo)

        $ready = Read-JsonLine -Process $bridge
        if ($ready.type -ne "ready") {
            throw "Expected bridge ready message, got $($ready.type)."
        }

        Send-JsonLine $bridge @{ id = "init"; action = "initialize"; payload = @{ projectRoot = $Workspace } }
        $state = Wait-ForType -Process $bridge -Type "state"
        if ($state.project_root -ne (Resolve-Path $Workspace).Path) {
            throw "Workspace state did not match test workspace."
        }
        Write-Ok "initialize/getState passed."

        Send-JsonLine $bridge @{ id = "mode"; action = "setMode"; payload = @{ mode = "reverie-gamer" } }
        $modeState = Wait-ForType -Process $bridge -Type "state"
        if ($modeState.config.mode -ne "reverie-gamer") {
            throw "Mode switch failed."
        }
        Write-Ok "mode switch passed."

        Send-JsonLine $bridge @{ id = "tools"; action = "listTools"; payload = @{} }
        $tools = Wait-ForType -Process $bridge -Type "tools"
        if (-not $tools.tools -or $tools.tools.Count -lt 10) {
            throw "Tool list looks incomplete."
        }
        Write-Ok "tool catalog passed."

        Send-JsonLine $bridge @{
            id = "model"
            action = "saveModel"
            payload = @{
                index = -1
                model_display_name = "Mock Reverie"
                model = "mock-reverie"
                base_url = "http://127.0.0.1:$port/v1"
                api_key = "smoke-test"
                provider = "openai-sdk"
                max_context_tokens = 128000
            }
        }
        $modelState = Wait-ForType -Process $bridge -Type "state"
        if (-not $modelState.config.active_model) {
            throw "Model save/select failed."
        }
        Write-Ok "model configuration passed."

        Send-JsonLine $bridge @{ id = "session"; action = "newSession"; payload = @{ name = "Smoke Session" } }
        $sessionState = Wait-ForType -Process $bridge -Type "state"
        $sessionId = [string]$sessionState.sessions.current_session_id
        if (-not $sessionId) {
            throw "New session failed."
        }
        Write-Ok "session creation passed."

        Send-JsonLine $bridge @{ id = "index"; action = "indexWorkspace"; payload = @{ projectRoot = $Workspace } }
        Wait-ForType -Process $bridge -Type "index.started" | Out-Null
        $indexComplete = Wait-ForType -Process $bridge -Type "index.complete" -TimeoutMs 60000
        if (-not $indexComplete.success) {
            throw "Context Engine indexing failed."
        }
        Write-Ok "Context Engine indexing passed."

        Send-JsonLine $bridge @{
            id = "chat"
            action = "chat"
            payload = @{
                projectRoot = $Workspace
                sessionId = $sessionId
                mode = "reverie"
                message = "Say the smoke test response."
            }
        }
        Wait-ForType -Process $bridge -Type "chat.started" | Out-Null
        $chatText = ""
        $deadline = [DateTime]::UtcNow.AddSeconds(90)
        while ([DateTime]::UtcNow -lt $deadline) {
            $message = Read-JsonLine -Process $bridge -TimeoutMs 90000
            if ($message.type -eq "chat.chunk") {
                $chatText += [string]$message.chunk
            }
            elseif ($message.type -eq "chat.complete") {
                break
            }
            elseif ($message.type -eq "error") {
                throw "Chat failed: $($message.error)"
            }
        }
        if ($chatText -notlike "*Reverie UI smoke chat ok*") {
            throw "Chat stream did not contain expected mock response. Got: $chatText"
        }
        Write-Ok "mock chat streaming passed."

        Send-JsonLine $bridge @{ id = "diagnostics"; action = "diagnostics"; payload = @{} }
        $diagnostics = Wait-ForType -Process $bridge -Type "diagnostics"
        if (-not $diagnostics.items) {
            throw "Diagnostics returned no items."
        }
        Write-Ok "diagnostics passed."

        $report = [ordered]@{
            generated_at = (Get-Date).ToString("o")
            workspace = (Resolve-Path $Workspace).Path
            mode_switch = "passed"
            tools = $tools.tools.Count
            model_config = "passed"
            sessions = "passed"
            indexing = "passed"
            chat_streaming = "passed"
            diagnostics = "passed"
        }
        $report | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
        Write-Ok "Bridge smoke tests passed. Report: $ReportPath"
    }
    finally {
        if ($bridge -and -not $bridge.HasExited) {
            try {
                Send-JsonLine $bridge @{ id = "shutdown"; action = "shutdown"; payload = @{} }
                if (-not $bridge.WaitForExit(3000)) {
                    Stop-ProcessSafe -Process $bridge
                }
            }
            catch {
                if (-not $bridge.HasExited) {
                    Stop-ProcessSafe -Process $bridge
                }
            }
        }
        if ($mockServer -and -not $mockServer.HasExited) {
            Stop-ProcessSafe -Process $mockServer
        }
    }
}

function Test-GuiLaunch {
    param([string]$Python)

    Write-Step "Launching GUI executable briefly"

    $ExePath = Join-Path $ScriptRoot "src\Reverie.UI\bin\$Configuration\net10.0-windows\Reverie.UI.exe"
    if (-not (Test-Path $ExePath)) {
        throw "GUI executable not found: $ExePath"
    }

    $process = Start-Process -FilePath $ExePath -WorkingDirectory (Split-Path -Parent $ExePath) -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 5
    if ($process.HasExited) {
        throw "GUI process exited during launch smoke test with code $($process.ExitCode)."
    }

    Stop-ProcessSafe -Process $process
    $process.WaitForExit()
    Write-Ok "GUI process launched successfully."
}

Write-Step "Checking prerequisites"
$ResolvedPython = Resolve-Python -Requested $PythonPath
Invoke-Checked "dotnet" @("--version")
Invoke-Checked $ResolvedPython @("--version")
Write-Ok "Using Python: $ResolvedPython"

if (-not $SkipTests -and (Test-Path $TestRoot)) {
    Remove-Item -LiteralPath $TestRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $TestRoot | Out-Null

Write-Step "Compiling Python bridge"
Invoke-Checked $ResolvedPython @("-m", "py_compile", $BridgePath)
Write-Ok "Python bridge syntax is valid."

Write-Step "Restoring .NET dependencies"
Invoke-Checked "dotnet" @("restore", $ProjectPath)

Write-Step "Building Reverie UI ($Configuration)"
Invoke-Checked "dotnet" @("build", $ProjectPath, "-c", $Configuration, "--no-restore")
Write-Ok "Build completed."

if (-not $SkipTests) {
    Invoke-BridgeSmokeTests -Python $ResolvedPython
}

if ($Publish) {
    Write-Step "Publishing Reverie UI"
    if (Test-Path $PublishDir) {
        Remove-Item -LiteralPath $PublishDir -Recurse -Force
    }
    Invoke-Checked "dotnet" @("publish", $ProjectPath, "-c", $Configuration, "-o", $PublishDir, "--no-restore")
    Write-Ok "Published to $PublishDir"
}

if (-not $SkipLaunch) {
    Test-GuiLaunch -Python $ResolvedPython
}

Write-Step "Build GUI script completed"
Write-Ok "Reverie UI build, verification, and smoke tests passed."
