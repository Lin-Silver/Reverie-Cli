import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';

export async function createConnectorFixture(repository,root) {
  const projectRoot=path.join(root,'workspace'),appRoot=path.join(root,'application'),auditFile=path.join(root,'stdio-audit.jsonl');
  for(const directory of [projectRoot,path.join(appRoot,'.reverie')])fs.mkdirSync(directory,{recursive:true});
  fs.writeFileSync(path.join(appRoot,'.reverie/config.json'),JSON.stringify({mode:'reverie',auto_index:false,models:[],active_model_source:'standard',active_model_index:0}));
  const secrets=['fixture-private-secret','fixture-client-secret','fixture-api-secret','fixture-oauth-access','fixture-oauth-refresh','fixture\tprivate-key'];
  const clients=new Map([['fixture-client',{method:'client_secret_basic',secret:secrets[1]}]]),codes=new Map();
  const stats={metadata:0,registrations:0,authorizations:0,exchanges:0,refreshes:0,revocations:0,mcp:0},requests=[];
  let base,holdAuthorization=false,failure;
  const json=(response,status,value)=>{response.writeHead(status,{'content-type':'application/json','cache-control':'no-store'});response.end(JSON.stringify(value));};
  const clean=request=>{assert(!request.headers.authorization);assert(!request.headers['x-configuration-secret']);assert(!request.headers['x-fixture-key']);};
  function authenticate(request,form){
    let id=form.get('client_id');
    if(request.headers.authorization?.startsWith('Basic ')){
      const [client,secret]=Buffer.from(request.headers.authorization.slice(6),'base64').toString('utf8').split(':');
      id=decodeURIComponent(client);assert.equal(decodeURIComponent(secret),clients.get(id)?.secret);assert.equal(clients.get(id)?.method,'client_secret_basic');
    }else assert.equal(clients.get(id)?.method,'none');
    return id;
  }
  const server=http.createServer(async(request,response)=>{
    try{
      const url=new URL(request.url,base);requests.push({method:request.method,path:url.pathname});
      if(url.pathname==='/audit'){json(response,200,stats);return;}
      if(url.pathname==='/control'){holdAuthorization=url.searchParams.get('hold')==='true';json(response,200,{});return;}
      if(url.pathname==='/resource'){clean(request);stats.metadata++;json(response,200,{resource:base+'/mcp',authorization_servers:[base+'/issuer'],scopes_supported:['files:read','files:write']});return;}
      if(url.pathname.startsWith('/.well-known/')){clean(request);stats.metadata++;if(url.pathname!=='/.well-known/oauth-authorization-server/issuer'){json(response,404,{});return;}json(response,200,{issuer:base+'/issuer',authorization_endpoint:base+'/authorize',token_endpoint:base+'/token',registration_endpoint:base+'/register',revocation_endpoint:base+'/revoke',token_endpoint_auth_methods_supported:['none','client_secret_basic'],code_challenge_methods_supported:['S256'],response_types_supported:['code'],authorization_response_iss_parameter_supported:true});return;}
      if(url.pathname==='/authorize'){
        clean(request);stats.authorizations++;const id=url.searchParams.get('client_id');assert(clients.has(id));assert.equal(url.searchParams.get('resource'),base+'/mcp');assert.equal(url.searchParams.get('code_challenge_method'),'S256');
        if(holdAuthorization){response.writeHead(200,{'content-type':'text/plain','cache-control':'no-store'});response.end('Local authorization fixture is waiting; return to Reverie to cancel.');return;}
        const redirect=new URL(url.searchParams.get('redirect_uri'));assert.equal(redirect.hostname,'127.0.0.1');const code=crypto.randomBytes(24).toString('base64url');codes.set(code,{client:id,redirect:redirect.href,challenge:url.searchParams.get('code_challenge')});
        redirect.searchParams.set('code',code);redirect.searchParams.set('state',url.searchParams.get('state'));redirect.searchParams.set('iss',base+'/issuer');response.writeHead(302,{location:redirect.href,'cache-control':'no-store'});response.end();return;
      }
      if(url.pathname==='/mcp'&&request.method==='GET'){clean(request);response.writeHead(401,{'www-authenticate':`Bearer resource_metadata="${base}/resource", scope="files:read"`});response.end();return;}
      let bytes='';for await(const chunk of request)bytes+=chunk;
      if(url.pathname==='/register'){clean(request);stats.registrations++;const value=JSON.parse(bytes);assert(['none','client_secret_basic'].includes(value.token_endpoint_auth_method));assert.equal(value.redirect_uris.length,1);const id='dynamic-'+crypto.randomUUID();const client={method:value.token_endpoint_auth_method,secret:value.token_endpoint_auth_method==='none'?undefined:secrets[1]};clients.set(id,client);json(response,201,{client_id:id,client_secret:client.secret,token_endpoint_auth_method:client.method,redirect_uris:value.redirect_uris});return;}
      if(url.pathname==='/token'){
        const form=new URLSearchParams(bytes),id=authenticate(request,form);assert.equal(form.get('resource'),base+'/mcp');
        if(form.get('grant_type')==='authorization_code'){stats.exchanges++;const saved=codes.get(form.get('code'));assert(saved);codes.delete(form.get('code'));assert.equal(saved.client,id);assert.equal(saved.redirect,form.get('redirect_uri'));assert.equal(saved.challenge,crypto.createHash('sha256').update(form.get('code_verifier')).digest('base64url'));}
        else{stats.refreshes++;assert.equal(form.get('grant_type'),'refresh_token');assert.equal(form.get('refresh_token'),secrets[4]);}
        json(response,200,{access_token:secrets[3],refresh_token:secrets[4],token_type:'Bearer',expires_in:3600,scope:'files:read'});return;
      }
      if(url.pathname==='/revoke'){const form=new URLSearchParams(bytes);authenticate(request,form);assert([secrets[3],secrets[4]].includes(form.get('token')));stats.revocations++;response.writeHead(200);response.end();return;}
      if(url.pathname==='/mcp'||url.pathname==='/alternate-mcp'){
        if(![`Bearer ${secrets[2]}`,`Bearer ${secrets[3]}`].includes(request.headers.authorization)&&request.headers['x-fixture-key']!==secrets[5]){response.writeHead(401,{'www-authenticate':`Bearer resource_metadata="${base}/resource", scope="files:read"`});response.end();return;}
        if(request.method==='DELETE'){response.writeHead(200);response.end();return;}const message=JSON.parse(bytes);if(message.method?.startsWith('notifications/')){response.writeHead(202);response.end();return;}stats.mcp++;
        const result=message.method==='initialize'?{protocolVersion:'2025-06-18',serverInfo:{name:'Native Connector fixture',version:'1'},capabilities:{tools:{},resources:{},prompts:{}}}:message.method==='tools/list'?{tools:[{name:'authorized-echo',inputSchema:{type:'object'}}]}:message.method==='resources/list'?{resources:[{uri:'fixture://authorized',name:'Authorized resource'}]}:message.method==='resources/templates/list'?{resourceTemplates:[]}:message.method==='prompts/list'?{prompts:[{name:'authorized-prompt',arguments:[{name:'name',required:true}]}]}:message.method==='resources/read'?{contents:[{uri:message.params.uri,text:'Authorized fixture resource'}]}:message.method==='prompts/get'?{messages:[{role:'user',content:{type:'text',text:'Authorized prompt '+message.params.arguments.name}}]}:{content:[{type:'text',text:'Authorized fixture tool'}]};json(response,200,{jsonrpc:'2.0',id:message.id,result});return;
      }
      json(response,404,{});
    }catch(error){failure=error;response.destroy(error);}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));base=`http://127.0.0.1:${server.address().port}`;
  const stdio={type:'stdio',command:process.execPath,args:[path.join(repository,'scripts/verification/rust-mcp-smoke.mjs'),'--serve-stdio'],env:{MCP_FIXTURE_AUDIT:auditFile,FIXTURE_SECRET:secrets[0]},enabled:true,trust:false,timeout:5000};
  const remote={type:'http',url:base+'/mcp',enabled:true,trust:false,timeout:5000};
  fs.writeFileSync(path.join(appRoot,'.reverie/mcp.json'),JSON.stringify({mcpServers:{'stdio-fixture':stdio,'oauth-fixture':remote,'disabled-fixture':{...stdio,enabled:false,includeModes:['writer']},'invalid-fixture':{type:'invalid',env:{FIXTURE_SECRET:secrets[0]}}}}));
  return {projectRoot,appRoot,auditFile,base,stdio,remote,secrets,stats,requests,assertHealthy:()=>{if(failure)throw failure;},setHold:value=>{holdAuthorization=value;},close:async()=>{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}};
}
