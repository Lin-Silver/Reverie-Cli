import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {startBridge} from './rust-bridge-client.mjs';

const executable = path.resolve(process.argv[2] || `ReverieCli-rs/target/release/reverie${process.platform === 'win32' ? '.exe' : ''}`);
const directory = path.resolve(process.argv[3] || '.runtime/rust-3.0/command-smoke');
fs.mkdirSync(directory, {recursive: true});
const root = fs.mkdtempSync(path.join(directory, 'case-'));
const project = path.join(root, '工作区😀');
const outside = path.join(root, 'outside');
const appRoot = path.join(root, 'application');
for (const item of [project, outside, path.join(appRoot, '.reverie')]) fs.mkdirSync(item, {recursive: true});
const checks = [];
let bridge;
let sequence = 0;
let serverFailure;
const scripts = {
  'args.mjs': "console.log(JSON.stringify(process.argv.slice(2)));\n",
  'stdin.mjs': "let input=''; process.stdin.on('data',chunk=>input+=chunk); process.stdin.on('end',()=>console.log('input='+JSON.stringify(input)));\n",
  'utf8.mjs': "const bytes=Buffer.from('命令😀完成\\n'); process.stdout.write(bytes.subarray(0,2)); setTimeout(()=>{process.stdout.write(bytes.subarray(2)); process.stderr.write('诊断😀\\n');},30);\n",
  'large.mjs': "process.stdout.write('😀'.repeat(55000)); process.stderr.write('x'.repeat(55000)); process.exitCode=7;\n",
  'write.mjs': "import fs from 'node:fs'; fs.writeFileSync('written.txt','实际命令写入😀'); console.log('written');\n",
  'child.mjs': "setInterval(()=>{},1000);\n",
  'tree.mjs': "import fs from 'node:fs'; import {spawn} from 'node:child_process'; const child=spawn(process.execPath,['child.mjs'],{stdio:'inherit'}); fs.writeFileSync('pids.json',JSON.stringify([process.pid,child.pid])); console.log('TREE_READY'); if(process.argv[2]==='exit')setTimeout(()=>process.exit(0),30); else setInterval(()=>{},1000);\n",
  'unsafe.mjs': "import fs from 'node:fs'; fs.unlinkSync('keep.txt');\n",
};
for (const [name, source] of Object.entries(scripts)) fs.writeFileSync(path.join(project, name), source);
fs.writeFileSync(path.join(project, 'keep.txt'), 'protected');
fs.writeFileSync(path.join(outside, 'keep.txt'), 'outside protected');
fs.symlinkSync(outside, path.join(project, 'linked'), process.platform === 'win32' ? 'junction' : 'dir');
function json(response, value) {response.writeHead(200, {'content-type': 'application/json'}); response.end(JSON.stringify(value));}
const server = http.createServer(async (request, response) => {
  try {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    const last = body.messages.at(-1);
    if (last.role === 'tool') {
      json(response, {choices: [{message: {role: 'assistant', content: last.content}, finish_reason: 'stop'}]});
      return;
    }
    const prompt = JSON.parse(body.messages.findLast(message => message.role === 'user').content);
    assert(body.tools.some(tool => tool.function.name === 'command_exec'));
    json(response, {choices: [{message: {role: 'assistant', content: null, tool_calls: [{id: `command-${++sequence}`, type: 'function', function: {name: prompt.name || 'command_exec', arguments: JSON.stringify(prompt.args)}}]}, finish_reason: 'tool_calls'}]});
  } catch (error) {serverFailure = error; response.destroy(error);}
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
fs.writeFileSync(path.join(appRoot, '.reverie/config.json'), JSON.stringify({mode: 'reverie', models: [{model: 'command-fixture', profile_id: 'command-profile', provider: 'openai-chat', base_url: `http://127.0.0.1:${server.address().port}/v1`, api_key: 'COMMAND_FIXTURE'}], active_model_source: 'standard', active_model_index: 0, stream_responses: false, auto_index: false, security: {permission_mode: 'full_access', permission_level: 'full_control'}}));
const quote = value => `"${value.replaceAll('"', '\\"')}"`;
const node = quote(process.execPath);
const eventsFor = run => bridge.events.filter(reply => reply.type === 'prompt.event' && reply.event.run_id === run).map(reply => reply.event);
async function wait(condition, label) {
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {if (condition()) return; await delay(10);}
  throw new Error(`Timed out: ${label}`);
}
function running(session, args, name = 'command_exec', ownership = {}) {
  const runId = `command-run-${++sequence}`;
  const pending = bridge.request('runPrompt', {projectRoot: project, sessionId: session, ...ownership, runId, prompt: JSON.stringify({name, args}), noIndex: true}, 20000);
  return {runId, pending};
}
async function call(session, args, name) {
  const {runId, pending} = running(session, args, name);
  const reply = await pending;
  assert.equal(reply.type, 'prompt.result', JSON.stringify(reply));
  assert.equal(reply.result.success, true, JSON.stringify(reply.result));
  return {result: JSON.parse(reply.result.output_text), runId, reply};
}
async function session(name, security, projectRoot = project) {
  const created = await bridge.request('createSession', {projectRoot, name});
  const id = created.session.id;
  if (security) {
    const configuration = await bridge.request('getConversationConfig', {projectRoot, sessionId: id});
    await bridge.request('getConversationConfig', {projectRoot, sessionId: id, revision: configuration.revision, configuration: {...configuration.configuration, settings: {...configuration.configuration.settings, security}}});
  }
  return id;
}
async function gone(pids) {
  await wait(() => pids.every(pid => {try {process.kill(pid, 0); return false;} catch (error) {return error.code === 'ESRCH';}}), `process tree exits ${pids}`);
}
try {
  bridge = startBridge(executable, project, appRoot);
  await bridge.ready;
  const state = (await bridge.request('initialize', {projectRoot: project})).state;
  const ordinary = await session('native commands');
  let {result} = await call(ordinary, {command: `${node} args.mjs "literal && text" "&&" "中文😀"`, timeout: 5});
  assert.equal(result.success, true);
  assert.equal(result.data.delivery, 'executed');
  assert.deepEqual(JSON.parse(result.data.stdout), ['literal && text', '&&', '中文😀']);
  checks.push('Actual argv and quoted operator text without shell execution');
  ({result} = await call(ordinary, {command: `${node} stdin.mjs`, timeout: 5}));
  assert.equal(result.data.stdout.trim(), 'input=""');
  checks.push('Closed command stdin does not consume SDK input or wait for a user');
  const utf8 = await call(ordinary, {command: `${node} utf8.mjs`, timeout: 5});
  assert.equal(utf8.result.data.stdout, '命令😀完成\n');
  assert.equal(utf8.result.data.stderr, '诊断😀\n');
  const progress = eventsFor(utf8.runId).filter(event => event.type === 'ui.event' && event.event.type === 'tool_progress');
  assert.equal(progress.filter(event => event.event.stream === 'stdout').map(event => event.event.text).join(''), '命令😀完成\n');
  assert(progress.every(event => event.session_id === ordinary && event.event.tool_call_id));
  assert.equal(eventsFor(utf8.runId).find(event => event.event?.type === 'tool_result')?.event.event, 'tool_result');
  checks.push('Incremental split UTF-8 stdout and stderr with run and tool ownership');
  const largeOutput = await session('Both command output pipes');
  // This fixture echoes both complete pipes, including duplicate output/data fields.
  // Give that one conversation room for the tool response and the fixture echo.
  assert.equal((await bridge.request('setSetting',{sessionId:largeOutput,key:'max_context_tokens',value:1048576})).type,'setting.updated');
  ({result} = await call(largeOutput, {command: `${node} large.mjs`, timeout: 10}));
  assert.equal(result.status, 'partial');
  assert.equal(result.success, false);
  assert.equal(result.data.exit_code, 7);
  assert.match(result.data.stdout, /truncated 5000 characters/);
  assert.equal(result.data.stdout_characters, 55000);
  assert.equal(result.data.stderr_characters, 55000);
  assert([...result.data.stdout].slice(0, 50000).every(character => character === '😀'));
  checks.push('Both pipes drain past bounded Unicode output and preserve a nonzero exit');
  for (const args of [{command: `${node} write.mjs && ${node} write.mjs`}, {command: 'rm keep.txt'}, {command: 'git --no-pager clean -fd'}, {command: `${node} -e "process.exit()"`}, {command: `${node} unsafe.mjs`}, {command: `${node} args.mjs ../outside`}, {command: `${node} args.mjs linked/keep.txt`}, {command: `${node} write.mjs`, cwd: outside}, {command: `${node} write.mjs`, env: {EXAMPLE: 'no'}}, {command: `${node} write.mjs`, timeout: 0}]) {
    ({result} = await call(ordinary, args));
    assert.equal(result.success, false, JSON.stringify(args));
    assert.equal(result.data.delivery, 'not_started', JSON.stringify(result));
  }
  assert.equal(fs.existsSync(path.join(project, 'written.txt')), false);
  assert.equal(fs.readFileSync(path.join(project, 'keep.txt'), 'utf8'), 'protected');
  assert.equal(fs.readFileSync(path.join(outside, 'keep.txt'), 'utf8'), 'outside protected');
  checks.push('Blocked operators, destructive commands and scripts, paths, junctions, env and timeout do not execute');
  ({result} = await call(ordinary, {command: 'reverie_verification_missing_executable', timeout: 5}));
  assert.equal(result.data.delivery, 'not_started');
  checks.push('Failed executable launch records no delivered command');
  const readOnly = await session('read-only commands', {permission_level: 'read_only', permission_mode: 'default'});
  ({result} = await call(readOnly, {command: `${node} write.mjs`, timeout: 5}));
  assert.equal(result.success, false);
  assert.equal(result.data.delivery, 'not_started');
  assert.equal(fs.existsSync(path.join(project, 'written.txt')), false);
  checks.push('Read-only permission denies commands before launch and records undelivered state');
  const strict = await session('strict commands', {permission_level: 'workspace_write', permission_mode: 'strict'});
  let active = running(strict, {command: `${node} write.mjs`, timeout: 5});
  await wait(() => eventsFor(active.runId).some(event => event.type === 'approval.request'), 'strict approval');
  assert.equal(fs.existsSync(path.join(project, 'written.txt')), false);
  const approval = eventsFor(active.runId).find(event => event.type === 'approval.request');
  await bridge.request('resolveApproval', {runId: active.runId, approvalId: approval.approval_id, decision: 'once'});
  const approved = await active.pending;
  assert.equal(JSON.parse(approved.result.output_text).success, true);
  assert.equal(fs.readFileSync(path.join(project, 'written.txt'), 'utf8'), '实际命令写入😀');
  checks.push('Strict approval precedes actual workspace writes');
  active = running(ordinary, {command: `${node} tree.mjs`, timeout: 15}, 'run_command');
  await wait(() => eventsFor(active.runId).some(event => event.event?.text?.includes('TREE_READY')), 'process tree started');
  const pids = JSON.parse(fs.readFileSync(path.join(project, 'pids.json'), 'utf8'));
  const other = await session('concurrent command');
  assert.equal((await call(other, {command: `${node} args.mjs parallel`, timeout: 5})).result.success, true);
  await bridge.request('stopPrompt', {runId: active.runId});
  const stopped = await active.pending;
  assert.equal(stopped.result.state, 'cancelled');
  const cancelled = eventsFor(active.runId).find(event => event.event?.type === 'tool_result')?.event;
  assert.equal(cancelled.status, 'cancelled');
  assert.equal(cancelled.data.delivery, 'executed');
  assert.match(cancelled.data.stdout, /TREE_READY/);
  await gone(pids);
  checks.push('Alias, concurrent session, cancellation, partial output and actual descendant cleanup');
  ({result} = await call(ordinary, {command: `${node} tree.mjs`, timeout: 1}));
  assert.equal(result.status, 'timeout');
  assert.equal(result.data.delivery, 'executed');
  assert.match(result.data.stdout, /TREE_READY/);
  await gone(JSON.parse(fs.readFileSync(path.join(project, 'pids.json'), 'utf8')));
  checks.push('Actual timeout reaps the parent and terminates descendants');
  ({result} = await call(ordinary, {command: `${node} tree.mjs exit`, timeout: 5}));
  assert.equal(result.success, true, JSON.stringify(result));
  await gone(JSON.parse(fs.readFileSync(path.join(project, 'pids.json'), 'utf8')));
  checks.push('Normally completed noninteractive commands leave no detached children');
  if (process.platform === 'win32') {
    ({result} = await call(ordinary, {command: 'Get-ChildItem . | Select-Object -First 2', timeout: 10}));
    assert.equal(result.success, true, JSON.stringify(result));
    assert.equal(result.data.delivery, 'executed');
    checks.push('Actual audited PowerShell cmdlet pipeline');
  }
  const normal = await session('Normal scoped grants',{permission_mode:'normal',permission_level:'workspace_write'});
  const normalRead=await call(normal,{operation:'read',path:'keep.txt'},'file_ops');
  assert(normalRead.result.success && !eventsFor(normalRead.runId).some(e=>e.type==='approval.request'));
  async function grant(task,decision) {
    await wait(()=>eventsFor(task.runId).some(e=>e.type==='approval.request'),decision+' approval');
    const event=eventsFor(task.runId).find(e=>e.type==='approval.request');
    assert.deepEqual(event.scopes,['once','session','project','global']);
    assert.equal((await bridge.request('resolveApproval',{approvalId:event.approval_id,runId:task.runId,decision})).type,'approval.resolved');
    return JSON.parse((await task.pending).result.output_text);
  }
  const projectArgs={command:node+' args.mjs project',timeout:5};
  assert((await grant(running(normal,projectArgs),'project')).success);
  const sibling=await session('Sibling strict grants',{permission_mode:'strict',permission_level:'workspace_write'});
  assert((await call(sibling,projectArgs)).result.success);
  fs.copyFileSync(path.join(project,'args.mjs'),path.join(outside,'args.mjs'));
  assert(!(await grant(running(sibling,projectArgs,'command_exec',{executionRoot:outside}),'deny')).success);
  const another=await session('Different project',{permission_mode:'strict',permission_level:'workspace_write'},outside);
  assert(!(await grant(running(another,projectArgs,'command_exec',{projectRoot:outside}),'deny')).success);
  const globalArgs={command:node+' args.mjs global',timeout:5};
  assert((await grant(running(sibling,globalArgs),'global')).success);
  await bridge.request('shutdown');
  assert.equal((await bridge.closed).code,0);
  bridge=startBridge(executable,project,appRoot); await bridge.ready;
  const restarted=await running(another,globalArgs,'command_exec',{projectRoot:outside}).pending;
  assert(JSON.parse(restarted.result.output_text).success);
  assert((await call(normal,projectArgs)).result.success);
  assert(!(await grant(running(normal,{...projectArgs,timeout:6}),'deny')).success);
  checks.push('Normal allows native reads, project command grants match sibling conversations, a changed execution root is isolated, global authorization survives restart, and a changed option prompts again');
  await bridge.request('shutdown');
  assert.equal((await bridge.closed).code, 0);
  const audit = fs.readFileSync(path.join(state.workspace.project_data_dir, 'security/command_audit.jsonl'), 'utf8').trim().split('\n').map(line => JSON.parse(line));
  assert(audit.some(event => event.event === 'command_blocked' && event.delivery === 'not_started'));
  assert(audit.some(event => event.event === 'command_result' && event.status === 'timeout' && event.delivery === 'executed'));
  assert(audit.some(event => event.event === 'command_result' && event.status === 'cancelled'));
  assert(audit.some(event => event.event === 'command_start_failed' && event.delivery === 'not_started'));
  checks.push('Parseable project audit records actual failure, timeout and cancellation');
  if (serverFailure) throw serverFailure;
  const report = {schema: 'reverie.rust-command-smoke.v1', passed: true, executable, executable_sha256: crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'), verified_at: new Date().toISOString(), root, checks, scope: 'Actual Rust commands, files, process trees and SDK approvals with a loopback model fixture; not live model, complete platform or OS sandbox verification.'};
  fs.writeFileSync(path.join(root, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({passed: true, checks: checks.length, report: path.join(root, 'report.json')}));
} catch (error) {
  fs.writeFileSync(path.join(root, 'failure.json'), JSON.stringify({passed: false, checks, error: String(error), stack: error.stack, events: bridge?.events}, null, 2) + '\n');
  throw error;
} finally {
  if (bridge?.child.exitCode === null) {bridge.child.stdin.end(); await bridge.closed;}
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
}
