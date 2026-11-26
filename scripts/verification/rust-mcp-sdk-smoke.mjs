import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import http from 'node:http';
import {setTimeout as delay} from 'node:timers/promises';
import {fileURLToPath} from 'node:url';
import {startBridge} from './rust-bridge-client.mjs';

const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const executable = path.resolve(process.argv[2] || `ReverieCli-rs/target/release/reverie${process.platform === 'win32' ? '.exe' : ''}`);
const directory = path.resolve(process.argv[3] || '.runtime/rust-3.0/mcp-sdk-smoke');
fs.mkdirSync(directory, {recursive: true});
const root = fs.mkdtempSync(path.join(directory, 'case-'));
const appRoot = path.join(root, 'application');
const project = path.join(root, 'workspace');
const auditFile = path.join(root, 'stdio-audit.jsonl');
for (const folder of [project, path.join(appRoot, '.reverie')]) fs.mkdirSync(folder, {recursive: true});
const secret = 'fixture-private-secret';
const checks = [], turns = [], readAudit = [], blockedRequests = [], deliveries = [];
let bridge, serverFailure, readServerId;
process.env.NO_PROXY = [process.env.NO_PROXY, '127.0.0.1', 'localhost'].filter(Boolean).join(',');
const modelServer = http.createServer(async (request, response) => {
  try {
    if (request.url === '/blocked-mcp') {
      blockedRequests.push(request.method);
      response.writeHead(401);
      response.end();
      return;
    }
    let bytes = '';
    for await (const chunk of request) bytes += chunk;
    const body = JSON.parse(bytes);
    if (request.url === '/read-mcp') {
      readAudit.push({method: body.method, id: body.id, name: body.params?.name, uri: body.params?.uri, request_id: body.params?.requestId});
      if (body.method.startsWith('notifications/')) {response.writeHead(202); response.end(); return;}
      let result;
      if (body.method === 'initialize') result = {protocolVersion: body.params.protocolVersion, serverInfo: {name: 'SDK read fixture', version: '1'}, capabilities: {resources: {}, prompts: {}}};
      else if (body.method === 'resources/list') result = {resources: [{uri: 'fixture://delayed', name: 'Delayed resource'}]};
      else if (body.method === 'resources/templates/list') result = {resourceTemplates: []};
      else if (body.method === 'prompts/list') result = {prompts: [{name: 'delayed-prompt', arguments: [{name: 'name', required: false}]}]};
      else if (body.method === 'resources/read' && body.params.uri === 'fixture://delayed') return;
      else if (body.method === 'prompts/get') {
        if (body.params.arguments.name === 'wait') return;
        result = {messages: [{role: 'user', content: {type: 'text', text: 'Unexpectedly executed empty-argument prompt'}}]};
      } else throw new Error('Unexpected read fixture method ' + body.method);
      response.writeHead(200, {'content-type': 'application/json'});
      response.end(JSON.stringify({jsonrpc: '2.0', id: body.id, result}));
      return;
    }
    assert.equal(request.url, '/v1/chat/completions');
    assert(!JSON.stringify(body).includes(secret));
    const last = body.messages.at(-1);
    let message, finishReason;
    if (last.role === 'tool') {
      const result = JSON.parse(last.content);
      turns.push({name: last.name, success: result.success, output: result.output, error: result.error, status: result.status, data: result.data});
      message = {role: 'assistant', content: result.success ? result.output : `Refused: ${result.error}`};
      finishReason = 'stop';
    } else {
      const prompt = body.messages.findLast(item => item.role === 'user').content;
      const suffix = prompt === 'HANG' ? '_hang' : '_echo';
      const read = ['INVALID_PROMPT_STRING', 'INVALID_PROMPT_ARRAY', 'HANG_PROMPT', 'HANG_RESOURCE'].includes(prompt);
      const name = read ? prompt === 'HANG_RESOURCE' ? 'mcp-resources-read' : 'mcp-prompts-get'
        : body.tools.find(item => item.function.name.endsWith(suffix))?.function.name;
      assert(name && body.tools.some(item => item.function.name === name), 'Native MCP tool must be present in the model catalog');
      const args = read ? prompt === 'HANG_RESOURCE' ? {server_id: readServerId, uri: 'fixture://delayed'}
        : {server_id: readServerId, name: 'delayed-prompt', arguments: prompt === 'INVALID_PROMPT_STRING' ? 'not-an-object' : prompt === 'INVALID_PROMPT_ARRAY' ? [] : {name: 'wait'}}
        : prompt === 'INVALID' ? {message: 17} : prompt === 'HANG' ? {} : {message: 'Native MCP message😀'};
      message = {role: 'assistant', content: '', tool_calls: [{id: `mcp-call-${turns.length}`, type: 'function', function: {name, arguments: JSON.stringify(args)}}]};
      finishReason = 'tool_calls';
    }
    response.writeHead(200, {'content-type': 'application/json'});
    response.end(JSON.stringify({choices: [{message, finish_reason: finishReason}]}));
  } catch (error) {serverFailure = error; response.destroy(error);}
});
await new Promise(resolve => modelServer.listen(0, '127.0.0.1', resolve));
const serviceBase = 'http://127.0.0.1:' + modelServer.address().port;
fs.writeFileSync(path.join(appRoot, '.reverie/config.json'), JSON.stringify({mode: 'reverie', auto_index: false, stream_responses: false,
  models: [{model: 'fixture-model', profile_id: 'fixture-profile', provider: 'openai-chat', base_url: `http://127.0.0.1:${modelServer.address().port}/v1`}],
  active_model_source: 'standard', active_model_index: 0, security: {permission_level: 'full_control', permission_mode: 'strict', strict_allow_read_only: true}}));
function audit() {return fs.existsSync(auditFile) ? fs.readFileSync(auditFile, 'utf8').trim().split('\n').filter(Boolean).map(line => JSON.parse(line)) : [];}
async function wait(check, label) {
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {const value = await check(); if (value) return value; await delay(15);}
  throw new Error(`Timed out: ${label}`);
}
async function request(action, payload = {}, expected) {
  const result = await bridge.request(action, {projectRoot: project, ...payload}, 20_000);
  if (expected) assert.equal(result.type, expected, JSON.stringify(result));
  return result;
}
async function approval(runId, decision = 'session') {
  const event = await wait(() => bridge.events.find(item => item.type === 'prompt.event' && item.event.run_id === runId && item.event.type === 'approval.request')?.event, 'bound MCP approval');
  return request('resolveApproval', {approvalId: event.approval_id, decision}, 'approval.resolved');
}
function run(sessionId, prompt, runId) {return request('runPrompt', {sessionId, prompt, runId, noIndex: true}, 'prompt.result');}
async function configuration() {return (await request('listMcp', {}, 'mcp')).servers.find(item => item.name === 'sdk-fixture');}
const source = {type: 'stdio', command: process.execPath, args: [path.join(repository, 'scripts/verification/rust-mcp-smoke.mjs'), '--serve-stdio'],
  env: {MCP_FIXTURE_AUDIT: auditFile, FIXTURE_SECRET: secret}, enabled: true, trust: false};
try {
  bridge = startBridge(executable, project, appRoot);
  const ready = await bridge.ready;
  await request('initialize', {}, 'state');
  const configured = await request('configureMcp', {name: 'sdk-fixture', configuration: source}, 'mcp.updated');
  assert(!JSON.stringify(configured).includes(secret));
  assert(configured.servers.some(item => item.name === 'sdk-fixture' && item.fingerprint.length === 64));
  let server = await configuration();
  assert(server && !server.trust && server.fingerprint.length === 64);
  const untrusted = await request('refreshMcp', {}, 'mcp.result');
  assert.equal(audit().length, 0);
  assert(!JSON.stringify(untrusted).includes(secret));
  assert.equal((await request('setMcpTrust', {name: server.name, trusted: true, fingerprint: '0'.repeat(64)})).type, 'error');
  const trusted = await request('setMcpTrust', {name: server.name, trusted: true, fingerprint: server.fingerprint}, 'mcp.updated');
  assert(!JSON.stringify(trusted).includes(secret));
  const discovered = await request('refreshMcp', {}, 'mcp.result');
  assert(audit().some(item => item.method === 'initialize'));
  assert(!JSON.stringify(discovered).includes(secret));
  checks.push('Actual SDK configuration stays inactive until the exact inspected execution fingerprint is trusted');

  const blocked = await request('configureMcp', {name: 'blocked-target-fixture', configuration: {type: 'http', url: serviceBase + '/blocked-mcp', enabled: true, trust: false}}, 'mcp.updated');
  const blockedServer = blocked.servers.find(item => item.name === 'blocked-target-fixture');
  assert(blockedServer);
  await request('setMcpTrust', {name: blockedServer.name, trusted: true, fingerprint: blockedServer.fingerprint}, 'mcp.updated');
  const unusedCredential = 'sdk-fixture-unused-credential';
  fs.writeFileSync(path.join(appRoot, '.reverie/connectors.json'), JSON.stringify({format: 1, retired_credentials: [], connectors: {
    [blockedServer.id]: {server_id: blockedServer.id, binding: '0'.repeat(64), credential_id: unusedCredential, kind: 'api_key',
      resource: serviceBase + '/blocked-mcp', issuer: null, client_id: null, auth_method: null, token_endpoint: null,
      revocation_endpoint: null, scopes: [], expires_at: null, approved_at: 0, api_header: 'authorization', state: 'authorized'},
  }}));
  const connectors = await request('listConnectors', {}, 'connectors');
  const blockedStatus = connectors.connectors.connectors.find(item => item.server_id === blockedServer.id);
  assert.equal(blockedStatus.status, 'target_changed');
  assert.equal(blockedStatus.configuration_current, false);
  assert(!JSON.stringify(connectors).includes(unusedCredential));
  const readConfigured = await request('configureMcp', {name: 'read-fixture', configuration: {type: 'http', url: serviceBase + '/read-mcp', enabled: true, trust: false}}, 'mcp.updated');
  const readServer = readConfigured.servers.find(item => item.name === 'read-fixture');
  assert(readServer);
  readServerId = readServer.id;
  await request('setMcpTrust', {name: readServer.name, trusted: true, fingerprint: readServer.fingerprint}, 'mcp.updated');

  const tools = await request('listTools', {mode: 'reverie'}, 'tools');
  assert(tools.tools.some(item => item.name.endsWith('_echo') && item.kind === 'mcp'));
  assert(tools.authorization_diagnostics.some(item => item.server_id === blockedServer.id));
  assert.equal(blockedRequests.length, 0);
  const resource = await request('readMcpResource', {server_id: server.id, uri: 'fixture://note'}, 'mcp.result');
  assert.equal(resource.mcp.contents[0].text, 'fixture resource');
  const prompt = await request('getMcpPrompt', {server_id: server.id, name: 'fixture-prompt', arguments: {name: 'Reverie😀'}}, 'mcp.result');
  assert.equal(prompt.mcp.messages[0].content.text, 'Hello Reverie😀');
  assert(!JSON.stringify([tools, resource, prompt]).includes(secret));
  checks.push('One native host discovers tools, paginated catalogs, resources and prompts without exposing configured secrets');

  const session = (await request('createSession', {name: 'MCP approval fixture'}, 'session.created')).session.id;
  let pending = run(session, 'VALID', 'mcp-valid');
  await approval('mcp-valid');
  assert.equal((await pending).result.success, true);
  assert.equal(turns.at(-1).success, true);
  assert.match(turns.at(-1).output, /Native MCP message😀/);
  assert.equal(blockedRequests.length, 0);
  checks.push('A target-changed Connector is diagnosed and excluded from MCP requests using metadata-only credentials, while unrelated stdio, listTools and runPrompt remain usable');
  const calls = audit().filter(item => item.method === 'tools/call').length;
  const invalid = await run(session, 'INVALID', 'mcp-invalid');
  assert.equal(invalid.result.success, true);
  assert.equal(turns.at(-1).success, false);
  assert.equal(audit().filter(item => item.method === 'tools/call').length, calls);
  checks.push('Dynamic MCP calls use the ordinary approval and conversation chain, and invalid arguments cause no native RPC');

  const promptRequests = readAudit.filter(item => item.method === 'prompts/get').length;
  for (const [kind, argumentsValue] of [['STRING', 'not-an-object'], ['ARRAY', []]]) {
    const rejected = await request('getMcpPrompt', {server_id: readServerId, name: 'delayed-prompt', arguments: argumentsValue});
    assert.equal(rejected.type, 'error');
    const invalidRunId = 'mcp-invalid-prompt-' + kind.toLowerCase();
    const invalidRun = run(session, 'INVALID_PROMPT_' + kind, invalidRunId);
    if (kind === 'STRING') await approval(invalidRunId);
    const invalidPrompt = await invalidRun;
    assert.equal(invalidPrompt.result.success, true);
    assert.equal(turns.at(-1).name, 'mcp-prompts-get');
    assert.equal(turns.at(-1).success, false);
    assert.match(turns.at(-1).error, /arguments.*object/i);
    assert.equal(readAudit.filter(item => item.method === 'prompts/get').length, promptRequests);
  }
  checks.push('Both SDK and model prompt requests reject explicit string/array arguments without sending prompts/get');

  const changed = await request('configureMcp', {name: 'sdk-fixture', configuration: {...source, env: {...source.env, REVISION: 'second'}}}, 'mcp.updated');
  assert(!JSON.stringify(changed).includes(secret));
  server = await configuration();
  assert.equal(server.trust, false);
  await request('setMcpTrust', {name: server.name, trusted: true, fingerprint: server.fingerprint}, 'mcp.updated');
  pending = run(session, 'VALID', 'mcp-new-identity');
  await approval('mcp-new-identity');
  assert.equal((await pending).result.success, true);
  checks.push('A changed MCP execution fingerprint does not reuse the old conversation approval');

  pending = run(session, 'HANG', 'mcp-hang');
  await approval('mcp-hang');
  await wait(() => audit().some(item => item.method === 'tools/call' && item.tool === 'hang'), 'actual hanging RPC');
  const stopped = await request('stopPrompt', {runId: 'mcp-hang'}, 'run.control');
  assert.equal(stopped.state, 'stopping');
  assert.equal((await pending).result.success, false);
  await wait(() => audit().some(item => item.method === 'notifications/cancelled'), 'native cancellation notification');
  const state = await request('listConversationRuns', {sessionId: session}, 'conversation.runs');
  assert(!JSON.stringify(state).includes(secret));
  checks.push('Stopping the actual SDK task cancels a pending MCP RPC and restores responsive control requests');

  for (const [promptName, method, tool] of [['HANG_RESOURCE', 'resources/read', 'mcp-resources-read'], ['HANG_PROMPT', 'prompts/get', 'mcp-prompts-get']]) {
    const runId = 'mcp-' + promptName.toLowerCase();
    const auditStart = readAudit.length;
    const previousCalls = readAudit.filter(item => item.method === method).length;
    pending = run(session, promptName, runId);
    if (tool === 'mcp-resources-read') await approval(runId);
    const transmitted = await wait(() => readAudit.slice(auditStart).find(item => item.method === method), 'transmitted ' + method);
    const stoppedRead = await request('stopPrompt', {runId}, 'run.control');
    assert.equal(stoppedRead.state, 'stopping');
    assert.equal((await pending).result.success, false);
    const activity = await wait(() => bridge.events.find(item => item.type === 'prompt.event' && item.event.run_id === runId
      && item.event.type === 'ui.event' && item.event.event.type === 'tool_result' && item.event.event.tool_name === tool)?.event.event, 'cancelled read delivery');
    deliveries.push({method, request_id: transmitted.id, delivery: activity.data?.delivery, status: activity.status});
    assert.equal(activity.data.delivery, 'unknown');
    assert.notEqual(activity.status, 'not_started');
    await wait(() => readAudit.some(item => item.method === 'notifications/cancelled' && item.request_id === transmitted.id), 'read cancellation notification');
    const recovered = await request('listTools', {mode: 'reverie'}, 'tools');
    assert(recovered.tools.some(item => item.name.endsWith('_echo') && item.kind === 'mcp'));
    assert.equal(readAudit.filter(item => item.method === method).length, previousCalls + 1);
    assert.equal(blockedRequests.length, 0);
    checks.push('A transmitted ' + method + ' retains Unknown delivery after Stop and is not replayed during discovery recovery');
  }

  const shutdown = await request('shutdown', {}, 'shutdown');
  assert.equal(shutdown.type, 'shutdown');
  assert.equal((await bridge.closed).code, 0);
  if (serverFailure) throw serverFailure;
  const report = {status: 'passed', verified_at: new Date().toISOString(), executable,
    sha256: crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'), size: fs.statSync(executable).size,
    root, checks, model_turns: turns.length, declared_actions: ready.capabilities?.actions?.length,
    blocked_connector_requests: blockedRequests.length, read_delivery: deliveries,
    scope: 'Actual Rust SDK and Agent with Node stdio/HTTP MCP and a loopback model. The target-changed case uses metadata with a deliberately wrong binding and no stored credential; no external service authorization, vault regression, other platforms or release acceptance.'};
  fs.writeFileSync(path.join(root, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({status: report.status, checks: checks.length, report: path.join(root, 'report.json')}));
} catch (error) {
  fs.writeFileSync(path.join(root, 'report.json'), JSON.stringify({status: 'failed', root, checks, blocked_connector_requests: blockedRequests.length,
    read_delivery: deliveries, read_rpc: readAudit, error: String(error), serverFailure: String(serverFailure || '')}, null, 2) + '\n');
  throw error;
} finally {
  if (bridge && bridge.child.exitCode === null) {try {await bridge.request('shutdown');} catch {} if (bridge.child.exitCode === null) bridge.child.kill();}
  modelServer.closeAllConnections();
  await new Promise(resolve => modelServer.close(resolve));
}
