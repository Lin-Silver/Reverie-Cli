import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawnSync} from 'node:child_process';

const executable=path.resolve(process.argv[2]||`ReverieCli-rs/target/release/reverie${process.platform==='win32'?'.exe':''}`);
const output=path.resolve(process.argv[3]||'.runtime/rust-3.0/resources-smoke');
fs.mkdirSync(output,{recursive:true});
const root=fs.mkdtempSync(path.join(output,'case-'));
const source=path.join(root,'source'); fs.mkdirSync(source);
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const files={};
function write(name,bytes) {
  fs.mkdirSync(path.dirname(path.join(source,name)),{recursive:true});
  fs.writeFileSync(path.join(source,name),bytes);
  files[name]={bytes:Buffer.byteLength(bytes),sha256:hash(bytes)};
}
const binary=Buffer.alloc(128);
if(process.platform==='win32') { binary.write('MZ'); binary.writeUInt32LE(64,60); binary.write('PE\0\0',64); binary.writeUInt16LE(0x8664,68); }
else if(process.platform==='linux') { Buffer.from([0x7f,0x45,0x4c,0x46,2,1]).copy(binary); binary.writeUInt16LE(62,18); }
else { Buffer.from([0xcf,0xfa,0xed,0xfe]).copy(binary); binary.writeUInt32LE(process.arch==='arm64'?0x0100000c:0x01000007,4); }
write('runtime/library',binary); write('LICENSE','Resource validation fixture; no production license or model.');
for(const role of ['embedding','reranker']) for(const file of ['model.onnx','tokenizer.json','config.json','special_tokens_map.json','tokenizer_config.json']) write(`${role}/${file}`,'fixture bytes');
const model=(id,revision,role)=>({id,revision,onnx:`${role}/model.onnx`,tokenizer_directory:role,max_length:512,precision:'fp32'});
const manifest={schema:'reverie.semantic-resource.v1',version:'fixture-v1',platform:{win32:'windows',linux:'linux',darwin:'macos'}[process.platform],architecture:{x64:'x86_64',arm64:'aarch64'}[process.arch],dimensions:384,
  runtime:{version:'1.31.0',api_version:24,library:'runtime/library'},embedding:model('intfloat/multilingual-e5-small','614241f622f53c4eeff9890bdc4f31cfecc418b3','embedding'),
  reranker:model('BAAI/bge-reranker-base','2cfc18c9415c912f9d8155881c133215df768a70','reranker'),files,licenses:['LICENSE'],provenance:{purpose:'Actual CLI resource-validation fixture, not neural inference'}};
const bytes=JSON.stringify(manifest,null,2); fs.writeFileSync(path.join(source,'manifest.json'),bytes);
const digest=hash(bytes); const store=path.join(root,'store'); const checks=[];
function run(args,success=true) {
  const result=spawnSync(executable,['--context-engine',...args],{encoding:'utf8',timeout:15000,windowsHide:true});
  assert.ifError(result.error); assert.equal(result.status,success?0:1,result.stderr);
  return success?JSON.parse(result.stdout):result.stderr;
}
try {
  const verified=run(['resources-verify',source,digest]); assert.equal(verified.activated,false);checks.push('Verify manifest, actual file bytes and native architecture');
  const staged=run(['resources-stage',store,source,digest]);assert.equal(staged.activated,false);assert(!fs.existsSync(path.join(store,'active.json')));checks.push('Stage without activating or running any candidate');
  run(['resources-verify',source,'0'.repeat(64)],false);checks.push('Reject incorrect manifest identity');
  fs.writeFileSync(path.join(staged.directory,'embedding/model.onnx'),'tampered bytes');run(['resources-stage',store,source,digest],false);checks.push('Reject corrupted previously staged content');
  const report={schema:'reverie.rust-resources-smoke.v1',passed:true,verified_at:new Date().toISOString(),executable_sha256:hash(fs.readFileSync(executable)),checks,root,
    scope:'Actual native CLI verification and immutable staging with fixture assets and native-format headers; not real ORT loading, model inference, digital signatures or activation health.'};
  const reportPath=path.join(root,'report.json');fs.writeFileSync(reportPath,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({passed:true,checks:checks.length,report:reportPath}));
} catch(error) {fs.writeFileSync(path.join(root,'failure.json'),JSON.stringify({checks,error:String(error)},null,2)+'\n');throw error;}
