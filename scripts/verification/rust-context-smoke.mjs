import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {startBridge} from './rust-bridge-client.mjs';

const executable=path.resolve(process.argv[2] || `ReverieCli-rs/target/release/reverie${process.platform==='win32'?'.exe':''}`);
const output=path.resolve(process.argv[3] || '.runtime/rust-3.0/context-smoke');fs.mkdirSync(output,{recursive:true});
const root=fs.mkdtempSync(path.join(output,'case-'));
const project=path.join(root,'project');fs.mkdirSync(path.join(project,'ignored'),{recursive:true});
fs.writeFileSync(path.join(project,'.gitignore'),'ignored/\n!ignored/keep.rs\n');
fs.writeFileSync(path.join(project,'ignored/keep.rs'),'pub fn excluded_marker() {}\n');
fs.writeFileSync(path.join(project,'game.rs'),'pub fn save_game() {\n helper();\n println!("save_marker");\n}\nfn helper() {}\n');
fs.writeFileSync(path.join(project,'chapter.txt'),Array.from({length:130},(_,i)=>i===92?'飞船失去动力，必须修复燃料阀门。':`line ${i}`).join('\n'));
const database=path.join(root,'context.sqlite3');
const checks=[];
function run(operation,args) {
  const result=spawnSync(executable,['--context-engine',operation,...args],{encoding:'utf8',timeout:15000,windowsHide:true});
  assert.ifError(result.error);assert.equal(result.status,0,result.stderr);checks.push({operation,exit_code:result.status});return JSON.parse(result.stdout);
}
assert.equal(run('index',[project,database]).scanned,2);
assert.equal(run('index',[project,database]).indexed,0);
const code=run('search',[database,'save_game']);assert(code.some(hit=>hit.content.includes('save_game')));
const narrative=run('search',[database,'飞船失去动力']);assert(narrative.some(hit=>hit.content.includes('飞船失去动力')));
for(const hit of [...code,...narrative]) {assert(hit.end_line-hit.start_line<72);assert.match(hit.content_hash,/^[a-f0-9]{64}$/);}
assert.deepEqual(run('paths',[database,'ignored/']),[]);
fs.renameSync(path.join(project,'game.rs'),path.join(project,'renamed.rs'));
assert.equal(run('index',[project,database]).removed,1);
assert.deepEqual(run('paths',[database,'renamed']),['renamed.rs']);
assert.equal(run('status',[database]).ready,true);
const lookup=request=>run('lookup',[database,JSON.stringify(request)]);
const symbol=lookup({query_type:'symbol',query:'renamed.save_game'});
assert.equal(symbol.symbol.file_path,'renamed.rs');assert.equal(symbol.symbol.language,'rust');
assert.equal(symbol.evidence[0].start_line,1);assert.equal(symbol.evidence[0].content_hash.length,64);
const dependencies=lookup({query_type:'dependencies',query:'save_game',direction:'outgoing'});
assert(dependencies.references.some(edge=>edge.to_symbol==='renamed.helper'&&edge.resolution==='lexical'));
assert.equal(lookup({query_type:'outline',query:'./renamed.rs'}).evidence.length,0);
assert.equal(lookup({query_type:'file',query:'./chapter.txt'}).evidence[0].end_line,72);
const task=lookup({query_type:'task',query:'飞船失去动力',max_tokens:16000});
assert.equal(task.max_tokens,16000);assert.equal(task.components.semantic,false);assert(task.evidence.length>0);
const escaped=spawnSync(executable,['--context-engine','lookup',database,JSON.stringify({query_type:'file',query:'../context.sqlite3'})],{encoding:'utf8',timeout:15000,windowsHide:true});
assert.ifError(escaped.error);assert.notEqual(escaped.status,0);assert.match(escaped.stderr,/traverse outside/);checks.push({operation:'lookup traversal rejection',exit_code:escaped.status});
let bridge=startBridge(executable,project,path.join(root,'application'));
try {
  await bridge.ready;
  const indexed=await bridge.request('indexWorkspace');assert.equal(indexed.type,'workspace.indexed');assert.equal(indexed.workspace.index_ready,true);
  const query=await bridge.request('queryContext',{query:'save_game',limit:10});assert.equal(query.type,'context.results');assert(query.results.length>0);
  fs.writeFileSync(path.join(project,'renamed.rs'),'pub fn new_state() {}\n');
  assert.equal((await bridge.request('queryContext',{query:'save_game'})).type,'error');
  assert.equal((await bridge.request('indexWorkspace')).result.indexed,1);
  assert.equal((await bridge.request('queryContext',{query:'new_state'})).results[0].file_path,'renamed.rs');
  await bridge.request('shutdown');assert.equal((await bridge.closed).code,0);
  bridge=startBridge(executable,project,path.join(root,'application'));await bridge.ready;
  const resumed=await bridge.request('initialize',{projectRoot:project});assert.equal(resumed.state.workspace.context_engine.ready,true);
  await bridge.request('shutdown');assert.equal((await bridge.closed).code,0);
  const report={schema:'reverie.rust-context-smoke.v1',passed:true,verified_at:new Date().toISOString(),executable_sha256:crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'),root,checks,sdk_checks:8,scope:'Actual CLI and SDK indexing, Git parent exclusion, lexical/CJK evidence, bounded fragments, stale source rejection, incremental rename and restart. Semantic models, full parser matrix and performance gates are unverified.'};
  fs.writeFileSync(path.join(root,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({passed:true,checks:checks.length+8,report:path.join(root,'report.json')}));
}finally {if(bridge.child.exitCode===null){bridge.child.stdin.end();await bridge.closed;}}
