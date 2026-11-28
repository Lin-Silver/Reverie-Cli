import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {createRequire} from 'node:module';
import {spawn, execFileSync} from 'node:child_process';

const require = createRequire(import.meta.url);
const repositoryRoot = path.resolve('.');
const uiRoot = path.join(repositoryRoot,'ReverieCli-ui');
const directory = path.resolve(process.argv[2] || '.runtime/rust-3.0/electron-smoke');
fs.mkdirSync(directory,{recursive:true});
const root = fs.mkdtempSync(path.join(directory,'case-'));
const projectRoot = path.join(root,'project');
const appRoot = path.join(root,'application');
const runtimeRoot = path.join(root,'desktop-runtime');
for(const directory of [projectRoot,path.join(appRoot,'.reverie'),runtimeRoot])fs.mkdirSync(directory,{recursive:true});
fs.mkdirSync(path.join(projectRoot,'.agents/skills/desktop-native-skill'),{recursive:true});
fs.writeFileSync(path.join(projectRoot,'.agents/skills/desktop-native-skill/SKILL.md'),'---\nname: desktop-native-skill\ndescription: Native desktop skills fixture.\n---\nDesktop instructions preserve their original source.\n');
// A real, independent Git fixture prevents the surrounding repository from owning this project.
fs.writeFileSync(path.join(projectRoot,'.gitignore'),'.reverie/\n');
fs.writeFileSync(path.join(projectRoot,'fixture.txt'),'Independent desktop workspace\n');
fs.writeFileSync(path.join(projectRoot,'command.mjs'),"console.log('COMMAND_LIVE😀'); setTimeout(()=>console.log('COMMAND_FINAL😀'),2000);\n");
for(const args of [['init','--initial-branch=main'],['add','.gitignore','fixture.txt'],['-c','user.name=Reverie verification','-c','user.email=verification@localhost','commit','-m','Independent desktop fixture']]) {
  execFileSync('git',args,{cwd:projectRoot,windowsHide:true,stdio:'ignore'});
}
const answer = '用户自定义第四项\n第二行 😀';
const fileContent = '完整文件\r\n保持换行 😀';
const outputFile = path.join(projectRoot,'desktop-output.txt');
const held = new Set();
const routes = new Map();
let fixtureFailure;
const server = http.createServer(async(request,response)=>{
  try {
    const chunks=[];for await(const chunk of request)chunks.push(chunk);
    const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));
    assert.equal(request.headers.authorization,'Bearer desktop-environment-fixture');
    const prompt=body.messages.findLast(message=>message.role==='user').content;
    if(prompt==='MODELSCOPE') {
      assert.equal(request.url,'/named/v1/chat/completions');
      assert.equal(body.model,'Qwen/Qwen3.8-27B');
      assert.equal(body.reasoning_effort,'low');
      assert.deepEqual(body.chat_template_kwargs,{enable_thinking:true});
      routes.set(prompt,request.url);
      response.writeHead(200,{'content-type':'text/event-stream'});
      response.end('data: '+JSON.stringify({choices:[{delta:{content:'DESKTOP_MODELSCOPE_CONFIRMED'},finish_reason:'stop'}]})+'\n\ndata: [DONE]\n\n');
      return;
    }
    assert.equal(body.model,'desktop-fixture');
    assert.equal(request.url,prompt==='QUESTION'?'/v1/chat/completions':'/alternate/chat/completions');
    routes.set(prompt,request.url);
    const last=body.messages.at(-1);
    response.writeHead(200,{'content-type':'text/event-stream'});
    const event=(delta,finish_reason=null)=>response.write(`data: ${JSON.stringify({choices:[{index:0,delta,finish_reason}]})}\n\n`);
    if(last.role==='tool')event({content:`完成\n${JSON.parse(last.content).output}`},'stop');
    else if(prompt==='WAIT'){event({content:'partial waiting output 😀'});held.add(response);response.once('close',()=>held.delete(response));return;}
    else {
      const question=prompt==='QUESTION';
      const command=prompt==='COMMAND';
      const args=question?{question:'选择实现方式？',reason:'明确用户偏好',options:['A','B','C']}:command?{command:`"${process.execPath}" command.mjs`,timeout:10}:{path:'desktop-output.txt',content:fileContent};
      event({tool_calls:[{index:0,id:`desktop-${Date.now()}`,type:'function',function:{name:question?'userInput':command?'command_exec':'create_file',arguments:JSON.stringify(args)}}]},'tool_calls');
    }
    response.end('data: [DONE]\n\n');
  }catch(error){fixtureFailure=error;response.destroy(error);}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const disposable=id=>({model:id,profile_id:id,model_display_name:id,provider:'openai-chat'});
fs.writeFileSync(path.join(appRoot,'.reverie/config.json'),JSON.stringify({models:[disposable('before-edit'),{model:'desktop-fixture',profile_id:'desktop-profile',provider:'openai-chat',model_display_name:'Rust 本地验收模型',
  base_url:`http://127.0.0.1:${server.address().port}/v1`,api_key:'fixture-only',max_context_tokens:65536,custom_headers:{'x-fixture-saved':'preserve'}},
  disposable('before-delete'),{model:'desktop-fixture',profile_id:'alternate-profile',provider:'openai-chat',model_display_name:'Alternate profile',supports_vision:true,
    base_url:`http://127.0.0.1:${server.address().port}/alternate`,api_key_env:'REVERIE_DESKTOP_TEST_KEY',max_context_tokens:32768},disposable('delete-target')],active_model_source:'standard',active_model_index:1,
  mode:'reverie',auto_index:false,stream_responses:true,security:{permission_mode:'strict',permission_level:'full_control'}}));
fs.writeFileSync(path.join(runtimeRoot,'desktop-settings.json'),JSON.stringify({projectRoot,coreAppRoot:appRoot,ui:{language:'zh-CN',startupMode:'gui',uiVariant:'classic',classicTheme:'dark'}}));
const options={uiRoot,runtimeRoot,projectRoot,outputRoot:root,appRoot,answer,fileContent,outputFile,namedUrl:'http://127.0.0.1:'+server.address().port+'/named'};
if(process.argv[3]||process.argv[4]) {
  if(!process.argv[3]||!process.argv[4])throw new Error('Supply both a real semantic bundle and its manifest SHA-256.');
  options.semantic={directory:path.resolve(process.argv[3]),digest:process.argv[4]};
  fs.writeFileSync(path.join(projectRoot,'saving.md'),'# 恢复冒险进度\n退出前把玩家进度和背包写入本地文件；下次启动时读取文件恢复上次的状态。\n');
  fs.writeFileSync(path.join(projectRoot,'menu.md'),'# 界面外观\n背景为蓝色渐变，按钮文字是白色。\n');
}
const optionsFile=path.join(root,'probe-config.json');fs.writeFileSync(optionsFile,JSON.stringify(options));
let child;
let timer;
try {
  const electron=require(path.join(uiRoot,'node_modules/electron'));
  child=spawn(electron,[path.join(repositoryRoot,'scripts/verification/rust-electron-probe.cjs'),optionsFile],{
    cwd:uiRoot,windowsHide:true,env:{...process.env,ELECTRON_RUN_AS_NODE:undefined,MODELSCOPE_API_KEY:'',MODELSCOPE_TOKEN:'',MODELSCOPE_ACCESS_TOKEN:'',REVERIE_DESKTOP_TEST_KEY:'desktop-environment-fixture'},stdio:['ignore','pipe','pipe'],
  });
  let output='';child.stdout.on('data',chunk=>output+=chunk);child.stderr.on('data',chunk=>output+=chunk);
  timer=setTimeout(()=>child.kill(),90_000);
  const code=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',resolve);});
  fs.writeFileSync(path.join(root,'electron.log'),output);
  if(fixtureFailure)throw fixtureFailure;
  if(code!==0 || !fs.existsSync(path.join(root,'report.json')))throw new Error(`Actual Electron verification failed (${code}): ${output.slice(-2200)}`);
  const reportFile=path.join(root,'report.json');
  const report=JSON.parse(fs.readFileSync(reportFile,'utf8'));
  assert.equal(report.passed,true);
  assert.deepEqual([...routes.keys()],['QUESTION','WRITE','COMMAND','WAIT','MODELSCOPE']);
  report.routes=Object.fromEntries(routes);
  report.kernel_sha256=createHash('sha256').update(fs.readFileSync(report.paths.kernelPath)).digest('hex');
  fs.writeFileSync(reportFile,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({passed:true,report:path.join(root,'report.json')}));
}finally{
  clearTimeout(timer);
  for(const response of held)response.destroy();server.closeAllConnections();
  await new Promise(resolve=>server.close(resolve));
}
