import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const executable = path.resolve(process.argv[2] || `ReverieCli-rs/target/release/reverie${process.platform === 'win32' ? '.exe' : ''}`);
const reportPath = process.argv[3];
const checks = [];
function run(name, args, input, expectedExit = 0) {
  const started = performance.now();
  const result = spawnSync(executable, args, { input, encoding: 'utf8', timeout: 15000, windowsHide: true });
  assert.ifError(result.error);
  assert.equal(result.status, expectedExit, `${name}: ${result.stderr}`);
  checks.push({ name, exit_code: result.status, milliseconds: performance.now() - started });
  return result.stdout;
}

const info = JSON.parse(run('kernel-info', ['--kernel-info']));
assert.equal(info.schema, 'reverie.kernel.v1');
assert.equal(info.bridge_protocol, 'sdk-bridge.v1');
assert.equal(info.platform, process.platform);
assert.equal(info.arch, process.arch);
assert.equal(info.implementation, 'rust');
assert.equal(info.release_status, 'development');
assert.match(run('version', ['--version']), /Kernel: rust/);
assert.match(run('help', ['--help']), /--sdk-bridge/);
run('unknown-option', ['--not-an-option'], undefined, 1);

const requests = '\ufeff' + [
  JSON.stringify({ id: '中文😀', action: 'hello' }),
  '{invalid json',
  '[]',
  JSON.stringify({ id: 9, action: 'unimplemented-action' }),
  JSON.stringify({ id: 'close', action: 'shutdown' }),
  JSON.stringify({ id: 'after-close', action: 'hello' }),
].join('\n') + '\n';
const replies = run('jsonl-errors-unicode-shutdown', ['--sdk-bridge'], requests).trim().split('\n').map(line => JSON.parse(line));
assert.equal(replies.length, 6);
assert.equal(replies[0].type, 'ready');
assert.equal(replies[0].protocol_version, 1);
assert.equal(replies[1].id, '中文😀');
assert.equal(replies[1].type, 'ready');
assert.equal(replies[2].type, 'error');
assert.equal(replies[3].type, 'error');
assert.equal(replies[4].id, 9);
assert.equal(replies[4].type, 'error');
assert.equal(replies[5].id, 'close');
assert.equal(replies[5].type, 'shutdown');
assert.equal(JSON.parse(run('eof-close', ['--sdk-bridge'], '').trim()).type, 'ready');

const report = { schema: 'reverie.rust-basic-smoke.v1', passed: true,
  verified_at: new Date().toISOString(), executable,
  executable_bytes: fs.statSync(executable).size,
  executable_sha256: crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'),
  kernel_info: info, checks,
  scope: 'Actual native entry, JSONL handshake, malformed input, Unicode IDs, explicit unknown actions, shutdown and EOF; not complete product acceptance.' };
if (reportPath) {
  fs.mkdirSync(path.dirname(path.resolve(reportPath)), { recursive: true });
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n');
}
console.log(JSON.stringify({ passed: report.passed, bytes: report.executable_bytes, checks: checks.length, report: reportPath || null }));
