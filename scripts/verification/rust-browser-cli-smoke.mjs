import assert from 'node:assert/strict';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import {setTimeout as delay} from 'node:timers/promises';
import fileCases from './rust-browser-file-cases.cjs';

const binary=path.resolve(process.argv[2]), directory=path.resolve(process.argv[3]||'.runtime/rust-3.0/browser-cli');
fs.mkdirSync(directory,{recursive:true});
const root=fs.mkdtempSync(path.join(directory,'case-')), project=path.join(root,'project'), app=path.join(root,'application');
for(const folder of [project,path.join(app,'.reverie')])fs.mkdirSync(folder,{recursive:true});
const checks=[],visits=[],calls=[];
const files=fileCases(project);
let base,scenario,routine,error;
const server=http.createServer(async(request,response)=>{
  if(await files.serve(request,response))return;
  if(request.url==='/form'){
    visits.push(request.headers['user-agent']);
    response.setHeader('Content-Type','text/html; charset=utf-8');
    response.setHeader('Cache-Control','no-store');
    response.end('<title>CLI browser form</title><button onclick="localStorage.saved=\'stored\';document.querySelector(\'p\').textContent=localStorage.saved">Save</button><p id="status"></p><script>document.querySelector("p").textContent=localStorage.saved||"fresh"</script>');
    return;
  }
  if(request.url!=='/v1/chat/completions'){response.writeHead(404);response.end();return;}
  try{
    let raw='';for await(const chunk of request)raw+=chunk;
    const body=JSON.parse(raw);
    assert.equal(body.tools.some(tool=>tool.function.name==='browser'),scenario!=='missing');
    const prior=body.messages.at(-1);
    const next=await routine.next(prior.role==='tool'?JSON.parse(prior.content):undefined);
    const message=next.done?{role:'assistant',content:'Verified '+scenario}:{role:'assistant',content:null,tool_calls:[{id:'act-'+calls.length,type:'function',function:{name:'browser',arguments:JSON.stringify(next.value)}}]};
    if(!next.done)calls.push(next.value.action);
    response.setHeader('Content-Type','application/json');response.end(JSON.stringify({choices:[{message,finish_reason:next.done?'stop':'tool_calls'}]}));
  }catch(problem){error=problem;response.writeHead(500);response.end('fixture failed');}
});
function* form(mode,initial,save){
  const open=yield {action:'open',url:base+'/form'};
  assert.equal(open.success,true,JSON.stringify(open));assert.equal(open.data.profile.mode,mode);
  const tab_id=open.data.result.tab.tab_id;
  function check(result,text){
    assert.equal(result.success,true,JSON.stringify(result));
    const data=result.data, page=data.result.observation;
    assert(page.elements.some(e=>e.text===text),'Expected actual form state '+text);
    assert(fs.existsSync(path.join(project,'.reverie/browser/observations',page.screenshot.image_id+'.png')));
    return {target:data.target,button:page.elements.find(e=>e.name==='Save').element_id};
  }
  let seen=check(yield {action:'observe',tab_id},initial);
  if(save){
    assert.equal((yield {action:'click',target:seen.target,element_id:seen.button}).success,true);
    seen=check(yield {action:'observe',tab_id},'stored');
    assert.equal((yield {action:'navigate',target:seen.target,url:base+'/form#saved'}).success,true);
    seen=check(yield {action:'observe',tab_id},'stored');
    for(const [action,url] of [['back','/form'],['forward','/form#saved'],['reload','/form#saved']]){
      const before=visits.length;
      const reply=yield {action,target:seen.target};
      assert.equal(reply.success,true,JSON.stringify(reply));assert.equal(reply.data.result.tab.url,base+url);
      seen=check(yield {action:'observe',tab_id},'stored');
      assert.equal(visits.length,before+(action==='reload'?1:0));
    }
    checks.push('The independent component traverses fragment history and reloads the persisted page from the server');
  }
  assert.equal((yield {action:'close',target:seen.target}).success,true);
}
async function run(label,mode,steps,overrides={}){
  scenario=label;routine=steps;
  fs.writeFileSync(path.join(app,'.reverie/config.json'),JSON.stringify({mode:'reverie',browser_profile:mode,models:[{model:'local',provider:'openai-chat',base_url:base+'/v1',api_key:'loopback'}],active_model_index:0,auto_index:false,stream_responses:false,api_max_retries:0,security:{permission_mode:'full_access',permission_level:'full_control'}}));
  const env={...process.env,REVERIE_APP_ROOT:app,NO_PROXY:'127.0.0.1,localhost',...overrides};
  const result=await promisify(execFile)(binary,['--project',project,'--prompt','Check the local browser: '+label,'--no-index','--json'],{cwd:project,env,windowsHide:true,timeout:90000,maxBuffer:8*1024*1024}).catch(failure=>{throw error||failure;});
  if(error)throw error;
  const reply=JSON.parse(result.stdout);
  assert.equal(reply.result.success,true,JSON.stringify(reply.result));assert.equal(reply.result.output_text,'Verified '+label);
}
try{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));base='http://127.0.0.1:'+server.address().port;
  const empty=function*(){};
  const profileRoot=path.join(app,'.reverie/browser-component');
  await run('missing','persistent',empty(),{REVERIE_BROWSER_COMPONENT:path.join(root,'missing')});
  await run('unused','persistent',empty());
  assert(!fs.existsSync(profileRoot));assert.equal(visits.length,0);
  checks.push('An absent component is omitted; an available component stays stopped until used');
  await run('first','persistent',form('persistent','fresh',true));
  await run('reopen','persistent',form('persistent','stored',false));
  await run('isolated','ephemeral',form('ephemeral','fresh',false));
  await run('files','ephemeral',files.flow(base,'full_access',async check=>{
    const limit=Date.now()+10000;
    while(!check()) { assert(Date.now()<limit,'File upload request did not arrive');await delay(20); }
  }));
  checks.push('The packaged CLI transfers binary bytes in both directions using its own Chromium component');
  assert.deepEqual(fs.readdirSync(profileRoot),['persistent']);
  assert.equal(visits.length,4);assert(visits.every(ua=>/Chrome\/\d+/.test(ua)));
  checks.push('Packaged CLI launches its Electron sibling and the real web form changes after a model click','Persistent storage survives a fresh CLI process; temporary storage and component exit are verified at return');
  fs.writeFileSync(path.join(root,'report.json'),JSON.stringify({passed:true,checks,binary,sha256:crypto.createHash('sha256').update(fs.readFileSync(binary)).digest('hex'),calls,visits,transfers:files.evidence()},null,2));
  console.log('CLI browser smoke passed: '+root);
}catch(failure){fs.writeFileSync(path.join(root,'failure.json'),JSON.stringify({checks,calls,visits,error:String(failure.stack||failure)},null,2));console.error(root,failure);process.exitCode=1;}
finally{server.closeAllConnections();server.close();}
