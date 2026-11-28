import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import http from 'node:http';
import {setTimeout as delay} from 'node:timers/promises';
import {startBridge} from './rust-bridge-client.mjs';
import {verifyMotion} from './rust-skills-motion.mjs';

const executable=path.resolve(process.argv[2]||`ReverieCli-rs/target/release/reverie${process.platform==='win32'?'.exe':''}`);
const directory=path.resolve(process.argv[3]||'.runtime/rust-3.0/skills-smoke');
fs.mkdirSync(directory,{recursive:true});
const root=fs.mkdtempSync(path.join(directory,'case-'));
const appRoot=path.join(root,'application'),project=path.join(root,'workspace-中文😀'),other=path.join(root,'other-workspace');
const inPlace=process.argv.includes('--installed');
const user=path.join(root,'test-user'),native=inPlace?path.dirname(executable):path.join(root,'native'),assets=path.join(native,'builtin_skills');
for(const folder of [project,other,user,native,path.join(appRoot,'.reverie'),path.join(project,'.git'),path.join(other,'.git')])fs.mkdirSync(folder,{recursive:true});
const installed=path.join(native,path.basename(executable));
if(!inPlace) {
  fs.copyFileSync(executable,installed);
  fs.cpSync(path.join(path.dirname(executable),'builtin_skills'),assets,{recursive:true});
}
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const checks=[],requests=[];
const imported=[];
for(const file of ['elayadesign-source.json','emilkowalski-source.json']) {
  const manifest=JSON.parse(fs.readFileSync(path.join(assets,file),'utf8'));
  assert(fs.existsSync(path.join(assets,manifest.license_file)));
  for(const [relative,expected] of Object.entries(manifest.files))assert.equal(hash(fs.readFileSync(path.join(assets,relative))),expected,relative);
  imported.push({file,revision:manifest.revision,files:Object.keys(manifest.files).length});
}
checks.push('Standalone native deployment retains the two upstream manifests, all 25 fixed hashes and license files');
const registered=JSON.parse(fs.readFileSync(path.join(assets,'reverie-builtin-skills.json'),'utf8'));
assert(registered.includes('photo-to-3d/SKILL.md'));assert(registered.includes('reverse-skill/SKILL.md'));
assert(registered.includes('reverie-motion/SKILL.md'));
const motionFiles=JSON.parse(fs.readFileSync(new URL('../../ReverieCli-rs/resources/builtin_skills/reverie-motion-files.json',import.meta.url),'utf8'));
for(const relative of ['LICENSE','NOTICE.md','PROVENANCE.json','LICENSES/OpenMotion-MIT.txt'])assert(relative in motionFiles);
const motionRoot=path.join(assets,'reverie-motion');
assert(fs.lstatSync(motionRoot).isDirectory());
const installedMotion={};
for(const entry of fs.readdirSync(motionRoot,{recursive:true,withFileTypes:true})) {
  if(entry.isDirectory())continue;
  const file=path.join(entry.parentPath,entry.name);
  const relative=path.relative(motionRoot,file).split(path.sep).join('/');
  assert(entry.isFile() && Object.hasOwn(motionFiles,relative),`Unreviewed Motion entry: ${relative}`);
  installedMotion[relative]=hash(fs.readFileSync(file));
}
assert.deepEqual(installedMotion,motionFiles,'Installed Motion file list and hashes must match the reviewed package');
checks.push(`Standalone deployment matches all ${Object.keys(motionFiles).length} reviewed Motion files and licenses`);

function skill(base,name,body,implicit=true) {
  const folder=path.join(base,name);fs.mkdirSync(path.join(folder,'agents'),{recursive:true});
  fs.writeFileSync(path.join(folder,'SKILL.md'),`---\nname: ${name}\ndescription: >-\n  Native fixture ${name}\n  preserves original evidence.\n---\n${body}`);
  fs.writeFileSync(path.join(folder,'agents/openai.yaml'),`policy:\n  allow_implicit_invocation: ${implicit}\n`);
  return folder;
}
const instructions='# Native skill\n完整原始说明😀\n'+('连续正文及引用 😀\n'.repeat(55));
const packageRoot=skill(path.join(project,'.agents/skills'),'fixture-native',instructions,false);
const reference='原始参考\r\n第二行 😀\n';fs.mkdirSync(path.join(packageRoot,'references'));
fs.writeFileSync(path.join(packageRoot,'references/guide.txt'),reference);
fs.writeFileSync(path.join(packageRoot,'references/binary.dat'),Buffer.from([0,1,2]));
const original=fs.readFileSync(path.join(packageRoot,'SKILL.md'));
skill(path.join(user,'.agents/skills'),'fixture-duplicate','USER_PRIORITY');
skill(path.join(project,'.agents/skills'),'fixture-duplicate','WORKSPACE_SHADOW');
skill(path.join(user,'.agents/skills'),'reverie-motion','USER_SHADOW_OF_BUILTIN');
skill(path.join(project,'.agents/skills'),'reverie-motion','WORKSPACE_SHADOW_OF_BUILTIN');
skill(path.join(project,'.agents/skills'),'fixture-container','# Container');
skill(path.join(project,'.agents/skills/fixture-container'),'must-stay-nested','# Nested package');
for(const name of ['fixture-second','fixture-third','fixture-fourth','fixture-fifth'])skill(path.join(project,'.agents/skills'),name,`# ${name}`);
skill(path.join(other,'.agents/skills'),'fixture-native','# OTHER_PROJECT_BODY',false);
const invalid=path.join(project,'.agents/skills/fixture-invalid');fs.mkdirSync(invalid);
fs.writeFileSync(path.join(invalid,'SKILL.md'),'---\nname: [unclosed\n---\nBad YAML');
fs.mkdirSync(path.join(root,'outside'));fs.writeFileSync(path.join(root,'outside/secret.txt'),'PACKAGE_BOUNDARY');
fs.symlinkSync(path.join(root,'outside'),path.join(packageRoot,'external'),process.platform==='win32'?'junction':'dir');
let bridge,held,serverFailure;
const motionCalls=new Map();
function answer(response,body,text) {response.writeHead(200,{'content-type':'application/json'});response.end(JSON.stringify({choices:[{message:{role:'assistant',content:text},finish_reason:'stop'}]}));}
function tool(response,body,args,name='skill_lookup') {response.writeHead(200,{'content-type':'application/json'});response.end(JSON.stringify({choices:[{message:{role:'assistant',content:null,tool_calls:[{id:`skill-${requests.length}`,type:'function',function:{name,arguments:JSON.stringify(args)}}]},finish_reason:'tool_calls'}]}));}
const server=http.createServer(async(request,response)=>{
  try {
    const chunks=[];for await(const chunk of request)chunks.push(chunk);
    const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));requests.push(body);
    const last=body.messages.at(-1),prompt=body.messages.findLast(message=>message.role==='user').content;
    if(last.role==='tool') {answer(response,body,last.content);return;}
    if(motionCalls.has(prompt)) {
      const {name,args}=motionCalls.get(prompt);
      tool(response,body,args,name);return;
    }
    if(prompt.startsWith('HOLD')) {held={response,body};return;}
    const args={operation:prompt.includes('RESOURCE')?'read_resource':'inspect',skill_name:'fixture-native',force_refresh:true};
    if(args.operation==='read_resource')args.resource_path='references/guide.txt';
    tool(response,body,args,prompt.includes('ALIAS')?'skills_help':'skill_lookup');
  }catch(error){serverFailure=error;response.destroy(error);}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const configuration={mode:'reverie',models:[{model:'skills-fixture',profile_id:'skills-fixture',provider:'openai-chat',base_url:`http://127.0.0.1:${server.address().port}/v1`,api_key:'SKILL_FIXTURE_KEY'}],active_model_source:'standard',active_model_index:0,auto_index:false,stream_responses:false,security:{permission_level:'full_control',permission_mode:'full_access'}};
fs.writeFileSync(path.join(appRoot,'.reverie/config.json'),JSON.stringify(configuration));
const environment={USERPROFILE:user,HOME:user,NO_PROXY:'127.0.0.1,localhost'};
async function request(action,payload={},type) {const reply=await bridge.request(action,payload,30000);if(type)assert.equal(reply.type,type,JSON.stringify(reply));return reply;}
async function run(sessionId,prompt) {const reply=await request('runPrompt',{sessionId,prompt,stream:false},'prompt.result');assert.equal(reply.result.success,true,JSON.stringify(reply));return JSON.parse(reply.result.output_text);}
try {
  bridge=startBridge(installed,project,appRoot,environment);await bridge.ready;
  let state=(await request('initialize',{},'state')).state;
  assert(state.skills.records.some(row=>row.name==='photo-to-3d'&&row.scope==='Built-in'));
  assert(!state.skills.records.some(row=>row.name==='reverie-engine'));
  assert(!state.skills.records.some(row=>row.name==='must-stay-nested'));
  assert.equal(state.skills.invalid_count,1);
  const duplicates=state.skills.records.filter(row=>row.name==='fixture-duplicate');assert.equal(duplicates.length,2);
  assert.equal(duplicates.find(row=>!row.shadowed).scope,'User');assert.equal(state.skills.shadowed_count,3);
  const builtinCopies=state.skills.records.filter(row=>row.name==='reverie-motion');
  assert.deepEqual(builtinCopies.map(row=>[row.scope,row.shadowed]),[['Built-in',false],['User',true],['Workspace',true]]);
  checks.push('Discover registered bundled, user and workspace packages with legacy precedence, nested-package boundary, mode gate and invalid YAML diagnostics');
  const inspected=await request('inspectSkill',{skill:'fixture-native'},'skill.inspect');assert.equal(inspected.record.body,instructions.trim());
  const search=await request('lookupSkill',{operation:'search',query:'连续正文',max_results:20},'skill.lookup');assert(search.data.items.some(row=>row.name==='fixture-native'));
  let body='',offset=0,parts=0;
  do {const reply=await request('lookupSkill',{operation:'inspect',skill_name:'fixture-native',body_offset:offset,max_body_chars:200},'skill.lookup');assert([...reply.data.body].length<=200);body+=reply.data.body;parts++;if(reply.data.complete)break;offset=reply.data.next_body_offset;}while(parts<30);
  assert.equal(body,instructions.trim());assert(parts>1);
  const resource=await request('lookupSkill',{operation:'read_resource',skill_name:'fixture-native',resource_path:'references/guide.txt'},'skill.lookup');assert.equal(resource.data.body,reference);
  for(const relative of ['../fixture-second/SKILL.md','external/secret.txt','references/binary.dat'])await request('lookupSkill',{operation:'read_resource',skill_name:'fixture-native',resource_path:relative},'error');
  checks.push('Search complete native bodies, paginate Unicode instructions, preserve reference bytes and reject traversal, junction escape and binary data');
  fs.appendFileSync(path.join(packageRoot,'SKILL.md'),'\nCHANGED');await request('inspectSkill',{skill:'fixture-native'},'error');
  fs.writeFileSync(path.join(packageRoot,'SKILL.md'),original);await request('refreshSkills',{},'skills');
  checks.push('Refuse changed instructions until an explicit rescan without rewriting the package');
  await request('pinSkill',{skill:'fixture-native',draft:true},'skill.pinned');
  const first=(await request('createSession',{name:'Pinned native skills'},'session.created')).session;
  assert.deepEqual((await request('listSkills',{sessionId:first.id},'skills')).skills.pinned.names,['fixture-native']);
  await request('clearPinnedSkills',{draft:true},'skill.pinned');
  const second=(await request('createSession',{name:'Independent pins'},'session.created')).session;
  assert.deepEqual((await request('getSession',{sessionId:second.id,select:false},'session')).skills.pinned.names,[]);
  assert.deepEqual((await request('getSession',{sessionId:first.id,select:false},'session')).skills.pinned.names,['fixture-native']);
  assert.equal((await request('listSessions',{},'sessions')).sessions.current_session_id,second.id);
  await request('pinSkill',{sessionId:first.id,skill:'fixture-second',expectedRevision:-1},'error');
  for(const name of ['fixture-second','fixture-third','fixture-fourth'])assert.equal((await request('pinSkill',{sessionId:first.id,skill:name},'skill.pinned')).status,'pinned');
  assert.equal((await request('pinSkill',{sessionId:first.id,skill:'fixture-fifth'},'skill.pinned')).status,'full');
  checks.push('Persist draft inheritance and independent conversation pins, return session-owned state, reject stale revisions and enforce four slots');
  await request('setSetting',{sessionId:second.id,key:'mode',value:'reverie-gamer'},'setting.updated');
  assert((await request('listSkills',{sessionId:second.id},'skills')).skills.records.some(row=>row.name==='reverie-engine'));
  assert(!(await request('listSkills',{sessionId:first.id},'skills')).skills.records.some(row=>row.name==='reverie-engine'));
  checks.push('Keep the bundled Engine skill and its cached catalog scoped to Gamer without affecting another conversation');
  await request('setSetting',{sessionId:second.id,key:'mode',value:'reverie'},'setting.updated');
  const pinned=await run(first.id,'PINNED');assert.equal(pinned.success,true);assert.equal(JSON.parse(pinned.output).body,instructions.trim());
  const firstRequest=requests[0];assert(firstRequest.messages[0].content.includes('"mandatory":true'));assert(firstRequest.messages[0].content.includes(instructions.trim()));
  const loadEvent=bridge.events.find(message=>message.event?.event?.event==='skills_loaded');
  assert(loadEvent);assert(loadEvent.event.event.records.some(record=>record.name==='fixture-native'&&record.complete&&record.sha256===hash(Buffer.from(instructions.trim()))));
  const blocked=await run(second.id,'IMPLICIT');assert.equal(blocked.success,false);assert.match(blocked.error,/explicit user request/i);
  const implicitRequest=requests.find(body=>body.messages.at(-1)?.role==='user'&&body.messages.at(-1).content==='IMPLICIT');
  const catalogLine=implicitRequest.messages[0].content.split('\n').find(line=>line.startsWith('Skill catalog: ')).slice('Skill catalog: '.length);
  const advertised=JSON.parse(catalogLine);
  const expected=state.skills.records.filter(row=>row.allow_implicit_invocation&&!row.shadowed);
  assert.deepEqual(advertised.map(row=>[row.name,row.path]).sort(),expected.map(row=>[row.name,row.path]).sort());
  assert.equal(advertised.filter(row=>row.name==='reverie-motion').length,1);
  assert([...catalogLine].length>8192);
  assert(advertised.every(row=>!row.mandatory&&!row.explicit));
  checks.push(`Implicit model request contains all ${expected.length} eligible built-in, user and workspace paths once (${[...catalogLine].length} characters)`);
  const explicit=await run(second.id,'EXPLICIT $fixture-native');assert.equal(JSON.parse(explicit.output).body,instructions.trim());
  const alias=await run(second.id,'ALIAS $fixture-native');assert.equal(alias.success,true);
  const modelReference=await run(second.id,'RESOURCE $fixture-native');assert.equal(JSON.parse(modelReference.output).body,reference);
  checks.push('Load pinned full instructions and body hashes before the actual model request; other skills remain on demand with explicit-only policy and aliases');
  const pending=request('runPrompt',{sessionId:first.id,prompt:'HOLD',stream:false},'prompt.result');
  const deadline=Date.now()+10000;while(!held&&Date.now()<deadline){if(serverFailure)throw serverFailure;await delay(5);}assert(held);
  await request('getState',{projectRoot:other},'state');tool(held.response,held.body,{operation:'inspect',skill_name:'fixture-native',force_refresh:true});held=undefined;
  const heldResult=await pending;assert.equal(heldResult.result.success,true);assert.equal(JSON.parse(JSON.parse(heldResult.result.output_text).output).body,instructions.trim());
  checks.push('A running task refreshes its original project catalog after the shared desktop switches workspaces');
  await request('shutdown',{},'shutdown');assert.equal((await bridge.closed).code,0);
  bridge=startBridge(installed,project,appRoot,environment);await bridge.ready;
  assert.equal((await request('listSkills',{sessionId:first.id},'skills')).skills.pinned.names.length,4);
  fs.renameSync(packageRoot,path.join(project,'released-fixture-native'));
  const unavailable=await request('refreshSkills',{sessionId:first.id},'skills');assert.deepEqual(unavailable.skills.pinned.unresolved,['fixture-native']);
  const callsBeforeFailure=requests.length;
  const missing=await request('runPrompt',{sessionId:first.id,prompt:'MISSING',stream:false},'prompt.result');assert.equal(missing.result.success,false);assert.match(missing.result.error,/unavailable/i);assert.equal(requests.length,callsBeforeFailure);
  fs.renameSync(path.join(project,'released-fixture-native'),packageRoot);
  for(const [body,expected] of [['','no instructions'],['x'.repeat(128001),'turn budget']]) {
    fs.writeFileSync(path.join(packageRoot,'SKILL.md'),`---\nname: fixture-native\ndescription: Explicit fixture.\n---\n${body}`);
    const rejected=await request('runPrompt',{sessionId:first.id,prompt:'INVALID_REQUIRED',stream:false},'prompt.result');assert.equal(rejected.result.success,false);assert(rejected.result.error.includes(expected));assert.equal(requests.length,callsBeforeFailure);
  }
  fs.writeFileSync(path.join(packageRoot,'SKILL.md'),original);
  checks.push('Missing, empty and oversized required instructions block the turn before any model request');
  assert.equal((await request('unpinSkill',{sessionId:first.id,skill:'fixture-native'},'skill.pinned')).status,'unpinned');
  assert.deepEqual(fs.readFileSync(path.join(packageRoot,'SKILL.md')),original);
  assert.deepEqual(fs.readFileSync(path.join(appRoot,'.reverie/config.json')),Buffer.from(JSON.stringify(configuration)));
  checks.push('Restore pins after native restart, retain missing-pin diagnostics until explicit release and preserve source/configuration bytes');
  const motion=await verifyMotion({bridge,project,assets,appState:state,motionCalls,checks});
  await request('shutdown',{},'shutdown');assert.equal((await bridge.closed).code,0);
  const report={schema:'reverie.rust-skills-smoke.v1',passed:true,verified_at:new Date().toISOString(),executable:installed,executable_sha256:hash(fs.readFileSync(installed)),root,imported,motion,checks,scope:'Actual standalone Rust deployment, JSONL, files, Unicode chunks, SQLite pins, loopback HTTP model tool execution and installed headless Chromium. Real-model selection and other platforms require separate validation.'};
  fs.writeFileSync(path.join(root,'report.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({passed:true,checks:checks.length,report:path.join(root,'report.json')}));
}catch(error){fs.writeFileSync(path.join(root,'failure.json'),JSON.stringify({passed:false,error:String(error),root,checks},null,2)+'\n');throw error;}
finally{if(held)held.response.destroy();if(bridge?.child.exitCode===null){bridge.child.stdin.end();await bridge.closed;}await new Promise(resolve=>server.close(resolve));}
