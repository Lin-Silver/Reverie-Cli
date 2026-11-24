import { createHash } from 'node:crypto';
import { chmodSync, copyFileSync, cpSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const uiRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repositoryRoot = path.resolve(uiRoot, '..');
const manifestPath = path.join(repositoryRoot, 'ReverieCli-rs/Cargo.toml');
const kernelDirectory = path.join(uiRoot, '.kernel/reverie-rust');
const generatedDirectory = path.join(uiRoot, 'build/generated');
const executableName = process.platform === 'win32' ? 'reverie.exe' : 'reverie';
function command(executable, args, options = {}) {
  const result = spawnSync(executable, args, {cwd: repositoryRoot, windowsHide: true, encoding: 'utf8', ...options});
  if (result.status !== 0) throw new Error(result.error?.message || result.stderr || String(result.status));
  return result.stdout;
}
command('cargo', ['build', '--manifest-path', manifestPath, '--release', '--locked'], {stdio: 'inherit'});
const metadata = JSON.parse(command('cargo', ['metadata', '--manifest-path', manifestPath, '--no-deps', '--format-version', '1']));
const executable = path.join(metadata.target_directory, 'release', executableName);
const info = JSON.parse(command(executable, ['--kernel-info']));
const version = JSON.parse(readFileSync(path.join(uiRoot, 'package.json'), 'utf8')).version;
if (info.schema !== 'reverie.kernel.v1' || info.bridge_protocol !== 'sdk-bridge.v1'
    || info.implementation !== 'rust' || info.version !== version || info.platform !== process.platform || info.arch !== process.arch) {
  throw new Error('Native kernel identity does not match this desktop build.');
}
command(process.execPath, [path.join(uiRoot, 'scripts/generate-core-types.mjs'), '--check'], {stdio: 'inherit'});
mkdirSync(kernelDirectory, {recursive: true});
mkdirSync(generatedDirectory, {recursive: true});
const staged = path.join(kernelDirectory, executableName);
copyFileSync(executable, staged);
cpSync(path.join(metadata.target_directory, 'release/builtin_skills'), path.join(kernelDirectory, 'builtin_skills'), {recursive:true});
if (process.platform !== 'win32') chmodSync(staged, 0o755);
copyFileSync(path.join(repositoryRoot, 'LICENSE'), path.join(kernelDirectory, 'LICENSE.txt'));
const sha256 = createHash('sha256').update(readFileSync(staged)).digest('hex');
const sourceSha = command('git', ['rev-parse', 'HEAD']).trim();
const sourceDirty = !!command('git', ['status', '--porcelain']).trim();
const trusted = {schema: 'reverie.trusted-kernels.v1', generated_at: new Date().toISOString(),
  kernels: [{sha256, platform: info.platform, arch: info.arch, version: info.version, bridge_protocol: info.bridge_protocol}]};
const trustBytes = JSON.stringify(trusted, null, 2) + '\n';
writeFileSync(path.join(kernelDirectory, 'reverie-trusted-kernels.json'), trustBytes, 'utf8');
writeFileSync(path.join(generatedDirectory, 'reverie-trusted-kernels.json'), trustBytes, 'utf8');
writeFileSync(path.join(kernelDirectory, 'reverie-kernel-build.json'), JSON.stringify({schema: 'reverie.kernel-build.v1', source_sha: sourceSha,
  source_dirty: sourceDirty, sha256, size: readFileSync(staged).length, kernel: info}, null, 2) + '\n', 'utf8');
if (!existsSync(staged)) throw new Error('The staged native kernel is missing.');
console.log('Reverie Rust desktop kernel: ' + staged);
