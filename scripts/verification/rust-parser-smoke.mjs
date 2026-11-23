import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawnSync} from 'node:child_process';

const executable=path.resolve(process.argv[2] || `ReverieCli-rs/target/release/reverie${process.platform==='win32'?'.exe':''}`);
const output=path.resolve(process.argv[3] || '.runtime/rust-3.0/parser-smoke');
fs.mkdirSync(output,{recursive:true});
const root=fs.mkdtempSync(path.join(output,'case-'));
const project=path.join(root,'project');fs.mkdirSync(project);
const fixtures=[
  ['c.c','int helper() { return 1; }\nint save() { return helper(); }\n','c.save','c','FUNCTION'],
  ['cpp.cpp','namespace game { class Ship { public: int save() { return 1; } }; }\n','cpp.game.Ship.save','cpp','METHOD'],
  ['sharp.cs','namespace Game { class Ship { public int Save() { return 1; } } }\n','sharp.Game.Ship.Save','csharp','METHOD'],
  ['logic.go','package game\n// Save current progress.\nfunc Save() int { return 1 }\n','logic.Save','go','FUNCTION'],
  ['Ship.java','class Ship { int save() { return 1; } }\n','Ship.Ship.save','java','METHOD'],
  ['zig_main.zig','pub const limit: u32 = 3;\npub fn Save() u32 { return limit; }\n','zig_main.Save','zig','FUNCTION'],
  ['page.html','<button id="save-game">Save</button>\n','page.save-game','html','PROPERTY'],
  ['style.css','.game, #save:hover { color: red; }\n','style.#save:hover','css','PROPERTY'],
  ['logic.lua','local Ship = {}\nfunction Ship:save() return 1 end\n','logic.Ship.save','lua','METHOD'],
  ['ship.gd','class_name Ship\nextends Node\nfunc save():\n    return 1\n','ship.Ship.save','gdscript','METHOD'],
];
for(const [name,content] of fixtures) fs.writeFileSync(path.join(project,name),content);
const database=path.join(root,'context.sqlite3');
const checks=[];
function run(operation,args) {
  const result=spawnSync(executable,['--context-engine',operation,...args],{encoding:'utf8',timeout:15000,windowsHide:true});
  assert.ifError(result.error);assert.equal(result.status,0,result.stderr);
  return JSON.parse(result.stdout);
}
try {
  assert.equal(run('index',[project,database]).indexed,fixtures.length);
  for(const [filename,source,symbol,language,kind] of fixtures) {
    const result=run('lookup',[database,JSON.stringify({query_type:'symbol',query:symbol})]);
    assert.equal(result.symbol.file_path,filename);assert.equal(result.symbol.language,language);assert.equal(result.symbol.kind,kind);
    const hit=result.evidence[0];assert(source.includes(hit.content));assert(hit.end_line-hit.start_line<72);
    assert.equal(hit.content_hash,crypto.createHash('sha256').update(source).digest('hex'));
    checks.push(language);
  }
  const dependencies=run('lookup',[database,JSON.stringify({query_type:'dependencies',query:'c.save'})]);
  assert(dependencies.references.some(edge=>edge.to_symbol==='c.helper'&&edge.resolution==='lexical'));
  assert.equal(run('index',[project,database]).indexed,0);
  const report={schema:'reverie.rust-parser-smoke.v1',passed:true,verified_at:new Date().toISOString(),executable_sha256:crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'),root,checks,scope:'Actual native CLI parsing of ten added languages, source identities and one lexical dependency; complete grammar constructs, import/type resolution and performance are not established.'};
  const reportPath=path.join(root,'report.json');fs.writeFileSync(reportPath,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({passed:true,checks:checks.length+3,report:reportPath}));
} catch(error) {
  fs.writeFileSync(path.join(root,'failure.json'),JSON.stringify({passed:false,checks,error:String(error),stack:error.stack},null,2)+'\n');throw error;
}
