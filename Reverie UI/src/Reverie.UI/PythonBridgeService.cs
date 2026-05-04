using System.Diagnostics;
using System.Text;

namespace Reverie.UI;

public sealed class ReverieBridgeService : IDisposable
{
    private readonly SemaphoreSlim _startLock = new(1, 1);
    private Process? _process;
    private StreamWriter? _stdin;
    private bool _disposed;

    public string BridgeKind { get; private set; } = "not-started";

    public event EventHandler<string>? OutputReceived;

    public async Task SendAsync(string json)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        await EnsureStartedAsync();

        if (_stdin is null)
        {
            throw new InvalidOperationException("Reverie bridge stdin is not available.");
        }

        await _stdin.WriteLineAsync(json);
        await _stdin.FlushAsync();
    }

    private async Task EnsureStartedAsync()
    {
        if (_process is { HasExited: false })
        {
            return;
        }

        await _startLock.WaitAsync();
        try
        {
            if (_process is { HasExited: false })
            {
                return;
            }

            Directory.CreateDirectory(Path.Combine(RuntimePaths.AppDataRoot, ".reverie"));
            var failures = new List<string>();
            foreach (var launch in BuildLaunches())
            {
                try
                {
                    await StartBridgeAsync(launch);
                    BridgeKind = launch.Kind;
                    EmitHostLog($"Started {launch.Kind}: {launch.FileName}");
                    return;
                }
                catch (Exception ex)
                {
                    failures.Add($"{launch.Kind}: {ex.Message}");
                    EmitHostLog($"Bridge launch failed ({launch.Kind}): {ex.Message}");
                }
            }

            throw new InvalidOperationException("Unable to start Reverie bridge. " + string.Join(" | ", failures));
        }
        finally
        {
            _startLock.Release();
        }
    }

    private static IEnumerable<BridgeLaunch> BuildLaunches()
    {
        if (!string.IsNullOrWhiteSpace(RuntimePaths.ReverieCliPath))
        {
            yield return new BridgeLaunch("embedded-exe", RuntimePaths.ReverieCliPath, "--sdk-bridge", RuntimePaths.WorkspaceRoot);
        }

        var python = Environment.GetEnvironmentVariable("REVERIE_UI_PYTHON");
        if (string.IsNullOrWhiteSpace(python))
        {
            var repoVenv = Path.Combine(RuntimePaths.WorkspaceRoot, "venv", "Scripts", "python.exe");
            python = File.Exists(repoVenv) ? repoVenv : "python";
        }

        var scriptPath = Path.Combine(RuntimePaths.RuntimeRoot, "reverie_ui_bridge.py");
        if (File.Exists(scriptPath))
        {
            yield return new BridgeLaunch("python-source", python, $"\"{scriptPath}\"", RuntimePaths.RuntimeRoot);
        }
    }

    private async Task StartBridgeAsync(BridgeLaunch launch)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = launch.FileName,
            Arguments = launch.Arguments,
            WorkingDirectory = launch.WorkingDirectory,
            UseShellExecute = false,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false),
            StandardOutputEncoding = new UTF8Encoding(false),
            StandardErrorEncoding = new UTF8Encoding(false),
            CreateNoWindow = true
        };

        startInfo.Environment["PYTHONUNBUFFERED"] = "1";
        startInfo.Environment["PYTHONIOENCODING"] = "utf-8";
        startInfo.Environment["REVERIE_APP_ROOT"] = RuntimePaths.AppDataRoot;
        startInfo.Environment["REVERIE_UI_HOST"] = "1";
        startInfo.Environment["NO_PROXY"] = "127.0.0.1,localhost";
        startInfo.Environment["no_proxy"] = "127.0.0.1,localhost";

        if (launch.Kind == "python-source")
        {
            startInfo.Environment["PYTHONPATH"] = RuntimePaths.RuntimeRoot;
        }

        var process = Process.Start(startInfo) ?? throw new InvalidOperationException("Process.Start returned null.");
        try
        {
            var firstLine = await process.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(12));
            if (string.IsNullOrWhiteSpace(firstLine))
            {
                var stderr = await ReadAvailableStderrAsync(process);
                throw new InvalidOperationException(string.IsNullOrWhiteSpace(stderr) ? "Bridge exited without a ready event." : stderr);
            }

            _process = process;
            _stdin = process.StandardInput;
            OutputReceived?.Invoke(this, firstLine);

            _ = Task.Run(() => ReadStdoutAsync(process));
            _ = Task.Run(() => ReadStderrAsync(process));
        }
        catch
        {
            try
            {
                if (!process.HasExited)
                {
                    process.Kill(entireProcessTree: true);
                }
            }
            catch
            {
            }

            process.Dispose();
            throw;
        }
    }

    private static async Task<string> ReadAvailableStderrAsync(Process process)
    {
        try
        {
            if (process.HasExited)
            {
                return await process.StandardError.ReadToEndAsync();
            }

            await Task.Delay(150);
            return process.HasExited ? await process.StandardError.ReadToEndAsync() : string.Empty;
        }
        catch
        {
            return string.Empty;
        }
    }

    private async Task ReadStdoutAsync(Process process)
    {
        try
        {
            while (await process.StandardOutput.ReadLineAsync() is { } line)
            {
                if (!string.IsNullOrWhiteSpace(line))
                {
                    OutputReceived?.Invoke(this, line);
                }
            }
        }
        catch (Exception ex)
        {
            EmitHostError(ex.Message);
        }
        finally
        {
            EmitHostError("Reverie bridge exited.");
        }
    }

    private async Task ReadStderrAsync(Process process)
    {
        try
        {
            while (await process.StandardError.ReadLineAsync() is { } line)
            {
                if (!string.IsNullOrWhiteSpace(line))
                {
                    EmitHostLog(line);
                }
            }
        }
        catch (Exception ex)
        {
            EmitHostError(ex.Message);
        }
    }

    private void EmitHostLog(string message)
    {
        OutputReceived?.Invoke(this, $$"""{"type":"host.log","message":{{JsonString(message)}}}""");
    }

    private void EmitHostError(string message)
    {
        OutputReceived?.Invoke(this, $$"""{"type":"host.error","error":{{JsonString(message)}}}""");
    }

    private static string JsonString(string value)
    {
        return System.Text.Json.JsonSerializer.Serialize(value ?? string.Empty);
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        try
        {
            if (_process is { HasExited: false })
            {
                _stdin?.WriteLine("""{"action":"shutdown"}""");
                _stdin?.Flush();
                if (!_process.WaitForExit(1200))
                {
                    _process.Kill(entireProcessTree: true);
                }
            }
        }
        catch
        {
            // Window shutdown should not be blocked by bridge cleanup.
        }
        finally
        {
            _stdin?.Dispose();
            _process?.Dispose();
            _startLock.Dispose();
        }
    }

    private sealed record BridgeLaunch(string Kind, string FileName, string Arguments, string WorkingDirectory);
}
