namespace Reverie.UI;

public static class RuntimePaths
{
    public static string RuntimeRoot { get; } = ResolveRuntimeRoot();

    public static string WorkspaceRoot { get; } = ResolveWorkspaceRoot();

    public static string AppDataRoot { get; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "Reverie UI");

    private static string ResolveRuntimeRoot()
    {
        var outputRuntime = Path.Combine(AppContext.BaseDirectory, "runtime");
        if (File.Exists(Path.Combine(outputRuntime, "reverie_ui_bridge.py")))
        {
            return outputRuntime;
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
}
