import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {spawn,execFileSync} from 'node:child_process';
import {createPluginFixture} from './rust-plugin-fixture.mjs';

const require=createRequire(import.meta.url),repo=process.cwd(),uiRoot=path.join(repo,'ReverieCli-ui');
const executable=path.resolve(process.argv[2]||'ReverieCli-rs/target/release/reverie.exe');
const directory=path.resolve(process.argv[3]||'.runtime/rust-3.0/plugins-electron-smoke');fs.mkdirSync(directory,{recursive:true});
const root=fs.mkdtempSync(path.join(directory,'case-')),fixture=createPluginFixture(repo,root),runtimeRoot=path.join(root,'desktop-runtime');fs.mkdirSync(runtimeRoot,{recursive:true});
const kernel={executable,sha256:crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'),size:fs.statSync(executable).size,info:JSON.parse(execFileSync(executable,['--kernel-info'],{encoding:'utf8',windowsHide:true}))};
if(kernel.info.implementation!=='rust')throw new Error('The verification executable is not Rust.');
fs.writeFileSync(path.join(runtimeRoot,'desktop-settings.json'),JSON.stringify({projectRoot:fixture.projectRoot,coreAppRoot:fixture.appRoot,ui:{language:'zh-CN',startupMode:'gui',uiVariant:'classic',classicTheme:'dark'}}));
const held=new Set(),requests=[];let base,timer;
const server=http.createServer((request,response)=>{
  const url=new URL(request.url,'http://127.0.0.1');requests.push(url.pathname);
  if(url.pathname==='/hold.zip'){held.add(response);response.once('close',()=>held.delete(response));return;}
  if(url.pathname==='/version'){fixture.writeVersion(url.searchParams.get('value')||'2.0.0');response.end('ok');return;}
  if(url.pathname==='/registry'){response.writeHead(200,{'content-type':'application/json'});response.end(JSON.stringify({servers:[{server:{name:'org.reverie/native-remote-fixture',version:'1.0.0',description:'Independent endpoint choice fixture',remotes:[{type:'streamable-http',url:base+'/mcp-one'},{type:'sse',url:base+'/mcp-two'}]}}],metadata:{nextCursor:null}}));return;}
  response.writeHead(404);response.end('Fixture endpoint must not be called.');
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));base=`http://127.0.0.1:${server.address().port}`;
const optionsFile=path.join(root,'probe-config.json');fs.writeFileSync(optionsFile,JSON.stringify({uiRoot,runtimeRoot,projectRoot:fixture.projectRoot,marketRoot:fixture.marketRoot,sourceRoot:fixture.sourceRoot,marker:fixture.marker,base,outputRoot:root,kernel}));
try {
  const child=spawn(require(path.join(uiRoot,'node_modules/electron')),[path.join(repo,'scripts/verification/rust-plugins-electron-probe.cjs'),optionsFile],{cwd:uiRoot,windowsHide:true,env:{...process.env,ELECTRON_RUN_AS_NODE:undefined,NO_PROXY:[process.env.NO_PROXY,'127.0.0.1','localhost'].filter(Boolean).join(',')},stdio:['ignore','pipe','pipe']});
  let output='';child.stdout.on('data',bytes=>output+=bytes);child.stderr.on('data',bytes=>output+=bytes);timer=setTimeout(()=>child.kill(),120_000);
  const code=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',resolve);});fs.writeFileSync(path.join(root,'electron.log'),output);fs.writeFileSync(path.join(root,'http-requests.json'),JSON.stringify(requests,null,2)+'\n');
  const reportFile=path.join(root,'report.json');if(code!==0||!fs.existsSync(reportFile))throw new Error(`Actual plugin window failed (${code}): ${output.slice(-2600)}`);
  const report=JSON.parse(fs.readFileSync(reportFile,'utf8'));if(!report.passed)throw new Error('The actual plugin report did not pass.');
  if(requests.some(url=>url==='/mcp-one'||url==='/mcp-two'))throw new Error('Preparing the untrusted Registry fixture contacted a remote service.');
  if(fs.existsSync(fixture.marker))throw new Error('Plugin management executed a business Hook.');
  console.log(JSON.stringify({passed:true,checks:report.checks.length,report:reportFile}));
}finally{clearTimeout(timer);for(const response of held)response.destroy();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
