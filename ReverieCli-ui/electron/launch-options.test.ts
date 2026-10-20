import { describe, expect, it } from "vitest";
import path from "node:path";
import { parseDesktopLaunchOptions, resolveDesktopStartupMode } from "./launch-options";

describe("desktop launch options", () => {
  it("resolves the reverieui project against the launcher working directory", () => {
    const workingDirectory = path.join(path.parse(process.cwd()).root, "workspace", "sample");
    const options = parseDesktopLaunchOptions(
      ["ReverieUI", "--project", ".", "--ignored"],
      workingDirectory,
    );
    expect(options.projectRoot).toBe(workingDirectory);
    expect(options.gui).toBe(false);
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

  it("lets an explicit launch switch override the saved startup mode", () => {
    const guiOptions = parseDesktopLaunchOptions(["ReverieUI", "--gui"]);
    const tuiOptions = parseDesktopLaunchOptions(["ReverieUI", "--tui"]);
    expect(resolveDesktopStartupMode(guiOptions, "tui")).toBe("gui");
    expect(resolveDesktopStartupMode(tuiOptions, "gui")).toBe("tui");
    expect(resolveDesktopStartupMode(parseDesktopLaunchOptions(["ReverieUI"]), "tui")).toBe("tui");
  });

  it("accepts the isolation probe switch with a report path and keeps it out of the TUI argument list", () => {
    const workingDirectory = path.join(path.parse(process.cwd()).root, "workspace", "sample");
    const options = parseDesktopLaunchOptions(
      ["ReverieUI", "--riu-isolation-probe", "--riu-probe-report", "report.json"],
      workingDirectory,
    );
    expect(options.isolationProbe).toBe(true);
    expect(options.isolationProbeReport).toBe(path.join(workingDirectory, "report.json"));
    expect(options.tui).toBe(false);
    expect(parseDesktopLaunchOptions(["ReverieUI"]).isolationProbe).toBe(false);
    expect(parseDesktopLaunchOptions(["ReverieUI", "--riu-isolation-probe"]).isolationProbeReport).toBeNull();
    expect(parseDesktopLaunchOptions(["ReverieUI", "--tui", "--riu-isolation-probe"]).tuiArgs).toEqual([]);
  });
});
