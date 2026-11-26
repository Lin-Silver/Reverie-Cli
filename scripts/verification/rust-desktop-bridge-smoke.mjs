import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {setTimeout as delay} from 'node:timers/promises';
import {DatabaseSync} from 'node:sqlite';

const require = createRequire(import.meta.url);
const {CoreBridge} = require('../../ReverieCli-ui/dist-electron/core-bridge.js');
const {assertCoreResponse} = require('../../ReverieCli-ui/dist-electron/core-actions.js');
const executable = path.resolve(process.argv[2] || `ReverieCli-rs/target/release/reverie${process.platform === 'win32' ? '.exe' : ''}`);
const directory = path.resolve(process.argv[3] || '.runtime/rust-3.0/desktop-bridge-smoke');
fs.mkdirSync(directory, {recursive:true});
const root = fs.mkdtempSync(path.join(directory, 'case-'));
const first = path.join(root, 'first-工作区😀');
const second = path.join(root, 'second-workspace');
const isolated = path.join(root, 'isolated-task');
const appRoot = path.join(root, 'application');
for (const item of [first,second,isolated,path.join(appRoot,'.reverie')]) fs.mkdirSync(item,{recursive:true});
fs.mkdirSync(path.join(first,'.agents/skills/native-bridge-skill'),{recursive:true});
fs.writeFileSync(path.join(first,'.agents/skills/native-bridge-skill/SKILL.md'),'---\nname: native-bridge-skill\ndescription: Actual bridge skill discovery.\n---\nPreserve native session ownership.\n');
const customAnswer = '自定义 fourth option\n保留原文 😀';
const fileContent = 'isolated 原文\r\nsecond line😀';
const events = [];
const checks = [];
const held = new Set();
let serverError;
let callId = 0;
function stream(response, delta, finishReason = null) {
  response.write(`data: ${JSON.stringify({choices:[{index:0,delta,finish_reason:finishReason}]})}\n\n`);
}
const server = http.createServer(async (request,response) => {
  try {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    assert.equal(body.model,'bridge-fixture');
    const prompt = body.messages.findLast(message => message.role === 'user').content;
    const last = body.messages.at(-1);
    response.writeHead(200,{'content-type':'text/event-stream'});
    if (last.role === 'tool') {
      stream(response,{content:`完成\n${JSON.parse(last.content).output}`},'stop');
    } else if (prompt === 'WAIT') {
      stream(response,{content:'partial waiting output 😀'});
      held.add(response);
      response.once('close',()=>held.delete(response));
      return;
    } else if (prompt === 'QUESTION' || prompt === 'WRITE') {
      const name = prompt === 'QUESTION' ? 'userInput' : 'create_file';
      const args = prompt === 'QUESTION' ? {question:'选择实现方式？',reason:'明确用户偏好',options:['A','B','C']}
        : {path:path.join(second,'output.txt'),content:fileContent};
      stream(response,{tool_calls:[{index:0,id:`bridge-call-${++callId}`,type:'function',function:{name,arguments:JSON.stringify(args)}}]},'tool_calls');
    } else stream(response,{content:`echo\n${prompt}`},'stop');
    response.end('data: [DONE]\n\n');
  } catch (error) { serverError = error; response.destroy(error); }
});
await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
fs.writeFileSync(path.join(appRoot,'.reverie/config.json'),JSON.stringify({models:[{model:'bridge-fixture',profile_id:'bridge-profile',provider:'openai-chat',
  base_url:`http://127.0.0.1:${server.address().port}/v1`,api_key:'fixture-secret'}],active_model_source:'standard',active_model_index:0,
  mode:'reverie',auto_index:false,stream_responses:true,security:{permission_mode:'default',permission_level:'full_control'}}));
const bridge = new CoreBridge(first,appRoot,executable,message => events.push(message),{
  settingsPath:path.join(root,'desktop-settings.json'),tempRoot:root,discoveryRoots:[],log:()=>{},
});
async function request(action,payload={}) { return assertCoreResponse(action,await bridge.request(action,payload)); }
async function waitFor(predicate) {
  for (let i=0;i<1000;i++) { if (predicate()) return; await delay(10); }
  throw new Error('Desktop bridge condition timed out.');
}
async function queued(projectRoot,sessionId,prompt,runId,extra={}) {
  const fixed = await request('getConversationConfig',{projectRoot,sessionId});
  const payload = {projectRoot,sessionId,prompt,runId,configuration:fixed.configuration,hostManaged:true,noIndex:true,...extra};
  const queued = await request('queueConversationRun',{projectRoot,sessionId,runId,configuration:fixed.configuration,configurationRevision:fixed.revision,request:payload});
  await request('updateConversationRun',{projectRoot,sessionId,runId,revision:queued.revision,state:'running',executionRoot:extra.executionRoot || projectRoot});
  return {payload,run:()=>request('runPrompt',payload),fixed};
}
let success = false;
try {
  const identity = JSON.parse(execFileSync(executable,['--kernel-info'],{encoding:'utf8',windowsHide:true}));
  assert.equal(identity.implementation,'rust');
  await bridge.start();
  const pid = bridge.getPid();
  const hello = await bridge.request('hello');
  assert.equal(hello.kernel.implementation,'rust');
  assert.equal(bridge.supports('runPrompt'),true);
  assert.equal(bridge.supports('listPlugins'),true);
  assert.equal((await bridge.request('listPlugins')).type,'plugins');
  assert.equal(bridge.supports('unknownFixtureAction'),false);
  const state = (await request('initialize',{projectRoot:first})).state;
  assert.equal(state.core.implementation,'rust');
  assert.equal(state.skills.count,state.skills.records.length);
  assert(state.skills.records.some(record=>record.name==='native-bridge-skill'&&record.scope==='Workspace'));
  assert(state.skills.records.some(record=>record.name==='photo-to-3d'&&record.scope==='Built-in'));
  assert.deepEqual(state.skills.pinned.names,[]);
  checks.push('Native identity, declared capabilities and truthful desktop bootstrap');
  const sessionA = (await request('createSession',{projectRoot:first,name:'first'})).session;
  const sessionB = (await request('createSession',{projectRoot:second,name:'second'})).session;
  const firstPending = request('runPrompt',{projectRoot:first,sessionId:sessionA.id,prompt:'WAIT',runId:'wait-native',noIndex:true});
  await waitFor(()=>events.some(message=>message.event?.type==='assistant.delta'));
  assert.deepEqual((await request('recoverConversationRuns',{projectRoot:first})).runs,[]);
  assert.equal((await request('listConversationRuns',{projectRoot:first,sessionId:sessionA.id})).runs[0].state,'running');
  checks.push('Recovery preserves a live conversation while another workspace is selected');
  const secondRun = await queued(second,sessionB.id,'QUESTION','question-native');
  const bEvents = [];
  const secondPending = bridge.request('runPrompt',secondRun.payload,message=>bEvents.push(message));
  await waitFor(()=>bEvents.some(message=>message.event?.type==='user.question'));
  const question = bEvents.find(message=>message.event.type==='user.question').event;
  assert.deepEqual(question.options,['A','B','C']);
  assert.equal(question.custom_answer,true);
  assert.equal(question.project_root,second);
  assert.equal(bridge.getPid(),pid);
  assert(!events.some(message=>message.event?.run_id==='question-native'));
  await assert.rejects(()=>request('resolveUserInput',{projectRoot:first,sessionId:sessionA.id,questionId:question.question_id,answer:'wrong owner'}));
  await request('resolveUserInput',{projectRoot:second,sessionId:sessionB.id,questionId:question.question_id,answer:customAnswer});
  const secondResult = assertCoreResponse('runPrompt',await secondPending);
  assert.equal(secondResult.result.output_text,`完成\n${customAnswer}`);
  assert(bEvents.every(message=>message.id===secondResult.id && message.event.run_id==='question-native' && message.event.session_id===sessionB.id));
  await request('updateConversationRun',{projectRoot:second,sessionId:sessionB.id,runId:'question-native',revision:secondResult.run_revision,state:'completed',result:secondResult.result});
  checks.push('One process routes concurrent session events and preserves a custom answer');
  const write = await queued(second,sessionB.id,'WRITE','write-isolated',{executionRoot:isolated});
  const writeResult = await write.run();
  assert.equal(writeResult.result.success,true);
  assert.equal(fs.readFileSync(path.join(isolated,'output.txt'),'utf8'),fileContent);
  assert.equal(fs.existsSync(path.join(second,'output.txt')),false);
  assert.equal(bridge.getPid(),pid);
  await request('updateConversationRun',{projectRoot:second,sessionId:sessionB.id,runId:'write-isolated',revision:writeResult.run_revision,state:'completed',result:writeResult.result});
  checks.push('Absolute original workspace paths map to the isolated execution directory');
  await request('stopPrompt',{projectRoot:first,sessionId:sessionA.id});
  const firstResult = await firstPending;
  assert.equal(firstResult.result.state,'cancelled');
  const restored = (await request('getSession',{projectRoot:first,sessionId:sessionA.id,select:false})).session;
  assert.equal(restored.interrupted_streams[0].content,'partial waiting output 😀');
  const page = (await request('getSession',{projectRoot:second,sessionId:sessionB.id,select:false})).session;
  assert(page.messages.some(message=>message.role==='tool' && JSON.parse(message.content).output===customAnswer));
  checks.push('Cancellation retains partial text and other conversations keep their exact transcript');
  const fixed = await request('getConversationConfig',{projectRoot:second,sessionId:sessionB.id});
  const args = {projectRoot:second,sessionId:sessionB.id,runId:'durable-queued',configuration:fixed.configuration,configurationRevision:fixed.revision,request:{prompt:'queued original'}};
  const registered = await request('queueConversationRun',args);
  assert.equal((await request('queueConversationRun',args)).revision,registered.revision);
  await assert.rejects(()=>request('queueConversationRun',{...args,request:{prompt:'replacement'}}));
  await bridge.stop('Test restart',true);
  const recovered = await request('recoverConversationRuns',{projectRoot:second});
  assert.equal(recovered.runs.length,1);
  assert.equal(recovered.runs[0].request.prompt,'queued original');
  await request('renameSession',{projectRoot:second,sessionId:sessionB.id,name:'renamed'});
  assert.equal((await request('getSession',{projectRoot:second,sessionId:sessionB.id})).session.name,'renamed');
  checks.push('Durable queued intent, replay protection, restart and desktop session response contract');
  const stateAfter = (await request('getState',{projectRoot:second})).state;
  const db = new DatabaseSync(path.join(stateAfter.workspace.project_data_dir,'conversations.sqlite3'),{readOnly:true});
  assert.equal(db.prepare('PRAGMA user_version').get().user_version,7);
  db.close();
  if (serverError) throw serverError;
  success = true;
  fs.writeFileSync(path.join(root,'report.json'),JSON.stringify({passed:true,scope:'actual Electron bridge with one native Rust process; no renderer or external model acceptance',
    identity,sha256:crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'),checks},null,2)+'\n');
  console.log(JSON.stringify({passed:true,checks:checks.length,report:path.join(root,'report.json')}));
} finally {
  await bridge.stop('Desktop bridge verification finished',true);
  for (const response of held) response.destroy();
  server.closeAllConnections();
  await new Promise(resolve=>server.close(resolve));
  if (!success) fs.writeFileSync(path.join(root,'failed.json'),JSON.stringify({passed:false,checks,serverError:String(serverError || '')},null,2));
}
