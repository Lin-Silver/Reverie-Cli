import { execFile } from "node:child_process";
import { describe, expect, it, vi } from "vitest";
import { getGitWorkspaceStatus } from "./git-workspace";

vi.mock("node:child_process", () => ({ execFile: vi.fn() }));

function failGit(stderr: string) {
  const error = Object.assign(new Error(stderr), { code: 128, stderr });
  vi.mocked(execFile).mockImplementationOnce((...args: unknown[]) => {
    const callback = args.at(-1) as (error: Error) => void;
    callback(error);
    return undefined as never;
  });
  return error;
}

describe("Git workspace discovery errors", () => {
  it.each([
    "fatal: not a git repository (or any of the parent directories): .git",
    "fatal: gitfile does not point to a valid repository: /workspace/.git",
  ])("returns no workspace for %s", async (stderr) => {
    failGit(stderr);
    expect(await getGitWorkspaceStatus("/workspace")).toBeNull();
  });

  it("preserves unrelated Git failures", async () => {
    const error = failGit("fatal: detected dubious ownership in repository at '/workspace'");
    await expect(getGitWorkspaceStatus("/workspace")).rejects.toBe(error);
  });
});
