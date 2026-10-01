// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { AttachmentCards, InputContext, type InputControls } from "./ComposerExtras";
import type { ComposerAttachment } from "../electron/attachments";
const image: ComposerAttachment = { id: "photo", name: "photo.png", relativePath: "photo.png", size: 20, status: "ready", kind: "reference", version: "original", thumbnail: "data:image/png;base64,thumb" };
const controls: InputControls = { projectRoot: "C:/workspace", sessionId: "session", behavior: "queue", setBehavior: vi.fn(), paste: vi.fn(), moveAttachment: vi.fn(), retryAttachment: vi.fn(), closeMentions: vi.fn(), error: "", status: "", queue: [], queuePaused: false, editQueue: vi.fn(), moveQueue: vi.fn(), deleteQueue: vi.fn(), resumeQueue: vi.fn(), forceStop: vi.fn(), vision: true, running: false, approval: false, sessionStates: {}, steer: vi.fn() };
afterEach(cleanup);
function mount(workbench: ReturnType<typeof vi.fn>, item = image) {
  Object.defineProperty(window, "reverie", { configurable: true, value: { workbench } });
  render(<InputContext.Provider value={controls}><AttachmentCards items={[item]} remove={vi.fn()} /></InputContext.Provider>);
}
it("loads the original photo and keeps Tab, Shift Tab, and Escape inside the preview", async () => {
  const workbench = vi.fn().mockResolvedValue({ kind: "image", version: "current", url: "data:image/png;base64,original" });
  mount(workbench); const user = userEvent.setup(); const opener = screen.getByRole("button", { name: /photo.png.*工作区引用/ });
  await user.click(opener); const dialog = screen.getByRole("dialog");
  await waitFor(() => expect(within(dialog).getByRole("img").getAttribute("src")).toBe("data:image/png;base64,original"));
  expect(workbench).toHaveBeenCalledWith("preview", { projectRoot: "C:/workspace", file: "photo.png" });
  const buttons = within(dialog).getAllByRole("button");
  buttons.at(-1)!.focus(); await user.tab(); expect(document.activeElement).toBe(buttons[0]);
  await user.tab({ shift: true }); expect(document.activeElement).toBe(buttons.at(-1));
  await user.keyboard("{Escape}"); expect(screen.queryByRole("dialog")).toBeNull(); expect(document.activeElement).toBe(opener);
});
it("keeps a failed photo load visible and ignores a late result after closing", async () => {
  let reject!: (error: Error) => void;
  mount(vi.fn(() => new Promise((_resolve, rejectPromise) => { reject = rejectPromise; })));
  const user = userEvent.setup(); await user.click(screen.getByRole("button", { name: /photo.png.*工作区引用/ }));
  expect(within(screen.getByRole("dialog")).getByRole("status")).toBeTruthy();
  await user.keyboard("{Escape}"); reject(new Error("missing file"));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull()); expect(screen.queryByRole("alert")).toBeNull();
});
it("does not preview changed copy bytes under the old hash", async () => {
  mount(vi.fn().mockResolvedValue({ kind: "image", version: "changed", url: "data:image/png;base64,changed" }), { ...image, kind: "copy" });
  const user = userEvent.setup(); await user.click(screen.getByRole("button", { name: /photo.png.*附件副本/ }));
  const dialog = screen.getByRole("dialog");
  await waitFor(() => expect(within(dialog).getByRole("alert").textContent).toContain("请重新导入附件"));
  expect(within(dialog).queryByRole("img")).toBeNull();
  fireEvent.keyDown(within(dialog).getByRole("button", { name: "关闭" }), { key: "Escape", isComposing: true });
  expect(screen.getByRole("dialog")).toBeTruthy(); await user.keyboard("{Escape}"); expect(screen.queryByRole("dialog")).toBeNull();
});
