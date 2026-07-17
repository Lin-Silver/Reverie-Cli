import path from "node:path";

export type DesktopLaunchOptions = {
  projectRoot: string | null;
  tui: boolean;
  tuiArgs: string[];
};

export function parseDesktopLaunchOptions(
  argv: readonly string[],
  cwd = process.cwd(),
): DesktopLaunchOptions {
  let projectRoot: string | null = null;
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
      continue;
    }
    if (tui) tuiArgs.push(argument);
  }

  return { projectRoot, tui, tuiArgs };
}
