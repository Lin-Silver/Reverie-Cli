import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const buildScript = readFileSync(new URL("../scripts/build-portable.mjs", import.meta.url), "utf8");
const packageJson = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const mainSource = readFileSync(new URL("./main.ts", import.meta.url), "utf8");

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
    expect(buildScript).not.toMatch(/^SetCompressor\b.*\/SOLID/im);
    expect(buildScript).toContain("IfFileExists");
    expect(buildScript).toContain('.reverie-build-${buildId}');
  });

  it("ships a valid multi-resolution Windows window icon separately from the EXE icon", () => {
    const resources = packageJson.build.win.extraResources;
    const icon = resources.find((resource: { to: string }) => resource.to === "reverie.ico");
    expect(icon).toBeDefined();
    const bytes = readFileSync(new URL(`../${icon.from}`, import.meta.url));
    expect(bytes.readUInt16LE(0)).toBe(0);
    expect(bytes.readUInt16LE(2)).toBe(1);
    const sizes = Array.from({ length: bytes.readUInt16LE(4) }, (_, index) => bytes[6 + 16 * index] || 256);
    expect(sizes).toEqual(expect.arrayContaining([16, 32, 48, 256]));
  });

  it("uses the installer application identity for taskbar grouping", () => {
    const identity = mainSource.match(/app\.setAppUserModelId\("([^"]+)"\)/)?.[1];
    expect(identity).toBe(packageJson.build.appId);
  });
});
