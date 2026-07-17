import { afterEach, describe, expect, it } from "vitest";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  findRepositoryCoreRoot,
  kernelExecutableName,
  packagedExecutableHome,
  packagedKernelPath,
  packagedRuntimeRoot,
} from "./runtime-paths";

const roots: string[] = [];
afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true });
});

describe("packaged runtime paths", () => {
  it("keeps portable state beside the original portable executable", () => {
    const executableHome = packagedExecutableHome(
      "C:\\Temp\\reverie-unpacked\\ReverieUI.exe",
      "G:\\Apps\\Reverie",
    );
    expect(executableHome).toBe(path.resolve("G:\\Apps\\Reverie"));
    expect(packagedRuntimeRoot(executableHome))
      .toBe(path.join(path.resolve("G:\\Apps\\Reverie"), ".reverie", "desktop"));
  });

  it("keeps the CLI kernel and its DLLs beside the packaged GUI executable", () => {
    const packagedRoot = path.resolve("tmp", "reverie-unpacked");
    expect(packagedKernelPath(path.join(packagedRoot, "ReverieUI.exe")))
      .toBe(path.join(packagedRoot, kernelExecutableName()));
  });

  it("finds the repository distribution root from release and win-unpacked layouts", () => {
    const repository = path.join(os.tmpdir(), `reverie-ui-paths-${Date.now()}`);
    roots.push(repository);
    mkdirSync(path.join(repository, ".git"), { recursive: true });
    mkdirSync(path.join(repository, "dist"), { recursive: true });
    mkdirSync(path.join(repository, "ReverieCli-ui", "release", "win-unpacked"), { recursive: true });
    writeFileSync(path.join(repository, "dist", kernelExecutableName()), "test");

    expect(findRepositoryCoreRoot(path.join(repository, "ReverieCli-ui", "release")))
      .toBe(path.join(repository, "dist"));
    expect(findRepositoryCoreRoot(path.join(repository, "ReverieCli-ui", "release", "win-unpacked")))
      .toBe(path.join(repository, "dist"));
  });
});
