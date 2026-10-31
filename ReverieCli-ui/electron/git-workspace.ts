import { execFile } from "node:child_process";
import { promisify } from "node:util";

const runFile = promisify(execFile);

export interface GitWorkspaceStatus {
  repositoryRoot: string;
  currentBranch: string;
  dirtyCount: number;
  localBranches: string[];
  remoteBranches: string[];
  branchDetails?: Record<string, { upstream: string; tracking: string; lastCommit: string; worktree: string }>;
}

async function git(cwd: string, ...args: string[]): Promise<string> {
  const { stdout } = await runFile("git", args, { cwd, timeout: 15_000, maxBuffer: 1024 * 1024, windowsHide: true });
  return stdout.trim();
}

export async function getGitWorkspaceStatus(projectRoot: string): Promise<GitWorkspaceStatus | null> {
  try {
    if (await git(projectRoot, "rev-parse", "--is-inside-work-tree") !== "true") return null;
    const repositoryRoot = await git(projectRoot, "rev-parse", "--show-toplevel");
    const [branch, local, remote, remotes, changes, details] = await Promise.all([
      git(projectRoot, "branch", "--show-current"),
      git(projectRoot, "for-each-ref", "--format=%(refname:short)", "refs/heads"),
      git(projectRoot, "for-each-ref", "--format=%(refname)", "refs/remotes"),
      git(projectRoot, "remote"),
      git(projectRoot, "status", "--porcelain=v1", "--untracked-files=normal"),
      git(projectRoot, "for-each-ref", "--format=%(refname:short)%00%(upstream:short)%00%(upstream:track)%00%(committerdate:iso8601-strict)%00%(worktreepath)", "refs/heads", "refs/remotes"),
    ]);
    const localBranches = local ? local.split(/\r?\n/) : [];
    const remoteNames = remotes ? remotes.split(/\r?\n/).sort((a, b) => b.length - a.length) : [];
    const remoteBranches = remote ? remote.split(/\r?\n/)
      .map((ref) => ref.slice("refs/remotes/".length))
      .filter((name) => !name.endsWith("/HEAD") && !remoteNames.some((remoteName) =>
        name.startsWith(`${remoteName}/`) && localBranches.includes(name.slice(remoteName.length + 1)))) : [];
    return {
      repositoryRoot,
      currentBranch: branch || `(detached ${await git(projectRoot, "rev-parse", "--short", "HEAD")})`,
      dirtyCount: changes ? changes.split(/\r?\n/).length : 0,
      localBranches,
      remoteBranches,
      branchDetails: Object.fromEntries(details.split(/\r?\n/).filter(Boolean).map(row => { const [name, upstream, tracking, lastCommit, worktree] = row.split("\0"); return [name, { upstream, tracking, lastCommit, worktree }]; })),
    };
  } catch (error) {
    const detail = error as NodeJS.ErrnoException & { stderr?: string };
    if (detail.code === "ENOENT" || detail.stderr?.includes("not a git repository")
      || detail.stderr?.includes("gitfile does not point to a valid repository")) return null;
    throw error;
  }
}

export async function switchGitBranch(projectRoot: string, name: string, remote: boolean): Promise<GitWorkspaceStatus> {
  const status = await getGitWorkspaceStatus(projectRoot);
  if (!status) throw new Error("The workspace is not a Git repository.");
  if (status.dirtyCount) throw new Error("Save the staged and working-tree changes before switching branches; Reverie will not stash or discard them.");
  const occupied = status.branchDetails?.[name]?.worktree;
  if (occupied && occupied.toLowerCase() !== status.repositoryRoot.toLowerCase()) throw new Error(`Branch is already checked out in ${occupied}`);
  if (remote ? !status.remoteBranches.includes(name) : !status.localBranches.includes(name)) {
    throw new Error("The selected Git branch no longer exists.");
  }
  await git(status.repositoryRoot, ...(remote ? ["switch", "--track", name] : ["switch", "--", name]));
  const next = await getGitWorkspaceStatus(projectRoot);
  if (!next) throw new Error("Git status is unavailable after switching branches.");
  return next;
}

export async function createGitBranch(projectRoot: string, name: string): Promise<GitWorkspaceStatus> {
  const status = await getGitWorkspaceStatus(projectRoot);
  if (!status) throw new Error("The workspace is not a Git repository.");
  if (status.dirtyCount) throw new Error("Save the staged and working-tree changes before creating and switching branches.");
  const branch = name.trim();
  if (!branch) throw new Error("Enter a branch name.");
  await git(status.repositoryRoot, "check-ref-format", "--branch", branch);
  await git(status.repositoryRoot, "switch", "-c", branch);
  const next = await getGitWorkspaceStatus(projectRoot);
  if (!next) throw new Error("Git status is unavailable after creating the branch.");
  return next;
}
