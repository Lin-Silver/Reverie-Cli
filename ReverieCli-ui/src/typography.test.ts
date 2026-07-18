/// <reference types="node" />

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const styles = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

describe("desktop typography", () => {
  it("uses one Windows-aware UI and monospace font stack", () => {
    expect(styles).toContain('"Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei"');
    expect(styles).toContain('--font-mono: "Cascadia Mono", "Cascadia Code"');
  });

  it("keeps captions readable and avoids fractional type scaling", () => {
    expect(styles).toContain("--font-caption: 11px");
    expect(styles).toContain(':root[data-font-size="compact"]');
    expect(styles).toContain(':root[data-font-size="large"]');
    expect(styles).not.toContain("--type-scale");

    const fixedSizes = [...styles.matchAll(/font-size:\s*([0-9]+(?:\.[0-9]+)?)px/g)]
      .map((match) => Number(match[1]));
    expect(fixedSizes.every((size) => size >= 11)).toBe(true);
    expect(fixedSizes.every(Number.isInteger)).toBe(true);
  });
});
