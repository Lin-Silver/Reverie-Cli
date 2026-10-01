import { execFileSync } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { createGitBranch, getGitWorkspaceStatus, switchGitBranch } from "./git-workspace";

const temporaryRoots: string[] = [];

function git(root: string, ...args: string[]): string {
  return execFileSync("git", args, { cwd: root, encoding: "utf8", windowsHide: true }).trim();
}

async function repository(): Promise<string> {
  const root = await mkdtemp(path.join(tmpdir(), "reverie-git-workspace-"));
  temporaryRoots.push(root);
  git(root, "init", "-b", "main");
  await writeFile(path.join(root, "readme.txt"), "initial\n");
  git(root, "add", "readme.txt");
  git(root, "-c", "user.name=Reverie Test", "-c", "user.email=test@example.invalid", "commit", "-m", "initial");
  return root;
}

afterEach(async () => {
  for (const root of temporaryRoots.splice(0)) await rm(root, { recursive: true, force: true });
});

describe("Git workspace branches", () => {
  it("detects a non-repository and lists local branches with working-tree changes", async () => {
    const root = await repository();
    const outside = await mkdtemp(path.join(tmpdir(), "reverie-not-git-"));
    temporaryRoots.push(outside);
    // Prevent discovery of the parent repository when TEMP is inside the project.
    await writeFile(path.join(outside, ".git"), "gitdir: ./missing\n");
    expect(await getGitWorkspaceStatus(outside)).toBeNull();
    git(root, "branch", "feature/ui");
    await writeFile(path.join(root, "readme.txt"), "changed\n");
    const status = await getGitWorkspaceStatus(root);
    expect(status?.currentBranch).toBe("main");
    expect(status?.localBranches).toEqual(["feature/ui", "main"]);
    expect(status?.dirtyCount).toBe(1);
  });

  it("switches and creates branches while rejecting unknown selections", async () => {
    const root = await repository();
    git(root, "branch", "feature/ui");
    expect((await switchGitBranch(root, "feature/ui", false)).currentBranch).toBe("feature/ui");
    expect((await createGitBranch(root, "feature/next")).currentBranch).toBe("feature/next");
    await expect(switchGitBranch(root, "missing", false)).rejects.toThrow("no longer exists");
    await expect(createGitBranch(root, "bad name")).rejects.toThrow();
    expect(git(root, "branch", "--show-current")).toBe("feature/next");
  });

  it("checks out a remote-only branch as a tracking branch", async () => {
    const root = await repository();
    const remote = await mkdtemp(path.join(tmpdir(), "reverie-git-remote-"));
    temporaryRoots.push(remote);
    git(remote, "init", "--bare");
    git(root, "remote", "add", "origin", remote);
    git(root, "push", "origin", "main");
    git(root, "remote", "set-head", "origin", "main");
    git(root, "branch", "remote-only");
    git(root, "push", "origin", "remote-only");
    git(root, "branch", "-D", "remote-only");
    const status = await getGitWorkspaceStatus(root);
    expect(status?.remoteBranches).toContain("origin/remote-only");
    expect(status?.remoteBranches).not.toContain("origin/HEAD");
    expect(status?.remoteBranches).not.toContain("origin/main");
    expect((await switchGitBranch(root, "origin/remote-only", true)).currentBranch).toBe("remote-only");
    expect(git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")).toBe("origin/remote-only");
  });
});
