// @vitest-environment jsdom
import {useState} from 'react';
import {cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {ConnectorsView} from './ConnectorsView';
import {useConnectors, type ConnectorsController} from './connector-state';
import type {ConnectorDiscovery,ConnectorsState,McpServerRecord} from './generated/core-types';

afterEach(cleanup);
const remote:McpServerRecord={id:'manual:remote',name:'Remote fixture',origin:'manual',type:'streamable_http',enabled:true,trust:true,command:'',args_count:0,url:'https://mcp.test/resource',cwd:'',timeout:1000,env_keys:['KEY_NAME'],header_keys:[],credential_configured:false,includeTools:[],excludeTools:[],includeModes:[],excludeModes:[],fingerprint:'a'.repeat(64)};
const disabled:McpServerRecord={...remote,id:'manual:disabled',name:'Disabled fixture',enabled:false,trust:false,includeModes:['writer'],fingerprint:'b'.repeat(64)};
const plugin:McpServerRecord={...remote,id:'plugin:plugin-1:remote',name:'Plugin fixture',origin:'plugin:plugin-1',fingerprint:'c'.repeat(64)};
const discovery:ConnectorDiscovery={discovery_id:'discovery-1',server_id:remote.id,resource:remote.url,metadata_url:'https://mcp.test/.well-known/oauth-protected-resource',created_at:Math.floor(Date.now()/1000),expires_at:Math.floor(Date.now()/1000)+600,required_scopes:['read'],supported_scopes:['read','write'],authorization_servers:[{issuer:'https://issuer.test',authorization_endpoint:'https://issuer.test/authorize',token_endpoint:'https://issuer.test/token',registration_endpoint:'https://issuer.test/register',revocation_endpoint:'https://issuer.test/revoke',token_endpoint_auth_methods_supported:['none','client_secret_basic'],pkce:'S256'}]};
function setup(options:{held?:boolean;orphan?:boolean;credentialProblem?:boolean}={}) {
  let management={type:'mcp',operation_id:'read',mcp:{path:'fixture/mcp.json',revision:1,servers:[],diagnostics:[{scope:'server',id:'manual:bad',name:'bad',origin:'manual',error:'Invalid type'}],readable:true},servers:[remote,disabled,plugin].map(value=>({...value})),effective_server_ids:[remote.id,plugin.id]};
  let connectors:ConnectorsState={connectors:options.orphan?[{server_id:'manual:removed',status:'configuration_missing',credential_configured:true,configuration_current:false,resource:'https://old.test',credential_storage:'system'}]:[{server_id:remote.id,status:'not_authorized',credential_configured:false,enabled:true,trust:true,configuration_current:true}],pending:[],pending_credential_cleanup:0};
  const listeners=new Set<(event:Record<string,unknown>)=>void>();
  let rejectComplete:((failure:Error)=>void)|undefined,controller:ConnectorsController|undefined;
  const request=vi.fn(async(action:string,payload:Record<string,unknown>)=>{
    if(action==='listMcp')return structuredClone(management);
    if(action==='listConnectors')return {type:'connectors',connectors:structuredClone(connectors),mcp_diagnostics:[],operation_id:payload.operation_id||'read'};
    if(action==='setMcpTrust'||action==='setMcpEnabled'){
      management={...management,mcp:{...management.mcp,revision:management.mcp.revision+1},servers:management.servers.map(server=>server.name===payload.name?{...server,...(action==='setMcpTrust'?{trust:Boolean(payload.trusted)}:{enabled:Boolean(payload.enabled)})}:server)};
      return {...structuredClone(management),type:'mcp.updated'};
    }
    if(action==='configureMcp')return {...structuredClone(management),type:'mcp.updated'};
    if(action==='removeMcp'){management={...management,servers:management.servers.filter(server=>server.name!==payload.name),mcp:{...management.mcp,revision:management.mcp.revision+1}};return {...structuredClone(management),type:'mcp.updated'};}
    if(action==='discoverConnector')return {type:'connector.updated',connector:structuredClone(discovery),connectors:structuredClone(connectors),operation_id:payload.operation_id};
    if(action==='authorizeConnector'){
      connectors={...connectors,pending:[{authorization_id:'authorization-1',server_id:remote.id,resource:remote.url,issuer:'https://issuer.test',scopes:['read'],status:'awaiting_authorization',expires_at:Math.floor(Date.now()/1000)+600,configuration_current:true}]};
      return {type:'connector.updated',connector:{...connectors.pending[0],authorization_url:'https://issuer.test/authorize?state=private-flow',client_id:'client',redirect_uri:'http://127.0.0.1:32100/callback'},connectors:structuredClone(connectors),operation_id:payload.operation_id};
    }
    if(action==='completeConnectorAuthorization'&&options.held)return await new Promise((_resolve,reject)=>{rejectComplete=reject;});
    if(action==='completeConnectorAuthorization'){connectors={...connectors,pending:[],connectors:[{server_id:remote.id,status:'authorized',credential_configured:true,configuration_current:true}]};return {type:'connector.updated',connector:connectors.connectors[0],connectors:structuredClone(connectors),operation_id:payload.operation_id};}
    if(action==='cancelConnectorAuthorization'){connectors={...connectors,pending:[]};return {type:'connector.control',authorization_id:payload.authorization_id,cancelled:true};}
    if(action==='stopPluginOperation'){rejectComplete?.(new Error('Connector authorization cancelled.'));return {type:'plugin.control',operation_id:payload.operation_id,cancelled:true};}
    if(action==='setConnectorApiKey'){if(payload.expected_fingerprint!==management.servers.find(server=>server.id===payload.server_id)?.fingerprint)throw new Error('Connector target changed; inspect and confirm the current configuration again.');connectors={...connectors,connectors:[{server_id:remote.id,status:'authorized',credential_configured:true,configuration_current:true,credential_storage:'system'}]};return {type:'connector.updated',connector:{server_id:remote.id,status:'authorized'},connectors:structuredClone(connectors),operation_id:payload.operation_id};}
    if(action==='clearConnectorCredentials'){connectors={...connectors,connectors:connectors.connectors.filter(value=>value.server_id!==payload.server_id)};return {type:'connector.updated',connector:{server_id:payload.server_id,status:'local_credentials_cleared'},connectors:structuredClone(connectors),operation_id:payload.operation_id};}
    if(action==='refreshMcp')return {type:'mcp.result',operation_id:payload.operation_id,mcp_diagnostics:[],authorization_diagnostics:options.credentialProblem?[{server_id:remote.id,name:remote.name,status:'reauthorization_required',error:'Explicit reauthorization is required.',connector:{server_id:remote.id,status:'reauthorization_required'}}]:[],mcp:{servers:options.credentialProblem?[]:[{id:remote.id,status:'ready'}],tools:options.credentialProblem?[]:[{server_id:remote.id,name:'fixture_tool'}],resources:[{server_id:remote.id,uri:'fixture://resource'}],resource_templates:[],prompts:[{server_id:remote.id,name:'fixture_prompt'}],client_capabilities:{}}};
    if(action==='readMcpResource')return {type:'mcp.result',mcp:{contents:[{text:'Actual fixture resource'}]},operation_id:payload.operation_id};
    if(action==='getMcpPrompt')return {type:'mcp.result',mcp:{messages:[{role:'user',content:{type:'text',text:'Actual fixture prompt'}}]},operation_id:payload.operation_id};
    throw new Error(`Unexpected connector action ${action}`);
  });
  const openExternal=vi.fn(async()=>true),openPlugin=vi.fn();
  window.reverie={request,openExternal,onEvent:(listener:(event:Record<string,unknown>)=>void)=>{listeners.add(listener);return()=>listeners.delete(listener);}} as unknown as typeof window.reverie;
  function Harness(){const [active,setActive]=useState(true);controller=useConnectors(active,'fixture/workspace');return <><button onClick={()=>setActive(value=>!value)}>切页</button>{active&&<ConnectorsView controller={controller} onOpenPlugin={openPlugin}/>}</>;}
  return {request,openExternal,openPlugin,Harness,getController:()=>controller!,changeTarget:()=>{management={...management,mcp:{...management.mcp,revision:management.mcp.revision+1},servers:management.servers.map(server=>server.id===remote.id?{...server,url:'https://changed.test',fingerprint:'d'.repeat(64)}:server)};},emit:(event:Record<string,unknown>)=>listeners.forEach(listener=>listener({event}))};
}
it('keeps disabled and out-of-mode configurations visible and delegates plugin controls',async()=>{
  const fixture=setup();render(<fixture.Harness/>);await screen.findByRole('heading',{name:remote.name});
  expect(screen.getByText(disabled.name)).toBeTruthy();expect(screen.getByText('配置与连接诊断')).toBeTruthy();expect(screen.getByText('Invalid type',{exact:false})).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:new RegExp(plugin.name)}));await screen.findByRole('heading',{name:plugin.name});
  expect(screen.queryByRole('checkbox',{name:'信任此执行配置'})).toBeNull();fireEvent.click(screen.getByRole('button',{name:'打开所属插件'}));expect(fixture.openPlugin).toHaveBeenCalledWith('plugin-1');
  expect(fixture.request.mock.calls.some(([action])=>action==='refreshMcp')).toBe(false);
});
it('binds first trust to an inspected revision and fingerprint without enabling the server',async()=>{
  const fixture=setup();render(<fixture.Harness/>);await screen.findByRole('heading',{name:remote.name});fireEvent.click(screen.getByRole('button',{name:new RegExp(disabled.name)}));
  fireEvent.click(screen.getByRole('checkbox',{name:'信任此执行配置'}));const dialog=await screen.findByRole('alertdialog');
  expect(dialog.textContent).toContain(disabled.fingerprint);expect((within(dialog).getByRole('button',{name:'确认操作'}) as HTMLButtonElement).disabled).toBe(true);
  expect(fixture.request.mock.calls.some(([action])=>action==='setMcpTrust')).toBe(false);
  fireEvent.click(within(dialog).getByRole('checkbox',{name:'我已审阅并确认本次操作'}));fireEvent.click(within(dialog).getByRole('button',{name:'确认操作'}));
  await waitFor(()=>expect(fixture.request).toHaveBeenCalledWith('setMcpTrust',expect.objectContaining({name:disabled.name,trusted:true,fingerprint:disabled.fingerprint,expected_revision:1,projectRoot:'fixture/workspace'})));
  expect((screen.getByRole('checkbox',{name:'启用此 MCP 服务'}) as HTMLInputElement).checked).toBe(false);
});
it('requires explicit complete configuration replacement and clears its temporary JSON after sending',async()=>{
  const fixture=setup();render(<fixture.Harness/>);await screen.findByRole('heading',{name:remote.name});
  fireEvent.click(screen.getByText('添加或完整替换手动 MCP 配置'));fireEvent.change(screen.getByLabelText('手动 MCP 名称'),{target:{value:'custom'}});
  const raw=JSON.stringify({type:'stdio',command:'node',args:['one','one'],env:{TEMP_SECRET:'fixture-config-secret'},custom:{preserved:true},enabled:false});
  fireEvent.change(screen.getByLabelText('完整 MCP 配置 JSON'),{target:{value:raw}});
  expect((screen.getByRole('button',{name:'保存完整配置'}) as HTMLButtonElement).disabled).toBe(true);
  expect(JSON.stringify(fixture.getController())).not.toContain('fixture-config-secret');
  fireEvent.click(screen.getByRole('checkbox',{name:'我确认新增或完整替换此手动配置'}));fireEvent.click(screen.getByRole('button',{name:'保存完整配置'}));
  await waitFor(()=>expect(fixture.request).toHaveBeenCalledWith('configureMcp',expect.objectContaining({name:'custom',configuration:{...JSON.parse(raw),trust:false},expected_revision:1})));
  expect((screen.getByLabelText('完整 MCP 配置 JSON') as HTMLTextAreaElement).value).toBe('');
  fireEvent.click(screen.getByRole('button',{name:'切页'}));fireEvent.click(screen.getByRole('button',{name:'切页'}));expect((screen.getByLabelText('手动 MCP 名称') as HTMLInputElement).value).toBe('custom');
});
it('discovers OAuth without registration and sends transient client secrets only after review',async()=>{
  const fixture=setup();render(<fixture.Harness/>);await screen.findByRole('heading',{name:remote.name});fireEvent.click(screen.getByRole('button',{name:'发现并审阅 OAuth'}));
  const dialog=await screen.findByRole('alertdialog');expect(dialog.textContent).toContain(discovery.resource);expect(dialog.textContent).toContain('https://issuer.test/register');
  expect(fixture.request.mock.calls.some(([action])=>action==='authorizeConnector')).toBe(false);expect(fixture.openExternal).not.toHaveBeenCalled();
  fireEvent.change(within(dialog).getByLabelText('客户端注册方式'),{target:{value:'existing'}});fireEvent.change(within(dialog).getByLabelText('客户端认证方式'),{target:{value:'client_secret_basic'}});
  fireEvent.change(within(dialog).getByLabelText('Client ID'),{target:{value:'registered-client'}});fireEvent.input(within(dialog).getByLabelText('Client secret'),{target:{value:'one-use-client-secret'}});
  expect(JSON.stringify(fixture.getController())).not.toContain('one-use-client-secret');fireEvent.click(within(dialog).getByRole('checkbox',{name:'我确认此资源、授权服务器、范围和注册方式'}));fireEvent.click(within(dialog).getByRole('button',{name:'开始浏览器登录'}));
  await waitFor(()=>expect(fixture.request).toHaveBeenCalledWith('authorizeConnector',expect.objectContaining({server_id:remote.id,discovery_id:'discovery-1',choice:expect.objectContaining({issuer:'https://issuer.test',scopes:['read'],client_id:'registered-client',client_secret:'one-use-client-secret',client_auth_method:'client_secret_basic',confirmed:true})})));
  await waitFor(()=>expect(fixture.openExternal).toHaveBeenCalledWith('https://issuer.test/authorize?state=private-flow'));
  expect(JSON.stringify(fixture.getController())).not.toContain('one-use-client-secret');expect(JSON.stringify(fixture.getController())).not.toContain('authorization_url');expect(document.body.textContent).not.toContain('private-flow');
});
it('keeps only public pending authorization across navigation and cancels the completion wait',async()=>{
  const fixture=setup({held:true});render(<fixture.Harness/>);await screen.findByRole('heading',{name:remote.name});fireEvent.click(screen.getByRole('button',{name:'发现并审阅 OAuth'}));
  const dialog=await screen.findByRole('alertdialog');fireEvent.click(within(dialog).getByRole('checkbox',{name:'我确认此资源、授权服务器、范围和注册方式'}));fireEvent.click(within(dialog).getByRole('button',{name:'开始浏览器登录'}));
  const complete=await screen.findByRole('button',{name:'等待并完成授权'});fireEvent.click(complete);await screen.findByRole('button',{name:'停止'});
  fireEvent.click(screen.getByRole('button',{name:'切页'}));fireEvent.click(screen.getByRole('button',{name:'切页'}));await screen.findByText('authorization-1');
  expect(JSON.stringify(fixture.getController())).not.toContain('private-flow');fireEvent.click(screen.getByRole('button',{name:'停止'}));
  await waitFor(()=>expect(fixture.request).toHaveBeenCalledWith('cancelConnectorAuthorization',{authorization_id:'authorization-1'}));
  await waitFor(()=>expect(fixture.request).toHaveBeenCalledWith('stopPluginOperation',{operation_id:expect.any(String)}));await waitFor(()=>expect(screen.queryByRole('button',{name:'停止'})).toBeNull());
});
it('keeps API keys outside controller drafts and requires a separate target confirmation',async()=>{
  const fixture=setup();render(<fixture.Harness/>);await screen.findByRole('heading',{name:remote.name});fireEvent.click(screen.getByRole('button',{name:'设置 API Key'}));const dialog=await screen.findByRole('alertdialog');
  const secret=within(dialog).getByLabelText('完整请求头值') as HTMLInputElement;expect(secret.type).toBe('password');fireEvent.input(secret,{target:{value:'Bearer one-use-api-key'}});
  expect((within(dialog).getByRole('button',{name:'保存凭据'}) as HTMLButtonElement).disabled).toBe(true);expect(JSON.stringify(fixture.getController())).not.toContain('one-use-api-key');
  fireEvent.click(within(dialog).getByRole('checkbox',{name:'我确认向上述连接目标使用此请求头凭据'}));fireEvent.click(within(dialog).getByRole('button',{name:'保存凭据'}));
  await waitFor(()=>expect(fixture.request).toHaveBeenCalledWith('setConnectorApiKey',expect.objectContaining({server_id:remote.id,expected_fingerprint:remote.fingerprint,header:'Authorization',secret:'Bearer one-use-api-key',confirmed:true})));
  expect(secret.value).toBe('');expect(JSON.stringify(fixture.getController())).not.toContain('one-use-api-key');
});
it('refuses a credential submission if the server target changed after its review',async()=>{
  const fixture=setup();render(<fixture.Harness/>);await screen.findByRole('heading',{name:remote.name});fireEvent.click(screen.getByRole('button',{name:'设置 API Key'}));const dialog=await screen.findByRole('alertdialog');
  const secret=within(dialog).getByLabelText('完整请求头值') as HTMLInputElement;fireEvent.input(secret,{target:{value:'Bearer target-bound-secret'}});fireEvent.click(within(dialog).getByRole('checkbox',{name:'我确认向上述连接目标使用此请求头凭据'}));
  fixture.changeTarget();fireEvent.click(within(dialog).getByRole('button',{name:'保存凭据'}));
  await screen.findByRole('alert');expect(screen.getByRole('alert').textContent).toContain('Connector target changed');expect(secret.value).toBe('');
  const submitted=fixture.request.mock.calls.find(([action])=>action==='setConnectorApiKey')![1];expect(submitted.expected_fingerprint).toBe(remote.fingerprint);
  expect(fixture.getController().state?.connectors?.connectors[0].credential_configured).toBe(false);expect(JSON.stringify(fixture.getController())).not.toContain('target-bound-secret');
});
it('allows explicit local credential clearing for a removed configuration without remote revocation',async()=>{
  const fixture=setup({orphan:true});render(<fixture.Harness/>);await screen.findByRole('heading',{name:remote.name});fireEvent.click(screen.getByRole('button',{name:/manual:removed/}));
  fireEvent.click(screen.getByRole('button',{name:'仅清理本地凭据'}));const dialog=await screen.findByRole('alertdialog');expect(dialog.textContent).toContain('https://old.test');
  fireEvent.click(within(dialog).getByRole('checkbox',{name:'我已审阅并确认本次操作'}));fireEvent.click(within(dialog).getByRole('button',{name:'确认操作'}));
  await waitFor(()=>expect(fixture.request).toHaveBeenCalledWith('clearConnectorCredentials',expect.objectContaining({server_id:'manual:removed',confirmed:true,projectRoot:'fixture/workspace'})));
  expect(fixture.request.mock.calls.some(([action])=>action==='revokeConnector')).toBe(false);
});
it('refreshes capabilities explicitly and routes resource and prompt reads through the kernel',async()=>{
  const fixture=setup();render(<fixture.Harness/>);await screen.findByRole('heading',{name:remote.name});fireEvent.click(screen.getByRole('button',{name:'连接并刷新能力'}));await screen.findByText('连接正常');
  expect(screen.getByText('工具 · 1')).toBeTruthy();fireEvent.change(screen.getByLabelText('资源 URI'),{target:{value:'fixture://resource'}});fireEvent.click(screen.getByRole('button',{name:'读取资源'}));await screen.findByText(/Actual fixture resource/);
  fireEvent.change(screen.getByLabelText('提示词名称'),{target:{value:'fixture_prompt'}});fireEvent.change(screen.getByLabelText('提示词参数 JSON'),{target:{value:'{"subject":"shared"}'}});fireEvent.click(screen.getByRole('button',{name:'读取提示词'}));await screen.findByText(/Actual fixture prompt/);
  expect(fixture.request).toHaveBeenCalledWith('readMcpResource',expect.objectContaining({server_id:remote.id,uri:'fixture://resource'}));expect(fixture.request).toHaveBeenCalledWith('getMcpPrompt',expect.objectContaining({server_id:remote.id,name:'fixture_prompt',arguments:{subject:'shared'}}));
});
it('retains authorization diagnostics after state reload when a bad credential excludes the runtime server',async()=>{
  const fixture=setup({credentialProblem:true});render(<fixture.Harness/>);await screen.findByRole('heading',{name:remote.name});fireEvent.click(screen.getByRole('button',{name:'连接并刷新能力'}));await screen.findByText('需要重新授权');
  expect(screen.getByText(/Explicit reauthorization is required/)).toBeTruthy();expect(screen.getByRole('heading',{name:remote.name})).toBeTruthy();expect(screen.queryByText('连接正常')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'刷新状态'}));await waitFor(()=>expect(fixture.getController().state?.diagnostics[0].server_id).toBe(remote.id));expect(screen.getByText('需要重新授权')).toBeTruthy();
});
it('ignores a late reply from a previous workspace even when that workspace is revisited',async()=>{
  let finish:((reply:unknown)=>void)|undefined,first=true;
  const request=vi.fn(async(action:string,payload:Record<string,unknown>)=>{
    if(action==='listConnectors')return {type:'connectors',connectors:{connectors:[],pending:[],pending_credential_cleanup:0},mcp_diagnostics:[],operation_id:'read'};
    if(payload.projectRoot==='first'&&first){first=false;return await new Promise(resolve=>{finish=resolve;});}
    return {type:'mcp',mcp:{revision:2,path:'fixture',servers:[],diagnostics:[],readable:true},servers:[{...remote,name:`Current ${payload.projectRoot}`}],effective_server_ids:[remote.id],operation_id:'read'};
  });window.reverie={request,onEvent:()=>()=>{}} as unknown as typeof window.reverie;
  function Harness(){const [root,setRoot]=useState('first');const c=useConnectors(true,root);return <><button onClick={()=>setRoot('second')}>第二项目</button><button onClick={()=>setRoot('first')}>第一项目</button><ConnectorsView controller={c}/></>;}
  render(<Harness/>);fireEvent.click(screen.getByRole('button',{name:'第二项目'}));await screen.findByRole('heading',{name:'Current second'});fireEvent.click(screen.getByRole('button',{name:'第一项目'}));await screen.findByRole('heading',{name:'Current first'});
  finish?.({type:'mcp',mcp:{revision:1,path:'fixture',servers:[],diagnostics:[],readable:true},servers:[{...remote,name:'Stale first'}],effective_server_ids:[remote.id],operation_id:'old'});
  await waitFor(()=>expect(screen.queryByRole('heading',{name:'Stale first'})).toBeNull());expect(screen.getByRole('heading',{name:'Current first'})).toBeTruthy();
});
