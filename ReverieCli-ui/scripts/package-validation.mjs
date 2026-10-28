// Installable validation packages never infer or contact a publication target.
import { chmodSync, lstatSync, readdirSync, realpathSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build, Platform, Arch } from 'electron-builder';

export function normalizeLinuxPayload(root) {
  const visit = (entry) => {
    const stat = lstatSync(entry);
    if (stat.isSymbolicLink()) return;
    if (stat.isDirectory()) {
      chmodSync(entry, 0o755);
      for (const child of readdirSync(entry)) visit(path.join(entry, child));
    } else if (stat.isFile()) {
      // Keep executable and special bits; shipped code/assets must be readable
      // by the installing machine's users, regardless of the build umask.
      chmodSync(entry, (stat.mode & 0o7000) | ((stat.mode & 0o111) ? 0o755 : 0o644));
    }
  };
  visit(realpathSync(root));
}

async function main() {
  if (process.platform !== 'win32') process.umask(0o022);
  const args = process.argv.slice(2);
  const options = {};
  for (let i = 0; i < args.length; i += 2) {
    if (!['--prepackaged', '--output', '--arch', '--targets'].includes(args[i]) || !args[i + 1]) {
      throw new Error('Usage: package-validation.mjs --output PATH [--prepackaged PATH] [--arch x64|arm64] [--targets deb|AppImage|dmg|nsis]');
    }
    options[args[i]] = args[i + 1];
  }
  if (!options['--output']) throw new Error('--output is required');
  const ui = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  const root = path.dirname(ui);
  const output = path.resolve(ui, options['--output']);
  const local = (p) => [path.join(root, '.runtime') + path.sep, path.join(ui, 'release') + path.sep]
    .some(prefix => p.startsWith(prefix));
  if (!local(output)) throw new Error('Keep validation output under .runtime or release');
  const architecture = options['--arch'] ?? process.arch;
  if (!['x64', 'arm64'].includes(architecture)) throw new Error('Unsupported architecture');
  const platform = process.platform === 'win32' ? Platform.WINDOWS : process.platform === 'darwin' ? Platform.MAC : Platform.LINUX;
  const names = options['--targets']?.split(',') ?? (process.platform === 'linux' ? ['AppImage', 'deb'] : process.platform === 'darwin' ? ['dmg'] : ['nsis']);
  const allowed = process.platform === 'linux' ? ['AppImage', 'deb'] : process.platform === 'darwin' ? ['dmg'] : ['nsis'];
  if (!names.length || names.some(name => !allowed.includes(name))) throw new Error('Target does not match native OS');
  const prepackaged = options['--prepackaged'] ? realpathSync(path.resolve(ui, options['--prepackaged'])) : undefined;
  if (prepackaged && !local(prepackaged)) throw new Error('Prepackaged payload must remain repository-local');
  if (prepackaged && process.platform === 'linux') normalizeLinuxPayload(prepackaged);
  await build({ projectDir: ui, prepackaged, publish: 'never',
    targets: platform.createTarget(names, architecture === 'x64' ? Arch.x64 : Arch.arm64),
    config: { publish: null, compression: 'normal', directories: { output },
      afterPack: async context => {
        if (context.electronPlatformName === 'linux') normalizeLinuxPayload(context.appOutDir);
      },
    },
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch(error => { console.error(error); process.exitCode = 1; });
}
