import { mkdtemp, mkdir, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, expect, it } from "vitest";
import { listDirectory, readEditorFile, saveEditorFile } from "./workbench";

const roots: string[] = [];
async function fixture() { const root = await mkdtemp(path.join(tmpdir(), "reverie-editor-")); roots.push(root); return root; }
afterEach(async () => { for (const root of roots.splice(0)) await rm(root, { recursive: true, force: true }); });

it("lists one directory with folders first and keeps Git metadata out of the explorer", async () => {
  const root = await fixture(); await mkdir(path.join(root, "src")); await mkdir(path.join(root, ".git"));
  await writeFile(path.join(root, "readme.md"), "text"); await writeFile(path.join(root, "src", "one.ts"), "nested");
  expect((await listDirectory(root)).entries).toEqual([{ name: "src", path: "src", directory: true }, { name: "readme.md", path: "readme.md", directory: false }]);
  expect((await listDirectory(root, "src")).entries[0].path).toBe("src/one.ts");
  await expect(listDirectory(root, "../")).rejects.toThrow("outside");
});

it("saves actual UTF-8 bytes, retaining the BOM and CRLF line endings", async () => {
  const root = await fixture(); const file = path.join(root, "中文.txt");
  await writeFile(file, "\uFEFF第一行\r\n第二行\r\n");
  const opened = await readEditorFile(root, "中文.txt");
  expect(opened).toMatchObject({ text: "第一行\n第二行\n", newline: "crlf", bom: true });
  const saved = await saveEditorFile(root, "中文.txt", "修改\n第二行\n", opened.version);
  expect(await readFile(file, "utf8")).toBe("\uFEFF修改\r\n第二行\r\n"); expect(saved.version).not.toBe(opened.version);
});

it("rejects an external edit and serializes simultaneous saves without overwriting either revision", async () => {
  const root = await fixture(); const file = path.join(root, "one.txt"); await writeFile(file, "original");
  const opened = await readEditorFile(root, "one.txt"); await writeFile(file, "external");
  await expect(saveEditorFile(root, "one.txt", "mine", opened.version)).rejects.toThrow("changed on disk");
  const next = await readEditorFile(root, "one.txt");
  const results = await Promise.allSettled([saveEditorFile(root, "one.txt", "first", next.version), saveEditorFile(root, "one.txt", "second", next.version)]);
  expect(results.filter(value => value.status === "fulfilled")).toHaveLength(1);
  expect(results.filter(value => value.status === "rejected")).toHaveLength(1);
  expect(await readFile(file, "utf8")).toBe(results[0].status === "fulfilled" ? "first" : "second");
});

it("keeps binary, oversized, invalid UTF-8 and mixed newline files read-only", async () => {
  const root = await fixture();
  for (const [name, bytes] of [["binary", Buffer.from([0, 1])], ["encoding", Buffer.from([255, 254])], ["big", Buffer.alloc(2 * 1024 * 1024 + 1, 65)], ["mixed", Buffer.from("a\r\nb\n")]] as const) {
    await writeFile(path.join(root, name), bytes); await expect(readEditorFile(root, name)).rejects.toThrow();
  }
});

it("shows an escaping directory link without following it or allowing edits through it", async () => {
  const root = await fixture(); const outside = await fixture(); await writeFile(path.join(outside, "one.txt"), "preserve");
  await symlink(outside, path.join(root, "external"), "junction");
  expect((await listDirectory(root)).entries[0]).toMatchObject({ path: "external", outside: true });
  await expect(readEditorFile(root, "external/one.txt")).rejects.toThrow("outside");
  expect(await readFile(path.join(outside, "one.txt"), "utf8")).toBe("preserve");
});
