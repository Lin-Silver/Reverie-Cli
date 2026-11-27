import assert from 'node:assert/strict';
import {execFileSync, spawn} from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {fileURLToPath} from 'node:url';
import {startBridge} from './rust-bridge-client.mjs';

const repo = fileURLToPath(new URL('../../', import.meta.url));
const argv = process.argv.slice(2).filter(a => a !== '--status-only');
const statusOnly = process.argv.includes('--status-only');
const executable = path.resolve(argv[0] || path.join(repo, 'ReverieCli-rs/target/release', process.platform === 'win32' ? 'reverie.exe' : 'reverie'));
const directory = path.resolve(argv[1] || path.join(repo, '.runtime/rust-3.0/computer-use-smoke'));
fs.mkdirSync(directory, {recursive: true});
const root = fs.mkdtempSync(path.join(directory, 'case-'));
const project = path.join(root, 'workspace'), app = path.join(root, 'app');
fs.mkdirSync(project);
fs.mkdirSync(path.join(app, '.reverie'), {recursive: true});
const checks = [];
let fixture, bridge, scenario, expectedTools, serverError, sequence = 0;
let imageBlocks=[];
let previousRef, windowId;
const source = 'Reverie 原生桌面 😀';
const artifact = path.join(root, 'fixture-saved.txt');
const tool = (name, args = {}) => ({name: 'computer_' + name, args});
function data(reply) {
  assert.equal(reply.success, true, reply.error || reply.output);
  assert.equal(reply.data.version, '2.6');
  assert.equal(reply.data.ok, true);
  return reply.data.data;
}
function refusal(reply, expected) {
  assert.equal(reply.success, false);
  assert.equal(reply.data.error.code, expected, reply.error);
  assert.deepEqual(reply.data.error.disposition, {delivery: 'not_delivered', retry: 'safe'});
}
function findNode(node, name) {
  if (node.name === name) return node;
  return (node.children || []).map(child => findNode(child, name)).find(Boolean);
}
function* control(name, role) {
  const matches = data(yield tool('find', {window_id: windowId, name, exact: true, ...(role ? {role} : {})})).matches;
  assert.equal(matches.length, 1, name);
  return matches[0].ref_id;
}
function* status() {
  const response = data(yield tool('status'));
  assert.equal(response.version, '1.2.0');
  assert.equal(response.platform, {win32:'windows', darwin:'macos', linux:'linux'}[process.platform]);
  assert(response.permissions);
  checks.push('SDK model tool executed the packaged protocol 2.6 engine and reported its OS permissions');
}
function* discover() {
  const rows = data(yield tool('list_windows', {app:'ReverieRustFixture.exe'}));
  const window = rows.find(w => w.pid === fixture.pid && w.title === 'Reverie Computer Use Verification');
  assert(window);
  windowId = window.id;
}
function* interactive() {
  yield* status();
  assert(data(yield tool('list_displays')).length > 0);
  assert(data(yield tool('list_apps')).apps.some(row => row.pid === fixture.pid));
  refusal(yield tool('snapshot', {window_id: 'never-listed'}), 'UNKNOWN_WINDOW');
  yield* discover();
  const tree = data(yield tool('snapshot', {window_id: windowId}));
  assert.equal(tree.window.id, windowId);
  const editor = findNode(tree.tree, 'Verification editor').ref_id;
  const increment = findNode(tree.tree, 'Increment counter').ref_id;
  checks.push('found the fixture PID and display and observed its exact window');
  data(yield tool('set_value', {ref: editor, value: source}));
  refusal(yield tool('click', {ref: increment}), 'STALE_REF');
  const fresh = yield* control('Verification editor');
  assert.equal(data(yield tool('get', {ref: fresh, property:'value'})).value, source);
  const button = yield* control('Increment counter');
  data(yield tool('click', {ref: button}));
  const count = data(yield tool('wait', {window_id:windowId, selector:':Count: 1'}));
  assert(findNode(count.tree, 'Count: 1'));
  checks.push('real UIA text and counter readbacks; consumed control ref refused');
  data(yield tool('set_state', {ref:yield* control('Enable verification'), state:'checked', value:true}));
  assert.equal(data(yield tool('is', {ref:yield* control('Enable verification'), property:'checked'})).result, true);
  data(yield tool('set_state', {ref:yield* control('Verification choice','combobox'), state:'expanded', value:true}));
  data(yield tool('select', {ref:yield* control('Beta','option'), value:'Beta'}));
  const selected = data(yield tool('snapshot',{window_id:windowId}));
  assert.equal(findNode(selected.tree,'Verification choice').value, 'Beta');
  checks.push('checkbox and combo selection verified on real controls');
  const scrolled=data(yield tool('scroll',{ref:yield* control('Verification scroll'),direction:'down',amount:3}));
  assert.equal(scrolled.disposition.delivery,'delivered_verified');
  const scrolledTo=data(yield tool('scroll_to',{ref:yield* control('Verification row 1')}));
  assert(['delivered_verified','not_delivered'].includes(scrolledTo.disposition.delivery));
  checks.push('native scroll verified and scroll-to returned its actual delivery disposition');
  const save = yield* control('Save verification');
  refusal(yield tool('click', {ref: save, physical:true}), 'INVALID_ARGS');
  data(yield tool('click', {ref: save}));
  assert.equal(fs.readFileSync(artifact, 'utf8').replace(/^\uFEFF/, ''), source);
  previousRef = yield* control('Increment counter');
  checks.push('fixture save wrote exact Unicode content; unsupported physical option refused');
}
function* foreign() {
  refusal(yield tool('click', {ref:previousRef}), 'STALE_REF');
  checks.push('new run rejected the previous run control ref');
}
function* screenshot(vision) {
  yield* discover();
  const shot=data(yield tool('screenshot',{window_id:windowId,max_dimension:640}));
  assert.equal(shot.model_visible,vision);
  assert.equal(shot.target.id,windowId);
  const saved=fs.readFileSync(shot.path);
  assert.equal(saved.readUInt32BE(16),shot.width);
  assert.equal(saved.readUInt32BE(20),shot.height);
  assert.equal(Math.max(shot.width,shot.height),640);
  const pixels=execFileSync('powershell.exe',['-NoProfile','-NonInteractive','-Command',
    'Add-Type -AssemblyName System.Drawing; $bitmap=[Drawing.Bitmap]::FromFile($env:REVERIE_FIXTURE_PNG); try { $blue=0; for($x=0;$x -lt $bitmap.Width;$x+=5){ for($y=0;$y -lt $bitmap.Height;$y+=5){ $c=$bitmap.GetPixel($x,$y); if($c.R -eq 135 -and $c.G -eq 206 -and $c.B -eq 250){$blue++} } }; $blue } finally { $bitmap.Dispose() }'],
    {encoding:'utf8',env:{...process.env,REVERIE_FIXTURE_PNG:shot.path},windowsHide:true});
  assert(Number(pixels.trim())>100,'the native screenshot must contain the fixture canvas');
  if (vision) {
    assert.equal(imageBlocks.length,1);
    assert(Buffer.from(imageBlocks[0].image_url.url.split(',')[1],'base64').equals(saved));
    // A later model request must continue receiving the originally captured bytes.
    fs.writeFileSync(shot.path,'fixture replaced this public preview');
    data(yield tool('status'));
    assert(Buffer.from(imageBlocks[0].image_url.url.split(',')[1],'base64').equals(saved));
    fs.writeFileSync(shot.path,saved);
  } else {assert.equal(imageBlocks.length,0);}
  const region={x:10,y:10,width:180,height:120};
  const cropped=data(yield tool('screenshot',{window_id:windowId,region}));
  assert.deepEqual(cropped.region,region);
  assert.equal(cropped.width,180);assert.equal(cropped.height,120);
  refusal(yield tool('screenshot',{window_id:windowId,region:{x:shot.original_width,y:0,width:2,height:2}}),'CAPTURE_FAILED');
  checks.push(vision ? 'vision request carried the exact captured PNG, preserved pixels after preview replacement and checked crop bounds' :
    'text-only model received a local PNG with independently measured fixture pixels and no image payload');
}
function* restricted() {
  const r = yield tool('list_windows');
  assert.equal(r.success,false); assert.match(r.error,/full_control/);
  checks.push('explicit permission level refused off-workspace observation');
}
function* strict() {
  const denied = yield tool('list_windows',{app:'ReverieRustFixture.exe'});
  assert.equal(denied.success,false);
  assert.match(denied.error,/denied|refused|rejected/i);
  yield* discover();
  const empty = data(yield tool('list_windows',{app:'ReverieNoSuchFixture.exe'}));
  assert.equal(empty.length,0);
  checks.push('Strict denial and session grant for the window tool with changed arguments');
}
function* waiting() {
  yield* discover();
  yield tool('wait', {window_id:windowId, selector:':reverie-never-present',timeout_ms:60000});
}
const server = http.createServer(async (req,res) => {
  try {
    let body = '';
    for await (const chunk of req) body += chunk;
    const request = JSON.parse(body);
    const names = request.tools.map(t => t.function.name);
    assert(names.includes('computer_status'));
    assert.equal(names.includes('computer_click'), expectedTools);
    imageBlocks=request.messages.flatMap(m=>Array.isArray(m.content)?m.content.filter(b=>b.type==='image_url'):[]);
    const last = request.messages.findLast(m=>m.role==='tool') ?? request.messages.at(-1);
    const next = scenario.next(last.role === 'tool' ? JSON.parse(last.content) : undefined);
    const message = next.done ? {role:'assistant',content:'Fixture checks complete.'} :
      {role:'assistant',content:null,tool_calls:[{id:'desktop-' + (++sequence),type:'function',
        function:{name:next.value.name,arguments:JSON.stringify(next.value.args)}}]};
    res.writeHead(200,{'content-type':'application/json'});
    res.end(JSON.stringify({choices:[{message,finish_reason:next.done ? 'stop' : 'tool_calls'}]}));
  } catch (err) { serverError = err; res.writeHead(400); res.end('fixture assertion failed'); }
});
await new Promise(r => server.listen(0,'127.0.0.1',r));
const model = {model:'desktop-test', profile_id:'desktop-test', provider:'openai-chat',
  base_url:`http://127.0.0.1:${server.address().port}/v1`,api_key:'local-fixture'};
fs.writeFileSync(path.join(app,'.reverie/config.json'), JSON.stringify({mode:'reverie',models:[model,{...model,model:'desktop-vision',profile_id:'desktop-vision',supports_vision:true}],
  active_model_source:'standard',active_model_index:0,auto_index:false,stream_responses:false,
  security:{permission_level:'full_control',permission_mode:'normal'}}));
async function request(action, payload) {
  return bridge.request(action,{projectRoot:project,...payload},90000);
}
async function run(id, actions, level='full_control', cancel=false, decisions=[]) {
  const {session} = await request('createSession',{name:id});
  if(id==='desktop-vision') {
    const selected=await request('selectModel',{sessionId:session.id,source:'standard',modelId:'desktop-vision'});
    assert.equal(selected.type,'model.selected');
  }
  const settings = await request('getConversationConfig',{sessionId:session.id});
  const saved = await request('getConversationConfig',{sessionId:session.id,revision:settings.revision,
    configuration:{...settings.configuration,settings:{...settings.configuration.settings,security:{permission_level:level,permission_mode:decisions.length ? 'strict' : 'normal'}}}});
  assert.equal(saved.type,'conversation.config');
  scenario = actions(); expectedTools = level === 'full_control';
  const response = request('runPrompt',{sessionId:session.id,runId:id,prompt:'Exercise the owned desktop fixture.',noIndex:true});
  if (cancel) {
    const until = Date.now()+25000;
    let pid;
    while (Date.now() < until && !pid) {
      if (serverError) throw serverError;
      if (bridge.events.some(e=>e.event?.event?.tool_name==='computer_wait' && e.event.run_id === id)) {
        const lines = execFileSync('powershell.exe',['-NoProfile','-NonInteractive','-Command',
          `Get-CimInstance Win32_Process -Filter "ParentProcessId = ${bridge.child.pid}" | Where-Object { $_.Name -eq 'agent-desktop.exe' -and $_.CommandLine -like '*--wait-for=*reverie-never-present*' } | Select-Object -ExpandProperty ProcessId`],
          {encoding:'utf8',windowsHide:true}).trim();
        if (lines) pid=Number(lines);
      }
      if (!pid) await delay(50);
    }
    assert(pid,'must witness the live native wait before requesting cancellation');
    await request('stopPrompt',{sessionId:session.id,runId:id});
    const stopped = await response;
    assert.equal(stopped.result.state,'cancelled');
    assert.throws(()=>process.kill(pid,0), {code:'ESRCH'});
    checks.push('cancelled a witnessed native wait process through the SDK and verified its exit');
  } else {
    const answered = new Set();
    for (const decision of decisions) {
      const until=Date.now()+12000;
      let approval;
      while (Date.now()<until && !approval) {
        if (serverError) throw serverError;
        approval=bridge.events.map(e=>e.event).find(e=>e?.run_id===id && e.type==='approval.request' && !answered.has(e.approval_id));
        if (!approval) await delay(20);
      }
      assert(approval,'missing Strict approval');
      assert.equal(approval.tool,'computer_list_windows');
      answered.add(approval.approval_id);
      await request('resolveApproval',{sessionId:session.id,approvalId:approval.approval_id,decision});
    }
    const reply = await response;
    if (serverError) throw serverError;
    assert.equal(reply.result?.success,true,JSON.stringify(reply.result || reply.type));
    assert.equal(reply.events.filter(e=>e.event.type==='approval.request').length, decisions.length);
  }
}
try {
  if (!statusOnly) {
    assert.equal(process.platform,'win32','Interactive fixture requires Windows; --status-only checks the engine on other hosts.');
    const file = path.join(root,'ReverieRustFixture.exe');
    execFileSync(path.join(process.env.WINDIR,'Microsoft.NET/Framework64/v4.0.30319/csc.exe'),['/nologo','/target:winexe',
      '/reference:System.Drawing.dll','/reference:System.Windows.Forms.dll','/out:'+file,path.join(repo,'scripts/verification/fixtures/computer-use/Fixture.cs')],{windowsHide:true});
    fixture=spawn(file,[artifact],{stdio:'ignore',env:{...process.env,REVERIE_EXTENDED_FIXTURE:'1'}});
  }
  bridge = startBridge(executable,project,app,{NO_PROXY:'127.0.0.1,localhost'});
  await bridge.ready;
  await request('initialize',{});
  await run('desktop-controls',statusOnly ? status : interactive);
  if (!statusOnly) {
    await run('desktop-new-run',foreign);
    await run('desktop-text-image',()=>screenshot(false));
    await run('desktop-vision',()=>screenshot(true));
    await run('desktop-strict',strict,'full_control',false,['deny','session']);
    await run('desktop-cancel',waiting,'full_control',true);
  }
  await run('desktop-low-level',restricted,'read_only');
  await request('shutdown',{});
  const report={executable,sha256:crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'),status_only:statusOnly,checks,passed:true};
  fs.writeFileSync(path.join(root,'report.json'),JSON.stringify(report,null,2)+'\n');
  console.log(root, checks);
} finally {
  bridge?.child.kill();
  fixture?.kill();
  server.closeAllConnections();
  server.close();
}
