import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import http from 'node:http';
import {createRequire} from 'node:module';
import {stripVTControlCharacters} from 'node:util';
import {setTimeout as delay} from 'node:timers/promises';
import {startBridge} from './rust-bridge-client.mjs';
import {createPluginFixture} from './rust-plugin-fixture.mjs';

const require=createRequire(import.meta.url),repo=process.cwd();
const pty=require(path.join(repo,'ReverieCli-ui/node_modules/node-pty')),{Terminal}=require(path.join(repo,'ReverieCli-ui/node_modules/@xterm/headless'));
const executable=path.resolve(process.argv[2]||path.join('ReverieCli-rs','target','release',process.platform==='win32'?'reverie.exe':'reverie'));
const executableSha256=crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'),executableSize=fs.statSync(executable).size;
const directory=path.resolve(process.argv[3]||'.runtime/rust-3.0/plugins-tui-smoke');fs.mkdirSync(directory,{recursive:true});
const root=fs.mkdtempSync(path.join(directory,'case-')),fixture=createPluginFixture(repo,root),display=new Terminal({allowProposedApi:true,cols:100,rows:30,scrollback:2000});
const checks=[],held=new Set();let output='',terminal,terminalExit,bridge,failure;
const server=http.createServer((_request,response)=>{held.add(response);response.once('close',()=>held.delete(response));});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
function screenText(){const buffer=display.buffer.active;return Array.from({length:buffer.length},(_,index)=>buffer.getLine(index).translateToString(true)).join('\n');}
function viewportText(){return screenText().split('\n').slice(-12).join('\n');}
const displayReplies=display.onData(bytes=>terminal?.write(bytes));
async function wait(condition,label){const deadline=Date.now()+15_000;while(Date.now()<deadline){if(await condition())return;await delay(25);}throw new Error(`Timed out: ${label}; exit=${JSON.stringify(terminalExit)}`);}
async function plugin(){return (await bridge.request('listPlugins',{projectRoot:fixture.projectRoot})).plugins.records.find(record=>record.name==='Native plugin fixture😀');}
async function submit(command,label){
  const offset=output.length;
  terminal.write(command+'\r');
  if(label==='Confirm inspected operation')await wait(()=>viewportText().includes(label),label);
  else if(label)await wait(()=>stripVTControlCharacters(output.slice(offset)).includes(label),label);
}
async function confirm(command){await submit(command,'Confirm inspected operation');const offset=output.length;terminal.write('\x1b[B\r');await wait(()=>stripVTControlCharacters(output.slice(offset)).includes('Plugin state updated:'),'confirmed native operation completion');await wait(()=>!viewportText().includes('Confirm inspected operation'),'confirmed panel closure');}
try {
  bridge=startBridge(executable,fixture.projectRoot,fixture.appRoot);await bridge.ready;await bridge.request('initialize',{projectRoot:fixture.projectRoot});
  terminal=pty.spawn(executable,['--project',fixture.projectRoot,'--no-index'],{name:'xterm-256color',cols:100,rows:30,cwd:fixture.projectRoot,env:{...process.env,REVERIE_APP_ROOT:fixture.appRoot,NO_PROXY:[process.env.NO_PROXY,'127.0.0.1','localhost'].filter(Boolean).join(',')}});
  terminal.onData(bytes=>{output+=bytes;display.write(bytes);});terminal.onExit(value=>{terminalExit=value;});
  await wait(()=>screenText().includes('Use /help for commands'),'native terminal startup');
  await submit('/plugins list','Plugins: 0');
  await submit(`/plugins prepare directory "${fixture.sourceRoot.replaceAll('\\','/')}"`,'Plugin candidate prepared:');
  let record=await plugin();assert(record&&!record.enabled&&!record.trusted&&!record.hooks_enabled&&!record.active_sha256);
  const first=record.candidates.find(candidate=>candidate.version==='1.0.0');assert(first?.approval_required);
  assert(!JSON.stringify(first).includes('PLUGIN_FIXTURE_SECRET'));
  checks.push('Actual directory preparation returns identity, license, sanitized components and an inactive untrusted candidate');
  await submit(`/plugins activate ${record.id} ${first.sha256}`,'Confirm inspected operation');
  terminal.write('\r');await wait(()=>!viewportText().includes('Confirm inspected operation')&&viewportText().includes('Enter send'),'default Cancel panel closure');assert.equal((await plugin()).active_sha256,'');
  await confirm(`/plugins activate ${record.id} ${first.sha256}`);await wait(async()=>Boolean((await plugin()).active_sha256),'explicit candidate activation');
  record=await plugin();assert.equal(record.active_sha256,first.sha256);assert(!record.trusted&&!record.enabled);
  await confirm(`/plugins trust ${record.id}`);await wait(async()=>Boolean((await plugin()).trusted),'exact-profile trust');
  assert.equal((await plugin()).auto_update,true);assert.equal((await plugin()).enabled,false);
  checks.push('Enter on the default Cancel leaves content inactive; explicit activation and exact-profile trust remain separate');
  await submit(`/plugins enable ${record.id}`,'Plugin state updated:');await wait(async()=>Boolean((await plugin()).enabled),'project enable');
  await submit('/plugin inspect '+record.id,'"plugin_id"');
  assert(!output.includes('PLUGIN_FIXTURE_SECRET'));
  await confirm(`/plugins hooks ${record.id} on`);await wait(async()=>Boolean((await plugin()).hooks_enabled),'explicit Hooks approval');
  assert(!fs.existsSync(fixture.marker));
  await submit(`/plugins hooks ${record.id} off`,'Plugin state updated:');await wait(async()=>!(await plugin()).hooks_enabled,'Hooks off');
  await submit(`/plugins auto-update ${record.id} off`,'Plugin state updated:');await wait(async()=>!(await plugin()).auto_update,'auto update off');
  checks.push('Project enable, inspected hook event/entry/permission approval and opt-out controls do not execute Hooks');
  fixture.writeVersion('2.0.0');await submit(`/plugins update ${record.id}`,'Plugin candidate prepared:');
  let current=await plugin();const second=current.candidates.find(candidate=>candidate.version==='2.0.0');assert(second&&second.approval_profile_sha256!==first.approval_profile_sha256);assert.equal(current.active_sha256,first.sha256);
  await confirm(`/plugins activate ${record.id} ${second.sha256}`);await wait(async()=>(await plugin()).active_sha256===second.sha256,'changed-profile activation');
  await confirm(`/plugins rollback ${record.id}`);await wait(async()=>(await plugin()).active_sha256===first.sha256,'approved rollback');
  checks.push('Update prepares a separate candidate; explicit changed-profile activation and rollback use inspected versions');
  for(const cancel of ['/plugins stop\r','\x03']) {
    await submit(`/plugins prepare archive "http://127.0.0.1:${server.address().port}/hold.zip"`);
    await wait(()=>held.size===1,'actual pending archive request');
    await submit('/plugins list','Plugins: 1');assert.equal(held.size,1);
    const offset=output.length;terminal.write(cancel);await wait(()=>held.size===0,'targeted archive cancellation');
    await wait(()=>stripVTControlCharacters(output.slice(offset)).includes('Extension download cancelled.'),'native cancellation completion');
    await wait(()=>viewportText().includes('Enter send')&&!viewportText().includes('Plugin preparePlugin'),'terminal recovery after archive cancellation');
  }
  assert.equal((await plugin()).active_sha256,first.sha256);checks.push('Native pending download stays responsive; /plugins stop and Ctrl+C cancel the operation without replacing activation');
  await confirm(`/plugins remove ${record.id}`);await wait(async()=>!(await plugin()),'confirmed removal');assert(!fs.existsSync(fixture.marker));
  await submit('/quit');await wait(()=>terminalExit!==undefined,'normal terminal exit');assert.equal(terminalExit.exitCode,0);
  await bridge.request('shutdown');assert.equal((await bridge.closed).code,0);
  checks.push('Confirmed removal and normal CLI/bridge shutdown leave no hook execution marker');
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'),executableSha256,'The executable changed during verification');
  const report={schema:'reverie.rust-plugins-tui-smoke.v1',passed:true,verified_at:new Date().toISOString(),platform:process.platform,executable,sha256:executableSha256,size:executableSize,root,checks,scope:'Actual Rust executable, native PTY, isolated local extension and loopback archive cancellation; no public packages, user extension execution, real OAuth, physical input/DPI or release acceptance.'};
  fs.writeFileSync(path.join(root,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({passed:true,checks:checks.length,report:path.join(root,'report.json')}));
}catch(error){failure=error;fs.writeFileSync(path.join(root,'failure.json'),JSON.stringify({passed:false,error:String(error.stack||error),checks,terminalExit},null,2));console.error(error);}
finally{fs.writeFileSync(path.join(root,'terminal.txt'),output);fs.writeFileSync(path.join(root,'screen.txt'),screenText());displayReplies.dispose();display.dispose();if(terminal&&!terminalExit)terminal.kill();if(bridge&&bridge.child.exitCode===null)bridge.child.kill();for(const response of held)response.destroy();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
process.exit(failure?1:0);
