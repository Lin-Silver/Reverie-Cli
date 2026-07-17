import { existsSync } from "node:fs";
import path from "node:path";

export function packagedExecutableHome(execPath: string, portableExecutableDir?: string): string {
  return path.resolve(portableExecutableDir?.trim() || path.dirname(execPath));
}

export function kernelExecutableName(platform: string = process.platform): string {
  return platform === "win32" ? "reverie.exe" : "reverie";
}

export function packagedKernelPath(execPath: string, platform: string = process.platform): string {
  const executableDirectory = path.dirname(path.resolve(execPath));
  const kernelDirectory = platform === "darwin"
    ? path.resolve(executableDirectory, "..")
    : executableDirectory;
  return path.join(kernelDirectory, kernelExecutableName(platform));
}

export function packagedRuntimeRoot(executableHome: string): string {
  return path.join(path.resolve(executableHome), ".reverie", "desktop");
}

export function findRepositoryCoreRoot(executableHome: string): string | null {
  let candidate = path.resolve(executableHome);
  for (let depth = 0; depth < 6; depth += 1) {
    const coreRoot = path.join(candidate, "dist");
    if (
      existsSync(path.join(candidate, ".git"))
      && existsSync(path.join(coreRoot, kernelExecutableName()))
    ) {
      return coreRoot;
    }
    const parent = path.dirname(candidate);
    if (parent === candidate) break;
    candidate = parent;
  }
  return null;
}
