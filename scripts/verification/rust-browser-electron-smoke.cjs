// Run with Electron after the desktop build. Arguments: Rust release binary, evidence directory.
const {app, BrowserWindow, webContents} = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const {setTimeout: delay} = require('node:timers/promises');
const repo = path.resolve(__dirname,'../..'), ui = path.join(repo,'ReverieCli-ui');
const binary = path.resolve(process.argv[2]), out = path.resolve(process.argv[3] || '.runtime/rust-3.0/browser-electron');
fs.mkdirSync(out,{recursive:true});
const root = fs.mkdtempSync(path.join(out,'case-')), project = path.join(root,'workspace'), data = path.join(root,'app'), desktop = path.join(root,'desktop');
for (const dir of [project,path.join(data,'.reverie'),desktop]) fs.mkdirSync(dir,{recursive:true});
process.env.CARGO_TARGET_DIR = path.dirname(path.dirname(binary));
process.env.REVERIE_DESKTOP_RUNTIME_ROOT = desktop;
process.env.NO_PROXY = [process.env.NO_PROXY,'localhost','127.0.0.1'].filter(Boolean).join(',');
process.argv = [process.execPath,ui,'--gui','--project',project];
app.setPath('userData',path.join(desktop,'user-data'));
const checks=[], observations=[], actions=[];
let win,base,sessionId,routine,modelFailure,finalText,requestNumber=0,heldRequest=false;
const snapshot = () => ({checks,actions,observations,chromium:process.versions.chrome,electron:process.versions.electron,binary,sha256:crypto.createHash('sha256').update(fs.readFileSync(binary)).digest('hex')});
const evaluate = js => win.webContents.executeJavaScript(js,true);
async function until(check,label) {
  const deadline=Date.now()+55000;
  while (Date.now()<deadline) { if(modelFailure) throw modelFailure; if(await check())return; await delay(30); }
  throw new Error('Timed out waiting for '+label);
}
const rpc = (name,payload) => evaluate('window.reverie.request('+JSON.stringify(name)+','+JSON.stringify(payload)+')');
function guest() { return webContents.getAllWebContents().find(w=>!w.isDestroyed() && w.getURL().startsWith(base+'/page')); }
async function* browserFlow() {
  const open = yield {action:'open',url:base+'/page'};
  assert.equal(open.success,true,JSON.stringify(open));
  const tab_id = open.data.result.tab.tab_id;
  await until(()=>evaluate("!!document.querySelector('.browser-page-slot')"),'rendered browser panel');
  const view=win.contentView.children.find(v=>v.webContents===guest());
  await until(()=>view?.getVisible() && view.getBounds().width<win.getContentSize()[0] && view.getBounds().height>100,'native guest in sidebar');
  await until(async()=>await guest().executeJavaScript("document.visibilityState")==='visible','visible Chromium document');
  assert.equal(await guest().executeJavaScript('typeof window.reverie + "/" + typeof window.require'),'undefined/undefined');
  checks.push('Production desktop sidebar displays the isolated native Chromium guest');
  function inspect(reply) {
    assert.equal(reply.success,true,JSON.stringify(reply));
    const {target,result}=reply.data, page=result.observation, image=page.screenshot;
    assert.equal(target.tab_id,tab_id); assert.equal(target.observation_id,reply.data.request_id);
    assert(image.returned_width>0 && image.returned_height>0);
    const file=path.join(project,'.reverie','browser','observations',image.image_id+'.png');
    assert.equal(fs.readFileSync(file).subarray(1,4).toString(),'PNG');
    observations.push({image:file,title:page.tab.title,revision:target.revision});
    const element=(name)=>{const e=page.elements.find(item=>item.name===name);assert(e,'Missing '+name);return e.element_id;};
    return {target,element,page};
  }
  const first=inspect(yield {action:'observe',tab_id});
  const typed=yield {action:'type',target:first.target,element_id:first.element('Message'),replace:true,text:'Reverie 输入'};
  assert.equal(typed.success,true,JSON.stringify(typed));
  const stale=yield {action:'click',target:first.target,element_id:first.element('Save')};
  assert.equal(stale.success,false); assert.equal(stale.data.code,'stale_observation');
  const next=inspect(yield {action:'observe',tab_id});
  assert(next.page.elements.some(e=>e.name==='Message' && e.text==='Reverie 输入'));
  const click=yield {action:'click',target:next.target,element_id:next.element('Save')};
  assert.equal(click.success,true,JSON.stringify(click));
  const after=inspect(yield {action:'observe',tab_id});
  assert(after.page.elements.some(e=>e.text==='Saved: Reverie 输入'));
  assert.equal(await guest().executeJavaScript("localStorage.getItem('saved')"),'Reverie 输入');
  checks.push('Actual browser inputs, stale target refusal, click, DOM readback and on-disk PNGs');
  const listed=yield {action:'list'};assert.deepEqual(listed.data.result.tabs.map(t=>t.tab_id),[tab_id]);
  const moved=yield {action:'navigate',target:after.target,url:base+'/page?next'};assert.equal(moved.success,true,JSON.stringify(moved));
  const location=inspect(yield {action:'observe',tab_id});assert.equal(location.page.tab.url,base+'/page?next');
  const keyed=yield {action:'key',target:location.target,key:'tab',shift:false};assert.equal(keyed.success,true,JSON.stringify(keyed));
  assert.equal(await guest().executeJavaScript("document.activeElement.id"),'entry');
  const scroll=inspect(yield {action:'observe',tab_id});
  const scrolled=yield {action:'scroll',target:scroll.target,element_id:null,delta_x:0,delta_y:120};assert.equal(scrolled.success,true,JSON.stringify(scrolled));
  assert.equal(await guest().executeJavaScript("window.scrollY"),120);
  checks.push('List, navigation, Tab focus and exact scroll displacement through the model tool');
}
async function* profileFlow(mode) {
  const open=yield {action:'open',url:base+'/page'};
  assert.equal(open.success,true,JSON.stringify(open)); assert.equal(open.data.profile.mode,mode);
  const contents=webContents.getAllWebContents().find(w=>!w.isDestroyed() && w.getURL()===base+'/page');
  assert(contents); assert.equal(await contents.executeJavaScript("localStorage.getItem('saved')"),mode==='persistent'?'Reverie 输入':null);
  const observed=yield {action:'observe',tab_id:open.data.result.tab.tab_id};assert.equal(observed.success,true,JSON.stringify(observed));
  if(mode==='persistent'){const close=yield {action:'close',target:observed.data.target};assert.equal(close.success,true,JSON.stringify(close));}
  checks.push('Verified '+mode+' browser storage through a separate run');
}
const server=http.createServer(async(req,res)=>{
  if(req.url==='/hold') { heldRequest=true; res.on('close',()=>{heldRequest=false;}); return; }
  if(req.url.startsWith('/page')){
    res.writeHead(200,{'content-type':'text/html; charset=utf-8'});
    res.end('<title>Reverie browser fixture</title><label>Message<input id="entry"></label><button onclick="localStorage.setItem(\'saved\',entry.value);document.querySelector(\'p\').textContent=\'Saved: \'+entry.value">Save</button><p>Ready</p><div style="height:200vh"></div>');return;
  }
  if(req.url!=='/v1/chat/completions'){res.writeHead(404);res.end();return;}
  try {
    let raw='';for await(const part of req)raw+=part;
    const body=JSON.parse(raw); assert(body.tools.some(t=>t.function.name==='browser')); assert(!body.tools.some(t=>t.function.name==='registerBrowserHost'));
    const last=body.messages.at(-1);
    const reply=last.role==='tool'?JSON.parse(last.content):undefined;
    const step=await routine.next(reply);
    let message;
    if(step.done) message={role:'assistant',content:finalText};
    else {actions.push(step.value.action);message={role:'assistant',content:null,tool_calls:[{id:'browser-'+(++requestNumber),type:'function',function:{name:'browser',arguments:JSON.stringify(step.value)}}]};}
    res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify({choices:[{message,finish_reason:step.done?'stop':'tool_calls'}]}));
  } catch(error){modelFailure=error;res.writeHead(500);res.end('fixture assertion failed');}
});
server.listen(0,'127.0.0.1',()=>{
  base='http://127.0.0.1:'+server.address().port;
  fs.writeFileSync(path.join(data,'.reverie/config.json'),JSON.stringify({models:[{model:'browser-fixture',provider:'openai-chat',base_url:base+'/v1',api_key:'loopback'}],mode:'reverie',active_model_source:'standard',active_model_index:0,auto_index:false,stream_responses:false,api_max_retries:0,security:{permission_level:'full_control',permission_mode:'full_access'}}));
});
fs.writeFileSync(path.join(desktop,'desktop-settings.json'),JSON.stringify({projectRoot:project,coreAppRoot:data,ui:{language:'en-US',startupMode:'gui',inspectorOpen:true}}));
require(path.join(ui,require(path.join(ui,'package.json')).main));
app.whenReady().then(async()=>{
  const watchdog=setTimeout(()=>{console.error('Browser verification deadline');app.exit(1);},150000);
  try {
    await until(()=>win=BrowserWindow.getAllWindows().find(w=>w.getTitle()==='Reverie'),'desktop window');
    await until(()=>evaluate("!!document.querySelector('.composer textarea')"),'composer');
    assert.equal(path.resolve((await evaluate('window.reverie.paths()')).kernelPath),binary);
    await evaluate("window.browserEvents=[];window.reverie.onEvent(msg=>window.browserEvents.push(msg.event?.type||msg.type));window.dispatchEvent(new CustomEvent('reverie:workbench',{detail:{tab:'browser'}}));true");
    routine=browserFlow();finalText='Browser interaction verified';
    await evaluate("document.querySelector('.composer textarea').focus()");
    await win.webContents.insertText('Use the browser to edit the local form.');
    win.webContents.sendInputEvent({type:'keyDown',keyCode:'Enter'});win.webContents.sendInputEvent({type:'keyUp',keyCode:'Enter'});
    await until(()=>evaluate("document.body.innerText.includes('Browser interaction verified') && window.browserEvents.includes('conversation.saved') && !document.querySelector('.send-behavior')"),'first browser turn saved');
    sessionId=(await rpc('getState',{})).state.sessions.current_session_id;
    assert(sessionId);
    for(const mode of ['persistent','ephemeral']) {
      await rpc('setSetting',{sessionId,key:'browser_profile',value:mode});
      routine=profileFlow(mode);finalText='Verified '+mode;
      const response=await rpc('runPrompt',{sessionId,projectRoot:project,prompt:finalText,noIndex:true});
      if(modelFailure)throw modelFailure;
      assert.equal(response.result.success,true,JSON.stringify(response.result));assert.equal(response.result.output_text,finalText);
    }
    assert(!webContents.getAllWebContents().some(w=>!w.isDestroyed() && w.getURL()===base+'/page'));
    routine=(async function* () { yield {action:'open',url:base+'/hold'}; })();
    const pending=rpc('runPrompt',{sessionId,projectRoot:project,prompt:'Open the slow local page.',noIndex:true});
    pending.catch(()=>{});
    await until(()=>heldRequest,'pending Chromium navigation');
    await rpc('stopPrompt',{sessionId,projectRoot:project});
    assert.equal((await pending).result.state,'cancelled');
    await until(()=>!heldRequest,'cancelled network request closed');
    checks.push('Stopping a real pending navigation retires the run and closes the guest connection');
    const events=await evaluate('window.browserEvents');assert(events.includes('browser.tabsChanged')); assert(!events.includes('browser.request')&&!events.includes('browser.cancel'));
    await assert.rejects(rpc('registerBrowserHost',{}),/Unsupported/);
    checks.push('Temporary guest retired at run end; desktop IPC keeps private adapter controls and requests out of the renderer');
    fs.writeFileSync(path.join(root,'report.json'),JSON.stringify({...snapshot(),passed:true},null,2));
    console.log('Browser smoke passed: '+root);
  }catch(error){
    const failure=String((modelFailure||error).stack||error);fs.writeFileSync(path.join(root,'failure.json'),JSON.stringify({...snapshot(),error:failure},null,2));console.error(root,failure);
    if(win && !win.isDestroyed())fs.writeFileSync(path.join(root,'screen.png'),(await win.webContents.capturePage()).toPNG());
    process.exitCode=1;
  }finally{clearTimeout(watchdog);server.closeAllConnections();server.close();if(process.exitCode)app.exit(1);else app.quit();}
});
