import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { saveBrowserImage } from "./browser-artifacts";

const base = path.resolve(".runtime", "browser-artifact-tests");
const roots: string[] = [];
async function fixture() { await mkdir(base, { recursive: true }); const root = await mkdtemp(path.join(base, "case-")); roots.push(root); return root; }
function png() { const value = Buffer.alloc(33); Buffer.from([137,80,78,71,13,10,26,10]).copy(value); value.writeUInt32BE(13, 8); value.write("IHDR", 12); value.writeUInt32BE(800, 16); value.writeUInt32BE(600, 20); return value; }
afterEach(async () => { for (const root of roots.splice(0)) { if (!path.resolve(root).startsWith(base + path.sep)) throw new Error("Unsafe browser test cleanup."); await rm(root, { recursive: true, force: true }); } });

describe("project browser image artifacts", () => {
  it("writes and synchronizes a new PNG within the requesting project", async () => {
    const root = await fixture(); const bytes = png(); const file = await saveBrowserImage(root, "image-1", bytes);
    expect(file).toBe(path.join(root, ".reverie", "browser", "observations", "image-1.png"));
    expect(await readFile(file)).toEqual(bytes);
  });

  it("refuses traversal and never overwrites a previously stored image", async () => {
    const root = await fixture(); await expect(saveBrowserImage(root, "../escape", png())).rejects.toThrow();
    const file = await saveBrowserImage(root, "image-1", png()); await writeFile(file, "original");
    await expect(saveBrowserImage(root, "image-1", png())).rejects.toThrow(); expect(await readFile(file, "utf8")).toBe("original");
  });

  it("rejects a shared junction instead of writing into its target", async () => {
    const root = await fixture(), outside = await fixture(); await mkdir(path.join(outside, "browser"));
    await symlink(outside, path.join(root, ".reverie"), "junction");
    await expect(saveBrowserImage(root, "image-1", png())).rejects.toThrow("unsafe");
    expect(await readFile(path.join(outside, "browser", "observations", "image-1.png")).catch(() => null)).toBeNull();
  });

  it("rejects non-PNG returns before creating the observation directory", async () => {
    const root = await fixture(); await expect(saveBrowserImage(root, "image-1", Buffer.from("not PNG"))).rejects.toThrow();
    expect(await readFile(path.join(root, ".reverie", "browser", "observations", "image-1.png")).catch(() => null)).toBeNull();
  });
});
