import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import readline from 'node:readline';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const secret = 'fixture-private-secret';
const tools = ['echo', 'fail', 'progress', 'rotate', 'hang', 'rpc_error'].map(name => ({name, description: `Fixture ${name}`, inputSchema: {type: 'object'}}));
tools[0].inputSchema = {type: 'object', required: ['message'], $defs: {message: {type: 'string'}}, properties: {message: {$ref: '#/$defs/message'}}};
function resultFor(message) {
  if (message.method === 'initialize') return {protocolVersion: '2025-06-18', serverInfo: {name: 'Node native MCP fixture', version: '1'}, capabilities: {tools: {listChanged: true}, resources: {}, prompts: {}}};
  if (message.method === 'tools/list') return message.params?.cursor ? {tools: [...tools.slice(2), {name: 'app_only', inputSchema: {type: 'object'}, _meta: {ui: {visibility: ['app']}}}, {name: 'broken', inputSchema: []}]} : {tools: tools.slice(0, 2), nextCursor: 'page-two'};
  if (message.method === 'resources/list') return {resources: [{uri: 'fixture://note', name: 'fixture note'}]};
  if (message.method === 'resources/templates/list') return {resourceTemplates: [{uriTemplate: 'fixture://{name}', name: 'fixture template'}]};
  if (message.method === 'resources/read') return {contents: [{uri: message.params.uri, text: 'fixture resource'}], _meta: {secret}};
  if (message.method === 'prompts/list') return {prompts: [{name: 'fixture-prompt', arguments: [{name: 'name', required: true}]}]};
  if (message.method === 'prompts/get') return {messages: [{role: 'user', content: {type: 'text', text: `Hello ${message.params.arguments.name}`}}]};
  if (message.method === 'tools/call') {
    if (message.params.name === 'hang') return undefined;
    if (message.params.name === 'fail') return {isError: true, content: [{type: 'text', text: 'fixture tool failure'}]};
    return {content: [{type: 'text', text: `${message.params.arguments.message || message.params.name} ${secret}`}], structuredContent: {fixture: true, _meta: {secret}}, _meta: {secret}};
  }
  throw new Error(`Unexpected MCP method ${message.method}`);
}
const packet = (message, result) => message.params?.name === 'rpc_error' || message.params?.uri === 'fixture://failure'
  ? {jsonrpc: '2.0', id: message.id, error: {code: -32603, message: 'Fixture RPC failure ' + secret}}
  : {jsonrpc: '2.0', id: message.id, result};
const event = message => `event: message\ndata: ${JSON.stringify(message)}\n\n`;
function notifications(message, send) {
  if (message.params?.name === 'progress') send({jsonrpc: '2.0', method: 'notifications/progress', params: {progressToken: 'fixture', progress: 1, message: secret, _meta: {secret}}});
  if (message.params?.name === 'rotate') send({jsonrpc: '2.0', method: 'notifications/tools/list_changed', params: {}});
}

if (process.argv.includes('--serve-stdio')) {
  const audit = process.env.MCP_FIXTURE_AUDIT;
  const log = value => {if (audit) fs.appendFileSync(audit, JSON.stringify(value) + '\n');};
  const send = value => process.stdout.write(JSON.stringify(value) + '\n');
  let initialize;
  log({event: 'started'});
  for await (const line of readline.createInterface({input: process.stdin, crlfDelay: Infinity})) {
    const message = JSON.parse(line);
    log({method: message.method, id: message.id, tool: message.params?.name});
    if (message.method === 'initialize') {
      initialize = message;
      send({jsonrpc: '2.0', id: 'fixture-roots', method: 'roots/list', params: {}});
    } else if (message.id === 'fixture-roots') {
      assert(message.result.roots[0].uri.startsWith('file:'));
      send(packet(initialize, resultFor(initialize)));
    } else if (message.method?.startsWith('notifications/')) {
      continue;
    } else {
      notifications(message, send);
      const result = resultFor(message);
      if (result !== undefined) send(packet(message, result));
    }
  }
  process.exit(0);
}

const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const directory = path.resolve(process.argv[2] || '.runtime/rust-3.0/mcp-smoke');
fs.mkdirSync(directory, {recursive: true});
const root = fs.mkdtempSync(path.join(directory, 'case-'));
const audit = [];
let stream;
let serverFailure;
let session = 0;
let rootRequest = 0;
const pendingRoots = new Map();
const server = http.createServer(async (request, response) => {
  try {
    audit.push({method: request.method, path: request.url});
    assert.equal(request.headers.authorization, `Bearer ${secret}`);
    if (request.url === '/sse' && request.method === 'GET') {
      response.writeHead(200, {'content-type': 'text/event-stream'});
      response.write('event: endpoint\ndata: /messages\n\n');
      stream = response;
      return;
    }
    if (request.method === 'DELETE') {response.writeHead(200); response.end(); return;}
    let bytes = '';
    for await (const chunk of request) bytes += chunk;
    const message = JSON.parse(bytes);
    audit.at(-1).rpc = message.method;
    audit.at(-1).tool = message.params?.name;
    if (message.params?.arguments?.message !== undefined) audit.at(-1).message_type = typeof message.params.arguments.message;
    if (!message.method && pendingRoots.has(message.id)) {
      assert(message.result.roots[0].uri.startsWith('file:'));
      audit.at(-1).rpc = 'roots/list response';
      const complete = pendingRoots.get(message.id);
      pendingRoots.delete(message.id);
      response.writeHead(202); response.end();
      complete();
      return;
    }
    if (message.method?.startsWith('notifications/')) {response.writeHead(202); response.end(); return;}
    assert.equal(message.jsonrpc, '2.0');
    const send = value => response.write(event(value));
    const result = resultFor(message);
    if (request.url === '/messages') {
      response.writeHead(202); response.end();
      if (message.method === 'initialize') {
        const id = `fixture-roots-${++rootRequest}`;
        pendingRoots.set(id, () => stream.write(event(packet(message, result))));
        stream.write(event({jsonrpc: '2.0', id, method: 'roots/list', params: {}}));
        return;
      }
      notifications(message, value => stream.write(event(value)));
      if (result !== undefined) stream.write(event(packet(message, result)));
    } else {
      const headers = {'content-type': 'text/event-stream'};
      if (message.method === 'initialize') headers['mcp-session-id'] = `fixture-${++session}`;
      response.writeHead(200, headers);
      if (message.method === 'initialize') {
        const id = `fixture-roots-${++rootRequest}`;
        pendingRoots.set(id, () => response.end(event(packet(message, result))));
        send({jsonrpc: '2.0', id, method: 'roots/list', params: {}});
        return;
      }
      notifications(message, send);
      if (result !== undefined) response.end(event(packet(message, result)));
    }
  } catch (error) {serverFailure = error; response.destroy(error);}
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const url = `http://127.0.0.1:${server.address().port}`;
try {
  const child = spawn(process.env.CARGO || 'cargo', ['test', '--manifest-path', 'ReverieCli-rs/Cargo.toml', '-p', 'reverie-core', 'mcp::tests::native_protocol_rpc', '--locked', '--', '--ignored', '--nocapture'], {
    cwd: repository, stdio: 'inherit', env: {...process.env, REVERIE_MCP_SMOKE_ROOT: root,
      REVERIE_MCP_FIXTURE_URL: url, REVERIE_MCP_NODE: process.execPath,
      NO_PROXY: [process.env.NO_PROXY, '127.0.0.1', 'localhost'].filter(Boolean).join(',')}, windowsHide: true,
  });
  const code = await new Promise((resolve, reject) => {child.on('error', reject); child.on('exit', resolve);});
  if (serverFailure) throw serverFailure;
  assert.equal(code, 0);
  const checks = JSON.parse(fs.readFileSync(path.join(root, 'native-result.json'), 'utf8')).checks;
  assert(audit.some(item => item.rpc === 'notifications/cancelled'));
  assert(audit.some(item => item.method === 'DELETE'));
  const echoes = audit.filter(item => item.rpc === 'tools/call' && item.tool === 'echo');
  assert.equal(echoes.length, 2, 'Invalid arguments must not reach HTTP or SSE.');
  assert(echoes.every(item => item.message_type === 'string'));
  fs.writeFileSync(path.join(root, 'report.json'), JSON.stringify({status: 'passed', root, checks, audit,
    limitations: ['Loopback fixtures verify actual Rust protocol execution; external MCP services, real OAuth and non-Windows platforms remain unverified.']}, null, 2) + '\n');
  console.log(JSON.stringify({status: 'passed', root, checks}));
} catch (error) {
  fs.writeFileSync(path.join(root, 'report.json'), JSON.stringify({status: 'failed', root, error: String(error), audit}, null, 2) + '\n');
  throw error;
} finally {server.closeAllConnections(); await new Promise(resolve => server.close(resolve));}
