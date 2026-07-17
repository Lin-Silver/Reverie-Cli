import { createHash } from "node:crypto";
import {
  chmodSync,
  createReadStream,
  existsSync,
  mkdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptRoot = path.dirname(fileURLToPath(import.meta.url));
const uiRoot = path.resolve(scriptRoot, "..");
const repositoryRoot = path.resolve(uiRoot, "..");
const pythonRoot = path.join(repositoryRoot, "ReverieCli-py");
const buildRoot = path.join(pythonRoot, "build");
const outputRoot = path.join(uiRoot, ".kernel");
const kernelDirectory = path.join(outputRoot, "reverie");
const generatedBuildDirectory = path.join(uiRoot, "build", "generated");
const executableName = process.platform === "win32" ? "reverie.exe" : "reverie";
const outputExecutable = path.join(kernelDirectory, executableName);
const outputRuntime = path.join(kernelDirectory, "reverie-runtime");
const venvBin = path.join(pythonRoot, "venv", process.platform === "win32" ? "Scripts" : "bin");
const pyInstaller = path.resolve(
  process.env.REVERIE_PYINSTALLER_PATH
    || path.join(venvBin, process.platform === "win32" ? "pyinstaller.exe" : "pyinstaller"),
);
const python = path.resolve(
  process.env.REVERIE_PYTHON_PATH
    || path.join(venvBin, process.platform === "win32" ? "python.exe" : "python"),
);
const bundleRoot = path.resolve(
  process.env.REVERIE_BUNDLE_RES_DIR || path.join(buildRoot, "bundle_resources"),
);
const temporaryRoot = path.join(buildRoot, "temp");

for (const required of [
  pyInstaller,
  python,
  path.join(bundleRoot, "comfy", "generate_image.py"),
  path.join(bundleRoot, "browser", "ms-playwright"),
]) {
  if (!existsSync(required)) {
    throw new Error(`Missing CLI build input: ${required}. Run ReverieCli-py/build.bat or build.sh first.`);
  }
}

if (!outputRoot.startsWith(`${uiRoot}${path.sep}`)) {
  throw new Error(`Refusing to clean an output path outside the UI project: ${outputRoot}`);
}
rmSync(outputRoot, { recursive: true, force: true });
mkdirSync(outputRoot, { recursive: true });
mkdirSync(temporaryRoot, { recursive: true });

const iconPath = process.platform === "win32"
  ? path.join(pythonRoot, "reverie.ico")
  : path.join(pythonRoot, "reverie.png");
const result = spawnSync(
  pyInstaller,
  [
    "--noconfirm",
    "--distpath", outputRoot,
    "--workpath", path.join(buildRoot, `pyinstaller-ui-${process.platform}-${process.arch}`),
    path.join(pythonRoot, "reverie.spec"),
  ],
  {
    cwd: pythonRoot,
    stdio: "inherit",
    env: {
      ...process.env,
      REVERIE_PYINSTALLER_MODE: "ui-onedir",
      REVERIE_BUNDLE_RES_DIR: bundleRoot,
      REVERIE_ICON_PATH: iconPath,
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
if (process.platform !== "win32") chmodSync(outputExecutable, 0o755);

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

async function sha256(filePath) {
  return new Promise((resolve, reject) => {
    const hash = createHash("sha256");
    const stream = createReadStream(filePath);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("error", reject);
    stream.on("end", () => resolve(hash.digest("hex")));
  });
}

const externalKernel = path.resolve(
  process.env.REVERIE_EXTERNAL_KERNEL_PATH || path.join(repositoryRoot, "dist", executableName),
);
const trustedKernels = [];
if (existsSync(externalKernel)) {
  const probe = spawnSync(externalKernel, ["--kernel-info"], {
    encoding: "utf8",
    timeout: 20_000,
    windowsHide: true,
  });
  if (probe.status !== 0) {
    throw new Error(`External release kernel failed --kernel-info: ${externalKernel}`);
  }
  const info = JSON.parse(probe.stdout.trim());
  if (
    info.schema !== "reverie.kernel.v1"
    || info.bridge_protocol !== "sdk-bridge.v1"
    || info.platform !== process.platform
    || info.arch !== process.arch
  ) {
    throw new Error(`External release kernel is incompatible with this desktop build: ${externalKernel}`);
  }
  trustedKernels.push({
    sha256: await sha256(externalKernel),
    platform: info.platform,
    arch: info.arch,
    version: info.version,
    bridge_protocol: info.bridge_protocol,
  });
}

const trustManifest = `${JSON.stringify({
  schema: "reverie.trusted-kernels.v1",
  generated_at: new Date().toISOString(),
  kernels: trustedKernels,
}, null, 2)}\n`;
mkdirSync(generatedBuildDirectory, { recursive: true });
writeFileSync(path.join(kernelDirectory, "reverie-trusted-kernels.json"), trustManifest, "utf8");
writeFileSync(path.join(generatedBuildDirectory, "reverie-trusted-kernels.json"), trustManifest, "utf8");

console.log(`Reverie UI kernel: ${outputExecutable}`);
console.log(`Trusted external kernels: ${trustedKernels.length}`);
