// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { FileBrowser } from "./FileBrowser";

let serial = 0;
beforeEach(() => { vi.stubGlobal("requestAnimationFrame", (fn: () => void) => setTimeout(fn, 0)); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const document = { relativePath: "src/one.ts", text: "original\n", version: "v1", size: 9, newline: "lf", bom: false };
function install(overrides: (operation: string, payload: Record<string, unknown>) => unknown = () => undefined) {
  const root = `C:/editor-fixture-${++serial}`;
  const workbench = vi.fn(async (operation: string, payload: Record<string, unknown>) => {
    const result = overrides(operation, payload); if (result !== undefined) return result;
    if (operation === "list-directory") return payload.directory === "." ? { directory: ".", entries: [{ name: "src", path: "src", directory: true }], truncated: false } : { directory: "src", entries: [{ name: "one.ts", path: document.relativePath, directory: false }], truncated: false };
    if (operation === "preview") return { ...document, path: `${root}/src/one.ts`, kind: "text", modifiedAt: "now", totalLines: 2, offset: 0, next: null };
    if (operation === "read-file") return document;
    if (operation === "save-file") return { ...document, version: "v2", text: payload.text };
    return {};
  });
  Object.defineProperty(window, "reverie", { configurable: true, value: { workbench } });
  return { root, workbench };
}
it("opens nested directories lazily, edits text and saves the expected disk revision", async () => {
  const { root, workbench } = install(); render(<FileBrowser root={root} running={false} requested={null} onDraft={vi.fn()} />);
  expect(workbench).not.toHaveBeenCalledWith("list-directory", expect.objectContaining({ directory: "src" }));
  fireEvent.click(await screen.findByRole("treeitem", { name: "src" }));
  fireEvent.click(await screen.findByRole("treeitem", { name: "one.ts" }));
  const editor = await screen.findByRole("textbox", { name: "文件编辑内容" });
  fireEvent.change(editor, { target: { value: "changed\n" } }); expect(screen.getByText("未保存")).toBeTruthy();
  fireEvent.click(screen.getByRole("treeitem", { name: "one.ts" }));
  expect((editor as HTMLTextAreaElement).value).toBe("changed\n");
  expect(workbench.mock.calls.filter(([operation]) => operation === "preview")).toHaveLength(1);
  fireEvent.keyDown(editor, { ctrlKey: true, key: "s" });
  await screen.findByText("文件已保存"); expect(workbench).toHaveBeenCalledWith("save-file", { projectRoot: root, file: document.relativePath, text: "changed\n", version: "v1" });
  expect(screen.queryByText("未保存")).toBeNull();
});
it("keeps a conflicting draft visible and lets the user cancel discarding it", async () => {
  const { root } = install(operation => operation === "save-file" ? Promise.reject(new Error("File changed on disk")) : undefined);
  render(<FileBrowser root={root} running={false} requested={{ path: document.relativePath, line: 1, sequence: 1 }} onDraft={vi.fn()} />);
  const editor = await screen.findByRole("textbox", { name: "文件编辑内容" }); fireEvent.change(editor, { target: { value: "my draft" } });
  fireEvent.click(screen.getByRole("button", { name: "保存文件" })); await screen.findByRole("alert"); expect((editor as HTMLTextAreaElement).value).toBe("my draft");
  fireEvent.click(screen.getByRole("button", { name: "重新加载" })); await screen.findByRole("alertdialog", { name: "文件尚未保存" });
  fireEvent.click(screen.getByRole("button", { name: "取消" })); expect((editor as HTMLTextAreaElement).value).toBe("my draft");
});
it("does not turn a paginated preview into an editable fragment", async () => {
  const { root, workbench } = install(operation => operation === "read-file" ? Promise.reject(new Error("File exceeds editing limit")) : undefined);
  render(<FileBrowser root={root} running={false} requested={{ path: document.relativePath, line: 1, sequence: 1 }} onDraft={vi.fn()} />);
  await screen.findByText("File exceeds editing limit"); expect(screen.queryByRole("textbox", { name: "文件编辑内容" })).toBeNull(); expect(screen.queryByRole("button", { name: "保存文件" })).toBeNull();
  expect(workbench).not.toHaveBeenCalledWith("save-file", expect.anything());
});
it("ignores a file response after its owning view is unmounted", async () => {
  let finish!: (value: unknown) => void;
  const { root } = install(operation => operation === "preview" ? new Promise(resolve => { finish = resolve; }) : undefined);
  const view = render(<FileBrowser root={root} running={false} requested={{ path: document.relativePath, line: 1, sequence: 1 }} onDraft={vi.fn()} />);
  await waitFor(() => expect(finish).toBeTypeOf("function")); view.unmount();
  await act(async () => finish({ kind: "text", relativePath: document.relativePath })); expect(screen.queryByText("original")).toBeNull();
});
