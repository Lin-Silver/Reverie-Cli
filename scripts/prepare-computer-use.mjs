import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const resources = fileURLToPath(new URL('../ReverieCli-rs/resources/computer-use/', import.meta.url));
const manifest = JSON.parse(fs.readFileSync(path.join(resources, 'manifest.json')));
const os = {win32: 'windows', linux: 'linux', darwin: 'macos'}[process.platform];
const arch = {x64: 'x86_64', arm64: 'aarch64'}[process.arch];
const platform = manifest.platforms[`${os}-${arch}`];
if (!platform || !process.argv[2]) throw new Error('Expected a supported native platform and a kernel directory.');
const target = path.resolve(process.argv[2], 'computer-use');
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const license = fs.readFileSync(path.join(resources, 'LICENSE'));
if (hash(license) !== manifest.license_sha256) throw new Error('Computer Use license checksum mismatch.');
fs.mkdirSync(target, {recursive: true});
const matches = (name, digest) => fs.existsSync(path.join(target, name)) && hash(fs.readFileSync(path.join(target, name))) === digest;
if (!Object.entries(platform.files).every(([name, digest]) => matches(name, digest))) {
  const cache = process.env.REVERIE_DESKTOP_ARCHIVE_DIR;
  let archive;
  if (cache) {
    archive = fs.readFileSync(path.join(cache, platform.archive));
  } else {
    const response = await fetch(`${manifest.repository}/releases/download/v${manifest.version}/${platform.archive}`,
      {signal: AbortSignal.timeout(120000)});
    if (!response.ok) throw new Error(`Computer Use archive returned HTTP ${response.status}`);
    archive = Buffer.from(await response.arrayBuffer());
  }
  if (hash(archive) !== platform.archive_sha256) throw new Error('Computer Use archive checksum mismatch.');
  const stage = fs.mkdtempSync(path.join(target, '.prepare-'));
  try {
    const tar = path.join(stage, 'engine.tar.gz');
    fs.writeFileSync(tar, archive);
    for (const [name, expected] of Object.entries(platform.files)) {
      const bytes = execFileSync('tar', ['-xOzf', tar, name], {maxBuffer: 32 * 1024 * 1024, windowsHide: true});
      if (hash(bytes) !== expected) throw new Error(`Computer Use checksum mismatch for ${name}.`);
      fs.writeFileSync(path.join(stage, name), bytes, {mode: 0o755});
    }
    for (const name of Object.keys(platform.files)) fs.renameSync(path.join(stage, name), path.join(target, name));
  } finally {
    fs.rmSync(stage, {recursive: true, force: true});
  }
}
fs.writeFileSync(path.join(target, 'LICENSE'), license);
fs.copyFileSync(path.join(resources, 'manifest.json'), path.join(target, 'manifest.json'));
fs.copyFileSync(path.resolve(resources, '../../crates/core/licenses/desktop-image-notices.txt'), path.join(target, 'desktop-image-notices.txt'));
console.log(`Prepared agent-desktop ${manifest.version} (${os}-${arch}) at ${target}`);
