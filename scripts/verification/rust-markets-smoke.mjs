import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import http from 'node:http';
import {execFileSync} from 'node:child_process';
import {setTimeout as delay} from 'node:timers/promises';
import {startBridge} from './rust-bridge-client.mjs';

const executable=path.resolve(process.argv[2]||`ReverieCli-rs/target/release/reverie${process.platform==='win32'?'.exe':''}`);
const directory=path.resolve(process.argv[3]||'.runtime/rust-3.0/markets-smoke');fs.mkdirSync(directory,{recursive:true});
const root=fs.mkdtempSync(path.join(directory,'case-')),project=path.join(root,'workspace'),app=path.join(root,'application'),repository=path.join(root,'source-repo');
for(const folder of [project,app,path.join(repository,'.claude-plugin'),path.join(repository,'.agents/plugins')])fs.mkdirSync(folder,{recursive:true});
const plugins=Array.from({length:55},(_,index)=>({name:`fixture-${String(index).padStart(3,'0')}`,description:`Native market description ${index}`,source:`./plugins/fixture-${index}`}));
plugins.push({name:'external',source:{source:'git-subdir',url:'https://example.invalid/repository.git',path:'plugins/package',sha:'a'.repeat(40)}});
plugins.push({name:'command-installer',source:{source:'command',command:`"${process.execPath}" -e "require('fs').writeFileSync('must-not-run.txt','bad')"`}});
const manifest={name:'native-fixture-market',plugins};
const codex={name:'codex-fixture',plugins:[{name:'codex-package',source:{source:'local',path:'./plugins/codex-package'},policy:{installation:'AVAILABLE',authentication:'ON_INSTALL'}}]};
fs.writeFileSync(path.join(repository,'.claude-plugin/marketplace.json'),JSON.stringify(manifest));
fs.writeFileSync(path.join(repository,'.agents/plugins/marketplace.json'),JSON.stringify(codex));
function git(args){return execFileSync('git',args,{cwd:repository,windowsHide:true,encoding:'utf8',stdio:['ignore','pipe','pipe']});}
git(['init','--initial-branch=main']);git(['add','.']);git(['-c','user.name=Native verification','-c','user.email=verification@localhost','commit','-m','Fixed native market fixture']);
const commit=git(['rev-parse','HEAD']).trim();
let broken=false,held,bridge,serverFailure;
const checks=[];
const server=http.createServer((request,response)=>{
  try {
    const url=new URL(request.url,'http://127.0.0.1');
    if(url.pathname==='/hold'){held=response;return;}
    response.writeHead(200,{'content-type':'application/json'});
    if(url.pathname==='/registry') {
      const cursor=url.searchParams.get('cursor');assert.equal(url.searchParams.get('limit'),'100');
      response.end(JSON.stringify({servers:[{server:{name:'org.example/mcp',description:'Public MCP metadata fixture',version:cursor?'2.0.0':'1.0.0',remotes:[{type:'streamable-http',url:'https://mcp.example.invalid'}]}}],metadata:{nextCursor:cursor?'':'second-page'}}));
    }else response.end(broken?'invalid JSON':JSON.stringify(manifest));
  }catch(error){serverFailure=error;response.destroy(error);}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const base=`http://127.0.0.1:${server.address().port}`;
async function request(action,payload={},type){const result=await bridge.request(action,payload,30000);if(type)assert.equal(result.type,type,JSON.stringify(result));return result;}
async function add(name,kind,location,manifest_path){return (await request('addMarket',{name,kind,location,manifest_path},'market.updated')).source;}
async function waitHeld(){const end=Date.now()+10000;while(!held&&Date.now()<end)await delay(5);assert(held);}
try {
  bridge=startBridge(executable,project,app);await bridge.ready;
  let state=(await request('listMarkets',{},'markets')).markets;
  assert.equal(state.sources.length,4);assert(state.sources.every(source=>source.builtin&&source.status==='not_loaded'&&source.entry_count===0));
  checks.push('Four official sources remain lazy with their correct Claude, Codex and MCP Registry paths');
  const local=await add('Local Claude catalog','directory',repository);
  const localAgain=await add('Duplicate catalog','directory',repository);assert.equal(localAgain.id,local.id);
  const loaded=await request('refreshMarket',{market_id:local.id},'market.entries');assert.equal(loaded.total,57);assert.equal(loaded.items.length,30);assert.equal(loaded.next_offset,30);
  assert.equal(loaded.source.content_sha256,crypto.createHash('sha256').update(fs.readFileSync(path.join(repository,'.claude-plugin/marketplace.json'))).digest('hex'));
  const page=await request('queryMarket',{market_id:local.id,query:'Native market description',offset:30,limit:5},'market.entries');assert.equal(page.total,55);assert.equal(page.items.length,5);
  assert.equal(fs.existsSync(path.join(project,'must-not-run.txt')),false);
  checks.push('Add and deduplicate a local source, read the full catalog with bounded pages/search and retain command metadata without executing it');
  const fixed=await add('Fixed Git Claude catalog','git',repository,'.claude-plugin/marketplace.json');
  const fixedResult=await request('refreshMarket',{market_id:fixed.id},'market.entries');assert.equal(fixedResult.source.source_commit,commit);
  const separate=await add('Codex catalog in same repository','git',repository,'.agents/plugins/marketplace.json');assert.notEqual(separate.id,fixed.id);
  const codexResult=await request('refreshMarket',{market_id:separate.id},'market.entries');assert.equal(codexResult.items[0].source_kind,'local');assert.equal(codexResult.items[0].manifest.policy.authentication,'ON_INSTALL');
  checks.push('Fetch actual Git content at a fixed commit and preserve separate manifests from one shared repository');
  const remote=await add('HTTP catalog','manifest',`${base}/catalog`);await request('refreshMarket',{market_id:remote.id},'market.entries');
  broken=true;await request('refreshMarket',{market_id:remote.id},'error');
  const cached=await request('queryMarket',{market_id:remote.id},'market.entries');assert.equal(cached.total,57);assert.equal(cached.source.status,'cached_error');broken=false;
  checks.push('Actual HTTP catalog reads preserve the previous valid cache after a malformed refresh');
  const registry=await add('Public registry fixture','mcp_registry',`${base}/registry`);
  const initialRegistry=await request('refreshMarket',{market_id:registry.id},'market.entries');assert.equal(initialRegistry.source.next_cursor,'second-page');
  await request('refreshMarket',{market_id:registry.id,cursor:'unrelated-page'},'error');
  const registryPage=await request('refreshMarket',{market_id:registry.id,cursor:'second-page'},'market.entries');assert.equal(registryPage.total,2);assert.deepEqual(registryPage.items.map(entry=>entry.version),['1.0.0','2.0.0']);
  checks.push('Keep MCP Registry name/version identities and append its real cursor pages without installing or authorizing a server');
  const holding=await add('Slow source','manifest',`${base}/hold`);
  const revision=(await request('listMarkets',{},'markets')).markets.revision;
  let pending=request('refreshMarket',{market_id:holding.id,expected_revision:revision});await waitHeld();
  await add('Independent source while downloading','manifest',`${base}/other`);held.writeHead(200,{'content-type':'application/json'});held.end(JSON.stringify(codex));held=undefined;
  const completed=await pending;assert.equal(completed.type,'market.entries',JSON.stringify(completed));assert.equal(completed.total,1);
  pending=request('refreshMarket',{market_id:holding.id});await waitHeld();
  await request('stopMarketRefresh',{market_id:holding.id},'market.control');assert.equal((await pending).type,'error');held.destroy();held=undefined;
  assert.equal((await request('queryMarket',{market_id:holding.id},'market.entries')).total,1);
  checks.push('SDK remains responsive during a fetch, unrelated sources do not break commit and explicit cancellation retains the cache');
  await request('addMarket',{name:'Traversal',kind:'directory',location:repository,manifest_path:'../outside.json'},'error');
  await request('addMarket',{name:'Credentials',kind:'manifest',location:'https://user:password@example.invalid/catalog'},'error');
  const stale=(await request('listMarkets',{},'markets')).markets.revision;
  await request('setMarketEnabled',{market_id:local.id,enabled:false,expected_revision:stale},'market.updated');
  await request('removeMarket',{market_id:remote.id,expected_revision:stale},'error');
  await request('refreshMarket',{market_id:local.id},'error');
  await request('setMarketEnabled',{market_id:local.id,enabled:true},'market.updated');
  await request('removeMarket',{market_id:remote.id},'market.updated');
  checks.push('Reject traversal, embedded credentials, stale mutations and refresh of a disabled source');
  await request('shutdown',{},'shutdown');assert.equal((await bridge.closed).code,0);
  bridge=startBridge(executable,project,app);await bridge.ready;
  assert.equal((await request('queryMarket',{market_id:fixed.id},'market.entries')).source.source_commit,commit);
  const catalogPath=path.join(app,'.reverie/extensions/markets/catalog.json'),before=fs.readFileSync(catalogPath);fs.writeFileSync(catalogPath,'{"schema":"unknown","revision":0,"sources":[],"entries":{}}');
  const invalid=fs.readFileSync(catalogPath);await request('listMarkets',{},'error');assert.deepEqual(fs.readFileSync(catalogPath),invalid);fs.writeFileSync(catalogPath,before);
  const tampered=JSON.parse(before);tampered.sources.find(source=>source.id===fixed.id).location='--upload-pack=must-not-execute';
  fs.writeFileSync(catalogPath,JSON.stringify(tampered));const refused=await request('refreshMarket',{market_id:fixed.id},'error');assert.match(refused.error,/valid marketplace source/);fs.writeFileSync(catalogPath,before);
  checks.push('Restore source and catalog identity after restart and preserve an incompatible catalog unchanged');
  await request('shutdown',{},'shutdown');assert.equal((await bridge.closed).code,0);if(serverFailure)throw serverFailure;
  const report={schema:'reverie.rust-markets-smoke.v1',passed:true,verified_at:new Date().toISOString(),executable,sha256:crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'),root,checks,scope:'Actual Rust JSONL, HTTP, Git, source state, catalog identity, pagination and cancellation; not package installation, publisher trust, OAuth, updates or full public-source acceptance.'};
  fs.writeFileSync(path.join(root,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({passed:true,checks:checks.length,report:path.join(root,'report.json')}));
}catch(error){fs.writeFileSync(path.join(root,'failed.json'),JSON.stringify({passed:false,error:String(error),checks},null,2)+'\n');throw error;}
finally{held?.destroy();if(bridge?.child.exitCode===null){bridge.child.stdin.end();await bridge.closed;}server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
