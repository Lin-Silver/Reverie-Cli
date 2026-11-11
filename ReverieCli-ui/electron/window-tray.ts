import { BrowserWindow, Menu, nativeImage, Tray } from "electron";

export function showWindow(window: BrowserWindow): void {
  if (window.isDestroyed()) return;
  if (window.isMinimized()) window.restore();
  window.show();
  window.focus();
}

export function createWindowTray(
  window: BrowserWindow,
  iconPath: string,
  language: "zh-CN" | "en-US",
  isQuitting: () => boolean,
  quit: () => void,
  toggleAiO?: () => void,
): Tray {
  const tray = new Tray(nativeImage.createFromPath(iconPath).resize({ width: 16, height: 16 }));
  const restore = () => showWindow(window);
  tray.setToolTip("Reverie");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: language === "en-US" ? "Show Reverie" : "显示 Reverie", click: restore },
    ...(toggleAiO ? [{ label: language === "en-US" ? "Pause / resume AiO" : "暂停 / 恢复 AiO", click: toggleAiO }] : []),
    { type: "separator" },
    { label: language === "en-US" ? "Quit Reverie" : "退出 Reverie", click: quit },
  ]));
  tray.on("click", restore);
  tray.on("double-click", restore);
  window.on("close", event => {
    if (isQuitting()) return;
    event.preventDefault();
    window.hide();
  });
  return tray;
}
