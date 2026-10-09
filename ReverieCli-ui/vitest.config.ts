import { defineConfig } from "vitest/config";
import { mkdirSync } from "node:fs";
import path from "node:path";

const testTemp = path.resolve(__dirname, ".runtime", "test-temp");
mkdirSync(testTemp, { recursive: true });
process.env.TEMP = process.env.TMP = testTemp;

export default defineConfig({
  test: {
    include: ["src/**/*.test.{ts,tsx}", "electron/**/*.test.ts"],
    // Real Git/PTY fixtures need room on Windows; avoid spawning a worker per core.
    maxWorkers: 2,
    testTimeout: 15_000,
  },
});
