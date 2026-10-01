import { mkdtemp, readFile, rm, writeFile, mkdir, unlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, expect, it } from "vitest";
import { importAttachments, saveClipboardImage, validateAttachments } from "./attachments";
const roots: string[] = [];
afterEach(async () => { for (const root of roots.splice(0)) await rm(root, { recursive: true, force: true }); });
it("references workspace files, copies external files and retains partial failures", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "reverie-input-")); roots.push(root);
  const workspace = path.join(root, "工作区"); await mkdir(workspace);
  await writeFile(path.join(workspace, "inside.txt"), "current\n");
  await writeFile(path.join(root, "external.txt"), "fixed\n");
  const result = await importAttachments(workspace, [path.join(workspace, "inside.txt"), path.join(root, "external.txt"), path.join(root, "missing.txt")]);
  expect(result.map(item => item.kind)).toEqual(["reference", "copy", undefined]);
  expect(result.map(item => item.status)).toEqual(["ready", "ready", "failed"]);
  expect(await readFile(path.join(workspace, result[1].relativePath), "utf8")).toBe("fixed\n");
  expect(result[0].version).toHaveLength(64);
  const clipboard = await saveClipboardImage(workspace, Buffer.from("real clipboard bytes"));
  expect(await readFile(path.join(workspace, clipboard.relativePath))).toEqual(Buffer.from("real clipboard bytes"));
});
it("reports unsupported drops and rejects batches larger than the fixed limit", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "reverie-input-")); roots.push(root);
  expect((await importAttachments(root, [root, ""]))[0].status).toBe("failed");
  await expect(importAttachments(root, Array(21).fill(""))).rejects.toThrow("20");
});

it("marks restored missing or modified copies invalid and refreshes references",async()=>{const root=await mkdtemp(path.join(tmpdir(),"reverie-restored-input-"));roots.push(root);const file=path.join(root,"file.txt");await writeFile(file,"original");const [reference]=await importAttachments(root,[file]);const [copy]=await importAttachments(root,[file],true);await writeFile(file,"current");await writeFile(path.join(root,copy.relativePath),"tampered");const refreshed=await validateAttachments(root,[reference,copy]);expect(refreshed[0].status).toBe("ready");expect(refreshed[0].version).not.toBe(reference.version);expect(refreshed[1].status).toBe("failed");await unlink(file);expect((await validateAttachments(root,[reference]))[0].status).toBe("failed");});
