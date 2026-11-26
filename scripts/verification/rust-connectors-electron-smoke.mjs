import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {spawn,execFileSync} from 'node:child_process';
import {createConnectorFixture} from './rust-connector-fixture.mjs';

const repository=process.cwd(),require=createRequire(import.meta.url),uiRoot=path.join(repository,'ReverieCli-ui');
const executable=path.resolve(process.argv[2]||'ReverieCli-rs/target/debug/reverie.exe'),directory=path.resolve(process.argv[3]||'.runtime/rust-3.0/connectors-electron-smoke');
const kernel={executable,sha256:crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'),size:fs.statSync(executable).size,info:JSON.parse(execFileSync(executable,['--kernel-info'],{encoding:'utf8',windowsHide:true}))};
if(kernel.info.implementation!=='rust')throw new Error('The coordinated verification program is not Rust.');
fs.mkdirSync(directory,{recursive:true});const root=fs.mkdtempSync(path.join(directory,'case-')),fixture=await createConnectorFixture(repository,root),runtimeRoot=path.join(root,'desktop-runtime');fs.mkdirSync(runtimeRoot,{recursive:true});
fs.writeFileSync(path.join(runtimeRoot,'desktop-settings.json'),JSON.stringify({projectRoot:fixture.projectRoot,coreAppRoot:fixture.appRoot,ui:{language:'zh-CN',startupMode:'gui',uiVariant:'classic',classicTheme:'dark'}}));
const optionsFile=path.join(root,'probe-config.json');fs.writeFileSync(optionsFile,JSON.stringify({uiRoot,runtimeRoot,projectRoot:fixture.projectRoot,appRoot:fixture.appRoot,base:fixture.base,stdio:fixture.stdio,remote:fixture.remote,secrets:fixture.secrets,outputRoot:root,kernel}));
let child,timer;
try{
  child=spawn(require(path.join(uiRoot,'node_modules/electron')),[path.join(repository,'scripts/verification/rust-connectors-electron-probe.cjs'),optionsFile],{cwd:uiRoot,windowsHide:true,env:{...process.env,ELECTRON_RUN_AS_NODE:undefined,NO_PROXY:[process.env.NO_PROXY,'127.0.0.1','localhost'].filter(Boolean).join(',')},stdio:['ignore','pipe','pipe']});
  let output='';child.stdout.on('data',bytes=>output+=bytes);child.stderr.on('data',bytes=>output+=bytes);timer=setTimeout(()=>child.kill(),120_000);
  const code=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',resolve);});fs.writeFileSync(path.join(root,'electron.log'),output);fs.writeFileSync(path.join(root,'http-requests.json'),JSON.stringify(fixture.requests,null,2)+'\n');fixture.assertHealthy();
  const reportFile=path.join(root,'report.json');if(code!==0||!fs.existsSync(reportFile))throw new Error(`Actual Connector window failed (${code}): ${output.slice(-2200)}`);
  const report=JSON.parse(fs.readFileSync(reportFile,'utf8'));if(!report.passed)throw new Error('The actual Connector report did not pass.');
  if(crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex')!==kernel.sha256)throw new Error('The verification executable changed during the run.');
  console.log(JSON.stringify({passed:true,checks:report.checks.length,report:reportFile}));
}finally{clearTimeout(timer);if(child?.exitCode===null)child.kill();await fixture.close();}
