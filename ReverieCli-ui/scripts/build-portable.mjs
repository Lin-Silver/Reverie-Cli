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
const artifactName = process.env.GITHUB_ACTIONS === "true"
  ? `Reverie-Portable-${packageJson.version}-${process.arch}.exe`
  : `Reverie-Portable-${process.arch}.exe`;
let output = path.join(outputRoot, artifactName);

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

const runtimeFiles = ["ReverieUI.exe", "reverie.exe", "resources/app.asar"];
if (!runtimeFiles.every((file) => existsSync(path.join(unpackedRoot, file)))) {
  throw new Error(`The unpacked GUI and CLI kernel must be built first: ${unpackedRoot}`);
}

const buildHash = createHash("sha256");
buildHash.update(readFileSync(fileURLToPath(import.meta.url)));
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
const extraction = walkFiles(unpackedRoot).sort().map((file) => {
  const directory = path.dirname(path.relative(unpackedRoot, file));
  const suffix = directory === "." ? "" : `\\${directory.replaceAll(path.sep, "\\").replaceAll("$", () => "$$")}`;
  return `  SetOutPath "\\\\?\\$INSTDIR${suffix}"
  ClearErrors
  File "/oname=${path.basename(file).replaceAll("$", () => "$$")}" "${nsisPath(path.toNamespacedPath(file))}"
  IfErrors extract_failed`;
}).join("\n");
const numericVersion = `${packageJson.version}.0`.split(".").slice(0, 4).join(".");
const cacheChecks = [`.reverie-build-${buildId}`, ...runtimeFiles].map((file) =>
  `  IfFileExists "$INSTDIR\\${file.replaceAll("/", "\\")}" 0 \${miss}`,
).join("\n");
try {
  rmSync(output, { force: true });
} catch (error) {
  if (!["EPERM", "EACCES", "EBUSY"].includes(error.code)) throw error;
  output = path.join(outputRoot, `Reverie-Portable-${packageJson.version}-${process.arch}-${buildId}.exe`);
  console.warn(`The previous portable executable cannot be replaced; writing ${output}`);
}
const script = `Unicode true
RequestExecutionLevel user
SilentInstall normal
AutoCloseWindow true
ShowInstDetails nevershow
WindowIcon off
CRCCheck off
SetDatablockOptimize on
; Independent blocks let a cached launch skip the entire application payload.
SetCompressor /FINAL zlib
Name "Reverie"
Caption "Reverie Portable"
OutFile "${nsisPath(output)}"
Icon "${nsisPath(path.join(repositoryRoot, "ReverieCli-py", "reverie.ico"))}"
VIProductVersion "${numericVersion}"
VIAddVersionKey /LANG=1033 "ProductName" "Reverie"
VIAddVersionKey /LANG=1033 "FileDescription" "Reverie Portable"
VIAddVersionKey /LANG=1033 "ProductVersion" "${packageJson.version}"
VIAddVersionKey /LANG=1033 "FileVersion" "${packageJson.version}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Reverie"
!include "FileFunc.nsh"

!macro CheckRuntimeCache miss
${cacheChecks}
!macroend

Page instfiles

Function .onInit
  StrCpy $INSTDIR "$EXEDIR\\.reverie\\desktop\\app-runtime"
  !insertmacro CheckRuntimeCache done
  SetSilent silent
done:
FunctionEnd

Section
  !insertmacro CheckRuntimeCache extract
  Goto launch

extract:
  RMDir /r "$INSTDIR"
  CreateDirectory "$INSTDIR"
${extraction}
  SetOutPath "\\\\?\\$INSTDIR"
  ClearErrors
  File /oname=.reverie-build-${buildId} "${nsisPath(markerSource)}"
  IfErrors extract_failed
  Goto launch

extract_failed:
  SetErrorLevel 2
  Quit

launch:
  IfSilent +2
  HideWindow
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

const result = spawnSync(makeNsis, ["-WX", "-INPUTCHARSET", "UTF8", scriptPath], {
  cwd: uiRoot,
  stdio: "inherit",
});
if (result.status !== 0 || !existsSync(output)) {
  throw new Error(`Failed to build the cached Reverie portable executable (exit ${result.status ?? "unknown"}).`);
}

console.log(`Portable Reverie: ${output}`);
const manifestDirectory = path.join(uiRoot, "build", "generated");
mkdirSync(manifestDirectory, { recursive: true });
writeFileSync(path.join(manifestDirectory, "portable-artifact.json"), JSON.stringify({ path: output, buildId, version: packageJson.version }, null, 2), "utf8");
