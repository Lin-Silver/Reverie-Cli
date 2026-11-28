import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath, pathToFileURL} from 'node:url';

const script = fileURLToPath(import.meta.url);
const repository = path.resolve(path.dirname(script), '../..');
const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

if (process.argv.includes('--fixture-child')) {
  setInterval(() => {}, 1000);
} else if (process.argv.includes('--serve')) {
  const root = process.env.LSP_FIXTURE_ROOT;
  const auditPath = process.env.LSP_FIXTURE_AUDIT;
  const secret = process.env.LSP_FIXTURE_SECRET;
  const log = value => fs.appendFileSync(auditPath, JSON.stringify({...value, pid: process.pid}) + '\n');
  const child = spawn(process.execPath, [script, '--fixture-child'], {stdio: 'ignore', windowsHide: true});
  child.unref();
  log({event: 'started', child_pid: child.pid, duplicate_args: process.argv.filter(value => value === '--duplicate').length});
  const documents = new Map();
  const requests = new Map();
  let sending = Promise.resolve();
  const send = message => {
    sending = sending.then(async () => {
      const body = Buffer.from(JSON.stringify(message), 'utf8');
      const bytes = Buffer.concat([Buffer.from(`Content-Length: ${body.length}\r\nContent-Type: application/vscode-jsonrpc; charset=utf-8\r\n\r\n`, 'ascii'), body]);
      process.stdout.write(bytes.subarray(0, 7));
      await sleep(1);
      process.stdout.write(bytes.subarray(7, bytes.length - 3));
      await sleep(1);
      process.stdout.write(bytes.subarray(bytes.length - 3));
    });
    return sending;
  };
  process.stdout.on('error', error => {if (error.code === 'EPIPE') process.exit(0); else throw error;});
  const reply = (request, result) => send({jsonrpc: '2.0', id: request.id, result});
  const serverRequest = (id, method, params) => {requests.set(id, method); return send({jsonrpc: '2.0', id, method, params});};
  const range = {start: {line: 0, character: 5}, end: {line: 0, character: 11}};
  const uri = pathToFileURL(path.join(root, '源码 😀.rs')).href;
  const outside = pathToFileURL(path.join(root, '..', 'outside.rs')).href;
  const publish = async (uri, version) => {
    const versioned = process.env.LSP_FIXTURE_UNVERSIONED ? {} : {version};
    await send({jsonrpc: '2.0', method: 'textDocument/publishDiagnostics', params: {uri, ...versioned, diagnostics: [
      {range, severity: 2, source: 'fixture', message: `Node diagnostic ${secret}`, data: {secret}},
      {range: {start: {line: 0, character: 999}, end: {line: 0, character: 1000}}, message: 'Invalid range'}
    ]}});
  };
  const handle = async message => {
    if (!message.method && requests.has(message.id)) {
      const method = requests.get(message.id);
      requests.delete(message.id);
      if (method === 'workspace/configuration') {
        assert.equal(message.result[0].enabled, true);
        assert.equal(message.result[1], null);
      } else if (method === 'workspace/workspaceFolders') {
        assert.equal(message.result.length, 1);
        assert.equal(message.result[0].uri, pathToFileURL(root).href);
      } else if (method === 'workspace/applyEdit') assert.equal(message.result.applied, false);
      else assert.equal(message.error.code, -32601);
      log({method: `client-reply:${method}`, rejected: Boolean(message.error || message.result?.applied === false)});
      return;
    }
    log({method: message.method, id: message.id, query: message.params?.query, version: message.params?.textDocument?.version, character: message.params?.position?.character});
    switch (message.method) {
      case 'initialize':
        assert.deepEqual(message.params.capabilities.general.positionEncodings, ['utf-16']);
        assert.equal(message.params.capabilities.workspace.applyEdit, false);
        assert.equal(message.params.rootUri, pathToFileURL(root).href);
        assert.equal(message.params.initializationOptions.fixture, true);
        assert.equal(message.params.workspaceFolders.length, 1);
        await reply(message, {capabilities: {positionEncoding: 'utf-16', textDocumentSync: {openClose: true, change: 2}, workspaceSymbolProvider: true, documentSymbolProvider: true, definitionProvider: true}});
        break;
      case 'initialized':
        await serverRequest('settings', 'workspace/configuration', {items: [{scopeUri: uri, section: 'fixture'}, {scopeUri: outside, section: 'fixture'}]});
        await serverRequest('folders', 'workspace/workspaceFolders', {});
        await serverRequest('edit', 'workspace/applyEdit', {edit: {changes: {[outside]: [{range, newText: 'unauthorized'}]}}});
        await serverRequest('register', 'client/registerCapability', {registrations: [{id: 'arbitrary', method: 'workspace/executeCommand'}]});
        await serverRequest('execute', 'workspace/executeCommand', {command: 'arbitrary'});
        await send({jsonrpc: '2.0', method: '$/progress', params: {token: 'fixture', value: {kind: 'report', message: secret, percentage: 50, data: {secret}}}});
        break;
      case 'workspace/didChangeConfiguration':
        assert.equal(message.params.settings.fixture.enabled, true);
        break;
      case 'textDocument/didOpen': {
        const document = message.params.textDocument;
        assert(!documents.has(document.uri));
        assert.equal(document.version, 1);
        assert.equal(document.languageId, 'rust');
        documents.set(document.uri, document);
        await publish(document.uri, document.version);
        break;
      }
      case 'textDocument/didChange': {
        const document = documents.get(message.params.textDocument.uri);
        assert(document);
        assert.equal(message.params.textDocument.version, document.version + 1);
        assert.equal(message.params.contentChanges.length, 1);
        const change = message.params.contentChanges[0];
        assert.deepEqual(change.range.start, {line: 0, character: 0});
        const lines = document.text.split('\n');
        const last = lines.at(-1).replace(/\r$/, '');
        assert.deepEqual(change.range.end, {line: lines.length - 1, character: last.length});
        const oldVersion = document.version;
        document.text = change.text;
        document.version = message.params.textDocument.version;
        await publish(document.uri, document.version);
        setTimeout(() => publish(document.uri, oldVersion).catch(error => {throw error;}), 40);
        break;
      }
      case 'textDocument/didClose':
        assert(documents.delete(message.params.textDocument.uri));
        break;
      case 'workspace/symbol':
        if (['hang', 'cancel'].includes(message.params.query)) break;
        if (message.params.query === 'error') {
          await send({jsonrpc: '2.0', id: message.id, error: {code: -32603, message: `Fixture failure ${secret}`, data: {secret}}});
          break;
        }
        if (message.params.query === 'delay') await sleep(250);
        await reply(message, [
          {name: 'symbol', kind: 12, location: {uri, range}, data: {secret}},
          {name: 'outside', kind: 12, location: {uri: outside, range}},
          {name: 'symbol', kind: 12, location: {uri, range}}
        ]);
        break;
      case 'textDocument/documentSymbol':
        assert(documents.has(message.params.textDocument.uri));
        await reply(message, [{name: 'root', kind: 2, range: {start: {line: 0, character: 0}, end: {line: 0, character: 15}}, selectionRange: {start: {line: 0, character: 0}, end: {line: 0, character: 2}}, children: [{name: 'symbol', kind: 12, range, selectionRange: range, data: {secret}}]}]);
        break;
      case 'textDocument/definition':
        assert(documents.has(message.params.textDocument.uri));
        assert.equal(message.params.position.line, 0);
        assert.equal(message.params.position.character, 5);
        await reply(message, [{targetUri: uri, targetRange: range, targetSelectionRange: range, originSelectionRange: range, data: {secret}}]);
        break;
      case '$/cancelRequest':
        break;
      case 'shutdown':
        await reply(message, null);
        break;
      case 'exit':
        await sending;
        process.exit(0);
      default:
        throw new Error(`Unexpected LSP fixture method ${message.method}`);
    }
  };
  let incoming = Buffer.alloc(0);
  let length;
  let handling = Promise.resolve();
  process.stdin.on('data', chunk => {
    incoming = Buffer.concat([incoming, chunk]);
    while (true) {
      if (length === undefined) {
        const end = incoming.indexOf('\r\n\r\n');
        if (end < 0) return;
        const headers = incoming.subarray(0, end).toString('ascii');
        length = Number(headers.match(/Content-Length:\s*(\d+)/i)[1]);
        incoming = incoming.subarray(end + 4);
      }
      if (incoming.length < length) return;
      const message = JSON.parse(incoming.subarray(0, length).toString('utf8'));
      incoming = incoming.subarray(length);
      length = undefined;
      handling = handling.then(() => handle(message)).catch(error => {log({event: 'failed', message: error.message}); process.exitCode = 1; process.stdin.destroy(); throw error;});
    }
  });
} else {
  const directory = path.resolve(process.argv[2] || path.join(repository, '.runtime/rust-3.0/lsp-smoke'));
  assert(directory.startsWith(repository + path.sep), 'Keep LSP fixture artifacts inside the repository');
  fs.mkdirSync(directory, {recursive: true});
  const base = fs.mkdtempSync(path.join(directory, 'case-'));
  const root = path.join(base, 'project');
  fs.mkdirSync(root);
  fs.writeFileSync(path.join(root, '源码 😀.rs'), '😀fn symbol() {}\r\nsecond line\n');
  fs.writeFileSync(path.join(base, 'outside.rs'), 'Private outside fixture content\n');
  const audit = path.join(base, 'audit.jsonl');
  const environment = {...process.env, REVERIE_LSP_FIXTURE_ROOT: root, REVERIE_LSP_FIXTURE_NODE: process.execPath, REVERIE_LSP_FIXTURE_SCRIPT: script, REVERIE_LSP_FIXTURE_AUDIT: audit};
  const testName = 'lsp::tests::native_stdio_lifecycle_and_evidence';
  const prebuilt = process.env.REVERIE_LSP_TEST_BINARY;
  const command = prebuilt || 'cargo';
  const args = prebuilt ? [testName, '--exact', '--ignored', '--nocapture'] : ['test', '--manifest-path', 'ReverieCli-rs/Cargo.toml', '-p', 'reverie-core', testName, '--locked', '--', '--ignored', '--exact', '--nocapture'];
  const child = spawn(command, args, {cwd: repository, env: environment, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe']});
  let output = '';
  child.stdout.on('data', bytes => {const text = bytes.toString(); output += text; process.stdout.write(text);});
  child.stderr.on('data', bytes => {const text = bytes.toString(); output += text; process.stderr.write(text);});
  let timer;
  const exitCode = await new Promise((resolve, reject) => {
    child.on('error', reject);
    child.on('close', code => {clearTimeout(timer); resolve(code);});
    timer = setTimeout(() => {child.kill(); reject(new Error('Rust LSP fixture build/test exceeded 15 minutes'));}, 900000);
  });
  const auditRows = fs.existsSync(audit) ? fs.readFileSync(audit, 'utf8').trim().split('\n').filter(Boolean).map(line => JSON.parse(line)) : [];
  const nativePath = path.join(root, 'native-result.json');
  const native = fs.existsSync(nativePath) ? JSON.parse(fs.readFileSync(nativePath, 'utf8')) : null;
  const pids = [...new Set(auditRows.flatMap(row => row.event === 'started' ? [row.pid, row.child_pid] : []))];
  const alive = pid => {try {process.kill(pid, 0); return true;} catch {return false;}};
  for (let wait = 0; wait < 50 && pids.some(alive); wait++) await sleep(100);
  const surviving = pids.filter(alive);
  const passed = exitCode === 0 && /1 passed; 0 failed/.test(output) && native?.status === 'passed' && !auditRows.some(row => row.event === 'failed') && surviving.length === 0;
  const report = {status: passed ? 'passed' : 'failed', root, checks: native?.checks || [], exit_code: exitCode,
    starts: auditRows.filter(row => row.event === 'started').length,
    opens: auditRows.filter(row => row.method === 'textDocument/didOpen').length,
    changes: auditRows.filter(row => row.method === 'textDocument/didChange').length,
    cancellations: auditRows.filter(row => row.method === '$/cancelRequest').length,
    shutdowns: auditRows.filter(row => row.method === 'shutdown').length,
    exits: auditRows.filter(row => row.method === 'exit').length,
    surviving_fixture_pids: surviving,
    limitations: ['Local protocol fixture, not an external production language server', 'Host GUI/TUI/Context Engine integration and four-platform release assets are separate acceptance']};
  fs.writeFileSync(path.join(base, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({report: path.join(base, 'report.json'), ...report}, null, 2));
  assert(passed, 'Native LSP lifecycle/evidence verification did not pass; retain the report and inspect the exact failure');
}
