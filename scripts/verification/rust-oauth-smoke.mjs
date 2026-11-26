import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const directory = path.resolve(process.argv[2] || '.runtime/rust-3.0/oauth-smoke');
fs.mkdirSync(directory, {recursive: true});
const root = fs.mkdtempSync(path.join(directory, 'case-'));
const clients = new Map([['preconfigured: a+b', {method: 'client_secret_basic', secret: 'fixture-client-secret'}]]);
const codes = new Map();
const refreshTokens = new Map();
const accessTokens = new Set();
const checks = {registrations: 0, exchanges: 0, refreshes: 0, revocations: 0, metadata: 0, mcp_calls: 0, scope_challenges: 0, total_requests: 0};
let disconnectRefresh = false;
let base;
let serverFailure;
const json = (response, status, value) => {response.writeHead(status, {'content-type': 'application/json'}); response.end(JSON.stringify(value));};
function authenticate(request, form) {
  if (request.headers.authorization?.startsWith('Basic ')) {
    const pair = Buffer.from(request.headers.authorization.slice(6), 'base64').toString('utf8').split(':');
    assert.equal(pair.length, 2);
    const id = new URLSearchParams('value=' + pair[0]).get('value');
    const secret = new URLSearchParams('value=' + pair[1]).get('value');
    assert.equal(clients.get(id)?.method, 'client_secret_basic');
    assert.equal(clients.get(id)?.secret, secret);
    return id;
  }
  const id = form.get('client_id');
  assert.equal(clients.get(id)?.method, 'none');
  return id;
}
const server = http.createServer(async (request, response) => {
  try {
    const url = new URL(request.url, base);
    const clean = () => {assert(!request.headers.authorization); assert(!request.headers['x-configuration-secret']);};
    if (url.pathname === '/audit') {json(response, 200, checks); return;}
    checks.total_requests++;
    if (url.pathname === '/resource') {
      clean(); checks.metadata++;
      json(response, 200, {resource: base + '/mcp', authorization_servers: [base + '/issuer-primary', base + '/issuer-alternate'], scopes_supported: ['files:read', 'files:write']}); return;
    }
    if (url.pathname.startsWith('/.well-known/')) {
      clean(); checks.metadata++;
      const primary = url.pathname === '/.well-known/oauth-authorization-server/issuer-primary';
      const alternate = url.pathname === '/.well-known/openid-configuration/issuer-alternate';
      if (!primary && !alternate) {json(response, 404, {}); return;}
      json(response, 200, {issuer: base + (primary ? '/issuer-primary' : '/issuer-alternate'), authorization_endpoint: base + '/authorize',
        token_endpoint: base + '/token', registration_endpoint: base + '/register', revocation_endpoint: base + '/revoke',
        token_endpoint_auth_methods_supported: primary ? ['none', 'client_secret_basic'] : ['client_secret_basic'],
        code_challenge_methods_supported: ['S256'], response_types_supported: ['code'], authorization_response_iss_parameter_supported: true}); return;
    }
    if (url.pathname === '/authorize') {
      clean();
      const id = url.searchParams.get('client_id');
      assert(clients.has(id)); assert.equal(url.searchParams.get('response_type'), 'code');
      assert.equal(url.searchParams.get('resource'), base + '/mcp'); assert.equal(url.searchParams.get('code_challenge_method'), 'S256');
      assert.equal(url.searchParams.get('scope'), 'files:read');
      const redirect = new URL(url.searchParams.get('redirect_uri'));
      assert.equal(redirect.hostname, '127.0.0.1');
      const registration = clients.get(id); if (registration.redirect) assert.equal(redirect.href, registration.redirect);
      const code = crypto.randomBytes(32).toString('base64url');
      const issuer = base + (id.startsWith('preconfigured') ? '/issuer-alternate' : '/issuer-primary');
      codes.set(code, {client: id, redirect: redirect.href, challenge: url.searchParams.get('code_challenge'), issuer});
      redirect.searchParams.set('code', code); redirect.searchParams.set('state', url.searchParams.get('state')); redirect.searchParams.set('iss', issuer);
      response.writeHead(302, {location: redirect.href, 'cache-control': 'no-store'}); response.end(); return;
    }
    if (url.pathname === '/mcp' && request.method === 'GET') {
      clean();
      response.writeHead(401, {'www-authenticate': 'Bearer resource_metadata="' + base + '/resource", scope="files:read"'}); response.end(); return;
    }
    let bytes = ''; for await (const chunk of request) bytes += chunk;
    if (url.pathname === '/fixture-control') {disconnectRefresh = JSON.parse(bytes).disconnect_refresh; json(response, 200, {}); return;}
    if (url.pathname === '/register') {
      clean(); checks.registrations++;
      const value = JSON.parse(bytes); assert.equal(value.token_endpoint_auth_method, 'none'); assert.equal(value.redirect_uris.length, 1);
      const id = 'dynamic-' + crypto.randomUUID(); clients.set(id, {method: 'none', redirect: value.redirect_uris[0]});
      json(response, 201, {client_id: id, token_endpoint_auth_method: 'none', redirect_uris: value.redirect_uris}); return;
    }
    if (url.pathname === '/token') {
      const form = new URLSearchParams(bytes); const id = authenticate(request, form);
      assert.equal(form.get('resource'), base + '/mcp'); assert.equal(request.headers['content-type'], 'application/x-www-form-urlencoded');
      const grant = form.get('grant_type');
      let expires = 3600;
      if (grant === 'authorization_code') {
        checks.exchanges++; expires = 0;
        const saved = codes.get(form.get('code')); assert(saved); codes.delete(form.get('code'));
        assert.equal(saved.client, id); assert.equal(saved.redirect, form.get('redirect_uri'));
        assert.equal(saved.challenge, crypto.createHash('sha256').update(form.get('code_verifier')).digest('base64url'));
      } else {
        assert.equal(grant, 'refresh_token'); checks.refreshes++;
        const saved = refreshTokens.get(form.get('refresh_token')); assert.equal(saved?.client, id); refreshTokens.delete(form.get('refresh_token'));
        if (disconnectRefresh) {disconnectRefresh = false; response.socket.destroy(); return;}
      }
      const access = 'oauth-' + (grant === 'authorization_code' ? 'initial' : 'refreshed') + '-' + crypto.randomUUID();
      const refresh = 'oauth-refresh-' + crypto.randomUUID(); accessTokens.add(access); refreshTokens.set(refresh, {client: id});
      json(response, 200, {access_token: access, refresh_token: refresh, token_type: 'Bearer', expires_in: expires, scope: 'files:read'}); return;
    }
    if (url.pathname === '/revoke') {
      const form = new URLSearchParams(bytes); authenticate(request, form); checks.revocations++;
      refreshTokens.delete(form.get('token')); accessTokens.delete(form.get('token'));
      response.writeHead(200); response.end(); return;
    }
    if (url.pathname === '/mcp') {
      const token = request.headers.authorization?.replace(/^Bearer /, '');
      if (!accessTokens.has(token)) {response.writeHead(401, {'www-authenticate': 'Bearer resource_metadata="' + base + '/resource", scope="files:read"'}); response.end(); return;}
      if (request.method === 'DELETE') {response.writeHead(200); response.end(); return;}
      const message = JSON.parse(bytes);
      if (message.method.startsWith('notifications/')) {response.writeHead(202); response.end(); return;}
      let result;
      if (message.method === 'initialize') result = {protocolVersion: '2025-06-18', serverInfo: {name: 'Authorized loopback fixture', version: '1'}, capabilities: {tools: {}}};
      else if (message.method === 'tools/list') result = {tools: [{name: 'authorized-echo', inputSchema: {type: 'object'}}, {name: 'needs-write', inputSchema: {type: 'object'}}]};
      else if (message.method === 'tools/call' && message.params.name === 'needs-write') {
        checks.scope_challenges++;
        response.writeHead(403, {'www-authenticate': 'Bearer resource_metadata="' + base + '/resource", error="insufficient_scope", scope="files:write", error_description="private-needle"'}); response.end(); return;
      }
      else {assert.equal(message.method, 'tools/call'); checks.mcp_calls++; result = {content: [{type: 'text', text: message.params.arguments.message + ' ' + token + ' fixture-config-secret'}], _meta: {token}};}
      json(response, 200, {jsonrpc: '2.0', id: message.id, result}); return;
    }
    throw new Error('Unexpected fixture endpoint ' + request.method + ' ' + url.pathname);
  } catch (error) {serverFailure = error; response.destroy(error);}
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); base = 'http://127.0.0.1:' + server.address().port;
try {
  const child = spawn(process.env.CARGO || 'cargo', ['test', '--manifest-path', 'ReverieCli-rs/Cargo.toml', '-p', 'reverie-core', 'connectors::tests::native_oauth_authorization_and_vault', '--locked', '--', '--ignored', '--nocapture'], {
    cwd: repository, stdio: 'inherit', windowsHide: true, env: {...process.env, REVERIE_OAUTH_SMOKE_ROOT: root, REVERIE_OAUTH_FIXTURE_URL: base,
      NO_PROXY: [process.env.NO_PROXY, '127.0.0.1', 'localhost'].filter(Boolean).join(',')},
  });
  const code = await new Promise((resolve, reject) => {child.on('error', reject); child.on('exit', resolve);});
  if (serverFailure) throw serverFailure; assert.equal(code, 0);
  const verified = JSON.parse(fs.readFileSync(path.join(root, 'native-result.json'), 'utf8')).checks;
  fs.writeFileSync(path.join(root, 'report.json'), JSON.stringify({status: 'passed', root, checks: verified, requests: checks,
    limitations: ['OAuth identity/consent is a local protocol fixture, not a real external account login.', 'OS vault access was actually exercised on this host; other OS credential backends remain unverified.']}, null, 2) + '\n');
  console.log(JSON.stringify({status: 'passed', root, checks: verified, requests: checks}));
} catch (error) {
  fs.writeFileSync(path.join(root, 'report.json'), JSON.stringify({status: 'failed', root, error: String(error), requests: checks}, null, 2) + '\n'); throw error;
} finally {server.closeAllConnections(); await new Promise(resolve => server.close(resolve));}
