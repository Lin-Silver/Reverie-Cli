using System.Diagnostics;
using System.Text;

namespace Reverie.UI;

public sealed class PythonBridgeService : IDisposable
{
    private readonly SemaphoreSlim _startLock = new(1, 1);
    private Process? _process;
    private StreamWriter? _stdin;
    private bool _disposed;

    public event EventHandler<string>? OutputReceived;

    public async Task SendAsync(string json)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        await EnsureStartedAsync();

        if (_stdin is null)
        {
            throw new InvalidOperationException("Python bridge stdin is not available.");
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

            var python = Environment.GetEnvironmentVariable("REVERIE_UI_PYTHON");
            if (string.IsNullOrWhiteSpace(python))
            {
                python = "python";
            }

            var scriptPath = Path.Combine(RuntimePaths.RuntimeRoot, "reverie_ui_bridge.py");
            var startInfo = new ProcessStartInfo
            {
                FileName = python,
                Arguments = $"\"{scriptPath}\"",
                WorkingDirectory = RuntimePaths.RuntimeRoot,
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
            startInfo.Environment["PYTHONPATH"] = RuntimePaths.RuntimeRoot;
            startInfo.Environment["REVERIE_APP_ROOT"] = RuntimePaths.AppDataRoot;

            Directory.CreateDirectory(RuntimePaths.AppDataRoot);
            _process = Process.Start(startInfo) ?? throw new InvalidOperationException("Failed to start Python bridge.");
            _stdin = _process.StandardInput;

            _ = Task.Run(() => ReadStdoutAsync(_process));
            _ = Task.Run(() => ReadStderrAsync(_process));
        }
        finally
        {
            _startLock.Release();
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
            EmitHostError("Python bridge exited.");
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
}
