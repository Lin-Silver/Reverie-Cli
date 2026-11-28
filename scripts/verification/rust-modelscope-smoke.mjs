import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {startBridge} from './rust-bridge-client.mjs';

const exe = path.resolve(process.argv[2] || 'ReverieCli-rs/target/release/reverie' + (process.platform === 'win32' ? '.exe' : ''));
const directory = path.resolve(process.argv[3] || '.runtime/rust-3.0/modelscope');
fs.mkdirSync(directory, {recursive:true});
const root = fs.mkdtempSync(path.join(directory, 'case-'));
const checks = [], traffic = [];
const qwen = 'Qwen/Qwen3.8-27B', glm = 'ZhipuAI/GLM-5.3';
const fixed = 'deepseek-ai/DeepSeek-V4.1-Flash', legacy = 'deepseek-ai/DeepSeek-V4-Pro';
const step = 'stepfun-ai/Step-3.7-Flash';
const unknown = {id:'inventory/new', architecture:{input_modalities:['image','text']},
  capabilities:{tools:false,reasoning:true}, context_window:'32768', max_tokens:320};
const inventory = {data:[unknown, qwen, glm, 'Inventory/New', {id:'image-only',output_modalities:['image']}]};
const environment = {MODELSCOPE_API_KEY:'', MODELSCOPE_TOKEN:'', MODELSCOPE_ACCESS_TOKEN:'', REVERIE_MODELSCOPE_ABSENT_KEY:'',
  REVERIE_NAMED_TEST_KEY:'fixture-env-only', NO_PROXY:'127.0.0.1,localhost'};
let bridge, failure;

async function server(name) {
  const state = {catalog:inventory, status:200, token:environment.REVERIE_NAMED_TEST_KEY};
  const instance = http.createServer(async (req,res) => {
    try {
      assert.equal(req.headers.authorization, 'Bearer ' + state.token);
      res.setHeader('content-type','application/json');
      if (req.method === 'GET') {
        assert.equal(req.url,'/v1/models');
        traffic.push({name, path:req.url, status:state.status});
        if (state.hold) {
          const held = state.hold;
          state.hold = undefined;
          held.started.resolve();
          await held.release.promise;
        }
        res.writeHead(state.status);
        res.end(JSON.stringify(state.catalog));
        return;
      }
      assert.equal(req.method,'POST');
      assert.equal(req.url,'/v1/chat/completions');
      let raw = '';
      for await (const bytes of req) raw += bytes;
      const body = JSON.parse(raw);
      assert(!raw.includes(state.token));
      traffic.push({name,path:req.url,model:body.model,kwargs:body.chat_template_kwargs,
        effort:body.reasoning_effort,max:body.max_tokens,top_p:body.top_p,tools:!!body.tools});
      res.end(JSON.stringify({choices:[{message:{role:'assistant',content:name + '/' + body.model},finish_reason:'stop'}]}));
    } catch (error) {failure = error; res.destroy(error);}
  });
  await new Promise(resolve => instance.listen(0,'127.0.0.1',resolve));
  return Object.assign(state, {instance,url:'http://127.0.0.1:' + instance.address().port});
}
const first = await server('first'), second = await server('second');
const source = reply => reply.models.sources.find(item => item.id === 'modelscope');
async function closeBridge() {
  if (!bridge) return;
  await bridge.request('shutdown');
  assert.equal((await bridge.closed).code,0);
  bridge = undefined;
}
try {
  for (const split of [false,true]) {
    const layout = split ? 'split' : 'inline';
    const project = path.join(root,layout), app = path.join(project,'app');
    const dir = path.join(app,'.reverie');
    fs.mkdirSync(path.join(dir,'Providers'),{recursive:true});
    const main = path.join(dir,'config.json'), profile = path.join(dir,'Providers/modelscope.json');
    const cfg = {api_url:first.url+'/v1/messages/',api_key:'fixture-literal',timeout:'52',max_tokens:4100};
    fs.writeFileSync(main,JSON.stringify({mode:'reverie',active_model_source:'standard',models:[],
      stream_responses:false,auto_index:false,api_max_retries:0,...(split ? {provider_files:{modelscope:'modelscope.json'}} : {modelscope:cfg})}));
    if (split) fs.writeFileSync(profile,JSON.stringify({provider_id:'modelscope',chat:cfg,extra:'untouched'}));
    first.status=200; first.catalog=inventory; first.token=environment.REVERIE_NAMED_TEST_KEY;
    const readConfig = () => split ? JSON.parse(fs.readFileSync(profile)).chat : JSON.parse(fs.readFileSync(main)).modelscope;
    const launch = async () => {bridge=startBridge(exe,project,app,environment); await bridge.ready; await request('initialize');};
    async function request(action,payload={}) {
      const r = await bridge.request(action,{projectRoot:project,...payload});
      if (failure) throw failure;
      assert.notEqual(r.type,'error',r.error);
      if (action !== 'revealProviderSecret') {
        for (const secret of ['fixture-literal',environment.REVERIE_NAMED_TEST_KEY]) assert(!JSON.stringify(r).includes(secret),action);
      }
      return r;
    }
    const patch = values => request('setProviderConfig',{source:'modelscope',patch:values});
    const select = (modelId,reasoning,sessionId) => request('selectModel',{source:'modelscope',modelId,reasoning,sessionId});
    const refresh = sessionId => request('refreshModelSources',{sessionId});
    const talk = async (sessionId,where,model) => {
      const r = await request('runPrompt',{sessionId,prompt:'reply with the fixture identifier',noIndex:true});
      assert.equal(r.result?.output_text,where+'/'+model,JSON.stringify(r.result));
      return traffic.at(-1);
    };
    await launch();
    let rows=source(await request('getModelSources'));
    assert.equal(rows.models.length,6); assert.equal(rows.catalog_live,false);
    assert.equal(rows.config.values.api_url,first.url+'/v1');
    assert.equal((await request('revealProviderSecret',{kind:'provider',source:'modelscope',field:'api_key'})).value,'fixture-literal');
    assert.equal((await bridge.request('revealProviderSecret',{kind:'provider',source:'modelscope',field:'api_url'})).type,'error');
    await patch({api_key_env:'REVERIE_NAMED_TEST_KEY'});
    assert.equal((await request('revealProviderSecret',{kind:'provider',source:'modelscope'})).value,'');
    await select(qwen,'low');
    const session=(await request('createSession',{name:layout})).session.id;
    let c=await request('getConversationConfig',{sessionId:session});
    assert.deepEqual(c.configuration.provider_settings,{max_tokens:4100,timeout:52,reasoning_effort:'low'});
    c.configuration.provider_settings={max_tokens:711,timeout:67,reasoning_effort:'medium'};
    await request('getConversationConfig',{sessionId:session,revision:c.revision,configuration:c.configuration});
    await select(qwen,'none',session);
    let hit=await talk(session,'first',qwen);
    assert.deepEqual(hit.kwargs,{enable_thinking:false}); assert.equal(hit.effort,undefined); assert.equal(hit.max,711);
    await select(qwen,'low',session);
    hit=await talk(session,'first',qwen);
    assert.deepEqual(hit.kwargs,{enable_thinking:true}); assert.equal(hit.effort,'low');
    await select(glm,'high',session);
    hit=await talk(session,'first',glm);
    assert.deepEqual(hit.kwargs,{enable_thinking:true,reasoning_effort:'high'}); assert.equal(hit.max,711);
    await select(step,'medium',session);
    hit=await talk(session,'first',step);
    assert.deepEqual(hit.kwargs,{reasoning_effort:'medium'}); assert.equal(hit.top_p,0.95);
    await select(fixed,undefined,session);
    assert.equal((await talk(session,'first',fixed)).kwargs,undefined);
    await select(legacy,'off',session);
    assert(source(await request('getModelSources',{sessionId:session})).models.some(m=>m.id===legacy && m.deprecated));
    assert.deepEqual((await talk(session,'first',legacy)).kwargs,{reasoning_effort:false});
    c=await request('getConversationConfig',{sessionId:session});
    assert.equal(c.configuration.provider_settings.timeout,67);
    assert.equal(source(await request('getWorkspaceConfig')).selected_model_id,qwen);
    checks.push(layout+' credentials, historical URL and model, independent session limits and wire parameters for four model families');

    rows=source(await refresh(session));
    assert.equal(rows.catalog_live,true);
    assert.equal(rows.models.length,3);
    const entry=rows.models.find(m=>m.id===unknown.id);
    assert.equal(entry.context_length,32768); assert.equal(entry.vision,true); assert.equal(entry.tool_calling,false);
    assert.equal(entry.reasoning.control,'fixed');
    await select(unknown.id,undefined,session);
    hit=await talk(session,'first',unknown.id);
    assert.equal(hit.max,320); assert.equal(hit.tools,false);
    const savedCache=readConfig().model_catalog;
    const key=createHash('sha256').update(first.url+'/v1/models\0'+environment.REVERIE_NAMED_TEST_KEY).digest('hex');
    assert.equal(savedCache.connection_key,key);
    first.status=503;
    const failed=await refresh(session);
    assert.match(failed.catalog_error,/503/); assert.deepEqual(source(failed).models,rows.models);
    assert.deepEqual(readConfig().model_catalog,savedCache);
    const before=traffic.length; await closeBridge(); await launch();
    assert.equal(source(await request('getModelSources',{sessionId:session})).selected_model_id,unknown.id);
    assert.equal(traffic.length,before);
    await talk(session,'first',unknown.id);
    first.status=200; first.catalog={data:[]};
    const empty=source(await refresh(session));
    assert.equal(empty.catalog_live,true); assert.deepEqual(empty.models,[]);
    await closeBridge(); await launch(); assert.deepEqual(source(await request('getModelSources',{sessionId:session})).models,[]);
    const missing=await bridge.request('runPrompt',{sessionId:session,prompt:'do not switch',noIndex:true});
    assert.equal(missing.type,'error'); assert.match(missing.error,/not found|unavailable/i);
    const held = {started:Promise.withResolvers(), release:Promise.withResolvers()};
    first.hold = held;
    const pending = bridge.request('refreshModelSources',{projectRoot:project,sessionId:session});
    try {
      await Promise.race([held.started.promise, pending.then(r=>{throw Error('Refresh returned before its HTTP request: '+r.type);})]);
      await patch({api_url:second.url+'/chat/completions'});
    } finally { held.release.resolve(); }
    const stale = await pending;
    assert.equal(stale.type,'error'); assert.match(stale.error,/connection changed/i);
    assert.equal(source(await request('getModelSources')).catalog_live,false);
    await select(qwen,'low',session); await talk(session,'second',qwen);
    await refresh(session);
    await patch({api_key_env:'REVERIE_MODELSCOPE_ABSENT_KEY'});
    assert.equal(source(await request('getModelSources')).catalog_live,false);
    const denied=await bridge.request('runPrompt',{sessionId:session,prompt:'no key',noIndex:true});
    assert.equal(denied.type,'error'); assert.match(denied.error,/API key/);
    const configFile = split ? profile : main;
    const disabled = JSON.parse(fs.readFileSync(configFile));
    (split ? disabled.chat : disabled.modelscope).enabled = false;
    fs.writeFileSync(configFile,JSON.stringify(disabled));
    const disabledRun=await bridge.request('runPrompt',{sessionId:session,prompt:'disabled',noIndex:true});
    assert.equal(disabledRun.type,'error'); assert.match(disabledRun.error,/disabled/i);
    if(split) {
      assert.equal(JSON.parse(fs.readFileSync(main)).modelscope,undefined);
      assert.equal(JSON.parse(fs.readFileSync(profile)).extra,'untouched');
    }
    checks.push(layout+' live inventory, per-model limits, empty list, failure fallback and restart');
    checks.push(layout+' stale in-flight refresh, URL and credential isolation, missing key and disabled provider');
    await closeBridge();
  }
  const report=path.join(root,'report.json');
  fs.writeFileSync(report,JSON.stringify({passed:true,checks,traffic,sha256:createHash('sha256').update(fs.readFileSync(exe)).digest('hex')},null,2));
  console.log(JSON.stringify({passed:true,checks:checks.length,requests:traffic.length,report}));
} finally {
  if(bridge){bridge.child.kill();await bridge.closed;}
  for(const s of [first,second]) {s.instance.closeAllConnections(); await new Promise(resolve=>s.instance.close(resolve));}
}
