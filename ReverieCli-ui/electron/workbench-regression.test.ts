import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, expect, it } from "vitest";
import { gitSnapshot, gitPatch, gitMutate } from "./workbench";

const roots: string[] = [];
const git = (cwd: string, ...args: string[]) => execFileSync("git", args, { cwd, windowsHide: true, stdio: "pipe" });
async function repository() {
  const root = await mkdtemp(path.join(tmpdir(), "reverie-menu-git-")); roots.push(root);
  git(root, "init", "-b", "main"); git(root, "config", "user.name", "Fixture"); git(root, "config", "user.email", "fixture@example.test");
  await writeFile(path.join(root, "one.txt"), "one\ntwo\n"); git(root, "add", "."); git(root, "commit", "-m", "Initial");
  return root;
}
afterEach(async () => { for (const root of roots.splice(0)) await rm(root, { recursive: true, force: true }); });

it("lists nested repositories without reading or mutating them as files", async () => {
  const root = await repository(); const nested = path.join(root, "nested"); await mkdir(nested);
  git(nested, "init"); await writeFile(path.join(nested, "inside.txt"), "preserve me");
  git(nested, "add", "."); git(nested, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "-m", "Nested");
  const snapshot = await gitSnapshot(root);
  expect(snapshot.files.find(file => file.path === "nested/")).toMatchObject({ directory: true, additions: 0 });
  await expect(gitPatch(root, { scope: "working", file: "nested/" })).rejects.toThrow("nested repository");
  await expect(gitMutate(root, { operation: "stage", file: "nested/", version: snapshot.version })).rejects.toThrow("Directory operations");
  expect(git(nested, "status", "--porcelain").toString()).toBe("");
});

it("counts renamed files and many changes with the same batch numstat result", async () => {
  const root = await repository(); git(root, "mv", "one.txt", "重命名 space.txt");
  const staged = await gitSnapshot(root, "staged");
  expect(staged.files[0]).toMatchObject({ path: "重命名 space.txt", oldPath: "one.txt", additions: 0, deletions: 0 });
  await writeFile(path.join(root, "重命名 space.txt"), "one\nchanged\nadded\n");
  expect((await gitSnapshot(root)).files[0]).toMatchObject({ additions: 2, deletions: 1 });
  await writeFile(path.join(root, "fresh.txt"), "one");
  const before = await gitSnapshot(root); await writeFile(path.join(root, "fresh.txt"), "two");
  await expect(gitMutate(root, { operation: "stage", file: "fresh.txt", version: before.version })).rejects.toThrow("changed");
});
