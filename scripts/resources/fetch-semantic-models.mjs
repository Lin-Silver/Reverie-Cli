// Resource production only. The first-party application never invokes Python or downloads models implicitly.
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {Readable} from 'node:stream';
import {pipeline} from 'node:stream/promises';

const [directoryArgument,ortPackageArgument,ortExtractedArgument]=process.argv.slice(2);
if(!directoryArgument||!ortPackageArgument||!ortExtractedArgument) throw Error('Usage: node scripts/resources/fetch-semantic-models.mjs <new-output-directory> <ORT-1.31.0.nupkg> <extracted-ORT-directory>');
const directory=path.resolve(directoryArgument), ortPackage=path.resolve(ortPackageArgument), extracted=path.resolve(ortExtractedArgument);
const packageDigest='7e35fdb4f5adb62f01e60798e2e5ed05108f5fbbe1cca03fbcc37903cf7c5e3b';
async function hash(file,algorithm='sha256',gitBlob=false) {
  const digest=crypto.createHash(algorithm);if(gitBlob) digest.update(`blob ${(await fsp.stat(file)).size}\0`);
  for await(const bytes of fs.createReadStream(file)) digest.update(bytes);
  return digest.digest('hex');
}
if(await hash(ortPackage)!==packageDigest) throw Error('ORT package SHA-256 mismatch');
const platform={win32:'windows',linux:'linux',darwin:'macos'}[process.platform];
const architecture={x64:'x86_64',arm64:'aarch64'}[process.arch];
const runtimeId={win32:{x64:'win-x64'},linux:{x64:'linux-x64'},darwin:{arm64:'osx-arm64',x64:'osx-x64'}}[process.platform]?.[process.arch];
if(!platform||!architecture||!runtimeId) throw Error('Unsupported target platform');
const native=path.join(extracted,'runtimes',runtimeId,'native');
if(!fs.existsSync(native)) throw Error('The fixed ORT package has no native files for this target. Intel Mac requires the separately verified source build.');
if(fs.existsSync(path.join(directory,'manifest.json'))) throw Error('Output already contains a completed manifest; select a new output directory.');
await fsp.mkdir(directory,{recursive:true});
const files={}; const downloads=[];
async function record(name) {const file=path.join(directory,name);files[name]={bytes:(await fsp.stat(file)).size,sha256:await hash(file)};}
async function download(repository,revision,entry,target) {
  const destination=path.join(directory,target);await fsp.mkdir(path.dirname(destination),{recursive:true});
  if(!fs.existsSync(destination)) {
    const url=`https://huggingface.co/${repository}/resolve/${revision}/${entry.path}?download=true`;
    console.log(JSON.stringify({downloading:target,expected_bytes:entry.size}));
    const temporary=`${destination}.part-${crypto.randomUUID()}`;
    if(entry.size>=64*1024*1024) {
      const prefix=path.basename(destination)+'.part-';
      const previous=(await fsp.readdir(path.dirname(destination),{withFileTypes:true})).filter(file=>file.isFile()&&file.name.startsWith(prefix));
      const partials=await Promise.all(previous.map(async file=>({file:path.join(path.dirname(destination),file.name),bytes:(await fsp.stat(path.join(path.dirname(destination),file.name))).size})));
      const seed=partials.filter(file=>file.bytes>0&&file.bytes<entry.size).sort((a,b)=>b.bytes-a.bytes)[0];
      if(seed) await fsp.copyFile(seed.file,temporary,fs.constants.COPYFILE_EXCL); else await fsp.writeFile(temporary,'',{flag:'wx'});
      let start=(await fsp.stat(temporary)).size;
      while(start<entry.size) {
        const end=Math.min(entry.size-1,start+8*1024*1024-1);
        const response=await fetch(`${url}&reverie_range=${start}-${end}`,{headers:{Range:`bytes=${start}-${end}`,'Accept-Encoding':'identity'},signal:AbortSignal.timeout(120000)});
        if(response.status!==206||response.headers.get('content-range')!==`bytes ${start}-${end}/${entry.size}`||!response.body) throw Error(`Range identity mismatch for ${entry.path} at ${start}`);
        await pipeline(Readable.fromWeb(response.body),fs.createWriteStream(temporary,{flags:'a'}));
        if((await fsp.stat(temporary)).size!==end+1) throw Error(`Range length mismatch for ${entry.path}`);
        start=end+1;console.log(JSON.stringify({received:target,bytes:start,total:entry.size}));
      }
    } else {
      const response=await fetch(url,{signal:AbortSignal.timeout(120000)});if(!response.ok||!response.body) throw Error(`Download ${entry.path}: HTTP ${response.status}`);
      await pipeline(Readable.fromWeb(response.body),fs.createWriteStream(temporary,{flags:'wx'}));
    }
    if((await fsp.stat(temporary)).size!==entry.size) throw Error(`Download size mismatch: ${entry.path}`);
    if(entry.lfs ? await hash(temporary)!==entry.lfs.oid : await hash(temporary,'sha1',true)!==entry.oid) throw Error(`Fixed source identity mismatch: ${entry.path}`);
    await fsp.rename(temporary,destination);
  }
  await record(target);
  if(files[target].bytes!==entry.size||(entry.lfs ? files[target].sha256!==entry.lfs.oid : await hash(destination,'sha1',true)!==entry.oid)) throw Error(`Existing download identity mismatch: ${entry.path}`);
  downloads.push({repository,revision,source:entry.path,target,git_blob:entry.oid,lfs_sha256:entry.lfs?.oid??null,...files[target]});
  console.log(JSON.stringify({downloaded:target,...files[target]}));
}
const models=[
  {role:'embedding',id:'intfloat/multilingual-e5-small',revision:'614241f622f53c4eeff9890bdc4f31cfecc418b3',prefix:'onnx/'},
  {role:'reranker',id:'BAAI/bge-reranker-base',revision:'2cfc18c9415c912f9d8155881c133215df768a70',prefix:''},
];
for(const model of models) {
  const url=`https://huggingface.co/api/models/${model.id}/tree/${model.revision}?recursive=true&expand=true`;
  const response=await fetch(url);if(!response.ok) throw Error(`Fixed model tree: ${response.status}`);
  const entries=await response.json();
  for(const name of ['model.onnx','tokenizer.json','config.json','special_tokens_map.json','tokenizer_config.json','README.md']) {
    const source=name==='model.onnx'?'onnx/model.onnx':name==='README.md'?'README.md':`${model.prefix}${name}`;
    const entry=entries.find(entry=>entry.path===source&&entry.type==='file');if(!entry) throw Error(`Fixed source has no ${source}`);
    await download(model.id,model.revision,entry,name==='README.md'?`licenses/${model.role}-model-card.md`:`${model.role}/${name}`);
  }
}
await fsp.mkdir(path.join(directory,'runtime'),{recursive:true});
for(const file of await fsp.readdir(native,{withFileTypes:true})) {
  if(!file.isFile()) throw Error('Unexpected runtime directory entry');
  await fsp.copyFile(path.join(native,file.name),path.join(directory,'runtime',file.name),fs.constants.COPYFILE_EXCL);await record(`runtime/${file.name}`);
}
const licenses=['licenses/embedding-model-card.md','licenses/reranker-model-card.md'];
for(const file of await fsp.readdir(extracted,{withFileTypes:true})) {
  if(file.isFile()&&/license|notice/i.test(file.name)) {
    const target=`licenses/ort-${file.name}`;await fsp.copyFile(path.join(extracted,file.name),path.join(directory,target),fs.constants.COPYFILE_EXCL);await record(target);licenses.push(target);
  }
}
if(!licenses.some(file=>/ort-.*license/i.test(file))) throw Error('ORT license file is missing');
const library={win32:'onnxruntime.dll',linux:'libonnxruntime.so',darwin:'libonnxruntime.dylib'}[process.platform];
if(!files[`runtime/${library}`]) throw Error('ORT runtime library is missing');
const model=({role,id,revision})=>({id,revision,onnx:`${role}/model.onnx`,tokenizer_directory:role,max_length:512,precision:'fp32'});
const manifest={schema:'reverie.semantic-resource.v1',version:'e5-bge-fp32-control-v1',platform,architecture,dimensions:384,runtime:{version:'1.31.0',api_version:24,library:`runtime/${library}`},
  embedding:model(models[0]),reranker:model(models[1]),files,licenses,provenance:{created_at:new Date().toISOString(),model_license_metadata:'MIT',
    runtime:{source:'https://api.nuget.org/v3-flatcontainer/microsoft.ml.onnxruntime/1.31.0/microsoft.ml.onnxruntime.1.31.0.nupkg',sha256:packageDigest},downloads,
    purpose:'Official FP32 control resources. Generic INT8 production and quality comparison are separate; this control is not the default INT8 release.'}};
const manifestPath=path.join(directory,'manifest.json');await fsp.writeFile(manifestPath,JSON.stringify(manifest,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({directory,manifest_sha256:await hash(manifestPath),bytes:Object.values(files).reduce((sum,file)=>sum+file.bytes,0)}));
