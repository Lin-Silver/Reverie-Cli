import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const buildScript = readFileSync(new URL("../scripts/build-portable.mjs", import.meta.url), "utf8");

describe("portable launcher startup", () => {
  it("can package from an isolated unpacked directory", () => {
    expect(buildScript).toContain("process.env.REVERIE_UNPACKED_ROOT");
  });

  it("reuses its extracted runtime without scanning the full payload on every launch", () => {
    expect(buildScript).toContain("CRCCheck off");
    expect(buildScript).toContain("IfFileExists");
    expect(buildScript).toContain('.reverie-build-${buildId}');
  });
});
