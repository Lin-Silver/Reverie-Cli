import { lstat, mkdir, open, realpath } from "node:fs/promises";
import path from "node:path";
import { browserId, pngDimensions } from "./browser-policy";

function inside(root: string, candidate: string): boolean {
  const relative = path.relative(root, candidate);
  return relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}

/** Browser images are newly created project artifacts; existing links and files are never followed or replaced. */
export async function saveBrowserImage(projectRoot: string, imageId: string, png: Buffer): Promise<string> {
  if (!path.isAbsolute(projectRoot) || !browserId(imageId) || png.length > 32 * 1024 * 1024) throw new Error("Invalid browser image artifact.");
  pngDimensions(png);
  const rootInfo = await lstat(projectRoot);
  if (rootInfo.isSymbolicLink() || !rootInfo.isDirectory()) throw new Error("Browser image root must be a real directory.");
  const root = await realpath(projectRoot);
  let directory = root;
  for (const part of [".reverie", "browser", "observations"]) {
    directory = path.join(directory, part);
    try { await mkdir(directory); } catch (error) { if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error; }
    const info = await lstat(directory);
    if (info.isSymbolicLink() || !info.isDirectory() || !inside(root, await realpath(directory))) throw new Error("Browser image directory is unsafe.");
  }
  const before = await realpath(directory);
  const file = path.join(directory, `${imageId}.png`);
  const handle = await open(file, "wx", 0o600);
  try { await handle.writeFile(png); await handle.sync(); } finally { await handle.close(); }
  const info = await lstat(file);
  if (info.isSymbolicLink() || !info.isFile() || await realpath(directory) !== before || !inside(root, await realpath(file))) throw new Error("Browser image path changed during capture.");
  return file;
}
