using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Reverie.UI;

public sealed class MainForm : Form
{
    private static readonly Color WindowBackground = Color.FromArgb(20, 20, 20);

    private readonly WebView2 _webView = new();
    private readonly ReverieBridgeService _bridge = new();

    public MainForm()
    {
        Text = "Reverie UI";
        BackColor = WindowBackground;
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
        WindowsChrome.ApplyDarkTitleBar(Handle);
    }

    private async void OnLoad(object? sender, EventArgs e)
    {
        await _webView.EnsureCoreWebView2Async();
        _webView.DefaultBackgroundColor = WindowBackground;
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
