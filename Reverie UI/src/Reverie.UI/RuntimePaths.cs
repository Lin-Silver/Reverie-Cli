using System.Text.Json;

namespace Reverie.UI;

public static class RuntimePaths
{
    private const string DefaultReleaseRepository = "Lin-Silver/Reverie-Cli";
    private const string DownloadedExeRelativePath = @".reverie\bin\reverie.exe";

    public static string RuntimeRoot { get; } = ResolveRuntimeRoot();

    public static string WorkspaceRoot { get; } = ResolveWorkspaceRoot();

    public static string? ReverieCliPath { get; } = ResolveReverieCliPath();

    public static string ReverieCliVersion { get; } = ResolveReverieCliVersion(ReverieCliPath);

    public static string AppDataRoot { get; } = ResolveAppDataRoot();

    private static string ResolveRuntimeRoot()
    {
        var outputRuntime = Path.Combine(AppContext.BaseDirectory, "runtime");
        if (File.Exists(Path.Combine(outputRuntime, "reverie_ui_bridge.py")))
        {
            return outputRuntime;
        }

        var workspaceRuntime = FindWorkspaceRuntimeRoot();
        if (!string.IsNullOrWhiteSpace(workspaceRuntime))
        {
            return workspaceRuntime;
        }

        var cursor = new DirectoryInfo(AppContext.BaseDirectory);
        while (cursor is not null)
        {
            var candidate = Path.Combine(cursor.FullName, "runtime");
            if (File.Exists(Path.Combine(candidate, "reverie_ui_bridge.py")))
            {
                return candidate;
            }

            cursor = cursor.Parent;
        }

        return outputRuntime;
    }

    private static string? FindWorkspaceRuntimeRoot()
    {
        var cursor = new DirectoryInfo(AppContext.BaseDirectory);
        while (cursor is not null)
        {
            var candidate = Path.Combine(cursor.FullName, "ReverieCli-py", "ui-runtime");
            if (File.Exists(Path.Combine(candidate, "reverie_ui_bridge.py")))
            {
                return candidate;
            }

            cursor = cursor.Parent;
        }

        return null;
    }

    private static string ResolveWorkspaceRoot()
    {
        foreach (var seed in new[] { RuntimeRoot, Directory.GetCurrentDirectory(), AppContext.BaseDirectory })
        {
            var cursor = new DirectoryInfo(seed);
            while (cursor is not null)
            {
                if (Directory.Exists(Path.Combine(cursor.FullName, ".git")))
                {
                    return cursor.FullName;
                }

                cursor = cursor.Parent;
            }
        }

        return Directory.GetCurrentDirectory();
    }

    private static string ResolveAppDataRoot()
    {
        var envRoot = Environment.GetEnvironmentVariable("REVERIE_APP_ROOT");
        if (!string.IsNullOrWhiteSpace(envRoot))
        {
            return Path.GetFullPath(Environment.ExpandEnvironmentVariables(envRoot.Trim().Trim('"')));
        }

        if (!string.IsNullOrWhiteSpace(ReverieCliPath) && !IsDownloadedCliPath(ReverieCliPath))
        {
            return Path.GetDirectoryName(ReverieCliPath) ?? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        }

        return UserProfileDirectory();
    }

    private static string? ResolveReverieCliPath()
    {
        foreach (var candidate in EnumerateSystemCliCandidates())
        {
            if (IsValidReverieCli(candidate))
            {
                return candidate;
            }
        }

        var downloaded = TryDownloadLatestReverieCli();
        if (!string.IsNullOrWhiteSpace(downloaded) && IsValidReverieCli(downloaded))
        {
            return downloaded;
        }

        foreach (var candidate in EnumerateBundledCliCandidates())
        {
            if (IsValidReverieCli(candidate))
            {
                return candidate;
            }
        }

        return null;
    }

    private static IEnumerable<string> EnumerateSystemCliCandidates()
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        foreach (var pathEntry in (Environment.GetEnvironmentVariable("PATH") ?? string.Empty).Split(Path.PathSeparator))
        {
            if (string.IsNullOrWhiteSpace(pathEntry))
            {
                continue;
            }

            foreach (var name in new[] { "reverie.exe", "reverie.cmd", "reverie.bat", "reverie" })
            {
                foreach (var expanded in ExpandCandidate(Path.Combine(pathEntry.Trim(), name)))
                {
                    if (seen.Add(expanded))
                    {
                        yield return expanded;
                    }
                }
            }
        }
    }

    private static IEnumerable<string> EnumerateBundledCliCandidates()
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        foreach (var value in new[]
        {
            DownloadedCliPath(),
            Path.Combine(AppContext.BaseDirectory, "reverie.exe"),
            Path.Combine(AppContext.BaseDirectory, "runtime", "reverie.exe"),
            Path.Combine(RuntimeRoot, "reverie.exe"),
            Path.Combine(WorkspaceRoot, "dist", "reverie.exe")
        })
        {
            foreach (var expanded in ExpandCandidate(value))
            {
                if (seen.Add(expanded))
                {
                    yield return expanded;
                }
            }
        }

        var cursor = new DirectoryInfo(AppContext.BaseDirectory);
        while (cursor is not null)
        {
            foreach (var value in new[]
            {
                Path.Combine(cursor.FullName, "reverie.exe"),
                Path.Combine(cursor.FullName, "dist", "reverie.exe"),
                Path.Combine(cursor.FullName, "runtime", "reverie.exe")
            })
            {
                foreach (var expanded in ExpandCandidate(value))
                {
                    if (seen.Add(expanded))
                    {
                        yield return expanded;
                    }
                }
            }

            cursor = cursor.Parent;
        }
    }

    private static string UserProfileDirectory()
    {
        var userProfile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        return string.IsNullOrWhiteSpace(userProfile) ? Directory.GetCurrentDirectory() : userProfile;
    }

    private static string DownloadedCliPath()
    {
        return Path.Combine(UserProfileDirectory(), DownloadedExeRelativePath);
    }

    private static bool IsDownloadedCliPath(string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            return false;
        }

        return string.Equals(
            Path.GetFullPath(path),
            Path.GetFullPath(DownloadedCliPath()),
            StringComparison.OrdinalIgnoreCase);
    }

    private static string? TryDownloadLatestReverieCli()
    {
        var targetPath = DownloadedCliPath();
        try
        {
            var releaseRepository = Environment.GetEnvironmentVariable("REVERIE_RELEASE_REPOSITORY");
            if (string.IsNullOrWhiteSpace(releaseRepository))
            {
                releaseRepository = DefaultReleaseRepository;
            }

            var asset = ResolveLatestReleaseExeAsset(releaseRepository);
            if (asset is null)
            {
                return File.Exists(targetPath) ? targetPath : null;
            }

            Directory.CreateDirectory(Path.GetDirectoryName(targetPath)!);
            var metadataPath = Path.ChangeExtension(targetPath, ".json");
            if (File.Exists(targetPath) && IsValidReverieCli(targetPath) && CachedDownloadMatches(metadataPath, asset.Version))
            {
                return targetPath;
            }

            var tempPath = Path.Combine(Path.GetDirectoryName(targetPath)!, $"reverie-download-{Guid.NewGuid():N}.exe");
            using var http = CreateGitHubHttpClient();
            using var response = http.GetAsync(asset.Url).GetAwaiter().GetResult();
            response.EnsureSuccessStatusCode();
            using (var input = response.Content.ReadAsStreamAsync().GetAwaiter().GetResult())
            using (var output = File.Create(tempPath))
            {
                input.CopyTo(output);
            }

            if (!IsValidReverieCli(tempPath))
            {
                File.Delete(tempPath);
                return File.Exists(targetPath) ? targetPath : null;
            }

            File.Move(tempPath, targetPath, overwrite: true);
            WriteDownloadMetadata(metadataPath, releaseRepository, asset);
            return targetPath;
        }
        catch
        {
            return File.Exists(targetPath) ? targetPath : null;
        }
    }

    private static ReleaseAsset? ResolveLatestReleaseExeAsset(string repository)
    {
        var cleaned = repository.Trim().Trim('/');
        if (string.IsNullOrWhiteSpace(cleaned) || !cleaned.Contains('/'))
        {
            cleaned = DefaultReleaseRepository;
        }

        using var http = CreateGitHubHttpClient();
        using var response = http.GetAsync($"https://api.github.com/repos/{cleaned}/releases/latest").GetAwaiter().GetResult();
        if (!response.IsSuccessStatusCode)
        {
            return null;
        }

        using var stream = response.Content.ReadAsStreamAsync().GetAwaiter().GetResult();
        using var doc = JsonDocument.Parse(stream);
        var version = doc.RootElement.TryGetProperty("tag_name", out var tagElement)
            ? tagElement.GetString() ?? "latest"
            : "latest";

        if (!doc.RootElement.TryGetProperty("assets", out var assets) || assets.ValueKind != JsonValueKind.Array)
        {
            return null;
        }

        ReleaseAsset? fallback = null;
        foreach (var asset in assets.EnumerateArray())
        {
            var name = asset.TryGetProperty("name", out var nameElement) ? nameElement.GetString() ?? string.Empty : string.Empty;
            var url = asset.TryGetProperty("browser_download_url", out var urlElement) ? urlElement.GetString() ?? string.Empty : string.Empty;
            if (string.IsNullOrWhiteSpace(url) || !name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            if (string.Equals(name, "reverie.exe", StringComparison.OrdinalIgnoreCase))
            {
                return new ReleaseAsset(url, version);
            }

            if (name.Contains("reverie", StringComparison.OrdinalIgnoreCase))
            {
                fallback ??= new ReleaseAsset(url, version);
            }
        }

        return fallback;
    }

    private static bool CachedDownloadMatches(string metadataPath, string version)
    {
        try
        {
            if (!File.Exists(metadataPath))
            {
                return false;
            }

            using var doc = JsonDocument.Parse(File.ReadAllText(metadataPath));
            return doc.RootElement.TryGetProperty("version", out var versionElement)
                && string.Equals(versionElement.GetString(), version, StringComparison.OrdinalIgnoreCase);
        }
        catch
        {
            return false;
        }
    }

    private static void WriteDownloadMetadata(string metadataPath, string repository, ReleaseAsset asset)
    {
        try
        {
            var payload = new
            {
                repository,
                version = asset.Version,
                asset_url = asset.Url,
                downloaded_at = DateTimeOffset.UtcNow.ToString("O")
            };
            File.WriteAllText(metadataPath, JsonSerializer.Serialize(payload, new JsonSerializerOptions { WriteIndented = true }));
        }
        catch
        {
        }
    }

    private static HttpClient CreateGitHubHttpClient()
    {
        var http = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(30)
        };
        http.DefaultRequestHeaders.UserAgent.ParseAdd("Reverie-UI/1.0");
        http.DefaultRequestHeaders.Accept.ParseAdd("application/vnd.github+json");
        return http;
    }

    private sealed record ReleaseAsset(string Url, string Version);

    private static IEnumerable<string> ExpandCandidate(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            yield break;
        }

        var trimmed = value.Trim().Trim('"');
        var expanded = Environment.ExpandEnvironmentVariables(trimmed);
        if (!Path.IsPathRooted(expanded))
        {
            expanded = Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), expanded));
        }

        if (File.Exists(expanded))
        {
            yield return Path.GetFullPath(expanded);
        }
    }

    private static bool IsValidReverieCli(string path)
    {
        try
        {
            using var process = new System.Diagnostics.Process();
            process.StartInfo = new System.Diagnostics.ProcessStartInfo
            {
                FileName = path,
                Arguments = "--version",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };
            process.Start();
            if (!process.WaitForExit(3000))
            {
                process.Kill(entireProcessTree: true);
                return false;
            }

            var output = (process.StandardOutput.ReadToEnd() + process.StandardError.ReadToEnd()).Trim();
            return process.ExitCode == 0 && output.Contains("Reverie", StringComparison.OrdinalIgnoreCase);
        }
        catch
        {
            return false;
        }
    }

    private static string ResolveReverieCliVersion(string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            return "not found";
        }

        try
        {
            using var process = new System.Diagnostics.Process();
            process.StartInfo = new System.Diagnostics.ProcessStartInfo
            {
                FileName = path,
                Arguments = "--version",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };
            process.Start();
            if (!process.WaitForExit(3000))
            {
                process.Kill(entireProcessTree: true);
                return "timeout";
            }

            return (process.StandardOutput.ReadToEnd() + process.StandardError.ReadToEnd()).Trim();
        }
        catch (Exception ex)
        {
            return ex.Message;
        }
    }
}
