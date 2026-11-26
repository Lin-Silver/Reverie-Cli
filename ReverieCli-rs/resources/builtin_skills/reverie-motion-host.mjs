// Loaded by the native command policy only for the hash-checked Motion package.
// Its CLI accepts JSON as well as flags. Check the effective input and the actual
// file operations, including derived output paths and files served for preview.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {syncBuiltinESMExports} from 'node:module';
import childProcess from 'node:child_process';

const workspace = fs.realpathSync.native(process.cwd());
const executionRoot = fs.realpathSync.native(process.env.REVERIE_BUILTIN_WORKSPACE);
const packageRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), 'reverie-motion');
const library = name => pathToFileURL(path.join(packageRoot, 'runtime/lib', name)).href;
const {findBrowsers} = await import(library('cdp.mjs'));
const {parseArgs} = await import(library('cli.mjs'));
const {TOOL_BY_CLI} = await import(library('tools.mjs'));
const browsers = new Set(findBrowsers().map(file => fs.realpathSync.native(file)));
const inside = (base, file) => {
  const relative = path.relative(base, file);
  return relative !== '..' && !relative.startsWith('..' + path.sep) && !path.isAbsolute(relative);
};

function resolved(file) {
  const full = path.resolve(file instanceof URL ? fileURLToPath(file) : file);
  if (fs.lstatSync(full, {throwIfNoEntry: false})) return fs.realpathSync.native(full);
  const parent = path.dirname(full);
  if (parent === full) throw new Error('Motion path has no existing root.');
  return path.join(resolved(parent), path.basename(full));
}
function checked(file, write) {
  const real = resolved(file);
  if ((!inside(workspace, real) && (write || !inside(packageRoot, real)))
      || (write && (inside(packageRoot, real) || (fs.lstatSync(real, {throwIfNoEntry:false})?.nlink > 1 && fs.statSync(real).isFile())))) {
    throw new Error('Motion file is outside its workspace permissions.');
  }
  return real;
}
const read = fs.readFileSync;
const write = fs.writeFileSync;
const mkdir = fs.mkdirSync;
const spawn = childProcess.spawn;
const [command, ...args] = process.argv.slice(2);
const tool = TOOL_BY_CLI.get(command);
if (!tool && !['doctor', 'help', '--help', 'version', '--version', 'schema'].includes(command)) {
  throw new Error('Only reviewed Motion design commands are available through the builtin entry.');
}
// Use the same bytes for preflight and for the CLI's subsequent --input read.
const inputs = new Map();
for (let i = 0; i < args.length; i++) {
  const name = args[i];
  if (name !== '--input' && !name.startsWith('--input=')) continue;
  const file = checked(name === '--input' ? args[++i] : name.slice(8), false);
  if (!inside(workspace, file)) throw new Error('Motion input must be in the workspace.');
  inputs.set(file, read(file, 'utf8'));
}
fs.readFileSync = (file, ...options) => {
  const real = checked(file, false);
  return inputs.get(real) ?? read(real, ...options);
};
fs.writeFileSync = (file, ...options) => write(checked(file, true), ...options);
fs.mkdirSync = (file, ...options) => mkdir(checked(file, true), ...options);
childProcess.spawn = (file, argv, options) => {
  const browser = fs.realpathSync.native(file);
  const profile = argv.find(arg => arg.startsWith('--user-data-dir='));
  if (!browsers.has(browser) || inside(executionRoot, browser) || !profile) throw new Error('Motion requires an installed browser.');
  const parent = checked(profile.slice('--user-data-dir='.length), true);
  // Chromium writes files itself. A fresh directory prevents it from following
  // pre-existing workspace links within its profile.
  const fresh = fs.mkdtempSync(path.join(parent, 'run-'));
  const identity = fs.lstatSync(fresh, {bigint:true});
  const child = spawn(browser, argv.map(arg => arg === profile ? '--user-data-dir=' + fresh : arg), options);
  child.once('exit', () => {
    // Browser helpers can inherit these handles and keep the Node CLI alive
    // after Chromium exits. No more CDP messages can arrive from that browser.
    for (const pipe of child.stdio) pipe?.destroy?.();
  });
  child.once('close', () => {
    const current = fs.lstatSync(fresh, {bigint:true, throwIfNoEntry:false});
    if (current?.isDirectory() && current.dev === identity.dev && current.ino === identity.ino
        && fs.realpathSync.native(fresh) === fresh) {
      try { fs.rmSync(fresh, {recursive:true, maxRetries:3, retryDelay:100}); }
      catch (error) { process.stderr.write(`Could not remove Motion preview profile: ${error.message}\n`); }
    }
  });
  return child;
};
syncBuiltinESMExports();
if (tool) {
  const input = parseArgs(tool, args);
  if (input.project !== undefined) checked(input.project, true);
  if (input.browser || input.allowRemote || (input.url && !/^https?:\/\//i.test(input.url))) {
    throw new Error('Use the configured browser and a local HTTP preview or a workspace file via --file.');
  }
}
