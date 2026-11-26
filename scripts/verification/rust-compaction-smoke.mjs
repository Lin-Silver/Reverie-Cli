import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import http from 'node:http';
import {DatabaseSync} from 'node:sqlite';
import {setTimeout as delay} from 'node:timers/promises';
import {fileURLToPath} from 'node:url';
import {startBridge} from './rust-bridge-client.mjs';

const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const executable = path.resolve(process.argv[2] || `ReverieCli-rs/target/release/reverie${process.platform === 'win32' ? '.exe' : ''}`);
assert(fs.statSync(executable).isFile(), 'Build the actual Rust executable before this smoke run');
const executableHash = crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex');
const directory = path.resolve(process.argv[3] || '.runtime/rust-3.0/compaction-smoke');
fs.mkdirSync(directory, {recursive: true});
const root = fs.mkdtempSync(path.join(directory, 'case-'));
const project = path.join(root, '工作区😀');
const appRoot = path.join(root, 'application');
for (const folder of [project, path.join(appRoot, '.reverie')]) fs.mkdirSync(folder, {recursive: true});
const source = fs.readFileSync(path.join(repository, 'ReverieCli-rs/crates/core/src/compaction.rs'), 'utf8').replaceAll('\r\n', '\n');
const compressionPrompt = source.match(/pub const COMPRESSION_SYSTEM_PROMPT: &str = r#"([\s\S]*?)"#;/)?.[1];
const handoffPrompt = source.match(/pub const HANDOFF_SYSTEM_PROMPT: &str = r#"([\s\S]*?)"#;/)?.[1];
assert(compressionPrompt && handoffPrompt, 'Fixed native summary prompts must exist');
assert.equal(crypto.createHash('sha256').update(compressionPrompt).digest('hex'), 'a4568c8742776db27eea428bd33f65820b21bc81dd0af4f663a5070d75e866f7');
assert.equal(crypto.createHash('sha256').update(handoffPrompt).digest('hex'), '5cc403604db63d685066fd3f1ea4d86dab1e20bf794b43fc90315b8ab4e1613b');
const requests = [];
const checks = [];
const held = new Map();
let phase;
let bridge;
let dbPath;
let dataRoot;
let serverFailure;
process.env.NO_PROXY = [process.env.NO_PROXY, '127.0.0.1', 'localhost'].filter(Boolean).join(',');

function finish(response, message) {
  response.writeHead(200, {'content-type': 'application/json'});
  response.end(JSON.stringify({choices: [{message, finish_reason: message.tool_calls?.length ? 'tool_calls' : 'stop'}]}));
}

function summary() {
  return 'Summary:\n\n1. **Primary Request and Intent:**\n- Preserve the original fixture transcript and continue the current task.\n\n9. **Immediate Next Step and Resume Instructions:**\n- Continue from the stored current request; do not replay old tool deliveries.';
}

const server = http.createServer(async (request, response) => {
  try {
    assert(phase, 'A model phase must be explicitly selected');
    assert.equal(request.url, '/v1/chat/completions');
    let bytes = '';
    for await (const chunk of request) bytes += chunk;
    const body = JSON.parse(bytes);
    assert.equal(body.model, 'session-main');
    assert.equal(body.stream, false);
    assert.equal(request.headers.authorization, 'Bearer FIXTURE_SECRET');
    assert(!bytes.includes('FIXTURE_SECRET'), 'Credentials must not enter summary or model messages');
    const first = body.messages[0]?.content;
    const kind = first === compressionPrompt ? 'compression' : first === handoffPrompt ? 'handoff' : 'main';
    const record = {case: phase.name, kind, model: body.model, message_count: body.messages.length,
      tools_count: body.tools?.length || 0, request_sha256: crypto.createHash('sha256').update(bytes).digest('hex')};
    requests.push(record);
    if (kind !== 'main') {
      assert.equal(body.messages.length, 2);
      assert(!body.tools?.length, 'Reduction and repair model requests must expose no tools');
      assert.equal(body.messages[1].role, 'user');
      if (kind === 'compression') {
        if (phase.focus) assert(body.messages[1].content.includes(phase.focus));
        if (phase.behavior === 'model-failure') {
          response.writeHead(503, {'content-type': 'application/json'});
          response.end('{"error":{"type":"fixture_unavailable"}}');
          return;
        }
        if (phase.behavior === 'forbidden-tool') {
          finish(response, {role: 'assistant', content: null, tool_calls: [{id: 'forbidden-summary-tool', type: 'function',
            function: {name: 'create_file', arguments: JSON.stringify({path: 'forbidden-summary.txt', content: 'must never execute'})}}]});
          return;
        }
        if (['cancel', 'revision', 'checkpoint'].includes(phase.behavior)) {
          held.set(phase.name, {response, kind});
          response.once('close', () => held.delete(phase.name));
          return;
        }
        finish(response, {role: 'assistant', content: summary()});
        return;
      }
      const repair = body.messages[1].content.startsWith('The previous handoff response was invalid or too empty.');
      record.repair = repair;
      const invalid = phase.behavior === 'invalid-handoff' || (phase.behavior === 'repair-handoff' && !repair);
      finish(response, {role: 'assistant', content: invalid ? '{"latest_user_request":"only an echo"}' : JSON.stringify({
        project_goal: 'Continue the current native task with original user text retained once.',
        current_state: ['The fixture old tool interaction completed.'],
        next_actions: ['Execute the requested native fixture file creation.'],
        verification_state: ['The loopback response proves protocol behavior only.'],
      })});
      return;
    }
    assert.notEqual(phase.kind, 'manual', 'Manual compaction must not run the main agent');
    const latest = body.messages.findLast(message => message.role === 'user');
    assert.equal(latest?.content, phase.expectedPrompt, 'Continue the original requested user text');
    assert(body.messages.every(message => message.segment_boundary === undefined && message.context_replay === undefined && message.native_context === undefined),
      'Internal projection markers must not enter the provider payload');
    if (phase.behavior === 'hold-main') {
      held.set(phase.name, {response, kind});
      response.once('close', () => held.delete(phase.name));
      return;
    }
    const callId = `native-effect-${phase.name}`;
    if (body.messages.at(-1).role === 'tool' && body.messages.at(-1).tool_call_id === callId) {
      const result = JSON.parse(body.messages.at(-1).content);
      assert.equal(result.success, true, JSON.stringify(result));
      assert.equal(fs.readFileSync(path.join(project, phase.toolPath), 'utf8'), phase.toolContent);
      finish(response, {role: 'assistant', content: 'Native effect verified; continued in the same conversation.'});
    } else {
      assert(body.tools.some(tool => tool.function.name === 'create_file'));
      finish(response, {role: 'assistant', content: null, tool_calls: [{id: callId, type: 'function', function: {
        name: 'create_file', arguments: JSON.stringify({path: phase.toolPath, content: phase.toolContent}),
      }}]});
    }
  } catch (error) {
    serverFailure = error;
    response.destroy(error);
  }
});

await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const models = ['global-default', 'session-main'].map(model => ({model, profile_id: model, provider: 'openai-chat',
  base_url: `http://127.0.0.1:${server.address().port}/v1`, api_key: 'FIXTURE_SECRET'}));
fs.writeFileSync(path.join(appRoot, '.reverie/config.json'), JSON.stringify({mode: 'reverie', models,
  active_model_source: 'standard', active_model_index: 0, auto_index: false, stream_responses: false,
  max_context_tokens: 128000, api_max_retries: 0, security: {permission_level: 'full_control', permission_mode: 'default'}}));

async function request(action, payload = {}, expected) {
  const reply = await bridge.request(action, {projectRoot: project, ...payload}, 30_000);
  if (serverFailure) throw serverFailure;
  if (expected) assert.equal(reply.type, expected, JSON.stringify(reply));
  assert(!JSON.stringify(reply).includes('FIXTURE_SECRET'));
  return reply;
}

async function start() {
  bridge = startBridge(executable, project, appRoot);
  await bridge.ready;
  const initialized = await request('initialize', {}, 'state');
  dataRoot = initialized.state.workspace.project_data_dir;
  dbPath = path.join(dataRoot, 'conversations.sqlite3');
}

async function stop() {
  if (bridge.child.exitCode === null) await request('shutdown', {}, 'shutdown');
  assert.equal((await bridge.closed).code, 0);
}

function raw(id) {
  const db = new DatabaseSync(dbPath, {readOnly: true});
  try {
    db.exec('BEGIN');
    const conversation = {...db.prepare('SELECT id,name,created_at,updated_at,metadata,revision,message_count FROM conversations WHERE id=?').get(id)};
    const records = db.prepare('SELECT sequence,id,payload,digest FROM messages WHERE session_id=? ORDER BY sequence').all(id).map(row => ({...row}));
    const configurations = db.prepare('SELECT revision,payload,created_at FROM configuration_versions WHERE session_id=? ORDER BY revision').all(id).map(row => ({...row}));
    const selected = db.prepare("SELECT value FROM navigation WHERE key='selected'").get()?.value;
    db.exec('COMMIT');
    return {conversation, records, configurations, selected};
  } finally { db.close(); }
}

function boundaries(state) {
  return state.records.map(record => JSON.parse(record.payload)).filter(message => message.segment_boundary === true);
}

function assertOriginals(before, after) {
  assert.deepEqual(after.records.slice(0, before.records.length), before.records, 'Every original id, byte string, digest and sequence must be unchanged');
  assert.deepEqual(after.configurations, before.configurations, 'Context projection changes must not create a configuration version');
  assert.equal(after.conversation.id, before.conversation.id);
  const oldMetadata = JSON.parse(before.conversation.metadata);
  const newMetadata = JSON.parse(after.conversation.metadata);
  assert.deepEqual(newMetadata.runtime_config, oldMetadata.runtime_config);
  assert.equal(newMetadata.workspace_id, oldMetadata.workspace_id);
  assert.equal(after.selected, before.selected);
}

async function seeded(name, capacity = 128000, longTail = false) {
  const session = (await request('createSession', {name}, 'session.created')).session;
  await request('selectModel', {sessionId: session.id, source: 'standard', modelId: 'session-main'}, 'model.selected');
  await request('setSetting', {sessionId: session.id, key: 'max_context_tokens', value: capacity}, 'setting.updated');
  await stop();
  const block = 'Verified source with pending implementation. 中文原文😀\r\n';
  const history = [{role: 'system', content: 'Durable original instruction: preserve source and the same task.'},
    ...Array.from({length: 30}, (_, index) => ({role: index % 2 ? 'Reverie' : 'user',
      content: `Original ${index}\r\n${block.repeat(120)}`, unknown: {index, keep: true}})),
    {role: 'user', content: 'Old complete interaction'},
    {role: 'Reverie', content: null, tool_calls: [{id: `old-a-${name}`, type: 'function', function: {name: 'read_file', arguments: '{"path":"fixture.txt"}'}},
      {id: `old-b-${name}`, type: 'function', function: {name: 'search_files', arguments: '{"pattern":"fixture"}'}}]},
    {role: 'tool', tool_call_id: `old-a-${name}`, name: 'read_file', content: longTail ? block.repeat(4000) : 'Observed old file source\r\n😀'},
    {role: 'tool', tool_call_id: `old-b-${name}`, name: 'search_files', content: longTail ? block.repeat(4000) : 'Observed old search result'},
    {role: 'Reverie', content: 'Both old calls completed.'},
    {role: 'user', content: `Stored user ${name}\r\n全部正文😀\n`, attachment: {path: '原文.png', revision: 7}}];
  const db = new DatabaseSync(dbPath);
  try {
    db.exec('BEGIN IMMEDIATE');
    const insert = db.prepare('INSERT INTO messages VALUES (?,?,?,?,?)');
    for (const [sequence, message] of history.entries()) {
      const payload = JSON.stringify(message);
      insert.run(session.id, sequence, `${name}-source-${sequence}`, payload, crypto.createHash('sha256').update(payload).digest('hex'));
    }
    db.prepare('UPDATE conversations SET message_count=?,revision=revision+1 WHERE id=?').run(history.length, session.id);
    db.exec('COMMIT');
  } finally { db.close(); }
  await start();
  return session.id;
}

function passed(label) { checks.push(label); }

async function waitHeld(name) {
  const until = Date.now() + 15_000;
  while (Date.now() < until) {
    if (serverFailure) throw serverFailure;
    if (held.has(name)) return held.get(name);
    await delay(20);
  }
  throw new Error(`No actual pending model request for ${name}`);
}

async function manual(name, behavior = 'normal') {
  const id = await seeded(name);
  const before = raw(id);
  phase = {name, kind: 'manual', behavior, focus: '保留完整需求、未完成事项及来源😀'};
  const reply = await request('compactContext', {sessionId: id, runId: `manual-${name}`, focus: phase.focus}, 'context.compacted');
  const after = raw(id);
  assertOriginals(before, after);
  assert.equal(after.records.length, before.records.length + 1);
  const boundary = boundaries(after).at(-1);
  assert.equal(boundary.native_context.kind, 'compression');
  assert.equal(boundary.native_context.origin, behavior === 'normal' ? 'model' : 'deterministic_fallback');
  assert.equal(boundary.native_context.source.session_id, id);
  assert.equal(boundary.native_context.usage_after.tokenizer.name, 'cl100k_base');
  assert.equal(boundary.native_context.usage_after.tokenizer.exact, false);
  assert.equal(boundary.native_context.usage_after.envelope_estimated, true);
  assert(boundary.native_context.usage_after.tokens < boundary.native_context.usage_before.tokens);
  const checkpoint = boundary.native_context.checkpoint;
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(checkpoint.path)).digest('hex'), checkpoint.sha256);
  assert.deepEqual(JSON.parse(fs.readFileSync(checkpoint.path, 'utf8')).records, before.records);
  const current = after.records.filter(record => JSON.parse(record.payload).role === 'user' && JSON.parse(record.payload).content === `Stored user ${name}\r\n全部正文😀\n`);
  assert.equal(current.length, 1);
  assert(!fs.existsSync(path.join(project, 'forbidden-summary.txt')));
  return {id, before, after, reply};
}

async function nativeRun(name, behavior = 'normal', longTail = false) {
  const id = await seeded(name, 16000, longTail);
  const before = raw(id);
  phase = {name, kind: 'run', behavior, expectedPrompt: `CURRENT:${name}\r\n保持原文😀\n`, toolPath: `${name}-effect.txt`, toolContent: 'Native tool effect\r\n完整正文😀\n'};
  const reply = await request('runPrompt', {sessionId: id, runId: `run-${name}`, prompt: phase.expectedPrompt, noIndex: true}, 'prompt.result');
  const after = raw(id);
  assertOriginals(before, after);
  assert.equal(after.records.filter(record => {const message = JSON.parse(record.payload); return message.role === 'user' && message.content === phase.expectedPrompt;}).length, 1);
  return {id, before, after, reply, calls: requests.filter(request => request.case === name)};
}

try {
  await start();
  const manualResult = await manual('manual');
  passed('Manual no-tools compaction preserves original rows, same ID, complete checkpoint and current user once');
  await stop();
  await start();
  assert.deepEqual(raw(manualResult.id), manualResult.after);
  const page = (await request('getSession', {sessionId: manualResult.id, select: false}, 'session')).session;
  assert.equal(page.id, manualResult.id);
  passed('Actual native shutdown and restart preserve the saved projection and raw transcript');

  await manual('fallback', 'model-failure');
  passed('Actual model HTTP failure uses the explicitly identified local compression fallback');
  await manual('forbidden-tool', 'forbidden-tool');
  passed('Summary tool calls are never dispatched and the fallback remains explicitly identified');

  for (const behavior of ['cancel', 'revision', 'checkpoint']) {
    const id = await seeded(behavior);
    const before = raw(id);
    phase = {name: behavior, kind: 'manual', behavior};
    const pending = request('compactContext', {sessionId: id, runId: `manual-${behavior}`, focus: 'Preserve source'});
    const holder = await waitHeld(behavior);
    let expected = before;
    let changedCheckpoint;
    let checkpointBytes;
    if (behavior === 'cancel') {
      await request('stopPrompt', {sessionId: id, runId: `manual-${behavior}`}, 'run.control');
    } else if (behavior === 'revision') {
      await request('setSetting', {sessionId: id, key: 'mode', value: 'atlas'}, 'setting.updated');
      expected = raw(id);
      finish(holder.response, {role: 'assistant', content: summary()});
    } else {
      const checkpointDirectory = path.join(dataRoot, 'context_checkpoints');
      changedCheckpoint = fs.readdirSync(checkpointDirectory).map(name => path.join(checkpointDirectory, name)).find(filename => {
        try {const data = JSON.parse(fs.readFileSync(filename, 'utf8')); return data.source.session_id === id && data.source.revision === before.conversation.revision;} catch {return false;}
      });
      assert(changedCheckpoint, 'Pre-model checkpoint must already exist');
      assert(path.resolve(changedCheckpoint).startsWith(path.resolve(root) + path.sep));
      checkpointBytes = fs.readFileSync(changedCheckpoint);
      fs.writeFileSync(changedCheckpoint, 'truncated isolated fixture checkpoint');
      finish(holder.response, {role: 'assistant', content: summary()});
    }
    const reply = await pending;
    assert(['error', 'context.compacted'].includes(reply.type), JSON.stringify(reply));
    const after = raw(id);
    assert.deepEqual(after.records, before.records);
    assert.deepEqual(after.conversation, expected.conversation);
    assert(!JSON.parse(after.conversation.metadata).native_context_projection);
    if (changedCheckpoint) fs.writeFileSync(changedCheckpoint, checkpointBytes);
    passed(`${behavior} leaves the original active context and immutable rows unchanged`);
  }

  const automatic = await nativeRun('automatic');
  assert.equal(automatic.reply.result.state, 'completed');
  assert.equal(automatic.calls[0].kind, 'compression');
  assert.equal(fs.readFileSync(path.join(project, 'automatic-effect.txt'), 'utf8'), 'Native tool effect\r\n完整正文😀\n');
  assert(boundaries(automatic.after).some(boundary => boundary.native_context.kind === 'compression'));
  passed('Automatic 70 percent compression continues the same native run and performs its actual file effect');

  for (const [name, behavior] of [['handoff', 'normal'], ['handoff-repair', 'repair-handoff']]) {
    const result = await nativeRun(name, behavior, true);
    assert.equal(result.reply.result.state, 'completed');
    assert.equal(result.calls[0].kind, 'compression', '82 percent must not skip the first compression');
    const handoffs = result.calls.filter(call => call.kind === 'handoff');
    assert.equal(handoffs.length, behavior === 'repair-handoff' ? 2 : 1);
    if (behavior === 'repair-handoff') assert.equal(handoffs[1].repair, true);
    const boundary = boundaries(result.after).findLast(boundary => boundary.native_context.kind === 'handoff');
    assert(boundary);
    assert.equal(boundary.native_context.handoff.schema_version, 2);
    const projection = JSON.parse(result.after.conversation.metadata).native_context_projection;
    assert.equal(projection.tail_sequences.length, 1, 'Handoff references only the exact current user request');
    const firstMain = result.calls.findIndex(call => call.kind === 'main');
    assert(firstMain > result.calls.findLastIndex(call => call.kind === 'handoff'));
    assert.equal(fs.readFileSync(path.join(project, `${name}-effect.txt`), 'utf8'), 'Native tool effect\r\n完整正文😀\n');
    passed(`${name} compacts first, recounts, uses model-only handoff and continues the same task`);
  }

  const invalid = await nativeRun('invalid-handoff', 'invalid-handoff', true);
  assert.equal(invalid.calls.filter(call => call.kind === 'handoff').length, 2);
  assert(!boundaries(invalid.after).some(boundary => boundary.native_context.kind === 'handoff'));
  assert(!fs.existsSync(path.join(project, 'invalid-handoff-effect.txt')));
  assert.equal(invalid.reply.result.state, 'failed');
  passed('An invalid handoff and its single invalid repair retain the last valid context without task effects');

  const resumeId = await seeded('resume');
  phase = {name: 'interrupted', kind: 'run', behavior: 'hold-main', expectedPrompt: 'CURRENT:resume\r\n完整请求😀\n'};
  const interrupted = request('runPrompt', {sessionId: resumeId, runId: 'interrupted-run', prompt: phase.expectedPrompt, noIndex: true}, 'prompt.result');
  await waitHeld('interrupted');
  await request('stopPrompt', {sessionId: resumeId, runId: 'interrupted-run'}, 'run.control');
  assert.equal((await interrupted).result.state, 'cancelled');
  const saved = raw(resumeId);
  await stop();
  await start();
  phase = {name: 'resumed', kind: 'run', behavior: 'normal', expectedPrompt: 'CURRENT:resume\r\n完整请求😀\n', toolPath: 'resumed-effect.txt', toolContent: 'Resumed native effect\r\n😀\n'};
  const resumed = await request('resumePrompt', {sessionId: resumeId, runId: 'resumed-run', noIndex: true}, 'prompt.result');
  assert.equal(resumed.result.state, 'completed');
  const afterResume = raw(resumeId);
  assertOriginals(saved, afterResume);
  assert.equal(afterResume.records.filter(record => {const message = JSON.parse(record.payload); return message.role === 'user' && message.content === phase.expectedPrompt;}).length, 1);
  assert.equal(fs.readFileSync(path.join(project, 'resumed-effect.txt'), 'utf8'), phase.toolContent);
  passed('Ordinary resumePrompt after an actual cancelled request and native restart reuses the exact saved user once');

  const attachmentId = await seeded('attachment-resume');
  const attachmentSource = raw(attachmentId);
  phase = {name: 'attachment-resumed', kind: 'run', behavior: 'normal', expectedPrompt: 'Stored user attachment-resume\r\n全部正文😀\n',
    toolPath: 'attachment-resumed-effect.txt', toolContent: 'Same saved payload\r\n😀\n'};
  const attachmentResumed = await request('resumePrompt', {sessionId: attachmentId, runId: 'attachment-resumed-run', noIndex: true}, 'prompt.result');
  assert.equal(attachmentResumed.result.state, 'completed');
  const attachmentAfter = raw(attachmentId);
  assertOriginals(attachmentSource, attachmentAfter);
  const originals = attachmentAfter.records.filter(record => {const message = JSON.parse(record.payload); return message.role === 'user' && message.content === phase.expectedPrompt;});
  assert.equal(originals.length, 1);
  assert.deepEqual(JSON.parse(originals[0].payload).attachment, {path: '原文.png', revision: 7});
  assert.equal(fs.readFileSync(path.join(project, 'attachment-resumed-effect.txt'), 'utf8'), phase.toolContent);
  passed('Imported ordinary history without a native task row resumes with its full saved attachment metadata and one original user row');

  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'), executableHash, 'The tested executable must not change mid-run');
  await stop();
  const report = {schema: 'reverie.rust-compaction-smoke.v1', passed: true, verified_at: new Date().toISOString(),
    executable, executable_sha256: executableHash, root, checks, requests,
    scope: 'Actual native JSONL, SQLite source rows/checkpoints/projection, loopback model transport, cancellation/revision/corruption, same-ID native tool effect and restart. Fixtures are injected into an isolated database while the bridge is stopped; not real user migration or real model summary-quality acceptance.',
    unverified: ['Real provider token equivalence and multimodal billing.', 'Real model summary factual retention and injection resilience.',
      'Full manual context_management, history restore/fork/rewind/export and file rollback.', 'Project MemoryOS and cross-session correction/deletion invalidation.',
      'Multi-platform packages, long-session memory/performance, AiO endurance and desktop UI.']};
  fs.writeFileSync(path.join(root, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({passed: true, checks: checks.length, model_requests: requests.length, report: path.join(root, 'report.json')}));
} catch (error) {
  fs.writeFileSync(path.join(root, 'failure.json'), JSON.stringify({passed: false, message: error.stack || String(error), checks, requests}, null, 2) + '\n');
  throw error;
} finally {
  if (bridge?.child.exitCode === null) {bridge.child.stdin.end(); await bridge.closed;}
  for (const {response} of held.values()) response.destroy();
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
}
