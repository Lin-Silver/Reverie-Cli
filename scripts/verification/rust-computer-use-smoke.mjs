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
const argv = process.argv.slice(2).filter(a => !['--status-only','--physical','--shortcuts'].includes(a));
const statusOnly = process.argv.includes('--status-only');
const physical = process.argv.includes('--physical');
const shortcutsOnly = process.argv.includes('--shortcuts');
assert([statusOnly, physical, shortcutsOnly].filter(Boolean).length <= 1, 'Choose one desktop smoke mode.');
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
let previousImage;
const contenderPrompt = 'Check the desktop from a second kernel.';
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
  assert.equal(reply.data?.error?.code, expected, reply.error);
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
async function* applicationEscape() {
  yield* discover();
  refusal(yield tool('press_key',{window_id:'never-listed',key:'Escape'}),'UNKNOWN_WINDOW');
  refusal(yield tool('press_key',{window_id:'never-listed',key:'Ctrl+S'}),'UNKNOWN_WINDOW');
  refusal(yield tool('press_key',{window_id:windowId,key:'Alt+Tab'}),'INVALID_ARGS');
  data(yield tool('click',{ref:yield* control('Open dismissal dialog')}));
  let dialog;
  const deadline=Date.now()+5000;
  do {
    const windows=data(yield tool('list_windows',{app:'ReverieRustFixture.exe'}));
    dialog=windows.find(w=>w.pid===fixture.pid && w.title==='Reverie dismissal dialog');
    if(!dialog) await delay(25);
  } while(!dialog && Date.now()<deadline);
  assert(dialog,'Owned modal dialog did not open');
  refusal(yield tool('press_key',{window_id:windowId,key:'Escape'}),'TARGET_NOT_FOCUSED');
  refusal(yield tool('press_key',{window_id:windowId,key:'Ctrl+S'}),'TARGET_NOT_FOCUSED');
  assert(!fs.existsSync(artifact+'.dialog'));
  data(yield tool('press_key',{window_id:dialog.id,key:'Escape'}));
  await untilFile(artifact+'.dialog','Cancel');
  yield* discover();
  data(yield tool('click',{ref:yield* control('Open dismissal menu')}));
  await untilFile(artifact+'.menu','open');
  data(yield tool('press_key',{window_id:windowId,key:'Escape'}));
  await untilFile(artifact+'.menu','Keyboard');
  data(yield tool('click',{ref:yield* control('Open native menu')}));
  await untilFile(artifact+'.native-menu','open');
  data(yield tool('press_key',{window_id:windowId,key:'Escape'}));
  await untilFile(artifact+'.native-menu','closed');
  checks.push('Window-local Escape dismissed an owned modal, a WinForms menu and a native menu, refused the wrong window and left the SDK task running');
}
async function untilFile(file,text,timeout=5000) {
  const deadline=Date.now()+timeout;
  while(Date.now()<deadline) {
    if(serverError) throw serverError;
    if(fs.existsSync(file) && fs.readFileSync(file,'utf8')===text) return;
    await delay(20);
  }
  assert.fail('Fixture did not record '+text+' in '+path.basename(file));
}
function* prepareShortcutEditor() {
  yield* discover();
  data(yield tool('window',{window_id:windowId,action:'focus'}));
  data(yield tool('set_value',{ref:yield* control('Verification editor'),value:'alpha beta'}));
  data(yield tool('focus',{ref:yield* control('Verification editor')}));
}
const shortcut = key => tool('press_key',{window_id:windowId,key});
async function* windowShortcuts() {
  yield* prepareShortcutEditor();
  const denied=yield shortcut('Ctrl+S');
  assert.equal(denied.success,false);
  assert.match(denied.error,/denied|refused|rejected/i);
  assert(!fs.existsSync(artifact+'.selection'));
  assert.equal(data(yield shortcut('End')).verification_scope,'foreground_input_queue');
  data(yield shortcut('Ctrl+Shift+Left'));
  data(yield shortcut('Ctrl+S'));
  await untilFile(artifact+'.selection','beta');
  data(yield shortcut('Ctrl+A'));
  data(yield shortcut('Ctrl+S'));
  await untilFile(artifact+'.selection','alpha beta');
  refusal(yield shortcut('Alt+Shift+Tab'),'INVALID_ARGS');
  refusal(yield shortcut('Win+R'),'INVALID_ARGS');
  checks.push('Strict refused a window shortcut then reused a session grant for different keys; real Ctrl+S read back word and full-editor selections');
  data(yield tool('click',{ref:yield* control('Open second window')}));
  const windows=data(yield tool('list_windows',{app:'ReverieRustFixture.exe'}));
  const other=windows.find(w=>w.pid===fixture.pid && w.title==='Reverie Verification Second Window');
  assert(other,'Second nonmodal window must be visible');
  data(yield tool('window',{window_id:other.id,action:'focus'}));
  changeFixture(7);
  refusal(yield shortcut('Ctrl+S'),'TARGET_NOT_FOCUSED');
  changeFixture(7);
  assert(!fs.existsSync(artifact+'.second-save'));
  data(yield tool('window',{window_id:windowId,action:'focus'}));
  data(yield tool('focus',{ref:yield* control('Verification editor')}));
  data(yield shortcut('End'));
  data(yield shortcut('Ctrl+S'));
  await untilFile(artifact+'.selection','');
  checks.push('An enabled background window rejected Ctrl+S while the other fixture kept foreground and received no save; explicit focus restored delivery');
}
function* shortcutDuringStop() {
  yield* prepareShortcutEditor();
  fs.writeFileSync(artifact+'.hold-shortcut','hold');
  yield shortcut('Ctrl+Shift+S');
  yield tool('wait',{window_id:windowId,selector:':reverie-never-present',timeout_ms:60000});
}
function* screenshot(vision) {
  yield* discover();
  const shot=data(yield tool('screenshot',{window_id:windowId,max_dimension:640}));
  assert.equal(shot.model_visible,vision);
  assert.equal(shot.target.id,windowId);
  if(!vision) {
    refusal(yield tool('click',{image_id:shot.image_id,x:1,y:1,physical:true}),'STALE_IMAGE');
  }
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
function marks(file) {
  const dest=path.join(root,file);
  return fs.existsSync(dest) ? fs.readFileSync(dest,'utf8').trim().split(/\r?\n/).filter(Boolean) : [];
}
function coloredTargets(shot) {
  const script=`
    Add-Type -AssemblyName System.Drawing
    $bitmap=[Drawing.Bitmap]::FromFile($env:REVERIE_FIXTURE_PNG)
    try {
      $pink=@(); $blue=@()
      for($y=0;$y -lt $bitmap.Height;$y+=3){for($x=0;$x -lt $bitmap.Width;$x+=3){
        $c=$bitmap.GetPixel($x,$y)
        if($c.R -eq 255 -and $c.G -eq 105 -and $c.B -eq 180){$pink+=,[PSCustomObject]@{x=$x;y=$y}}
        if($c.R -eq 135 -and $c.G -eq 206 -and $c.B -eq 250){$blue+=,[PSCustomObject]@{x=$x;y=$y}}
      }}
      if($pink.Count -lt 8 -or $blue.Count -lt 20){throw 'Expected fixture colors are missing from this screenshot'}
      $px=$pink.x|Measure-Object -Minimum -Maximum;$py=$pink.y|Measure-Object -Minimum -Maximum
      $bx=$blue.x|Measure-Object -Minimum -Maximum;$by=$blue.y|Measure-Object -Minimum -Maximum
      [PSCustomObject]@{x=($px.Minimum+$px.Maximum)/2;y=($py.Minimum+$py.Maximum)/2;
        ax=(3*$bx.Minimum+$bx.Maximum)/4;bx=($bx.Minimum+3*$bx.Maximum)/4;cy=($by.Minimum+$by.Maximum)/2}|ConvertTo-Json -Compress
    } finally { $bitmap.Dispose() }
  `;
  return JSON.parse(execFileSync('powershell.exe',['-NoProfile','-NonInteractive','-Command',script],
    {encoding:'utf8',env:{...process.env,REVERIE_FIXTURE_PNG:shot.path},windowsHide:true}));
}
function changeFixture(action) {
  const script=`
    Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public static class FixtureHost{
      [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr w,out uint p);
      [DllImport("user32.dll")] public static extern IntPtr SendMessageW(IntPtr w,uint m,IntPtr a,IntPtr b);}'
    $w=[IntPtr][long]$env:REVERIE_FIXTURE_HWND;$owner=[uint32]0
    $null=[FixtureHost]::GetWindowThreadProcessId($w,[ref]$owner)
    if($owner -ne [uint32]$env:REVERIE_FIXTURE_PID){throw 'Fixture HWND changed'}
    if([FixtureHost]::SendMessageW($w,0x8519,[IntPtr][int]$env:REVERIE_FIXTURE_ACTION,[IntPtr]::Zero).ToInt64() -ne 1){throw 'Fixture did not acknowledge its control message'}
  `;
  execFileSync('powershell.exe',['-NoProfile','-NonInteractive','-Command',script],{windowsHide:true,timeout:12000,
    env:{...process.env,REVERIE_FIXTURE_HWND:windowId.slice(2),REVERIE_FIXTURE_PID:String(fixture.pid),REVERIE_FIXTURE_ACTION:String(action)}});
}
async function waitForClicks(expected) {
  const until=Date.now()+5000;
  while(Date.now()<until && marks('clicks.log').length<expected) await delay(20);
  assert.equal(marks('clicks.log').length,expected);
}
function* focusedText() {
  yield* discover();
  data(yield tool('window',{action:'focus',window_id:windowId}));
  const editor = () => control('Verification editor');
  data(yield tool('set_value',{ref:yield* editor(),value:'A12Z'}));
  const target = yield* editor();
  data(yield tool('focus',{ref:target}));
  refusal(yield tool('type_text',{ref:target,text:'old reference',physical:true}),'STALE_REF');
  assert.equal(data(yield tool('is',{ref:yield* editor(),property:'focused'})).result,true);
  changeFixture(6);
  const insert = '中文😀 --headed';
  const denied = yield tool('type_text',{ref:yield* editor(),text:insert});
  refusal(denied,'POLICY_DENIED');
  assert.equal(data(yield tool('get',{ref:yield* editor(),property:'value'})).value,'A12Z');
  const fresh = yield* editor();
  refusal(yield tool('type_text',{ref:fresh,text:'界'.repeat(3334),physical:true}),'INVALID_ARGS');
  data(yield tool('type_text',{ref:fresh,text:insert,physical:true}));
  const edited = 'A' + insert + 'Z';
  assert.equal(data(yield tool('get',{ref:yield* editor(),property:'value'})).value,edited);
  data(yield tool('click',{ref:yield* control('Save verification')}));
  assert.equal(fs.readFileSync(artifact,'utf8').replace(/^\uFEFF/,''),edited);
  checks.push('observed editor focus and UTF-8 text insertion at a real selection; default Windows physical-input refusal, byte limit, stale ref, accessibility and saved file checked');
}
async function* coordinateInput() {
  yield* discover();
  data(yield tool('window',{action:'focus',window_id:windowId}));
  const base=data(yield tool('screenshot',{window_id:windowId}));
  assert.equal(base.coordinate_available,true);
  assert.equal(base.target.is_focused,true);
  const x=Math.floor(base.original_width*0.6);
  const region={x,y:0,width:base.original_width-x,height:base.original_height};
  const capture=()=>tool('screenshot',{window_id:windowId,region,max_dimension:360});
  const click=(image,x,y)=>tool('click',{image_id:image.image_id,x,y,physical:true});
  const initial=data(yield capture());
  const latest=data(yield capture());
  const pts=coloredTargets(latest);
  refusal(yield click(initial,pts.x,pts.y),'STALE_IMAGE');
  refusal(yield click(latest,latest.width,pts.y),'INVALID_ARGS');
  assert.equal(marks('clicks.log').length,0);
  const sent=data(yield click(latest,pts.x,pts.y));
  assert.equal(sent.disposition.delivery,'delivered_unverified');
  await waitForClicks(1);
  refusal(yield click(latest,pts.x,pts.y),'STALE_IMAGE');
  const fresh=data(yield capture());
  const drag=tool('drag',{from_image_id:fresh.image_id,from_x:pts.ax,from_y:pts.cy,to_image_id:fresh.image_id,to_x:pts.bx,to_y:pts.cy});
  assert.equal(data(yield drag).disposition.retry,'unsafe');
  data(yield tool('wait',{window_id:windowId,selector:':Drag completed: 1'}));
  const gesture=marks('drag.log').map(s=>s.split(' '));
  assert.deepEqual(gesture.map(row=>row[0]),['down','up']);
  assert(Number(gesture[1][1])-Number(gesture[0][1])>30);
  checks.push('cropped, downscaled screenshot pixels clicked the pink button once and dragged across the blue canvas; independent window logs and counter matched');
  const moved=data(yield capture());
  changeFixture(1);
  refusal(yield click(moved,pts.x,pts.y),'STALE_IMAGE');
  data(yield tool('window',{action:'focus',window_id:windowId}));
  const covered=data(yield capture());
  assert.equal(covered.target.is_focused,true);
  changeFixture(2);
  try {refusal(yield click(covered,pts.ax,pts.cy),'TARGET_OCCLUDED');}finally { changeFixture(3); }
  assert.equal(marks('clicks.log').length,1);
  assert.equal(marks('drag.log').length,2);
  previousImage=data(yield capture()).image_id;
  checks.push('replaced, consumed, out-of-bounds, moved-window and covered screenshot targets were refused without additional fixture input');
}
function* foreignImage() {
  refusal(yield tool('click',{image_id:previousImage,x:1,y:1,physical:true}),'STALE_IMAGE');
  checks.push('a separate run could not reuse the previous run screenshot for input');
}
async function* strictCoordinates(){
  yield* discover();
  data(yield tool('window',{action:'focus',window_id:windowId}));
  const capture=()=>tool('screenshot',{window_id:windowId,max_dimension:640});
  const shot=data(yield capture());
  const {x,y}=coloredTargets(shot);
  const click=(s,px)=>tool('click',{physical:true,image_id:s.image_id,x:px,y});
  const before=marks('clicks.log').length;
  const denied=yield click(shot,x);
  assert.equal(denied.success,false);assert.match(denied.error,/denied|refused|rejected/i);
  assert.equal(marks('clicks.log').length,before);
  data(yield click(shot,x));
  await waitForClicks(before+1);
  data(yield click(data(yield capture()),x+1));
  await waitForClicks(before+2);
  checks.push('Strict denied a real pointer request before dispatch, then reused the click-tool session grant on a fresh image and different pixel');
}
function* escapeWait(){
  yield* discover();
  data(yield tool('window',{action:'focus',window_id:windowId}));
  yield tool('wait',{window_id:windowId,selector:':reverie-never-present',timeout_ms:60000});
}
function* restricted() {
  const r = yield tool('list_windows');
  assert.equal(r.success,false); assert.match(r.error,/full_control/);
  const sent=yield tool('click',{image_id:'not-authorized',x:1,y:1,physical:true});
  assert.equal(sent.success,false);assert.match(sent.error,/full_control/);
  if(process.platform==='win32') {
    const pressed=yield tool('press_key',{window_id:'never-authorized',key:'Ctrl+S'});
    assert.equal(pressed.success,false);assert.match(pressed.error,/full_control/);
  }
  checks.push('explicit permission level refused off-workspace observation and input');
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
    if (request.messages.some(m => m.role === 'user' && m.content === contenderPrompt)) {
      const last = request.messages.at(-1);
      if (last.role === 'tool') assert.equal(data(JSON.parse(last.content)).version, '1.2.0');
      const message = last.role === 'tool' ? {role:'assistant',content:'Second kernel observed the desktop.'} :
        {role:'assistant',content:null,tool_calls:[{id:'other-status',type:'function',function:{name:'computer_status',arguments:'{}'}}]};
      res.writeHead(200,{'content-type':'application/json'});
      res.end(JSON.stringify({choices:[{message,finish_reason:last.role === 'tool' ? 'stop' : 'tool_calls'}]}));
      return;
    }
    const names = request.tools.map(t => t.function.name);
    assert(names.includes('computer_status'));
    assert.equal(names.includes('computer_click'), expectedTools);
    assert.equal(names.includes('computer_press_key'), expectedTools && process.platform==='win32');
    imageBlocks=request.messages.flatMap(m=>Array.isArray(m.content)?m.content.filter(b=>b.type==='image_url'):[]);
    const last = request.messages.findLast(m=>m.role==='tool') ?? request.messages.at(-1);
    const next = await scenario.next(last.role === 'tool' ? JSON.parse(last.content) : undefined);
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
async function checkContendingKernel(release) {
  const otherProject = path.join(root,'second-workspace'), otherApp = path.join(root,'second-app');
  fs.mkdirSync(otherProject);
  fs.mkdirSync(path.join(otherApp,'.reverie'),{recursive:true});
  fs.copyFileSync(path.join(app,'.reverie/config.json'),path.join(otherApp,'.reverie/config.json'));
  const other = startBridge(executable,otherProject,otherApp,{NO_PROXY:'127.0.0.1,localhost'});
  try {
    await other.ready;
    const payload = {projectRoot:otherProject};
    await other.request('initialize',payload);
    const {session} = await other.request('createSession',{...payload,name:'competing kernel'});
    const response = other.request('runPrompt',{...payload,sessionId:session.id,runId:'competing',prompt:contenderPrompt,noIndex:true},30000);
    const deadline = Date.now()+8000;
    while (!other.events.some(e=>e.event?.event?.tool_name==='computer_status')) {
      if (serverError) throw serverError;
      assert(Date.now()<deadline,'second kernel must reach the desktop tool');
      await delay(20);
    }
    changeFixture(5);
    assert.equal(await Promise.race([response.then(()=>true),delay(350,false)]),false,'second process entered while the first held the desktop');
    await release();
    const reply = await response;
    assert.equal(reply.result.output_text,'Second kernel observed the desktop.');
    checks.push('two independent SDK kernel processes serialized desktop access across different workspaces and resumed after cancelling the owner');
    await other.request('shutdown',payload);
    assert.equal((await other.closed).code,0);
  } finally { if(other.child.exitCode===null) other.child.kill(); }
}
async function run(id, actions, level='full_control', cancel=false, decisions=[]) {
  const {session} = await request('createSession',{name:id});
  if(['desktop-vision','desktop-pointer','desktop-foreign-image','desktop-strict-pointer'].includes(id)) {
    const selected=await request('selectModel',{sessionId:session.id,source:'standard',modelId:'desktop-vision'});
    assert.equal(selected.type,'model.selected');
  }
  const settings = await request('getConversationConfig',{sessionId:session.id});
  const saved = await request('getConversationConfig',{sessionId:session.id,revision:settings.revision,
    configuration:{...settings.configuration,settings:{...settings.configuration.settings,security:{permission_level:level,permission_mode:decisions.length ? 'strict' : 'normal'}}}});
  assert.equal(saved.type,'conversation.config');
  scenario = actions(); expectedTools = level === 'full_control';
  const response = request('runPrompt',{sessionId:session.id,runId:id,prompt:'Exercise the owned desktop fixture.',noIndex:true});
  if (cancel==='shortcut') {
    try {
      await untilFile(artifact+'.shortcut-down','Ctrl+Shift+S',25000);
      await request('stopPrompt',{sessionId:session.id,runId:id});
      assert.equal((await response).result.state,'cancelled');
    } finally { fs.writeFileSync(artifact+'.resume-shortcut','resume'); }
    await untilFile(artifact+'.shortcut-up','released');
    checks.push('Cancelled while the fixture handled Ctrl+Shift+S; it later consumed key-up and independently observed Ctrl, Shift and S all released');
  } else if (cancel) {
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
    const stop=()=>request('stopPrompt',{sessionId:session.id,runId:id});
    if(cancel==='escape') changeFixture(4);
    else if(physical) await checkContendingKernel(stop);
    else await stop();
    const stopped = await response;
    assert.equal(stopped.result.state,'cancelled');
    assert.throws(()=>process.kill(pid,0), {code:'ESRCH'});
    checks.push(cancel==='escape' ? 'foreground fixture injected OS Escape during a text-only native wait without capturing a screenshot; run cancelled and process exited without an SDK stop request' :
      'cancelled a witnessed native wait process through the SDK and verified its exit');
  } else {
    const answered = new Set();
    for (const item of decisions) {
      const [toolName,decision]=Array.isArray(item)?item:['computer_list_windows',item];
      const until=Date.now()+12000;
      let approval;
      while (Date.now()<until && !approval) {
        if (serverError) throw serverError;
        approval=bridge.events.map(e=>e.event).find(e=>e?.run_id===id && e.type==='approval.request' && !answered.has(e.approval_id));
        if (!approval) await delay(20);
      }
      assert(approval,'missing Strict approval');
      assert.equal(approval.tool,toolName);
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
    fixture=spawn(file,[artifact],{stdio:'ignore',env:{...process.env,REVERIE_EXTENDED_FIXTURE:'1',...(physical||shortcutsOnly?{REVERIE_POINTER_FIXTURE:root}:{})}});
  }
  bridge = startBridge(executable,project,app,{NO_PROXY:'127.0.0.1,localhost'});
  await bridge.ready;
  await request('initialize',{});
  if(!shortcutsOnly) await run('desktop-controls',statusOnly ? status : interactive);
  if (!statusOnly && !shortcutsOnly) {
    await run('desktop-new-run',foreign);
    await run('desktop-local-escape',applicationEscape);
    await run('desktop-text-image',()=>screenshot(false));
    await run('desktop-vision',()=>screenshot(true));
    if(physical){
      await run('desktop-focused-text',focusedText);
      await run('desktop-pointer',coordinateInput);
      await run('desktop-foreign-image',foreignImage);
      await run('desktop-strict-pointer',strictCoordinates,'full_control',false,[
        ['computer_list_windows','session'],['computer_window','session'],['computer_screenshot','session'],
        ['computer_click','deny'],['computer_click','session']]);
      await run('desktop-escape',escapeWait,'full_control','escape');
    }
    await run('desktop-strict',strict,'full_control',false,['deny','session']);
    await run('desktop-cancel',waiting,'full_control',true);
  }
  if (physical || shortcutsOnly) {
    await run('desktop-shortcuts',windowShortcuts,'full_control',false,[
      ['computer_list_windows','session'],['computer_window','session'],['computer_find','session'],
      ['computer_set_value','session'],['computer_focus','session'],['computer_press_key','deny'],['computer_press_key','session'],['computer_click','session']]);
    await run('desktop-shortcut-stop',shortcutDuringStop,'full_control','shortcut');
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
