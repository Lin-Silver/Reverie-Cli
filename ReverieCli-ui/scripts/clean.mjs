import { rm } from "node:fs/promises";

for (const path of ["dist", "dist-electron", ".kernel", ".vite-cache", "release"]) {
  await rm(path, { recursive: true, force: true });
}
