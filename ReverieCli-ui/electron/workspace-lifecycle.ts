import { statSync } from "node:fs";
import path from "node:path";

export interface WorkspaceBridge {
  setProjectRoot(projectRoot: string): void;
}

function comparablePath(value: string): string {
  const resolved = path.resolve(value);
  return process.platform === "win32" ? resolved.toLowerCase() : resolved;
}

export function samePath(left: string, right: string): boolean {
  return comparablePath(left) === comparablePath(right);
}

export function pathIsWithin(candidate: string, root: string): boolean {
  const relative = path.relative(comparablePath(root), comparablePath(candidate));
  return relative === "" || (
    relative !== ".."
    && !relative.startsWith(`..${path.sep}`)
    && !path.isAbsolute(relative)
  );
}

export function isWorkspaceDirectory(projectRoot: string): boolean {
  try {
    return statSync(path.resolve(projectRoot)).isDirectory();
  } catch {
    return false;
  }
}

export async function activateWorkspaceInPlace(
  bridge: WorkspaceBridge,
  projectRoot: string,
  persist: (resolvedProjectRoot: string) => Promise<void>,
): Promise<string> {
  const input = String(projectRoot ?? "").trim();
  if (!input) throw new Error("Workspace path is required.");
  const resolved = path.resolve(input);
  if (!isWorkspaceDirectory(resolved)) throw new Error(`Workspace is not a directory: ${resolved}`);
  await persist(resolved);
  bridge.setProjectRoot(resolved);
  return resolved;
}
