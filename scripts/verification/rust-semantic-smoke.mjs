import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';

const [executableArgument, bundleArgument, digest, outputArgument] = process.argv.slice(2);
if (!executableArgument || !bundleArgument || !digest) {
  throw Error('Usage: node rust-semantic-smoke.mjs <executable> <real-bundle> <manifest-sha256> [output]');
}
const executable = path.resolve(executableArgument);
const bundle = path.resolve(bundleArgument);
const output = path.resolve(outputArgument || '.runtime/rust-3.0/semantic-smoke');
fs.mkdirSync(output, {recursive: true});
const root = fs.mkdtempSync(path.join(output, 'case-'));
const workspace = path.join(root, 'workspace');
fs.mkdirSync(workspace);
const database = path.join(root, 'context.sqlite3');
fs.writeFileSync(path.join(workspace, 'saving.md'), '# 持久化进度\n退出关卡前把玩家的冒险进度、背包和已完成的目标写入本地文件。\n重新启动时读取文件恢复上次的状态。\n');
fs.writeFileSync(path.join(workspace, 'menu.md'), '# 外观\n菜单背景使用蓝色渐变，按钮文字为白色。\n');
fs.writeFileSync(path.join(workspace, 'long.md'), Array.from({length: 170}, (_, index) => `界面排版记录第 ${index + 1} 行。`).join('\n'));
const checks = [];
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
let invocation = 0;
function run(arguments_, success = true) {
  const result = spawnSync(executable, ['--context-engine', ...arguments_], {encoding: 'utf8', timeout: 90000, windowsHide: true});
  const prefix = path.join(root, `native-${++invocation}`);
  fs.writeFileSync(`${prefix}.stdout`, result.stdout || '');
  fs.writeFileSync(`${prefix}.stderr`, result.stderr || '');
  assert.ifError(result.error);
  assert.equal(result.status, success ? 0 : 1, result.stderr);
  return success ? JSON.parse(result.stdout) : result.stderr;
}
try {
  const structural = run(['index', workspace, database]);
  const first = run(['semantic-index', database, bundle, digest]);
  assert.equal(first.index.revision, structural.revision);
  assert(first.index.vectors >= 5);
  checks.push('Build actual persisted vectors from bounded, hashed source evidence');
  const repeated = run(['semantic-index', database, bundle, digest]);
  assert.equal(repeated.index.generation, first.index.generation);
  assert.equal(repeated.models.embedding_loaded, false);
  checks.push('Reuse a complete generation after process restart without loading the embedding model');
  const question = 'How can I recover player progress after closing the game?';
  const lexical = run(['search', database, question]);
  assert.equal(lexical.length, 0);
  const result = run(['semantic-search', database, bundle, digest, question]);
  assert.equal(result.results[0].file_path, 'saving.md');
  assert(result.results[0].sources.includes('semantic'));
  assert(result.results[0].sources.includes('neural_rerank'));
  assert.equal(result.models.effective_device, 'cpu');
  assert.equal(result.models.embedding_loaded, true);
  assert.equal(result.models.reranker_loaded, true);
  assert(result.results.every(hit => hit.end_line - hit.start_line + 1 <= 72 && hit.content.split('\n').length <= 72));
  assert(result.results.reduce((sum, hit) => sum + Math.floor(Array.from(hit.content).length / 4), 0) <= 12000);
  checks.push('Retrieve Chinese evidence with an English query, actual vectors and local neural reranking');
  checks.push('Preserve 72-line evidence and the historical character-count budget');
  fs.appendFileSync(path.join(workspace, 'saving.md'), '新的进度字段保存钥匙数量。\n');
  assert.match(run(['semantic-index', database, bundle, digest], false), /changed since indexing/);
  checks.push('Reject stale source before replacing the semantic generation');
  const changedStructure = run(['index', workspace, database]);
  const updated = run(['semantic-index', database, bundle, digest]);
  assert.equal(updated.index.revision, changedStructure.revision);
  assert(updated.index.generation > first.index.generation);
  const refreshed = run(['semantic-search', database, bundle, digest, question]);
  assert(refreshed.results[0].content.includes('钥匙数量'));
  assert.equal(refreshed.results[0].content_hash, hash(fs.readFileSync(path.join(workspace, 'saving.md'))));
  checks.push('Refresh changed evidence and persisted vectors with the new content identity');
  fs.unlinkSync(path.join(workspace, 'saving.md'));
  run(['index', workspace, database]);
  const removed = run(['semantic-search', database, bundle, digest, question]);
  assert(removed.results.every(hit => hit.file_path !== 'saving.md'));
  checks.push('Exclude deleted evidence when the semantic generation trails the structural index');
  run(['semantic-index', database, bundle, digest]);
  const report = {schema: 'reverie.rust-semantic-smoke.v1', passed: true, verified_at: new Date().toISOString(), executable_sha256: hash(fs.readFileSync(executable)), manifest_sha256: digest, checks, root,
    scope: 'Actual native CPU models, persistent vectors, hybrid evidence and reranking on a small independent workspace; not frozen Recall, full quantization quality, warmed latency, concurrent model updates or four-platform inference acceptance.'};
  const reportPath = path.join(root, 'report.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({passed: true, checks: checks.length, report: reportPath}));
} catch (error) {
  fs.writeFileSync(path.join(root, 'failure.json'), JSON.stringify({checks, error: String(error)}, null, 2) + '\n');
  throw error;
}
