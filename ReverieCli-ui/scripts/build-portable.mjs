import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptRoot = path.dirname(fileURLToPath(import.meta.url));
const uiRoot = path.resolve(scriptRoot, "..");
const repositoryRoot = path.resolve(uiRoot, "..");
const unpackedRoot = process.env.REVERIE_UNPACKED_ROOT
  ? path.resolve(process.env.REVERIE_UNPACKED_ROOT)
  : path.join(uiRoot, "release", "win-unpacked");
const cacheRoot = path.join(uiRoot, ".cache", "portable-build");
const outputRoot = path.join(repositoryRoot, "dist");
const packageJson = JSON.parse(readFileSync(path.join(uiRoot, "package.json"), "utf8"));
const artifactName = `Reverie-Portable-${packageJson.version}-${process.arch}.exe`;
const output = path.join(outputRoot, artifactName);

function walkFiles(root) {
  const files = [];
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const absolute = path.join(root, entry.name);
    if (entry.isDirectory()) files.push(...walkFiles(absolute));
    else if (entry.isFile()) files.push(absolute);
  }
  return files;
}

function findMakeNsis(root) {
  if (!root || !existsSync(root)) return null;
  return walkFiles(root).find((candidate) =>
    path.basename(candidate).toLowerCase() === "makensis.exe"
    && path.basename(path.dirname(candidate)).toLowerCase() === "bin",
  ) ?? null;
}

if (!existsSync(path.join(unpackedRoot, "ReverieUI.exe")) || !existsSync(path.join(unpackedRoot, "reverie.exe"))) {
  throw new Error(`The unpacked GUI and CLI kernel must be built first: ${unpackedRoot}`);
}

const buildHash = createHash("sha256");
for (const file of walkFiles(unpackedRoot).sort()) {
  const stats = statSync(file);
  buildHash.update(path.relative(unpackedRoot, file).replaceAll(path.sep, "/"));
  buildHash.update(`${stats.size}:${Math.trunc(stats.mtimeMs)}`);
}
const buildId = buildHash.digest("hex").slice(0, 16);

mkdirSync(cacheRoot, { recursive: true });
mkdirSync(outputRoot, { recursive: true });
const markerSource = path.join(cacheRoot, `build-${buildId}.txt`);
const scriptPath = path.join(cacheRoot, "portable.nsi");
writeFileSync(markerSource, `${packageJson.version}\n${buildId}\n`, "utf8");

const nsisPath = (value) => path.resolve(value).replaceAll("/", "\\");
const numericVersion = `${packageJson.version}.0`.split(".").slice(0, 4).join(".");
const script = `Unicode true
RequestExecutionLevel user
SilentInstall silent
AutoCloseWindow true
WindowIcon off
CRCCheck off
SetDatablockOptimize on
SetCompressor /FINAL zlib
Name "Reverie"
OutFile "${nsisPath(output)}"
Icon "${nsisPath(path.join(repositoryRoot, "ReverieCli-py", "reverie.ico"))}"
VIProductVersion "${numericVersion}"
VIAddVersionKey /LANG=1033 "ProductName" "Reverie"
VIAddVersionKey /LANG=1033 "FileDescription" "Reverie Portable"
VIAddVersionKey /LANG=1033 "ProductVersion" "${packageJson.version}"
VIAddVersionKey /LANG=1033 "FileVersion" "${packageJson.version}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Reverie"
!include "FileFunc.nsh"

Section
  StrCpy $INSTDIR "$EXEDIR\\.reverie\\desktop\\app-runtime"
  IfFileExists "$INSTDIR\\.reverie-build-${buildId}" launch
  RMDir /r "$INSTDIR"
  CreateDirectory "$INSTDIR"
  SetOutPath "$INSTDIR"
  File /r "${nsisPath(unpackedRoot)}\\*.*"
  File /oname=.reverie-build-${buildId} "${nsisPath(markerSource)}"

launch:
  CreateDirectory "$EXEDIR\\.reverie\\desktop\\temp"
  System::Call 'Kernel32::SetEnvironmentVariable(t, t)i ("PORTABLE_EXECUTABLE_DIR", "$EXEDIR").r0'
  System::Call 'Kernel32::SetEnvironmentVariable(t, t)i ("PORTABLE_EXECUTABLE_FILE", "$EXEPATH").r0'
  System::Call 'Kernel32::SetEnvironmentVariable(t, t)i ("PORTABLE_EXECUTABLE_APP_FILENAME", "ReverieUI.exe").r0'
  System::Call 'Kernel32::SetEnvironmentVariable(t, t)i ("TEMP", "$EXEDIR\\.reverie\\desktop\\temp").r0'
  System::Call 'Kernel32::SetEnvironmentVariable(t, t)i ("TMP", "$EXEDIR\\.reverie\\desktop\\temp").r0'
  ${"${GetParameters}"} $R0
  ExecWait '"$INSTDIR\\ReverieUI.exe" $R0' $0
  SetErrorLevel $0
SectionEnd
`;
writeFileSync(scriptPath, script, "utf8");

const localNsisRoot = path.join(uiRoot, ".cache", "electron-builder");
const globalNsisRoot = process.env.LOCALAPPDATA
  ? path.join(process.env.LOCALAPPDATA, "electron-builder", "Cache")
  : "";
const makeNsis = findMakeNsis(localNsisRoot) ?? findMakeNsis(globalNsisRoot);
if (!makeNsis) throw new Error("makensis.exe was not found. Run the Electron NSIS build once first.");

rmSync(output, { force: true });
const result = spawnSync(makeNsis, ["-WX", "-INPUTCHARSET", "UTF8", scriptPath], {
  cwd: uiRoot,
  stdio: "inherit",
});
if (result.status !== 0 || !existsSync(output)) {
  throw new Error(`Failed to build the cached Reverie portable executable (exit ${result.status ?? "unknown"}).`);
}

console.log(`Portable Reverie: ${output}`);
