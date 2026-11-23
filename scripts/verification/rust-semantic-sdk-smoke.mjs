import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import {setTimeout as delay} from 'node:timers/promises';
import {startBridge} from './rust-bridge-client.mjs';

const [exeArgument,bundleArgument,digest,outputArgument]=process.argv.slice(2);
if(!exeArgument||!bundleArgument||!digest)throw Error('Usage: rust-semantic-sdk-smoke.mjs <actual-executable> <real-bundle> <manifest-sha256> [output]');
const executable=path.resolve(exeArgument),bundle=path.resolve(bundleArgument);
const output=path.resolve(outputArgument||'.runtime/rust-3.0/semantic-sdk-smoke');fs.mkdirSync(output,{recursive:true});
const root=fs.mkdtempSync(path.join(output,'case-')),project=path.join(root,'workspace'),appRoot=path.join(root,'application');
fs.mkdirSync(project);fs.mkdirSync(path.join(appRoot,'.reverie'),{recursive:true});
fs.writeFileSync(path.join(project,'saving.md'),'# 恢复冒险进度\n退出之前把玩家进度和背包写入本地文件。下次启动读取文件，恢复上次的状态。\n');
fs.writeFileSync(path.join(project,'menu.md'),'# 界面外观\n菜单背景使用蓝色渐变，按钮文字为白色。\n');
const question='How can I restore player progress after closing the game?';
const checks=[],requests=[];
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
let bridge,held,serverFailure;
process.env.NO_PROXY=[process.env.NO_PROXY,'127.0.0.1','localhost'].filter(Boolean).join(',');
function finish(response,content) {response.writeHead(200,{'content-type':'application/json'});response.end(JSON.stringify({choices:[{message:{role:'assistant',content},finish_reason:'stop'}]}));}
const server=http.createServer(async(request,response)=>{
  try {
    let text='';for await(const bytes of request)text+=bytes;const body=JSON.parse(text);requests.push(body);
    const prompt=body.messages.findLast(message=>message.role==='user').content;
    if(body.messages.at(-1).role==='tool') {finish(response,body.messages.at(-1).content);return;}
    if(prompt.startsWith('LEASE:')) {held={response,body};return;}
    if(prompt.startsWith('TOOL:')) {response.writeHead(200,{'content-type':'application/json'});response.end(JSON.stringify({choices:[{message:{role:'assistant',content:null,tool_calls:[{id:'semantic-task',type:'function',function:{name:'codebase-retrieval',arguments:JSON.stringify({query_type:'task',query:question,max_symbols:10})}}]},finish_reason:'tool_calls'}]}));return;}
    finish(response,'ACTUAL_SDK_REPLY');
  }catch(error){serverFailure=error;response.destroy(error);}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
fs.writeFileSync(path.join(appRoot,'.reverie/config.json'),JSON.stringify({models:[{model:'semantic-fixture',profile_id:'semantic-profile',provider:'openai-chat',base_url:`http://127.0.0.1:${server.address().port}/v1`,api_key:'fixture-only'}],active_model_source:'standard',active_model_index:0,mode:'reverie',auto_index:true,stream_responses:false,security:{permission_level:'full_control',permission_mode:'default'}}));
const activation=path.join(appRoot,'.reverie/resources/semantic/active.json');
function event(operation,phase) {return bridge.events.find(message=>message.event?.operation_id===operation&&message.event?.phase===phase);}
async function until(predicate,timeout=30000) {const end=Date.now()+timeout;while(Date.now()<end){if(serverFailure)throw serverFailure;if(predicate())return;await delay(5);}throw Error('Native semantic operation did not reach its observed boundary.');}
async function request(action,payload={},type='context.resources') {const response=await bridge.request(action,payload,120000);assert.equal(response.type,type,JSON.stringify(response));return response;}
function makeCandidate(name,version,broken=false) {
  const target=path.join(root,name);fs.mkdirSync(target);
  const manifest=JSON.parse(fs.readFileSync(path.join(bundle,'manifest.json'),'utf8'));
  manifest.version=version;manifest.provenance.fixture={scope:broken?'Invalid model-health candidate':'Same real weights with a distinct manifest identity'};
  for(const name of Object.keys(manifest.files)) {
    const output=path.join(target,name);fs.mkdirSync(path.dirname(output),{recursive:true});
    if(broken&&name.endsWith('model.onnx')) {fs.writeFileSync(output,'not-an-onnx-model');manifest.files[name]={bytes:Buffer.byteLength('not-an-onnx-model'),sha256:hash('not-an-onnx-model')};}
    else fs.copyFileSync(path.join(bundle,name),output);
  }
  const bytes=JSON.stringify(manifest,null,2)+'\n';fs.writeFileSync(path.join(target,'manifest.json'),bytes);
  return {directory:target,manifestSha256:hash(bytes)};
}
try {
  bridge=startBridge(executable,project,appRoot);await bridge.ready;
  const empty=await request('getSemanticResources');assert.equal(empty.semantic.available,false);
  const installing=bridge.request('installSemanticResources',{directory:bundle,manifestSha256:digest,operationId:'install-initial'},120000);
  await until(()=>event('install-initial','working'));
  const live=await request('getState',{},'state');assert.equal(live.state.core.implementation,'rust');
  assert(!bridge.events.some(message=>message.operation_id==='install-initial'&&message.type==='context.resources'));
  const installed=await installing;assert.equal(installed.type,'context.resources');assert.equal(installed.activated,true);assert.equal(installed.semantic.active.manifest_sha256,digest);
  assert.deepEqual(installed.health.vector_dimensions,[384,384]);
  assert.equal(installed.semantic.models.embedding_loaded,false);
  const initialActivation=fs.readFileSync(activation);
  const invalidRevision=await bridge.request('disableSemanticResources',{expectedRevision:'0'});
  assert.equal(invalidRevision.type,'error');assert.match(invalidRevision.error,/invalid type/i);
  assert.deepEqual(fs.readFileSync(activation),initialActivation);
  checks.push('Install actual local models after health and atomic activation while SDK control stays responsive');
  const indexed=await request('indexSemanticWorkspace',{},'context.semantic-indexed');const originalGeneration=indexed.context_engine.semantic_index.generation;
  const query=await request('queryContext',{query:question,strategy:'hybrid'},'context.results');
  assert.equal(query.results[0].file_path,'saving.md');assert.equal(query.retrieval.strategy,'hybrid');assert.equal(query.retrieval.manifest_sha256,digest);
  const basic=await request('queryContext',{query:'恢复',strategy:'basic'},'context.results');assert.equal(basic.retrieval.strategy,'basic');
  checks.push('Run shared SDK structural, vector, fusion and neural retrieval with explicit basic selection');
  const session=(await request('createSession',{name:'Semantic tool checks'},'session.created')).session;
  const tool=await request('runPrompt',{sessionId:session.id,prompt:`TOOL:${question}`,stream:false},'prompt.result');
  assert.equal(tool.result.success,true);const result=JSON.parse(tool.result.output_text);const task=JSON.parse(result.output);assert.equal(task.components.semantic,true);assert(task.evidence.some(hit=>hit.file_path==='saving.md'));
  checks.push('Supply actual neural evidence to the Agent and its explicit codebase task tool');
  const failed=makeCandidate('invalid-models','invalid-model-health',true);const previousBytes=fs.readFileSync(activation);
  const rejected=await bridge.request('installSemanticResources',failed,120000);assert.equal(rejected.type,'error');assert.match(rejected.error,/onnx|protobuf|session/i);
  assert.deepEqual(fs.readFileSync(activation),previousBytes);
  checks.push('Reject a hashed but invalid ONNX candidate without changing the prior activation');
  for(let i=0;i<100;i++)fs.writeFileSync(path.join(project,`new-note-${i}.txt`),`气象记录 ${i}：晴天、低风速、观测站状态正常。\n`);
  const cancelling=bridge.request('indexSemanticWorkspace',{operationId:'cancel-generation'},120000);
  await until(()=>event('cancel-generation','embedding'));
  await request('stopContextOperation',{operationId:'cancel-generation'},'context.control');
  assert.equal((await cancelling).type,'error');
  const afterCancel=await request('getContextStatus',{},'context.status');assert.equal(afterCancel.context_engine.semantic_index.generation,originalGeneration);
  checks.push('Cancel a real embedding update and keep the previous committed generation');
  const holding=bridge.request('runPrompt',{sessionId:session.id,prompt:`LEASE:${question}`,stream:false,runId:'leased-model-run'},120000);await until(()=>held);
  const replacement=makeCandidate('replacement-bundle','same-weights-resource-update');
  const updated=await request('installSemanticResources',replacement);
  assert.equal(updated.semantic.active.manifest_sha256,replacement.manifestSha256);
  assert.equal(updated.semantic.previous.manifest_sha256,digest);
  assert.equal((await bridge.request('removeSemanticResources',{manifestSha256:digest,confirmed:true},120000)).type,'error');
  finish(held.response,'LEASED_MODEL_REPLY');held=null;
  const completed=await holding;assert.equal(completed.result.success,true);assert(completed.events.some(message=>message.event?.type==='context.retrieved'&&message.event.retrieval.manifest_sha256===digest));
  assert(requests.some(body=>body.messages[0].content.includes('sha256:')&&body.messages[0].content.includes('恢复冒险进度')));
  checks.push('Pin the old model resource for an active Agent while a healthy replacement becomes active');
  const rolledBack=await request('rollbackSemanticResources');assert.equal(rolledBack.semantic.active.manifest_sha256,digest);
  await request('selectSemanticResources',{manifestSha256:replacement.manifestSha256});
  checks.push('Restore the previous healthy resource and select a verified installed version');
  await request('unloadSemanticModels');
  assert.equal((await bridge.request('removeSemanticResources',{manifestSha256:digest})).type,'error');
  const pending=await request('removeSemanticResources',{manifestSha256:digest,confirmed:true});assert.equal(pending.pending_restart,true);assert.equal(pending.removed,false);
  checks.push('Require explicit removal and retain the mapped ORT runtime until process restart');
  const firstEvents=bridge.events.slice();await request('shutdown',{},'shutdown');assert.equal((await bridge.closed).code,0);
  bridge=startBridge(executable,project,appRoot);await bridge.ready;
  const restored=await request('getSemanticResources');assert.equal(restored.semantic.active.manifest_sha256,replacement.manifestSha256);assert.equal(restored.semantic.models.embedding_loaded,false);
  const removed=await request('removeSemanticResources',{manifestSha256:digest,confirmed:true});assert.equal(removed.removed,true);
  assert(!fs.existsSync(path.join(appRoot,'.reverie/resources/semantic/versions',digest)));
  checks.push('Resume the selected resource lazily and complete managed removal after restart');
  await request('removeSemanticResources',{manifestSha256:replacement.manifestSha256,confirmed:true});
  fs.writeFileSync(activation,'{"schema":"damaged"}');
  assert.equal((await request('getSemanticResources')).semantic.status,'error');
  const unaffected=await request('queryContext',{query:'恢复',strategy:'basic'},'context.results');assert(unaffected.results.length>0);
  checks.push('Preserve a damaged resource record while basic retrieval remains available');
  fs.writeFileSync(path.join(root,'sdk-events.json'),JSON.stringify([...firstEvents,...bridge.events],null,2)+'\n');
  const report={schema:'reverie.rust-semantic-sdk-smoke.v1',passed:true,verified_at:new Date().toISOString(),executable_sha256:hash(fs.readFileSync(executable)),manifest_sha256:digest,checks,root,
    scope:'Actual native Windows CPU resources, local ONNX health, SDK/Agent retrieval, activation, task leases, cancellation and managed removal. The HTTP model is a loopback protocol fixture; this is not external model quality, frozen Recall, warmed p95, full update failures or four-platform inference acceptance.'};
  fs.writeFileSync(path.join(root,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({passed:true,checks:checks.length,report:path.join(root,'report.json')}));
}catch(error){if(bridge)fs.writeFileSync(path.join(root,'sdk-events.json'),JSON.stringify(bridge.events,null,2)+'\n');fs.writeFileSync(path.join(root,'failure.json'),JSON.stringify({checks,error:String(error)},null,2)+'\n');throw error;}
finally {if(held)held.response.destroy();if(bridge&&bridge.child.exitCode===null){bridge.child.stdin.end();await bridge.closed;}server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
