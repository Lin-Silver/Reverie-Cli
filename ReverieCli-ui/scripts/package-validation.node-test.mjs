import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, statSync, symlinkSync, rmSync, readFileSync, chmodSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { normalizeLinuxPayload } from './package-validation.mjs';

test('a restrictive build umask does not make installed code unreadable to other users', { skip: process.platform === 'win32' }, () => {
  const temporary = mkdtempSync(path.join(tmpdir(), 'riu-package-mode-'));
  try {
    const payload = path.join(temporary, 'payload');
    mkdirSync(payload, { mode: 0o700 });
    mkdirSync(path.join(payload, 'resources'), { mode: 0o700 });
    writeFileSync(path.join(payload, 'resources/app.asar'), 'code', { mode: 0o600 });
    writeFileSync(path.join(payload, 'ReverieUI'), 'executable', { mode: 0o700 });
    const outside = path.join(temporary, 'outside');
    writeFileSync(outside, 'private', { mode: 0o600 });
    symlinkSync(outside, path.join(payload, 'external'));
    normalizeLinuxPayload(payload);
    const mode = p => statSync(p).mode & 0o777;
    assert.equal(mode(payload), 0o755);
    assert.equal(mode(path.join(payload, 'resources')), 0o755);
    assert.equal(mode(path.join(payload, 'resources/app.asar')), 0o644);
    assert.equal(mode(path.join(payload, 'ReverieUI')), 0o755);
    assert.equal(mode(outside), 0o600);
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
});

test('the Linux distribution command always normalizes payload permissions before packaging', () => {
  const manifest = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
  assert.match(manifest.scripts['dist:linux'], /scripts\/package-validation\.mjs/);
});

test('the Linux desktop launcher resolves its real directory when invoked through an installed symlink', { skip: process.platform === 'win32' }, () => {
  const temporary = mkdtempSync(path.join(tmpdir(), 'riu-launcher-link-'));
  try {
    const app = path.join(temporary, 'opt', 'Reverie');
    const bin = path.join(temporary, 'usr', 'bin');
    const workingDirectory = path.join(temporary, 'working directory');
    mkdirSync(app, { recursive: true });
    mkdirSync(bin, { recursive: true });
    mkdirSync(workingDirectory);
    const launcher = path.join(app, 'reverieui');
    writeFileSync(launcher, readFileSync(new URL('../build/launchers/reverieui', import.meta.url)), { mode: 0o755 });
    const gui = path.join(app, 'ReverieUI');
    writeFileSync(gui, '#!/bin/sh\nprintf "GUI_PATH=<%s>\\n" "$0"\nprintf "GUI_ARG=<%s>\\n" "$@"\n');
    chmodSync(gui, 0o755);
    const installedLauncher = path.join(bin, 'reverieui');
    symlinkSync(launcher, installedLauncher);

    const output = execFileSync('/bin/sh', [installedLauncher, '--smoke-flag'], {
      cwd: workingDirectory,
      encoding: 'utf8',
    });
    assert.equal(output, [
      `GUI_PATH=<${gui}>`,
      'GUI_ARG=<--project>',
      `GUI_ARG=<${workingDirectory}>`,
      'GUI_ARG=<--smoke-flag>',
      '',
    ].join('\n'));
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
});
