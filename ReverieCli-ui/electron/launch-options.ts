import path from "node:path";

export type DesktopLaunchOptions = {
  projectRoot: string | null;
  gui: boolean;
  tui: boolean;
  tuiArgs: string[];
};

export type DesktopStartupMode = "gui" | "tui";

export function parseDesktopLaunchOptions(
  argv: readonly string[],
  cwd = process.cwd(),
): DesktopLaunchOptions {
  let projectRoot: string | null = null;
  let gui = false;
  let tui = false;
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
    if (tui) tuiArgs.push(argument);
  }

  return { projectRoot, gui, tui, tuiArgs };
}

export function resolveDesktopStartupMode(
  options: DesktopLaunchOptions,
  preference: DesktopStartupMode,
): DesktopStartupMode {
  if (options.tui) return "tui";
  if (options.gui) return "gui";
  return preference;
}
