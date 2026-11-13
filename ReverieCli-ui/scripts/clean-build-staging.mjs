import { rmSync, statfsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const uiRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const pythonBuild = path.resolve(uiRoot, "../ReverieCli-py/build");
const preparing = process.argv.includes("--prepare");

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

if (preparing) {
  const gib = 1024 ** 3;
  const minimumGiB = 8;
  const { bavail, bsize } = statfsSync(uiRoot);
  const freeGiB = bavail * bsize / gib;
  if (freeGiB < minimumGiB) {
    console.error(`[ERROR] ${uiRoot} has ${freeGiB.toFixed(2)} GiB free after cleaning build staging. The Windows build requires at least ${minimumGiB} GiB free. Free disk space or move the checkout to another drive and retry.`);
    process.exitCode = 1;
  } else {
    console.log(`[OK] Windows build volume has ${freeGiB.toFixed(2)} GiB free.`);
  }
}
