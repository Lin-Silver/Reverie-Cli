import { existsSync, mkdirSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptRoot = path.dirname(fileURLToPath(import.meta.url));
const uiRoot = path.resolve(scriptRoot, "..");
const repositoryRoot = path.resolve(uiRoot, "..");
const pythonRoot = path.join(repositoryRoot, "ReverieCli-py");
const buildRoot = path.join(pythonRoot, "build");
const outputRoot = path.join(uiRoot, ".kernel");
const outputExecutable = path.join(outputRoot, "reverie", "reverie.exe");
const outputRuntime = path.join(outputRoot, "reverie", "reverie-runtime");
const pyInstaller = path.resolve(
  process.env.REVERIE_PYINSTALLER_PATH || path.join(pythonRoot, "venv", "Scripts", "pyinstaller.exe"),
);
const python = path.resolve(
  process.env.REVERIE_PYTHON_PATH || path.join(pythonRoot, "venv", "Scripts", "python.exe"),
);
const bundleRoot = path.resolve(
  process.env.REVERIE_BUNDLE_RES_DIR || path.join(buildRoot, "bundle_resources"),
);
const temporaryRoot = path.join(buildRoot, "temp");

for (const required of [
  pyInstaller,
  path.join(bundleRoot, "comfy", "generate_image.py"),
  path.join(bundleRoot, "browser", "ms-playwright"),
]) {
  if (!existsSync(required)) {
    throw new Error(`Missing CLI build input: ${required}. Run ReverieCli-py\\build.bat first.`);
  }
}

if (!outputRoot.startsWith(`${uiRoot}${path.sep}`)) {
  throw new Error(`Refusing to clean an output path outside the UI project: ${outputRoot}`);
}
rmSync(outputRoot, { recursive: true, force: true });
mkdirSync(outputRoot, { recursive: true });
mkdirSync(temporaryRoot, { recursive: true });

const result = spawnSync(
  pyInstaller,
  [
    "--noconfirm",
    "--distpath", outputRoot,
    "--workpath", path.join(buildRoot, "pyinstaller-ui"),
    path.join(pythonRoot, "reverie.spec"),
  ],
  {
    cwd: pythonRoot,
    stdio: "inherit",
    env: {
      ...process.env,
      REVERIE_PYINSTALLER_MODE: "ui-onedir",
      REVERIE_BUNDLE_RES_DIR: bundleRoot,
      REVERIE_ICON_PATH: path.join(pythonRoot, "reverie.ico"),
      PYINSTALLER_CONFIG_DIR: path.join(buildRoot, "pyinstaller-config"),
      TEMP: temporaryRoot,
      TMP: temporaryRoot,
      TMPDIR: temporaryRoot,
      PYTHONWARNINGS: "ignore:Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.:UserWarning",
    },
  },
);

if (result.status !== 0 || !existsSync(outputExecutable)) {
  throw new Error(`Failed to build the unpacked Reverie UI kernel (exit ${result.status ?? "unknown"}).`);
}

const resourcePack = spawnSync(
  python,
  [
    path.join(pythonRoot, "scripts", "pack_ui_resources.py"),
    "--browser", path.join(bundleRoot, "browser", "ms-playwright"),
    "--output", path.join(outputRuntime, "reverie_resources"),
  ],
  { cwd: pythonRoot, stdio: "inherit", env: process.env },
);
if (resourcePack.status !== 0) {
  throw new Error(`Failed to pack lazy UI-kernel resources (exit ${resourcePack.status ?? "unknown"}).`);
}

console.log(`Reverie UI kernel: ${outputExecutable}`);
