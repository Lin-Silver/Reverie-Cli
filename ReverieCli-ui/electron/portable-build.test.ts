import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const buildScript = readFileSync(new URL("../scripts/build-portable.mjs", import.meta.url), "utf8");
const packageJson = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));

describe("portable launcher startup", () => {
  it.each([
    [undefined, "Reverie-Portable-x64.exe"],
    ["false", "Reverie-Portable-x64.exe"],
    ["true", `Reverie-Portable-${packageJson.version}-x64.exe`],
  ])("keeps local filenames stable and GitHub Actions filenames versioned (%s)", (actions, expected) => {
    const expression = buildScript.match(/const artifactName = ([\s\S]+?);/)?.[1];
    expect(expression).toBeDefined();
    const resolveName = new Function("process", "packageJson", `return ${expression};`);
    expect(resolveName({ arch: "x64", env: { GITHUB_ACTIONS: actions } }, packageJson)).toBe(expected);
  });

  it("can package from an isolated unpacked directory", () => {
    expect(buildScript).toContain("process.env.REVERIE_UNPACKED_ROOT");
  });

  it("reuses its extracted runtime without scanning the full payload on every launch", () => {
    expect(buildScript).toContain("CRCCheck off");
    expect(buildScript).toContain("IfFileExists");
    expect(buildScript).toContain('.reverie-build-${buildId}');
  });
});
