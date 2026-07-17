import { describe, expect, it } from "vitest";
import path from "node:path";
import { parseDesktopLaunchOptions } from "./launch-options";

describe("desktop launch options", () => {
  it("resolves the reverieui project against the launcher working directory", () => {
    const workingDirectory = path.join(path.parse(process.cwd()).root, "workspace", "sample");
    const options = parseDesktopLaunchOptions(
      ["ReverieUI", "--project", ".", "--ignored"],
      workingDirectory,
    );
    expect(options.projectRoot).toBe(workingDirectory);
    expect(options.tui).toBe(false);
  });

  it("forwards only arguments following the explicit TUI switch", () => {
    const options = parseDesktopLaunchOptions(
      ["ReverieUI", "--project", "demo", "--tui", "--no-index", "src"],
      process.cwd(),
    );
    expect(options.tui).toBe(true);
    expect(options.tuiArgs).toEqual(["--no-index", "src"]);
  });
});
