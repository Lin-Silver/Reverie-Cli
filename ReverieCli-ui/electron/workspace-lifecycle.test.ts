import { describe, expect, it, vi } from "vitest";
import path from "node:path";
import {
  activateWorkspaceInPlace,
  pathIsWithin,
  samePath,
} from "./workspace-lifecycle";

describe("workspace lifecycle", () => {
  it("switches the existing bridge in place without a stop/start contract", async () => {
    const bridge = { setProjectRoot: vi.fn() };
    const persist = vi.fn(async () => undefined);

    const projectRoot = await activateWorkspaceInPlace(bridge, process.cwd(), persist);

    expect(bridge.setProjectRoot).toHaveBeenCalledWith(projectRoot);
    expect(persist).toHaveBeenCalledWith(projectRoot);
    expect(Object.keys(bridge)).toEqual(["setProjectRoot"]);
  });

  it("rejects files and blank workspace paths", async () => {
    const bridge = { setProjectRoot: vi.fn() };
    const persist = vi.fn(async () => undefined);

    await expect(activateWorkspaceInPlace(bridge, "", persist)).rejects.toThrow("required");
    await expect(activateWorkspaceInPlace(bridge, path.resolve("package.json"), persist)).rejects.toThrow("not a directory");
    expect(bridge.setProjectRoot).not.toHaveBeenCalled();
    expect(persist).not.toHaveBeenCalled();
  });

  it("uses path boundaries instead of string prefixes", () => {
    const root = path.resolve("workspace");
    expect(samePath(root, path.join(root, "."))).toBe(true);
    expect(pathIsWithin(path.join(root, "src", "app.ts"), root)).toBe(true);
    expect(pathIsWithin(`${root}-sibling`, root)).toBe(false);
  });
});
