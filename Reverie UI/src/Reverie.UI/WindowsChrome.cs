using System.Runtime.InteropServices;

namespace Reverie.UI;

internal static class WindowsChrome
{
    private const int DwmwaUseImmersiveDarkMode = 20;
    private const int DwmwaUseImmersiveDarkModeBefore20h1 = 19;
    private const int DwmwaCaptionColor = 35;
    private const int DwmwaTextColor = 36;

    public static void ApplyDarkTitleBar(IntPtr hwnd)
    {
        if (!OperatingSystem.IsWindows())
        {
            return;
        }

        try
        {
            var enabled = 1;
            DwmSetWindowAttribute(hwnd, DwmwaUseImmersiveDarkMode, ref enabled, sizeof(int));
            DwmSetWindowAttribute(hwnd, DwmwaUseImmersiveDarkModeBefore20h1, ref enabled, sizeof(int));

            var caption = ColorTranslator.ToWin32(Color.FromArgb(20, 20, 20));
            var text = ColorTranslator.ToWin32(Color.FromArgb(240, 240, 240));
            DwmSetWindowAttribute(hwnd, DwmwaCaptionColor, ref caption, sizeof(int));
            DwmSetWindowAttribute(hwnd, DwmwaTextColor, ref text, sizeof(int));
        }
        catch
        {
            // Older Windows builds simply keep the system title bar.
        }
    }

    [DllImport("dwmapi.dll", PreserveSig = true)]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int attrValue, int attrSize);
}
