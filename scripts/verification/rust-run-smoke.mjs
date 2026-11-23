import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import http from 'node:http';
import {setTimeout as delay} from 'node:timers/promises';
import {DatabaseSync} from 'node:sqlite';
import {startBridge} from './rust-bridge-client.mjs';

const executable = path.resolve(process.argv[2] || `ReverieCli-rs/target/release/reverie${process.platform === 'win32' ? '.exe' : ''}`);
const directory = path.resolve(process.argv[3] || '.runtime/rust-3.0/run-smoke');
fs.mkdirSync(directory, {recursive: true});
const root = fs.mkdtempSync(path.join(directory, 'case-'));
const appRoot = path.join(root, 'application');
const project = path.join(root, '工作区😀');
const otherProject = path.join(root, 'second-workspace');
for (const folder of [project, otherProject, path.join(appRoot, '.reverie')]) fs.mkdirSync(folder, {recursive: true});
const source = 'exact first line\r\n中文😀\nfinal line';
fs.writeFileSync(path.join(project, 'input.txt'), source);
fs.writeFileSync(path.join(project, 'evidence.txt'), 'unique_first_project_evidence');
fs.writeFileSync(path.join(otherProject, 'evidence.txt'), 'unique_second_project_evidence');
const held = new Map();
const requests = [];
const checks = [];
let bridge;
let toolSequence = 0;
let serverFailure;
process.env.NO_PROXY = [process.env.NO_PROXY, '127.0.0.1', 'localhost'].filter(Boolean).join(',');

function event(response, value) {
  response.write(`data: ${JSON.stringify(value)}\r\n\r\n`);
}
function finish(response, body, content) {
  if (!body.stream) {
    response.writeHead(200, {'content-type': 'application/json'});
    response.end(JSON.stringify({choices: [{message: {role: 'assistant', content}, finish_reason: 'stop'}]}));
    return;
  }
  for (const text of [content.slice(0, 2), content.slice(2)]) event(response, {choices: [{delta: {content: text}}]});
  event(response, {choices: [{delta: {}, finish_reason: 'stop'}], usage: {prompt_tokens: 17, completion_tokens: 9, total_tokens: 26}});
  response.end('data: [DONE]\n\n');
}
const server = http.createServer(async (request, response) => {
  try {
    assert.equal(request.url, '/v1/chat/completions');
    let bytes = '';
    for await (const chunk of request) bytes += chunk;
    const body = JSON.parse(bytes);
    assert.equal(body.model, 'fixture-model');
    assert.equal(request.headers.authorization, 'Bearer FIXTURE_SECRET');
    requests.push(body);
    const prompt = body.messages.findLast(message => message.role === 'user').content;
    if (body.stream) response.writeHead(200, {'content-type': 'text/event-stream'});
    const last = body.messages.at(-1);
    if (last.role === 'tool') {
      const result = JSON.parse(last.content);
      finish(response, body, `${result.success ? '完成' : '拒绝'}\n${result.success ? result.output : result.error}`);
      return;
    }
    if (prompt.startsWith('HOLD:') || prompt === 'PARTIAL' || prompt === 'TRUNCATED') {
      event(response, {choices: [{delta: {content: '保留部分😀'}}]});
      if (prompt === 'TRUNCATED') {response.end(); return;}
      held.set(prompt, {response, body});
      response.once('close', () => held.delete(prompt));
      return;
    }
    let name;
    let args;
    if (prompt === 'READ') {name = 'file_ops'; args = {operation: 'read', path: 'input.txt'};}
    else if (prompt.startsWith('WRITE:')) {name = 'create_file'; args = {path: prompt.slice(6), content: source};}
    else if (prompt === 'QUESTION') {name = 'userInput'; args = {question: '选择实现方式？', reason: 'fixture-requirements', options: ['A', 'B', 'C']};}
    else if (prompt === 'BAD_JSON') {name = 'create_file'; args = '{broken';}
    else {finish(response, body, `实际协议回复😀\n${prompt}`); return;}
    const serialized = typeof args === 'string' ? args : JSON.stringify(args);
    const callId = `fixture-call-${++toolSequence}`;
    if (!body.stream) {
      response.writeHead(200, {'content-type': 'application/json'});
      response.end(JSON.stringify({choices: [{message: {role: 'assistant', content: null, tool_calls: [{id: callId, type: 'function', function: {name, arguments: serialized}}]}, finish_reason: 'tool_calls'}]}));
    } else {
      response.write(': fixture comment\r\n\r\n');
      event(response, {choices: [{delta: {tool_calls: [{index: 0, id: callId, type: 'function', function: {name, arguments: serialized.slice(0, 5)}}]}}]});
      event(response, {choices: [{delta: {tool_calls: [{index: 0, function: {arguments: serialized.slice(5)}}]}, finish_reason: 'tool_calls'}]});
      response.end('data: [DONE]\n\n');
    }
  } catch (error) {
    serverFailure = error;
    response.destroy(error);
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const model = {model: 'fixture-model', profile_id: 'fixture-profile', provider: 'openai-chat',
  base_url: `http://127.0.0.1:${server.address().port}/v1`, api_key: 'FIXTURE_SECRET'};
fs.writeFileSync(path.join(appRoot, '.reverie/config.json'), JSON.stringify({mode: 'reverie', models: [model], active_model_source: 'standard', active_model_index: 0,
  auto_index: true, stream_responses: true, security: {permission_level: 'full_control', permission_mode: 'default'}}));

async function request(action, payload = {}, type) {
  const reply = await bridge.request(action, payload, 15000);
  if (type) assert.equal(reply.type, type, JSON.stringify(reply));
  return reply;
}
async function waitEvent(runId, type) {
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    const event = bridge.events.find(reply => reply.type === 'prompt.event' && reply.event.run_id === runId && reply.event.type === type)?.event;
    if (event) return event;
    await delay(10);
  }
  throw new Error(`Missing ${type} for ${runId}`);
}
async function create(name, configuration) {
  const session = (await request('createSession', {projectRoot: project, name}, 'session.created')).session;
  if (configuration) {
    const saved = await request('getConversationConfig', {sessionId: session.id}, 'conversation.config');
    await request('getConversationConfig', {sessionId: session.id, revision: saved.revision,
      configuration: {...saved.configuration, settings: {...saved.configuration.settings, ...configuration}}}, 'conversation.config');
  }
  return session.id;
}
function run(sessionId, prompt, runId, extra = {}) {
  return request('runPrompt', {projectRoot: project, sessionId, prompt, runId, ...extra}, 'prompt.result');
}
function passed(name) {checks.push(name);}
try {
  bridge = startBridge(executable, project, appRoot);
  await bridge.ready;
  const state = (await request('initialize', {projectRoot: project}, 'state')).state;
  const session = await create('stream and actual files');
  let result = await run(session, 'READ', 'read-1');
  assert.equal(result.result.output_text, `完成\n${source}`);
  assert(result.events.some(reply => reply.event.type === 'assistant.delta'));
  assert(result.events.every(reply => reply.id === result.id && reply.event.session_id === session));
  assert(!JSON.stringify(result).includes('FIXTURE_SECRET'));
  passed('SSE tool fragments, exact native read, final result and bound events');
  result = await run(session, 'WRITE:created.txt', 'write-1');
  assert.equal(result.result.success, true);
  assert.equal(fs.readFileSync(path.join(project, 'created.txt'), 'utf8'), source);
  passed('Actual atomic workspace file creation');
  const readOnly = await create('read-only', {security: {permission_level: 'read_only', permission_mode: 'default'}});
  result = await run(readOnly, 'WRITE:denied.txt', 'deny-1');
  assert.match(result.result.output_text, /^拒绝/);
  assert.equal(fs.existsSync(path.join(project, 'denied.txt')), false);
  passed('Permission denial has no write effect');
  const strict = await create('strict', {security: {permission_level: 'full_control', permission_mode: 'strict'}});
  let running = run(strict, 'WRITE:message-denied.txt', 'strict-message');
  const approval = await waitEvent('strict-message', 'approval.request');
  await request('resolveApproval', {approvalId: approval.approval_id, decision: 'invalid'}, 'error');
  await request('resolveApproval', {approvalId: approval.approval_id, sessionId: session, decision: 'once'}, 'error');
  await request('resolveApproval', {approvalId: approval.approval_id, sessionId: strict, decision: 'message', message: '请保留原文件😀'}, 'approval.resolved');
  result = await running;
  assert.match(result.result.output_text, /请保留原文件😀/);
  assert.equal(fs.existsSync(path.join(project, 'message-denied.txt')), false);
  passed('Invalid and wrong-owner approvals stay pending; custom denial reaches the model');
  running = run(strict, 'WRITE:approved-1.txt', 'strict-session');
  const grant = await waitEvent('strict-session', 'approval.request');
  await request('resolveApproval', {approvalId: grant.approval_id, decision: 'session'}, 'approval.resolved');
  assert.equal((await running).result.success, true);
  result = await run(strict, 'WRITE:approved-2.txt', 'strict-session-next');
  assert.equal(result.events.some(reply => reply.event.type === 'approval.request'), false);
  assert.equal(fs.readFileSync(path.join(project, 'approved-2.txt'), 'utf8'), source);
  passed('Explicit session grant survives the next run in the same conversation');
  running = run(session, 'QUESTION', 'question-1');
  const question = await waitEvent('question-1', 'user.question');
  assert.deepEqual(question.options, ['A', 'B', 'C']);
  await request('resolveUserInput', {questionId: question.question_id, answer: ' '}, 'error');
  await request('resolveUserInput', {questionId: question.question_id, sessionId: session, answer: '自定义第四项\n保持换行😀'}, 'user.resolved');
  assert.match((await running).result.output_text, /自定义第四项\n保持换行😀/);
  passed('Three choices and explicit custom answer; empty submission cannot consume a question');
  result = await run(session, 'BAD_JSON', 'bad-json');
  assert.match(result.result.output_text, /valid JSON/);
  passed('Malformed tool arguments produce an actual tool failure');
  running = run(session, 'PARTIAL', 'partial-1', {noIndex: true});
  await waitEvent('partial-1', 'assistant.delta');
  await request('stopPrompt', {runId: 'partial-1', projectRoot: otherProject}, 'error');
  await request('runPrompt', {projectRoot: project, sessionId: strict, prompt: 'duplicate', runId: 'partial-1', noIndex: true}, 'error');
  await request('stopPrompt', {runId: 'partial-1'}, 'run.control');
  assert.equal((await running).result.state, 'cancelled');
  const interrupted = (await request('getSession', {projectRoot: project, sessionId: session, select: false}, 'session')).session.interrupted_streams;
  assert.equal(interrupted.find(item => item.run_id === 'partial-1' && item.kind === 'assistant').content, '保留部分😀');
  passed('Network cancellation, duplicate run rejection and persisted partial output');
  result = await run(session, 'TRUNCATED', 'truncated-1', {noIndex: true});
  assert.equal(result.result.success, false);
  assert.match(result.result.error, /completion marker/);
  passed('Truncated stream cannot be saved as completed');
  running = run(session, 'HOLD:first-project', 'held-project', {noIndex: false});
  await waitEvent('held-project', 'assistant.delta');
  await request('initialize', {projectRoot: otherProject}, 'state');
  const other = (await request('createSession', {projectRoot: otherProject, name: 'other project'}, 'session.created')).session;
  const second = await request('runPrompt', {projectRoot: otherProject, sessionId: other.id, prompt: 'SECOND', runId: 'second-project'}, 'prompt.result');
  assert.equal(second.result.success, true);
  const hold = held.get('HOLD:first-project');
  event(hold.response, {choices: [{delta: {content: '\n原项目完成'}, finish_reason: 'stop'}]});
  hold.response.end('data: [DONE]\n\n');
  assert.equal((await running).result.success, true);
  const firstPage = (await request('getSession', {projectRoot: project, sessionId: session, select: false}, 'session')).session;
  assert.equal(firstPage.messages.at(-1).content, '保留部分😀\n原项目完成');
  const secondPage = (await request('getSession', {projectRoot: otherProject, sessionId: other.id, select: false}, 'session')).session;
  assert.equal(secondPage.messages.length, 2);
  assert.equal(secondPage.messages.at(-1).content, '实际协议回复😀\nSECOND');
  passed('Concurrent projects keep their own configuration, context and transcript stores');
  const nonstream = await create('JSON response', {stream_responses: false});
  assert.equal((await run(nonstream, 'READ', 'json-1', {noIndex: true})).result.output_text, `完成\n${source}`);
  passed('Nonstream JSON response and tool continuation');
  running = run(session, 'immediate cancellation', 'queued-stop', {noIndex: true});
  await request('stopPrompt', {runId: 'queued-stop'}, 'run.control');
  assert.equal((await running).result.state, 'cancelled');
  passed('Back-to-back run and stop are registered in input order');
  await request('shutdown', {}, 'shutdown');
  assert.deepEqual(await bridge.closed, {code: 0, signal: null, stderr: ''});
  const db = new DatabaseSync(path.join(state.workspace.project_data_dir, 'conversations.sqlite3'), {readOnly: true});
  assert.equal(db.prepare("SELECT count(*) AS count FROM task_runs WHERE state='running'").get().count, 0);
  assert.equal(db.prepare("SELECT state FROM task_runs WHERE id='partial-1'").get().state, 'cancelled');
  assert.equal(db.prepare("SELECT state FROM task_runs WHERE id='truncated-1'").get().state, 'failed');
  db.close();
  passed('Explicit shutdown finalizes active state and exits cleanly');
  bridge = startBridge(executable, project, appRoot);
  await bridge.ready;
  running = run(session, 'PARTIAL', 'eof-1', {noIndex: true});
  await waitEvent('eof-1', 'assistant.delta');
  bridge.child.stdin.end();
  assert.equal((await running).result.state, 'cancelled');
  assert.equal((await bridge.closed).code, 0);
  passed('EOF cancels the actual pending HTTP request and exits cleanly');
  if (serverFailure) throw serverFailure;
  const report = {schema: 'reverie.rust-run-smoke.v1', passed: true, verified_at: new Date().toISOString(), executable,
    executable_sha256: crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'), root, checks, model_requests: requests.length,
    scope: 'Real native Rust executable and files with loopback model protocol fixture; no external model quality, full provider, full product, performance or GUI claim.'};
  fs.writeFileSync(path.join(root, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({passed: true, checks: checks.length, report: path.join(root, 'report.json')}));
} catch (error) {
  fs.writeFileSync(path.join(root, 'failure.json'), JSON.stringify({passed: false, checks, error: String(error), stack: error.stack, events: bridge?.events}, null, 2) + '\n');
  throw error;
} finally {
  if (bridge && bridge.child.exitCode === null) {bridge.child.stdin.end(); await bridge.closed;}
  for (const {response} of held.values()) response.destroy();
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
}
