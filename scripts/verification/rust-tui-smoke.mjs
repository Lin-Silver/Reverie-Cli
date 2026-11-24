import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import http from 'node:http';
import {createRequire} from 'node:module';
import {spawn} from 'node:child_process';
import {stripVTControlCharacters} from 'node:util';
import {setTimeout as delay} from 'node:timers/promises';
import {DatabaseSync} from 'node:sqlite';
import {startBridge} from './rust-bridge-client.mjs';

const require = createRequire(import.meta.url);
const pty = require(path.resolve('ReverieCli-ui/node_modules/node-pty'));
const {Terminal} = require(path.resolve('ReverieCli-ui/node_modules/@xterm/headless'));
const display = new Terminal({allowProposedApi: true, cols: 84, rows: 26, scrollback: 1000});
function screenText() {
  const buffer = display.buffer.active;
  return Array.from({length: buffer.length}, (_, index) => buffer.getLine(index).translateToString(true)).join('\n');
}
function viewportText() {
  const buffer=display.buffer.active;
  return Array.from({length:display.rows},(_,index)=>buffer.getLine(buffer.viewportY+index)?.translateToString(true)||'').join('\n');
}
const executable = path.resolve(process.argv[2] || `ReverieCli-rs/target/release/reverie${process.platform === 'win32' ? '.exe' : ''}`);
const directory = path.resolve(process.argv[3] || '.runtime/rust-3.0/tui-smoke');
fs.mkdirSync(directory, {recursive: true});
const root = fs.mkdtempSync(path.join(directory, 'case-'));
const project = path.join(root, '工作区😀');
const appRoot = path.join(root, 'application');
fs.mkdirSync(project, {recursive: true});
fs.mkdirSync(path.join(appRoot, '.reverie'), {recursive: true});
fs.writeFileSync(path.join(project, 'terminal-command.mjs'), "console.log('COMMAND_TERMINAL_PROGRESS😀'); setTimeout(()=>console.log('COMMAND_TERMINAL_FINISHED'),1000);\n");
fs.writeFileSync(path.join(project, 'terminal-context.md'), '# terminal_context_marker\n共享 Rust 内核返回的终端证据。\n');
fs.mkdirSync(path.join(project, '.agents/skills/tui-native-skill'), {recursive:true});
fs.writeFileSync(path.join(project, '.agents/skills/tui-native-skill/SKILL.md'), '---\nname: tui-native-skill\ndescription: Native terminal fixture.\n---\nTUI_SKILL_BODY中文😀\n');
fs.writeFileSync(path.join(project, '.agents/skills/tui-native-skill/reference.md'), 'TUI_REFERENCE中文😀\n');
const prompts = [];
const requests = [];
const checks = [];
let terminal;
let cursorRepliesEnabled = true;
const displayReplies = display.onData(bytes => {
  if (!cursorRepliesEnabled && /^\x1b\[\d+;\d+R$/.test(bytes)) return;
  terminal?.write(bytes);
});
let output = '';
let terminalExit;
let held;
let serverFailure;
function frame(response, data) {response.write(`data: ${JSON.stringify(data)}\n\n`);}
function finish(response, text) {
  frame(response, {choices: [{delta: {content: text.slice(0, 5)}}]});
  frame(response, {choices: [{delta: {content: text.slice(5)}, finish_reason: 'stop'}]});
  response.end('data: [DONE]\n\n');
}
const server = http.createServer(async (request, response) => {
  try {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    requests.push(body);
    response.writeHead(200, {'content-type': 'text/event-stream'});
    const last = body.messages.at(-1);
    if (last.role === 'tool') {
      const result = JSON.parse(last.content);
      finish(response, `UI_REPLY:\n${result.success ? result.output : result.error}`);
      return;
    }
    const prompt = body.messages.findLast(message => message.role === 'user').content;
    prompts.push(prompt);
    if (prompt === 'HOLD') {
      frame(response, {choices: [{delta: {content: 'PARTIAL_UI_REPLY😀'}}]});
      held = response;
      response.once('close', () => {held = undefined;});
    } else if (prompt === 'QUESTION' || prompt === 'HEADLESS_QUESTION') {
      frame(response, {choices: [{delta: {tool_calls: [{index: 0, id: `question-${requests.length}`, function: {name: 'userInput', arguments: JSON.stringify({question: 'Choose an implementation', reason: 'fixture-question', options: ['Option A', 'Option B', 'Option C']})}}]}, finish_reason: 'tool_calls'}]});
      response.end('data: [DONE]\n\n');
    } else if (prompt === 'COMMAND') {
      frame(response, {choices: [{delta: {tool_calls: [{index: 0, id: `command-${requests.length}`, function: {name: 'command_exec', arguments: JSON.stringify({command: `"${process.execPath}" terminal-command.mjs`, timeout: 5})}}]}, finish_reason: 'tool_calls'}]});
      response.end('data: [DONE]\n\n');
    } else if (prompt === 'WRITE') {
      frame(response, {choices: [{delta: {tool_calls: [{index: 0, id: `write-${requests.length}`, function: {name: 'create_file', arguments: JSON.stringify({path: 'must-not-exist.txt', content: 'denied fixture'})}}]}, finish_reason: 'tool_calls'}]});
      response.end('data: [DONE]\n\n');
    } else finish(response, `UI_REPLY:\n${prompt}`);
  } catch (error) {serverFailure = error; response.destroy(error);}
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
fs.writeFileSync(path.join(appRoot, '.reverie/config.json'), JSON.stringify({mode: 'reverie', models: [{model: 'tui-fixture', profile_id: 'tui-profile', provider: 'openai-chat',
  base_url: `http://127.0.0.1:${server.address().port}/v1`, api_key: 'TUI_FIXTURE_KEY'}], active_model_source: 'standard', active_model_index: 0, stream_responses: true, auto_index: false,
  security: {permission_level: 'full_control', permission_mode: 'default'}}));
const environment = {...process.env, REVERIE_APP_ROOT: appRoot, NO_PROXY: [process.env.NO_PROXY, '127.0.0.1', 'localhost'].filter(Boolean).join(',')};
async function wait(condition, label) {
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {if (condition()) return; await delay(20);}
  throw new Error(`Timed out: ${label}; terminal exit=${JSON.stringify(terminalExit)}`);
}
function headless(args) {
  return new Promise((resolve, reject) => {
    const child = spawn(executable, args, {cwd: project, env: environment, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe']});
    let stdout = ''; let stderr = '';
    child.stdout.on('data', bytes => {stdout += bytes.toString();});
    child.stderr.on('data', bytes => {stderr += bytes.toString();});
    child.on('error', reject);
    child.on('exit', code => resolve({code, stdout, stderr}));
    child.stdin.end();
  });
}
let database;
try {
  const bridge = startBridge(executable, project, appRoot);
  await bridge.ready;
  const state = (await bridge.request('initialize', {projectRoot: project})).state;
  await bridge.request('shutdown');
  assert.equal((await bridge.closed).code, 0);
  database = new DatabaseSync(path.join(state.workspace.project_data_dir, 'conversations.sqlite3'), {readOnly: true});
  const messageRows = () => database.prepare('SELECT payload FROM messages ORDER BY rowid').all().map(row => JSON.parse(row.payload));
  const completedCount = () => database.prepare("SELECT count(*) AS count FROM task_runs WHERE state='completed'").get().count;
  terminal = pty.spawn(executable, ['--project', project, '--no-index'], {name: 'xterm-256color', cols: 84, rows: 26, cwd: project, env: environment});
  terminal.onData(bytes => {output += bytes; display.write(bytes);});
  terminal.onExit(value => {terminalExit = value;});
  await wait(() => stripVTControlCharacters(output).includes('Use /help for commands') && screenText().includes('Reverie CLI'), 'native terminal startup');
  assert(!output.includes('\x1b[?1049h'));
  // A busy bracketed-paste parser can withhold CPR. The renderer must keep its
  // known cursor instead of synchronously querying the input channel mid-run.
  cursorRepliesEnabled = false;
  checks.push('Actual scrolling viewport without an alternate screen');
  terminal.write('/skill tui-native-skill\r');
  await wait(() => screenText().includes('Skill pinned: tui-native-skill'), 'conversation skill pin');
  terminal.write('/skills inspect tui-native-skill\r');
  await wait(() => screenText().includes('TUI_SKILL_BODY中文😀'), 'complete native skill instructions');
  terminal.write('/skills resource tui-native-skill reference.md\r');
  await wait(() => screenText().includes('TUI_REFERENCE中文😀'), 'native packaged skill resource');
  checks.push('Native /skills pin, complete instructions and packaged resources through the shared kernel');
  const pasted = 'PASTED_FIRST😀\nPASTED_SECOND';
  terminal.write(`\x1b[200~${pasted}\x1b[201~`);
  await delay(200);
  assert.equal(prompts.length, 0, `Paste submitted before Enter: ${JSON.stringify(prompts)}`);
  terminal.write('\r');
  await wait(() => completedCount() === 1, 'pasted prompt completion');
  assert.equal(prompts[0], pasted);
  assert.equal(messageRows().filter(message => message.role === 'Reverie').at(-1).content, `UI_REPLY:\n${pasted}`);
  checks.push('Bracketed paste preserves CJK/emoji and multiple lines until explicit Enter');
  const splitHostMarkers = process.env.REVERIE_TUI_SPLIT_HOST_MARKERS === '1';
  terminal.write(splitHostMarkers ? '\x1b[20' : '\x1b[200~');
  await delay(20);
  terminal.write(`${splitHostMarkers ? '0~' : ''}PASTED_中文😀\r\n`);
  terminal.write(`SECOND_CRLF${splitHostMarkers ? '\x1b[201' : ''}`);
  await delay(20);
  terminal.write(splitHostMarkers ? '~' : '\x1b[201~');
  await delay(200);
  assert.equal(prompts.length, 1, 'Fragmented CRLF paste submitted before Enter');
  terminal.write('\r');
  await wait(() => completedCount() === 2, 'fragmented CRLF prompt completion');
  assert.equal(prompts[1], 'PASTED_中文😀\nSECOND_CRLF');
  checks.push(`${splitHostMarkers ? 'Fragmented host paste markers' : 'Fragmented paste body'} and CRLF preserve text without an automatic action`);
  terminal.write('QUESTION\r');
  await wait(() => screenText().includes('Write a custom answer'), 'three-option question panel');
  const requestsBeforeReply = requests.length;
  terminal.write('\x1b[200~CUSTOM_REPLY😀\nSECOND_REPLY\x1b[201~');
  await delay(200);
  assert.equal(requests.length, requestsBeforeReply, 'Pasted question answer was submitted implicitly');
  terminal.write('\r');
  await wait(() => completedCount() === 3, 'custom question completion');
  assert.match(messageRows().filter(message => message.role === 'Reverie').at(-1).content, /CUSTOM_REPLY😀/);
  checks.push('Three options and a fourth custom answer through the shared kernel');
  terminal.write('COMMAND\r');
  await wait(() => screenText().includes('COMMAND_TERMINAL_PROGRESS😀'), 'actual command progress in terminal scrollback');
  assert.equal(completedCount(), 3, 'Command output was only shown after completion');
  await wait(() => completedCount() === 4, 'native terminal command completion');
  checks.push('Actual command output reaches terminal scrollback before completion');
  terminal.write('/model\r');
  await wait(() => screenText().includes('Choose model'), 'model panel');
  terminal.write('\x1b');
  await delay(100);
  terminal.write('/permission strict\r');
  await wait(() => JSON.parse(database.prepare('SELECT metadata FROM conversations WHERE deleted=0 ORDER BY updated_at DESC LIMIT 1').get().metadata).runtime_config.settings.security.permission_mode === 'strict', 'strict mode change');
  terminal.write('WRITE\r');
  await wait(() => screenText().includes('Approve create_file?'), 'approval panel');
  terminal.write('PLEASE_DO_NOT_WRITE\r');
  await wait(() => completedCount() === 5, 'custom approval denial');
  assert(!fs.existsSync(path.join(project, 'must-not-exist.txt')));
  assert.match(messageRows().filter(message => message.role === 'Reverie').at(-1).content, /PLEASE_DO_NOT_WRITE/);
  await wait(()=>viewportText().includes('tui-fixture')&&!viewportText().includes('Approve create_file?')&&!viewportText().includes('Reverie is working'),'terminal result delivery after approval');
  checks.push('Model panel, per-conversation Strict and custom denial with no file side effect');
  display.resize(42, 12);
  const beforeResize=output.length;
  terminal.resize(42, 12);
  await wait(()=>output.length>beforeResize&&viewportText().includes('Enter send'),'actual terminal redraw after resize');
  terminal.write('HOLD\r');
  await wait(() => Boolean(held), 'pending HTTP request');
  await wait(() => screenText().includes('PARTIAL_UI_REPLY😀') && database.prepare("SELECT group_concat(content, '') AS content FROM stream_chunks WHERE kind='assistant'").get().content === 'PARTIAL_UI_REPLY😀', 'native partial reply displayed and persisted before cancellation');
  terminal.write('\x03');
  await wait(() => database.prepare("SELECT count(*) AS count FROM task_runs WHERE state='cancelled'").get().count === 1 && !held, 'actual Ctrl+C cancellation');
  assert.equal(database.prepare("SELECT group_concat(content, '') AS content FROM stream_chunks WHERE kind='assistant'").get().content, 'PARTIAL_UI_REPLY😀');
  terminal.write('/context status\r');
  await wait(() => screenText().includes('resource_not_installed'), 'terminal resource state');
  terminal.write('/context index\r');
  await wait(() => screenText().includes('"structure_ready": true'), 'terminal background structural index');
  const modelRequests = requests.length;
  terminal.write('/context search terminal_context_marker\r');
  await wait(() => screenText().includes('Retrieval: basic') && screenText().includes('共享 Rust 内核返回的终端证据。'), 'actual terminal context evidence');
  assert.equal(requests.length, modelRequests, 'Context management invoked the remote model');
  checks.push('Terminal resources, cancellable background indexing and actual shared-kernel evidence without a model request');
  terminal.write('/quit\r');
  await wait(() => terminalExit !== undefined, 'normal terminal exit');
  assert.equal(terminalExit.exitCode, 0);
  assert(output.includes('\x1b[?2004l'));
  checks.push('Resize, Ctrl+C, retained partial text and normal terminal cleanup');
  const jsonRun = await headless(['--project', project, '--prompt', 'CLI_JSON', '--no-index', '--json']);
  assert.equal(jsonRun.code, 0, jsonRun.stderr);
  assert.equal(JSON.parse(jsonRun.stdout).result.output_text, 'UI_REPLY:\nCLI_JSON');
  assert(!jsonRun.stdout.includes('TUI_FIXTURE_KEY'));
  const question = await headless(['--project', project, '--prompt', 'HEADLESS_QUESTION', '--no-index', '--json']);
  assert.equal(question.code, 1);
  assert.equal(JSON.parse(question.stdout).result.state, 'cancelled');
  checks.push('Native single-prompt JSON entry and no implicit headless authorization');
  if (serverFailure) throw serverFailure;
  const report = {schema: 'reverie.rust-tui-smoke.v1', passed: true, verified_at: new Date().toISOString(), executable,
    executable_sha256: crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'), root, platform: process.platform, checks,
    scope: 'Actual native executable and pseudoterminal input/output, shared Rust kernel, SQLite transcript and loopback model fixture; not physical keyboard/IME, GUI, DPI or full terminal acceptance.'};
  fs.writeFileSync(path.join(root, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({passed: true, checks: checks.length, report: path.join(root, 'report.json')}));
} catch (error) {
  console.error(JSON.stringify({error:String(error),terminalExit,prompts,terminal_tail:stripVTControlCharacters(output).slice(-3500)}));
  fs.writeFileSync(path.join(root, 'failure.json'), JSON.stringify({passed: false, checks, prompts, error: String(error), stack: error.stack, terminalExit}, null, 2) + '\n');
  fs.writeFileSync(path.join(root, 'fixture-requests.json'), JSON.stringify(requests, null, 2) + '\n');
  throw error;
} finally {
  fs.writeFileSync(path.join(root, 'terminal.txt'), output);
  fs.writeFileSync(path.join(root, 'screen.txt'), screenText());
  displayReplies.dispose();
  display.dispose();
  database?.close();
  if (terminal && !terminalExit) terminal.kill();
  held?.destroy();
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
}
// node-pty keeps its ConPTY reader worker alive after the verified child exit.
// Terminate this driver after saving evidence and closing its server/database.
process.exit(0);
