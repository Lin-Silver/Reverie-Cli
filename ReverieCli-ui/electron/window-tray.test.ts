import { EventEmitter } from "node:events";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { BrowserWindow } from "electron";

const mocks = vi.hoisted(() => ({ menu: vi.fn((items: unknown[]) => items), image: vi.fn() }));
vi.mock("electron", () => ({
  BrowserWindow: class {},
  Tray: class extends EventEmitter {
    setToolTip = vi.fn();
    setContextMenu = vi.fn();
  },
  Menu: { buildFromTemplate: mocks.menu },
  nativeImage: { createFromPath: mocks.image },
}));
import { createWindowTray, showWindow } from "./window-tray";

function fakeWindow() {
  return Object.assign(new EventEmitter(), {
    isDestroyed: vi.fn(() => false), isMinimized: vi.fn(() => false),
    restore: vi.fn(), show: vi.fn(), hide: vi.fn(), focus: vi.fn(),
  });
}

describe("window tray lifecycle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.image.mockReturnValue({ resize: vi.fn(() => ({})) });
  });

  it("hides on close and restores the same window from tray clicks", () => {
    const window = fakeWindow();
    const quit = vi.fn();
    const tray = createWindowTray(window as unknown as BrowserWindow, "icon.png", "zh-CN", () => false, quit);
    const event = { preventDefault: vi.fn() };
    window.emit("close", event);
    expect(event.preventDefault).toHaveBeenCalledOnce();
    expect(window.hide).toHaveBeenCalledOnce();
    expect(quit).not.toHaveBeenCalled();
    window.isMinimized.mockReturnValue(true);
    tray.emit("click");
    expect(window.restore).toHaveBeenCalledOnce();
    expect(window.show).toHaveBeenCalledOnce();
    expect(window.focus).toHaveBeenCalledOnce();
    tray.emit("double-click");
    expect(window.show).toHaveBeenCalledTimes(2);
  });

  it("allows an explicit quit to close and offers localized restore and quit actions", () => {
    const window = fakeWindow();
    const quit = vi.fn();
    createWindowTray(window as unknown as BrowserWindow, "icon.png", "en-US", () => true, quit);
    const event = { preventDefault: vi.fn() };
    window.emit("close", event);
    expect(event.preventDefault).not.toHaveBeenCalled();
    expect(window.hide).not.toHaveBeenCalled();
    const items = mocks.menu.mock.calls[0][0] as Array<{ label?: string; click?: () => void }>;
    expect(items.map(item => item.label).filter(Boolean)).toEqual(["Show Reverie", "Quit Reverie"]);
    items[0].click?.();
    expect(window.show).toHaveBeenCalledOnce();
    items[2].click?.();
    expect(quit).toHaveBeenCalledOnce();
  });

  it("does not try to restore a destroyed window", () => {
    const window = fakeWindow();
    window.isDestroyed.mockReturnValue(true);
    showWindow(window as unknown as BrowserWindow);
    expect(window.show).not.toHaveBeenCalled();
  });
});
