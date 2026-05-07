using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Reverie.UI;

public sealed class MainForm : Form
{
    private static readonly Color DefaultWindowBackground = Color.FromArgb(17, 21, 35);

    private readonly WebView2 _webView = new();
    private readonly ReverieBridgeService _bridge = new();
    private Color _windowBackground = DefaultWindowBackground;
    private Color _captionColor = DefaultWindowBackground;
    private Color _captionTextColor = Color.FromArgb(248, 246, 255);
    private bool _darkTitleBar = true;

    public MainForm()
    {
        Text = "Reverie UI";
        BackColor = _windowBackground;
        MinimumSize = new Size(1120, 720);
        StartPosition = FormStartPosition.CenterScreen;
        WindowState = FormWindowState.Maximized;

        _webView.Dock = DockStyle.Fill;
        Controls.Add(_webView);

        Load += OnLoad;
        FormClosing += OnFormClosing;
        _bridge.OutputReceived += OnBridgeOutputReceived;
    }

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        ApplyHostThemeToChrome();
    }

    private async void OnLoad(object? sender, EventArgs e)
    {
        await _webView.EnsureCoreWebView2Async();
        _webView.DefaultBackgroundColor = _windowBackground;
        _webView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
        _webView.CoreWebView2.Settings.AreDevToolsEnabled = true;
        _webView.CoreWebView2.WebMessageReceived += OnWebMessageReceived;

        var indexPath = Path.Combine(AppContext.BaseDirectory, "wwwroot", "index.html");
        _webView.CoreWebView2.Navigate(new Uri(indexPath).AbsoluteUri);
    }

    private async void OnWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        var payload = e.WebMessageAsJson;
        try
        {
            using var doc = JsonDocument.Parse(payload);
            var action = doc.RootElement.TryGetProperty("action", out var actionElement)
                ? actionElement.GetString()
                : string.Empty;

            if (string.Equals(action, "hostInfo", StringComparison.OrdinalIgnoreCase))
            {
                PostToWeb(new
                {
                    type = "host.info",
                    cwd = Directory.GetCurrentDirectory(),
                    workspaceRoot = RuntimePaths.WorkspaceRoot,
                    runtimeRoot = RuntimePaths.RuntimeRoot,
                    appDataRoot = RuntimePaths.AppDataRoot,
                    reverieCliPath = RuntimePaths.ReverieCliPath,
                    reverieCliVersion = RuntimePaths.ReverieCliVersion,
                    bridgeKind = _bridge.BridgeKind
                });
                return;
            }

            if (string.Equals(action, "setHostTheme", StringComparison.OrdinalIgnoreCase))
            {
                ApplyHostTheme(doc.RootElement);
                return;
            }

            await _bridge.SendAsync(payload);
        }
        catch (Exception ex)
        {
            PostToWeb(new
            {
                type = "host.error",
                error = ex.Message
            });
        }
    }

    private void ApplyHostTheme(JsonElement root)
    {
        var payload = root.TryGetProperty("payload", out var payloadElement) ? payloadElement : root;
        var theme = payload.TryGetProperty("theme", out var themeElement)
            ? themeElement.GetString()
            : "reverie";
        var appearance = payload.TryGetProperty("appearance", out var appearanceElement)
            ? appearanceElement.GetString()
            : "dark";

        (_windowBackground, _captionColor, _captionTextColor, _darkTitleBar) =
            ResolveHostTheme(theme, appearance);
        BackColor = _windowBackground;
        if (_webView.CoreWebView2 is not null)
        {
            _webView.DefaultBackgroundColor = _windowBackground;
        }
        ApplyHostThemeToChrome();
    }

    private void ApplyHostThemeToChrome()
    {
        if (IsHandleCreated)
        {
            WindowsChrome.ApplyTitleBar(Handle, _darkTitleBar, _captionColor, _captionTextColor);
        }
    }

    private static (Color Window, Color Caption, Color Text, bool Dark) ResolveHostTheme(string? theme, string? appearance)
    {
        var normalizedTheme = (theme ?? "reverie").Trim().ToLowerInvariant();
        var normalizedAppearance = (appearance ?? "dark").Trim().ToLowerInvariant();
        if (normalizedTheme == "reverie" && normalizedAppearance == "light")
        {
            return (
                Color.FromArgb(251, 248, 255),
                Color.FromArgb(243, 237, 255),
                Color.FromArgb(35, 26, 53),
                false
            );
        }
        if (normalizedTheme == "classic")
        {
            return (
                Color.FromArgb(20, 20, 20),
                Color.FromArgb(20, 20, 20),
                Color.FromArgb(240, 240, 240),
                true
            );
        }
        return (
            Color.FromArgb(17, 21, 35),
            Color.FromArgb(17, 21, 35),
            Color.FromArgb(248, 246, 255),
            true
        );
    }

    private void OnBridgeOutputReceived(object? sender, string json)
    {
        if (_webView.CoreWebView2 is null)
        {
            return;
        }

        BeginInvoke(() => _webView.CoreWebView2.PostWebMessageAsJson(json));
    }

    private void PostToWeb(object payload)
    {
        if (_webView.CoreWebView2 is null)
        {
            return;
        }

        _webView.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(payload));
    }

    private void OnFormClosing(object? sender, FormClosingEventArgs e)
    {
        _bridge.Dispose();
    }
}
