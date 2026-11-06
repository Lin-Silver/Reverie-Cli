import { rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const uiRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const pythonBuild = path.resolve(uiRoot, "../ReverieCli-py/build");

// Only disposable packaging output. Keep dependencies and download caches for rebuilds.
for (const [root, name] of [
  [pythonBuild, "pyinstaller"],
  [pythonBuild, "pyinstaller-dist"],
  [pythonBuild, `pyinstaller-ui-${process.platform}-${process.arch}`],
  [uiRoot, ".kernel"],
  [uiRoot, "release/win-unpacked"],
  [uiRoot, ".cache/portable-build"],
]) {
  const target = path.resolve(root, name);
  if (!target.startsWith(`${root}${path.sep}`)) throw new Error(`Unsafe staging path: ${target}`);
  rmSync(target, { recursive: true, force: true });
}
console.log("Removed disposable build staging; release artifacts and reusable dependencies are retained.");
