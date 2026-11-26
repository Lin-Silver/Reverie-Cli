import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {spawn,execFileSync} from 'node:child_process';
const require=createRequire(import.meta.url),repo=process.cwd(),uiRoot=path.join(repo,'ReverieCli-ui');
const directory=path.resolve(process.argv[2]||'.runtime/rust-3.0/markets-electron-smoke');fs.mkdirSync(directory,{recursive:true});
const root=fs.mkdtempSync(path.join(directory,'case-')),projectRoot=path.join(root,'workspace'),appRoot=path.join(root,'application'),runtimeRoot=path.join(root,'desktop-runtime'),sourceRoot=path.join(root,'market-source');
for(const folder of [projectRoot,path.join(appRoot,'.reverie'),runtimeRoot,path.join(sourceRoot,'.claude-plugin')])fs.mkdirSync(folder,{recursive:true});
fs.writeFileSync(path.join(projectRoot,'.gitignore'),'.reverie/\n');
for(const args of [['init','--initial-branch=main'],['add','.gitignore'],['-c','user.name=Reverie verification','-c','user.email=verification@localhost','commit','-m','Independent market workspace']])execFileSync('git',args,{cwd:projectRoot,windowsHide:true,stdio:'ignore'});
const manifest={name:'native-gui-fixture',plugins:Array.from({length:50},(_,index)=>({name:`fixture-${String(index).padStart(2,'0')}`,description:`Native market entry ${index}`,source:`./plugins/fixture-${index}`}))};
fs.writeFileSync(path.join(sourceRoot,'.claude-plugin/marketplace.json'),JSON.stringify(manifest));
let broken=false;const held=new Set();
const server=http.createServer((request,response)=>{
  const url=new URL(request.url,'http://127.0.0.1');
  if(url.pathname==='/hold'){held.add(response);response.once('close',()=>held.delete(response));return;}
  if(url.pathname==='/control'){broken=url.searchParams.get('broken')==='1';response.end('ok');return;}
  response.writeHead(200,{'content-type':'application/json'});response.end(broken?'invalid-json':JSON.stringify(manifest));
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const base=`http://127.0.0.1:${server.address().port}`;
fs.writeFileSync(path.join(appRoot,'.reverie/config.json'),JSON.stringify({mode:'reverie',auto_index:false,models:[],active_model_source:'standard',active_model_index:0}));
fs.writeFileSync(path.join(runtimeRoot,'desktop-settings.json'),JSON.stringify({projectRoot,coreAppRoot:appRoot,ui:{language:'zh-CN',startupMode:'gui',uiVariant:'classic',classicTheme:'dark'}}));
const optionsFile=path.join(root,'probe-config.json');
const executable=path.join(uiRoot,'.kernel/reverie-rust/reverie.exe');
const kernelRecord=JSON.parse(fs.readFileSync(path.join(path.dirname(executable),'reverie-kernel-build.json'),'utf8'));
const kernelEvidence={executable,sha256:crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'),size:fs.statSync(executable).size,record:kernelRecord};
if(kernelEvidence.sha256!==kernelRecord.sha256||kernelEvidence.size!==kernelRecord.size)throw new Error('The staged native kernel does not match its build record.');
fs.writeFileSync(optionsFile,JSON.stringify({uiRoot,runtimeRoot,projectRoot,sourceRoot,base,outputRoot:root,kernelEvidence}));
let timer;
try {
  const child=spawn(require(path.join(uiRoot,'node_modules/electron')),[path.join(repo,'scripts/verification/rust-markets-electron-probe.cjs'),optionsFile],{cwd:uiRoot,windowsHide:true,env:{...process.env,ELECTRON_RUN_AS_NODE:undefined},stdio:['ignore','pipe','pipe']});
  let output='';child.stdout.on('data',bytes=>output+=bytes);child.stderr.on('data',bytes=>output+=bytes);timer=setTimeout(()=>child.kill(),90_000);
  const code=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',resolve);});fs.writeFileSync(path.join(root,'electron.log'),output);
  const reportFile=path.join(root,'report.json');if(code!==0||!fs.existsSync(reportFile))throw new Error(`Actual market window failed (${code}): ${output.slice(-2200)}`);
  const report=JSON.parse(fs.readFileSync(reportFile,'utf8'));if(!report.passed)throw new Error('The native market report did not pass.');
  console.log(JSON.stringify({passed:true,checks:report.checks.length,report:reportFile}));
}finally{clearTimeout(timer);for(const response of held)response.destroy();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
