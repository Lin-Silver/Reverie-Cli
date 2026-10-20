import path from "node:path";

export type DesktopLaunchOptions = {
  projectRoot: string | null;
  gui: boolean;
  tui: boolean;
  tuiArgs: string[];
  isolationProbe: boolean;
  isolationProbeReport: string | null;
};

export type DesktopStartupMode = "gui" | "tui";

export function parseDesktopLaunchOptions(
  argv: readonly string[],
  cwd = process.cwd(),
): DesktopLaunchOptions {
  let projectRoot: string | null = null;
  let gui = false;
  let tui = false;
  let isolationProbe = false;
  let isolationProbeReport: string | null = null;
  const tuiArgs: string[] = [];

  for (let index = 1; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--project") {
      const value = argv[index + 1];
      if (value && !value.startsWith("--")) {
        projectRoot = path.resolve(cwd, value);
        index += 1;
      }
      continue;
    }
    if (argument === "--tui") {
      tui = true;
      gui = false;
      continue;
    }
    if (argument === "--gui") {
      gui = true;
      tui = false;
      continue;
    }
    // Isolation-probe switches drive the trusted host itself, so they never reach the TUI.
    if (argument === "--riu-isolation-probe") {
      isolationProbe = true;
      continue;
    }
    if (argument === "--riu-probe-report") {
      const value = argv[index + 1];
      if (value && !value.startsWith("--")) {
        isolationProbeReport = path.resolve(cwd, value);
        index += 1;
      }
      continue;
    }
    if (tui) tuiArgs.push(argument);
  }

  return { projectRoot, gui, tui, tuiArgs, isolationProbe, isolationProbeReport };
}

export function resolveDesktopStartupMode(
  options: DesktopLaunchOptions,
  preference: DesktopStartupMode,
): DesktopStartupMode {
  if (options.tui) return "tui";
  if (options.gui) return "gui";
  return preference;
}
