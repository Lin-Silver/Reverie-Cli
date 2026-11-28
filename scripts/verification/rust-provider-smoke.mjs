import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {startBridge} from './rust-bridge-client.mjs';

const executable=path.resolve(process.argv[2] || 'ReverieCli-rs/target/release/reverie'+(process.platform==='win32'?'.exe':''));
const directory=path.resolve(process.argv[3] || '.runtime/rust-3.0/provider-smoke');
fs.mkdirSync(directory,{recursive:true});
const root=fs.mkdtempSync(path.join(directory,'case-'));
const project=path.join(root,'project');
const appRoot=path.join(root,'application');
for(const item of [project,path.join(appRoot,'.reverie')])fs.mkdirSync(item,{recursive:true});
const transports=['openai-chat','openai-responses','anthropic','gemini'];
const checks=[];
const counts=new Map();
const contexts=new Map();
let failure;
let bridge;
process.env.REVERIE_PROVIDER_SMOKE_KEY='loopback-only-test-key';
process.env.NO_PROXY=[process.env.NO_PROXY,'127.0.0.1','localhost'].filter(Boolean).join(',');

function messages(body,transport) {
  if(transport==='openai-responses')return body.input;
  if(transport==='gemini')return body.contents;
  return body.messages;
}
function promptFor(body,transport) {
  if(transport==='gemini')return messages(body,transport).findLast(item=>item.role==='user' && item.parts.some(part=>typeof part.text==='string')).parts.find(item=>typeof item.text==='string').text;
  const user=messages(body,transport).findLast(item=>item.role==='user' && (typeof item.content==='string' || item.content?.some(part=>['text','input_text'].includes(part.type))));
  if(typeof user.content==='string')return user.content;
  return user.content.find(item=>['text','input_text'].includes(item.type)).text;
}
function toolResult(body,transport) {
  const last=messages(body,transport).at(-1);
  if(transport==='openai-responses')return last.type==='function_call_output';
  if(transport==='anthropic')return last.content?.some(item=>item.type==='tool_result');
  if(transport==='gemini')return last.parts?.some(item=>item.functionResponse);
  return last.role==='tool';
}
function responseValue(transport,call,text,reasoning='思考😀') {
  if(transport==='openai-chat')return {choices:[{message:call?{role:'assistant',content:null,tool_calls:[{id:call.id,type:'function',function:{name:'create_file',arguments:JSON.stringify(call.args)}}]}:{role:'assistant',content:text},finish_reason:call?'tool_calls':'stop'}],usage:{prompt_tokens:9,completion_tokens:6}};
  if(transport==='anthropic')return {type:'message',role:'assistant',stop_reason:call?'tool_use':'end_turn',usage:{input_tokens:9,output_tokens:6},content:call?[{type:'thinking',thinking:reasoning,signature:'opaque-anthropic-signature'},{type:'tool_use',id:call.id,name:'create_file',input:call.args}]:[{type:'text',text}]};
  if(transport==='gemini')return {candidates:[{content:{role:'model',parts:call?[{text:reasoning,thought:true},{functionCall:{id:call.id,name:'create_file',args:call.args},thoughtSignature:'opaque-gemini-signature'}]:[{text}]},finishReason:'STOP'}],usageMetadata:{promptTokenCount:9,candidatesTokenCount:6}};
  return {type:'response',status:'completed',usage:{input_tokens:9,output_tokens:6},output:call?[{type:'reasoning',id:'reasoning',encrypted_content:'opaque-responses-reasoning',summary:[{type:'summary_text',text:reasoning}]},{type:'function_call',id:'function',call_id:call.id,name:'create_file',arguments:JSON.stringify(call.args),status:'completed'}]:[{type:'message',id:'message',role:'assistant',status:'completed',content:[{type:'output_text',text,annotations:[]}]}]};
}
function recordsFor(transport,call,text) {
  const value=responseValue(transport,call,text);
  if(transport==='openai-chat')return [value,'[DONE]'];
  if(transport==='gemini')return [value];
  if(transport==='openai-responses') {
    if(!call)return [{type:'response.output_text.delta',delta:text.slice(0,2)},{type:'response.output_text.delta',delta:text.slice(2)},{type:'response.completed',response:value}];
    const args=JSON.stringify(call.args);
    return [{type:'response.reasoning_summary_text.delta',delta:'思考😀'},{type:'response.output_item.added',output_index:1,item:{type:'function_call',id:'function',call_id:call.id,name:'create_file',arguments:''}},
      {type:'response.function_call_arguments.delta',output_index:1,delta:args.slice(0,7)},{type:'response.function_call_arguments.delta',output_index:1,delta:args.slice(7)},
      {type:'response.function_call_arguments.done',output_index:1,arguments:args},{type:'response.output_item.done',output_index:1,item:value.output[1]},{type:'response.completed',response:value}];
  }
  const records=[{type:'message_start',message:{usage:{input_tokens:9}}}];
  value.content.forEach((block,index)=>{
    records.push({type:'content_block_start',index,content_block:block.type==='tool_use'?{...block,input:{}}:block.type==='thinking'?{...block,thinking:'',signature:''}:{...block,text:''}});
    if(block.type==='tool_use') {
      const args=JSON.stringify(block.input);
      records.push({type:'content_block_delta',index,delta:{type:'input_json_delta',partial_json:args.slice(0,7)}},{type:'content_block_delta',index,delta:{type:'input_json_delta',partial_json:args.slice(7)}});
    } else if(block.type==='thinking')records.push({type:'content_block_delta',index,delta:{type:'thinking_delta',thinking:block.thinking}},{type:'content_block_delta',index,delta:{type:'signature_delta',signature:block.signature}});
    else records.push({type:'content_block_delta',index,delta:{type:'text_delta',text:block.text}});
    records.push({type:'content_block_stop',index});
  });
  records.push({type:'message_delta',delta:{stop_reason:value.stop_reason},usage:{output_tokens:6}},{type:'message_stop'});
  return records;
}
async function sse(response,records) {
  response.writeHead(200,{'content-type':'text/event-stream'});
  for(const record of records) {
    const bytes=Buffer.from('data: '+(typeof record==='string'?record:JSON.stringify(record))+'\r\n\r\n');
    // Split inside UTF-8, JSON strings and SSE record boundaries.
    for(let offset=0;offset<bytes.length;offset+=11) { response.write(bytes.subarray(offset,offset+11)); await delay(1); }
  }
  response.end();
}
const server=http.createServer(async(request,response)=>{
  try {
    const chunks=[];for await(const chunk of request)chunks.push(chunk);
    const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));
    const transport=body.model?.replace('-fixture','') || 'gemini';
    const prompt=promptFor(body,transport);
    const context=contexts.get(prompt);
    assert(context,'Unexpected model prompt');
    assert.equal(request.headers[transport==='anthropic'?'x-api-key':transport==='gemini'?'x-goog-api-key':'authorization'],transport==='anthropic'||transport==='gemini'?process.env.REVERIE_PROVIDER_SMOKE_KEY:'Bearer '+process.env.REVERIE_PROVIDER_SMOKE_KEY);
    if(transport==='anthropic')assert.equal(request.headers['anthropic-version'],'2023-06-01');
    if(transport==='gemini') {
      assert(request.url.includes('/models/gemini-fixture:'+(context.stream?'streamGenerateContent':'generateContent')));
      assert.equal(new URL(request.url,'http://fixture').searchParams.get('alt'),context.stream?'sse':null);
      assert(body.tools[0].functionDeclarations[0].parametersJsonSchema);
    }
    const final=toolResult(body,transport);
    const key=prompt+':'+(final?'final':'initial');
    counts.set(key,(counts.get(key)||0)+1);
    if(context.bad) {
      if(transport==='anthropic')await sse(response,[{type:'message_start',message:{usage:{}}},{type:'content_block_start',index:0,content_block:{type:'text',text:''}},{type:'content_block_delta',index:0,delta:{type:'text_delta',text:'unfinished😀'}}]);
      else if(transport==='gemini')await sse(response,[{candidates:[{content:{parts:[{text:'unfinished😀'}]}}]}]);
      else if(transport==='openai-responses')await sse(response,[{type:'response.output_text.delta',delta:'unfinished😀'}]);
      else await sse(response,[{choices:[{delta:{content:'unfinished😀'}}]}]);
      return;
    }
    if(!final && counts.get(key)===1) { response.writeHead(503,{'retry-after':'0'});response.end('temporary');return; }
    if(final) {
      if(transport==='anthropic')assert.equal(body.messages.find(item=>item.role==='assistant').content[0].signature,'opaque-anthropic-signature');
      if(transport==='openai-responses') {
        assert.equal(body.input.find(item=>item.type==='reasoning').encrypted_content,'opaque-responses-reasoning');
        assert.equal(body.input.filter(item=>item.type==='function_call').length,1);
      }
      if(transport==='gemini')assert.equal(body.contents.find(item=>item.role==='model').parts.find(item=>item.functionCall).thoughtSignature,'opaque-gemini-signature');
      assert.equal(fs.readFileSync(path.join(project,context.file),'utf8'),context.content);
    }
    const call=final?null:{id:'call-'+prompt,args:{path:context.file,content:context.content}};
    const text='完成\n'+context.content;
    if(context.stream)await sse(response,recordsFor(transport,call,text));
    else { response.writeHead(200,{'content-type':'application/json'});response.end(JSON.stringify(responseValue(transport,call,text))); }
  } catch(error) { failure=error;response.destroy(error); }
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const base='http://127.0.0.1:'+server.address().port;
const models=transports.map(provider=>({model:provider+'-fixture',provider,profile_id:provider,base_url:provider==='gemini'?base:base+'/v1',api_key_env:'REVERIE_PROVIDER_SMOKE_KEY'}));
fs.writeFileSync(path.join(appRoot,'.reverie/config.json'),JSON.stringify({models,active_model_source:'standard',active_model_index:0,auto_index:false,stream_responses:true,mode:'reverie',api_max_retries:2,api_initial_backoff:0,api_timeout:10,security:{permission_level:'full_control',permission_mode:'default'}}));
async function request(action,payload={}) {
  const reply=await bridge.request(action,{projectRoot:project,...payload},15_000);
  if(failure)throw failure;
  assert.notEqual(reply.type,'error',reply.error);
  return reply;
}
try {
  bridge=startBridge(executable,project,appRoot,{
    REVERIE_SMOKE_EMPTY_TOKEN:'   ', REVERIE_SMOKE_ORDINARY:'ordinary', 'REVERIE-SMOKE-KEY':'invalid-name'
  });await bridge.ready;await request('initialize');
  const environment=await request('listApiKeyEnvironmentVariables');
  assert.equal(environment.type,'provider.environment');
  assert(environment.names.includes('REVERIE_PROVIDER_SMOKE_KEY'));
  assert(environment.names.every((name,i)=>typeof name==='string'&&(!i||environment.names[i-1]<name)));
  assert(!environment.names.some(name=>['REVERIE_SMOKE_EMPTY_TOKEN','REVERIE_SMOKE_ORDINARY','REVERIE-SMOKE-KEY'].includes(name)));
  assert(!JSON.stringify(environment).includes(process.env.REVERIE_PROVIDER_SMOKE_KEY));
  const modelFile=path.join(appRoot,'.reverie/config.json');
  const beforeSelection=fs.readFileSync(modelFile);
  const mismatch=await bridge.request('selectModel',{source:'standard',modelId:'openai-responses-fixture',profileId:'gemini'});
  assert.equal(mismatch.type,'error'); assert(beforeSelection.equals(fs.readFileSync(modelFile)));
  const owner=(await request('createSession',{name:'legacy model reference'})).session.id;
  const previous=await request('getConversationConfig',{sessionId:owner});
  const legacy={...previous.configuration,model_ref:{...previous.configuration.model_ref,profile_id:''}};
  await request('getConversationConfig',{sessionId:owner,revision:previous.revision,configuration:legacy});
  const added=await request('addStandardModel',{model:{model:models[0].model,provider:'anthropic',base_url:base}});
  assert(added.profile_id);
  const switched=await request('selectModel',{sessionId:owner,source:'standard',modelId:models[0].model,profileId:added.profile_id});
  assert.equal(switched.selected.profile_id,added.profile_id);
  await request('deleteStandardModel',{index:added.index});
  await request('selectModel',{sessionId:owner,modelId:models[0].model,profileId:models[0].profile_id});
  const restoredConfig=(await request('getConversationConfig',{sessionId:owner})).configuration;
  assert.deepEqual(restoredConfig.settings,legacy.settings);
  assert.equal(restoredConfig.model_ref.profile_id,models[0].profile_id);
  checks.push('Explicit selection recovered a legacy ambiguous reference and a removed profile, preserved conversation settings, and refused a mismatched profile');
  const modelAtZero=()=>JSON.parse(fs.readFileSync(modelFile,'utf8')).models[0];
  const change=async model=>(await request('updateStandardModel',{index:0,model})).models.sources[0].models[0];
  const literal='literal-fixture-only';
  assert.equal((await change({api_key:literal,api_key_env:''})).api_key_source,'config');
  await change({api_key:'',description:'edited without re-entering the key'});
  assert.equal(modelAtZero().api_key,literal);
  const beforeInvalid=fs.readFileSync(modelFile);
  const invalid=await bridge.request('updateStandardModel',{index:0,model:{api_key_env:'bad-name'}});
  assert.equal(invalid.type,'error'); assert(beforeInvalid.equals(fs.readFileSync(modelFile)));
  const envRow=await change({api_key_env:' REVERIE_PROVIDER_SMOKE_KEY '});
  assert.equal(envRow.api_key_source,'env'); assert.equal(envRow.api_key_configured,true);
  assert.equal(envRow.api_key_env,'REVERIE_PROVIDER_SMOKE_KEY');
  assert(!('api_key' in envRow)); assert(!modelAtZero().api_key);
  assert(!fs.readFileSync(modelFile,'utf8').includes(process.env.REVERIE_PROVIDER_SMOKE_KEY));
  checks.push('Credential suggestions contain sorted variable names only; editing a standard model preserves a stored key or switches to its validated environment reference');
  for(const transport of transports) {
    await request('selectModel',{source:'standard',modelId:transport+'-fixture'});
    for(const stream of [true,false]) {
      await request('setSetting',{key:'stream_responses',value:stream});
      const prompt=transport+'-'+(stream?'sse':'json');
      const context={stream,file:prompt+'.txt',content:transport+'\r\n原文😀',bad:false};contexts.set(prompt,context);
      const session=(await request('createSession',{name:prompt})).session;
      const reply=await request('runPrompt',{sessionId:session.id,runId:prompt,prompt,noIndex:true});
      assert.equal(reply.result.success,true);
      assert.equal(reply.result.output_text,'完成\n'+context.content);
      assert.equal(counts.get(prompt+':initial'),2);
      assert.equal(counts.get(prompt+':final'),1);
      assert.equal(reply.events.filter(item=>item.event?.type==='model.retry').length,1);
      assert.equal(fs.readFileSync(path.join(project,context.file),'utf8'),context.content);
      const page=(await request('getSession',{sessionId:session.id,select:false})).session;
      const assistant=page.messages.find(item=>item.role==='assistant');
      if(transport!=='openai-chat')assert.equal(assistant.provider_content.transport,transport);
      assert(!JSON.stringify(reply).includes(process.env.REVERIE_PROVIDER_SMOKE_KEY));
      checks.push(transport+' '+(stream?'SSE':'JSON')+': authentication, bounded retry, complete native tool, signed state and exact transcript');
    }
    await request('setSetting',{key:'stream_responses',value:true});
    const prompt=transport+'-incomplete';contexts.set(prompt,{stream:true,bad:true});
    const session=(await request('createSession',{name:prompt})).session;
    const reply=await request('runPrompt',{sessionId:session.id,runId:prompt,prompt,noIndex:true});
    assert.equal(reply.result.success,false);
    assert.equal(counts.get(prompt+':initial'),1);
    const page=(await request('getSession',{sessionId:session.id,select:false})).session;
    assert(page.interrupted_streams.some(item=>item.content==='unfinished😀'));
    checks.push(transport+': truncated output is preserved, fails and is not retried');
  }
  const saved=(await request('getState')).state;
  await bridge.request('shutdown');assert.equal((await bridge.closed).code,0);
  bridge=startBridge(executable,project,appRoot);await bridge.ready;await request('initialize');
  const restored=(await request('getSession',{sessionId:saved.sessions.current_session_id,select:false})).session;
  assert(restored.interrupted_streams.some(item=>item.content==='unfinished😀'));
  checks.push('New native process restores interrupted output and configuration');
  fs.writeFileSync(path.join(root,'report.json'),JSON.stringify({passed:true,scope:'actual Rust HTTP, tools, persistence and transport fixtures; no external service or cryptographic model verification',sha256:crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'),checks,requests:Object.fromEntries(counts)},null,2)+'\n');
  console.log(JSON.stringify({passed:true,checks:checks.length,report:path.join(root,'report.json')}));
} catch(error) {
  fs.writeFileSync(path.join(root,'failed.json'),JSON.stringify({passed:false,error:String(error.stack||error),checks,requests:Object.fromEntries(counts)},null,2));
  throw error;
} finally {
  if(bridge.child.exitCode===null) { await bridge.request('shutdown').catch(()=>{});await bridge.closed; }
  server.closeAllConnections();await new Promise(resolve=>server.close(resolve));
}
