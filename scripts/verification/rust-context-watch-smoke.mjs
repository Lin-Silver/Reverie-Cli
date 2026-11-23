import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {setTimeout as delay} from 'node:timers/promises';
import {startBridge} from './rust-bridge-client.mjs';

const [exeArgument,bundleArgument,digest,outputArgument]=process.argv.slice(2);
if(!exeArgument||!bundleArgument||!digest)throw Error('Usage: rust-context-watch-smoke.mjs <actual-executable> <real-bundle> <manifest-sha256> [output]');
const executable=path.resolve(exeArgument),bundle=path.resolve(bundleArgument);
const output=path.resolve(outputArgument||'.runtime/rust-3.0/context-watch-smoke');fs.mkdirSync(output,{recursive:true});
const root=fs.mkdtempSync(path.join(output,'case-')),project=path.join(root,'workspace'),appRoot=path.join(root,'application');
fs.mkdirSync(project);fs.mkdirSync(path.join(appRoot,'.reverie'),{recursive:true});
fs.writeFileSync(path.join(appRoot,'.reverie/config.json'),JSON.stringify({mode:'reverie',auto_index:false}));
const source=path.join(project,'saving.md');fs.writeFileSync(source,'# 恢复冒险进度\n退出之前把玩家进度和背包写入本地文件。下次启动读取文件，恢复上次的状态。\n');
fs.writeFileSync(path.join(project,'menu.md'),'# 界面外观\n菜单背景使用蓝色渐变，按钮文字为白色。\n');
const question='How can I restore player progress after closing the game?';
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const checks=[],events=[];let bridge;
async function request(action,payload={},type) {const response=await bridge.request(action,payload,120000);if(type)assert.equal(response.type,type,JSON.stringify(response));return response;}
async function status() {return (await request('getContextStatus',{},'context.status')).context_engine;}
async function until(predicate,timeout=45000) {const end=Date.now()+timeout;let current;while(Date.now()<end){current=await status();if(predicate(current))return current;await delay(10);}throw Error(`Native watcher did not reach its boundary: ${JSON.stringify(current)}`);}
async function watch(enabled) {await request('setSetting',{key:'auto_index',value:enabled},'setting.updated');}
async function close() {events.push(...bridge.events);await request('shutdown',{},'shutdown');assert.equal((await bridge.closed).code,0);bridge=null;}
try {
  bridge=startBridge(executable,project,appRoot);await bridge.ready;
  await request('installSemanticResources',{directory:bundle,manifestSha256:digest},'context.resources');
  const initial=await request('indexSemanticWorkspace',{},'context.semantic-indexed');
  assert.equal(initial.result.index.ann.algorithm,'hnsw-cosine-f32');
  assert(!initial.context_engine.watcher?.enabled);
  await watch(true);
  const ready=await until(state=>state.watcher?.status==='watching'&&state.watcher.semantic_revision===state.revision);
  assert.equal(ready.semantic_index.generation,initial.result.index.generation);
  checks.push('Start native background observation without rebuilding the complete existing semantic generation');
  fs.appendFileSync(source,'新规则要求退出前保存钥匙数量。\n');
  const changed=await until(state=>state.watcher?.status==='watching'&&state.revision>ready.revision&&state.watcher.semantic_revision===state.revision);
  const query=await request('queryContext',{query:question,strategy:'hybrid'},'context.results');
  assert.equal(query.results[0].file_path,'saving.md');assert(query.results[0].content.includes('钥匙数量'));
  assert.equal(query.results[0].content_hash,hash(fs.readFileSync(source)));
  assert(changed.semantic_index.generation>ready.semantic_index.generation);
  assert(bridge.events.some(message=>message.id===undefined&&message.event?.automatic===true&&message.event.phase==='embedding'));
  checks.push('Observe a real file write, publish current hashed neural evidence, and send background events without a finished request identity');
  await watch(false);await until(state=>state.watcher?.enabled===false&&!state.watcher.operation);
  const paused=await status();fs.appendFileSync(source,'读档后恢复玩家当前关卡。\n');await delay(600);
  assert.equal((await status()).revision,paused.revision);
  await watch(true);
  const resumed=await until(state=>state.watcher?.status==='watching'&&state.revision>paused.revision&&state.watcher.semantic_revision===state.revision);
  assert((await request('queryContext',{query:question,strategy:'hybrid'},'context.results')).results[0].content.includes('当前关卡'));
  checks.push('Persist pause and resume through the shared auto_index setting and catch up changes made while paused');
  for(let i=0;i<100;i++)fs.writeFileSync(path.join(project,`note-${i}.txt`),`气象观测 ${i}：晴天、低风速、观测站状态正常。\n`);
  const embedding=await until(state=>state.watcher?.operation?.phase==='embedding');
  const operation=embedding.watcher.operation.operation_id;
  assert.equal((await request('stopContextOperation',{operationId:operation,projectRoot:appRoot})).type,'error');
  await request('stopContextOperation',{operationId:operation,projectRoot:project},'context.control');
  await watch(false);await until(state=>!state.watcher?.enabled&&!state.watcher?.operation);
  assert.equal((await status()).semantic_index.generation,resumed.semantic_index.generation);
  checks.push('Scope cancellation to its project and preserve the previous complete HNSW generation');
  const state=await request('getState',{},'state');
  const semanticPath=path.join(state.state.workspace.project_data_dir,'context/rust-3.0.semantic.sqlite3');
  await close();
  bridge=startBridge(executable,project,appRoot);await bridge.ready;
  await request('initialize',{projectRoot:project},'state');
  assert.notEqual((await status()).watcher?.enabled,true);
  assert.equal((await request('listSettings',{},'settings')).settings.items.find(item=>item.key==='auto_index').value,false);
  await watch(true);await until(state=>state.watcher?.status==='watching'&&state.watcher.semantic_revision===state.revision);
  const beforeDelete=await status();
  fs.unlinkSync(path.join(project,'menu.md'));
  await until(state=>state.watcher?.status==='watching'&&state.revision>beforeDelete.revision&&state.watcher.semantic_revision===state.revision);
  assert(!(await request('queryContext',{query:'menu appearance',strategy:'hybrid'},'context.results')).results.some(hit=>hit.file_path==='menu.md'));
  checks.push('Close and restart the actual process, resume background indexing, and remove deleted evidence');
  await watch(false);await until(state=>!state.watcher?.enabled&&!state.watcher?.operation);await close();
  const database=new DatabaseSync(semanticPath);database.exec('PRAGMA user_version=88');database.close();
  const damaged=fs.readFileSync(semanticPath);
  bridge=startBridge(executable,project,appRoot);await bridge.ready;
  await request('initialize',{projectRoot:project},'state');
  const unavailable=await status();assert.equal(unavailable.ready,true);assert.match(unavailable.semantic_index_error,/incompatible/i);
  assert((await request('queryContext',{query:'恢复',strategy:'basic'},'context.results')).results.length>0);
  assert.deepEqual(fs.readFileSync(semanticPath),damaged);
  checks.push('Preserve an incompatible semantic database and keep current basic evidence available');
  await close();
  fs.writeFileSync(path.join(root,'sdk-events.json'),JSON.stringify(events,null,2)+'\n');
  const report={schema:'reverie.rust-context-watch-smoke.v1',passed:true,verified_at:new Date().toISOString(),executable_sha256:hash(fs.readFileSync(executable)),manifest_sha256:digest,checks,root,scope:'Actual native filesystem events, Windows CPU E5/BGE/HNSW, SDK cancellation, pause, restart and derived-index isolation. Not full watcher platforms/network filesystems, performance, model quality, or all concurrency faults.'};
  fs.writeFileSync(path.join(root,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({passed:true,checks:checks.length,report:path.join(root,'report.json')}));
}catch(error){fs.writeFileSync(path.join(root,'failure.json'),JSON.stringify({checks,error:String(error)},null,2)+'\n');throw error;}
finally{if(bridge){fs.writeFileSync(path.join(root,'sdk-events.json'),JSON.stringify([...events,...bridge.events],null,2)+'\n');if(bridge.child.exitCode===null){bridge.child.stdin.end();await bridge.closed;}}}
