import {useCallback, useEffect, useRef, useState} from 'react';
import type {CoreResponse} from './core-protocol';
import type {ConnectorAuthorizationChoice, ConnectorDiscovery, ConnectorRecord, ConnectorsState, JsonValue, McpServerRecord, McpSnapshotState, PendingConnectorAuthorization} from './generated/core-types';

type Management=Omit<CoreResponse<'listMcp'>,'type'>;
interface Scope {root:string;generation:number}
interface ConnectorViewState {root:string;management:Management|null;connectors:ConnectorsState|null;health:McpSnapshotState|null;diagnostics:Record<string,unknown>[];configurationDiagnostics:Record<string,unknown>[]}
export interface ConnectorDraft {name:string;serverId:string;query:string}
export interface ConnectorReview {kind:'trust'|'remove'|'revoke'|'clear';root:string;serverId:string;name:string;server:McpServerRecord|null;credential:ConnectorRecord|null;revision:number|undefined;acknowledged:boolean}
export interface ConnectorOAuthReview {root:string;discovery:ConnectorDiscovery;issuer:string;scopes:string[];registration:'dynamic'|'existing';clientId:string;clientAuthMethod:string;redirectUri:string;acknowledged:boolean}
interface Operation extends Scope {id:string;action:string;serverId:string;authorizationId?:string}
const blank=(root:string):ConnectorViewState=>({root,management:null,connectors:null,health:null,diagnostics:[],configurationDiagnostics:[]});
const message=(error:unknown)=>error instanceof Error?error.message:String(error);
export function connectorObject(value:unknown):Record<string,unknown>|null {return value!==null&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:null;}

export function useConnectors(active:boolean,projectRoot:string) {
  const [draft,setDraft]=useState<ConnectorDraft>({name:'',serverId:'',query:''}),[state,setState]=useState<ConnectorViewState|null>(null);
  const [review,setReview]=useState<ConnectorReview|null>(null),[oauth,setOAuth]=useState<ConnectorOAuthReview|null>(null);
  const [loading,setLoading]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[pending,setPending]=useState<Operation|null>(null),[result,setResult]=useState<{root:string;content:unknown}|null>(null);
  const scope=useRef(projectRoot),generation=useRef(0),alive=useRef(true),store=useRef(state),latest=useRef(draft),operation=useRef<Operation|null>(null),readGeneration=useRef(0);
  if(scope.current!==projectRoot){scope.current=projectRoot;generation.current++;readGeneration.current++;}
  store.current=state;latest.current=draft;
  const bind=()=>({root:scope.current,generation:generation.current});
  const current=useCallback((bound:Scope)=>alive.current&&scope.current===bound.root&&generation.current===bound.generation,[]);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;generation.current++;};},[]);
  const patch=useCallback((value:Partial<ConnectorDraft>)=>setDraft(previous=>({...previous,...value})),[]);
  const acceptManagement=useCallback((management:Management,bound:Scope)=>{
    if(!current(bound))return;
    setState(previous=>{
      const existing=previous?.root===bound.root?previous:blank(bound.root);
      const revision=existing.management?.mcp.revision;
      if(revision!==null&&revision!==undefined&&management.mcp.revision!==null&&management.mcp.revision<revision)return existing;
      return {...existing,management,health:revision===management.mcp.revision?existing.health:null,diagnostics:revision===management.mcp.revision?existing.diagnostics:[]};
    });
    setDraft(previous=>management.servers.some(server=>server.id===previous.serverId)||store.current?.root===bound.root&&store.current.connectors?.connectors.some(record=>record.server_id===previous.serverId)?previous:{...previous,serverId:management.servers[0]?.id||''});
  },[current]);
  const acceptConnectors=useCallback((connectors:ConnectorsState,bound:Scope)=>{
    if(current(bound))setState(previous=>({...((previous?.root===bound.root?previous:null)||blank(bound.root)),connectors}));
  },[current]);
  const reload=useCallback(async()=>{
    const bound={root:scope.current,generation:generation.current};if(!bound.root)return null;
    const read=++readGeneration.current;setLoading(true);
    const [mcp,connectors]=await Promise.allSettled([
      window.reverie.request('listMcp',{projectRoot:bound.root}),window.reverie.request('listConnectors',{projectRoot:bound.root})
    ]);
    if(!current(bound)||read!==readGeneration.current)return null;
    setLoading(false);
    if(mcp.status==='fulfilled')acceptManagement(mcp.value,bound);
    if(connectors.status==='fulfilled'){
      acceptConnectors(connectors.value.connectors,bound);
      setState(previous=>({...((previous?.root===bound.root?previous:null)||blank(bound.root)),configurationDiagnostics:connectors.value.mcp_diagnostics}));
    }
    const failures=[mcp,connectors].flatMap(reply=>reply.status==='rejected'?[message(reply.reason)]:[]);setError(failures.join('\n'));
    return mcp.status==='fulfilled'&&connectors.status==='fulfilled'?{management:mcp.value,connectors:connectors.value.connectors}:null;
  },[acceptConnectors,acceptManagement,current]);
  useEffect(()=>{setReview(null);setOAuth(null);setResult(null);setError('');setNotice('');if(active&&projectRoot)void reload();},[active,projectRoot,reload]);
  useEffect(()=>window.reverie?.onEvent?.(envelope=>{
    const event=connectorObject(envelope.event)||envelope;
    if(event.project_root!==scope.current)return;
    if(event.type==='mcp.notification'&&typeof event.authorization_id==='string'&&typeof event.status==='string'){
      const bound=bind();setState(previous=>previous?.root===bound.root&&previous.connectors?{...previous,connectors:{...previous.connectors,pending:previous.connectors.pending.map(item=>item.authorization_id===event.authorization_id?{...item,status:String(event.status)}:item)}}:previous);
      if(event.status==='callback_received'||event.status==='denied')void reload();
    }
  }),[reload]);
  const perform=async(action:string,serverId:string,work:(op:Operation)=>Promise<void>,authorizationId?:string)=>{
    if(operation.current)return;
    const op:Operation={...bind(),id:crypto.randomUUID(),action,serverId,authorizationId};
    operation.current=op;setPending(op);setError('');setNotice('');
    try{await work(op);if(current(op))await reload();}
    catch(failure){if(current(op)){await reload();setError(message(failure));}}
    finally{if(operation.current===op){operation.current=null;if(alive.current)setPending(null);}}
  };
  const clearHealth=(bound:Scope)=>{if(current(bound))setState(previous=>previous?.root===bound.root?{...previous,health:null,diagnostics:[]}:previous);};
  const configure=async(raw:string,confirmed:boolean)=>{
    if(!confirmed||operation.current)return;
    let configuration:{[key:string]:JsonValue};
    try{const parsed:JsonValue=JSON.parse(raw);if(parsed===null||typeof parsed!=='object'||Array.isArray(parsed))throw new Error('MCP 配置必须是 JSON 对象。');if(parsed.trust===true)throw new Error('保存配置后，请单独审阅并信任其执行指纹。');configuration={...parsed,trust:false};}
    catch(failure){setError(message(failure));return;}
    const name=latest.current.name.trim();if(!name){setError('请输入手动 MCP 名称。');return;}
    await perform('configureMcp',name,async op=>{
      const reply=await window.reverie.request('configureMcp',{projectRoot:op.root,operation_id:op.id,name,configuration,expected_revision:store.current?.root===op.root?store.current.management?.mcp.revision??undefined:undefined});acceptManagement(reply,op);
    });
  };
  const control=async(server:McpServerRecord,action:'setMcpTrust'|'setMcpEnabled',value:boolean)=>{
    if(server.origin!=='manual')return;
    await perform(action,server.id,async op=>{
      const reply=await window.reverie.request(action,{projectRoot:op.root,operation_id:op.id,name:server.name,...(action==='setMcpTrust'?{trusted:value}:{enabled:value}),expected_revision:store.current?.management?.mcp.revision??undefined});acceptManagement(reply,op);
    });
  };
  const requestReview=async(kind:ConnectorReview['kind'],serverId:string)=>{
    if(operation.current)return;const bound=bind();const refreshed=await reload();if(!refreshed||!current(bound))return;
    const server=refreshed.management.servers.find(value=>value.id===serverId)||null;
    const credential=refreshed.connectors.connectors.find(value=>value.server_id===serverId)||null;
    if((kind==='trust'||kind==='remove')&&(!server||server.origin!=='manual'))return;
    if(kind==='revoke'&&!server)return;
    if(kind==='clear'&&!credential)return;
    setReview({kind,root:bound.root,serverId,name:server?.name||serverId,server,credential,revision:refreshed.management.mcp.revision??undefined,acknowledged:false});
  };
  const confirmReview=async()=>{
    const selected=review;if(!selected?.acknowledged||operation.current||selected.root!==scope.current)return;
    setReview(null);
    if(selected.kind==='trust'||selected.kind==='remove')await perform(selected.kind==='trust'?'setMcpTrust':'removeMcp',selected.serverId,async op=>{
      const reply=selected.kind==='trust'?await window.reverie.request('setMcpTrust',{name:selected.name,trusted:true,fingerprint:selected.server!.fingerprint,expected_revision:selected.revision,projectRoot:op.root,operation_id:op.id}):await window.reverie.request('removeMcp',{name:selected.name,confirmed:true,expected_revision:selected.revision,projectRoot:op.root,operation_id:op.id});acceptManagement(reply,op);
    });
    else await perform(selected.kind==='revoke'?'revokeConnector':'clearConnectorCredentials',selected.serverId,async op=>{
      const reply=selected.kind==='revoke'?await window.reverie.request('revokeConnector',{server_id:selected.serverId,projectRoot:op.root,operation_id:op.id}):await window.reverie.request('clearConnectorCredentials',{server_id:selected.serverId,confirmed:true,projectRoot:op.root,operation_id:op.id});acceptConnectors(reply.connectors,op);clearHealth(op);if(current(op))setResult({root:op.root,content:reply.connector});
    });
  };
  const discover=async(server:McpServerRecord)=>perform('discoverConnector',server.id,async op=>{
    const reply=await window.reverie.request('discoverConnector',{server_id:server.id,projectRoot:op.root,operation_id:op.id});acceptConnectors(reply.connectors,op);if(!current(op))return;
    const issuer=reply.connector.authorization_servers[0];if(!issuer)throw new Error('此服务没有可用的 OAuth 授权服务器。');
    setOAuth({root:op.root,discovery:reply.connector,issuer:issuer.issuer,scopes:[...reply.connector.required_scopes],registration:issuer.registration_endpoint?'dynamic':'existing',clientId:'',clientAuthMethod:issuer.token_endpoint_auth_methods_supported.includes('none')?'none':issuer.token_endpoint_auth_methods_supported.find(method=>method==='client_secret_basic'||method==='client_secret_post')||'',redirectUri:'',acknowledged:false});
  });
  const authorize=async(secrets:{clientSecret:string;registrationToken:string})=>{
    const selected=oauth;if(!selected?.acknowledged||selected.root!==scope.current||operation.current)return;
    const choice:ConnectorAuthorizationChoice={issuer:selected.issuer,scopes:selected.scopes,client_auth_method:selected.clientAuthMethod,redirect_uri:selected.redirectUri.trim()||undefined,confirmed:true,...(selected.registration==='existing'?{client_id:selected.clientId.trim(),client_secret:secrets.clientSecret||undefined}:{registration_token:secrets.registrationToken||undefined})};
    setOAuth(null);
    await perform('authorizeConnector',selected.discovery.server_id,async op=>{
      const reply=await window.reverie.request('authorizeConnector',{server_id:selected.discovery.server_id,discovery_id:selected.discovery.discovery_id,choice,projectRoot:op.root,operation_id:op.id});acceptConnectors(reply.connectors,op);
      if(!current(op))return;
      const opened=await window.reverie.openExternal(reply.connector.authorization_url);
      if(!opened)setNotice('浏览器未打开。请取消此授权并重新开始登录。');
    });
  };
  const complete=async(authorization:PendingConnectorAuthorization)=>perform('completeConnectorAuthorization',authorization.server_id,async op=>{
    const reply=await window.reverie.request('completeConnectorAuthorization',{server_id:authorization.server_id,authorization_id:authorization.authorization_id,projectRoot:op.root,operation_id:op.id});acceptConnectors(reply.connectors,op);clearHealth(op);if(current(op))setResult({root:op.root,content:reply.connector});
  },authorization.authorization_id);
  const cancelAuthorization=async(authorizationId:string)=>{
    try{await window.reverie.request('cancelConnectorAuthorization',{authorization_id:authorizationId});if(operation.current?.authorizationId===authorizationId)await window.reverie.request('stopPluginOperation',{operation_id:operation.current.id});await reload();}
    catch(failure){if(alive.current)setError(message(failure));}
  };
  const setApiKey=async(server:McpServerRecord,header:string,secret:string)=>perform('setConnectorApiKey',server.id,async op=>{
    const reply=await window.reverie.request('setConnectorApiKey',{server_id:server.id,expected_fingerprint:server.fingerprint,header,secret,confirmed:true,projectRoot:op.root,operation_id:op.id});acceptConnectors(reply.connectors,op);clearHealth(op);if(current(op))setResult({root:op.root,content:reply.connector});
  });
  const refresh=async()=>perform('refreshMcp','',async op=>{
    const reply=await window.reverie.request('refreshMcp',{projectRoot:op.root,operation_id:op.id});if(current(op))setState(previous=>({...((previous?.root===op.root?previous:null)||blank(op.root)),health:reply.mcp,diagnostics:[...reply.mcp_diagnostics,...reply.authorization_diagnostics]}));
  });
  const readResource=async(serverId:string,uri:string)=>perform('readMcpResource',serverId,async op=>{
    const reply=await window.reverie.request('readMcpResource',{server_id:serverId,uri,projectRoot:op.root,operation_id:op.id});if(current(op))setResult({root:op.root,content:reply.mcp});
  });
  const getPrompt=async(serverId:string,name:string,rawArguments:string)=>{
    let args:JsonValue;
    try{const parsed:JsonValue=JSON.parse(rawArguments||'{}');if(parsed===null||typeof parsed!=='object'||Array.isArray(parsed))throw new Error('提示词参数必须是 JSON 对象。');args=parsed;}catch(failure){setError(message(failure));return;}
    await perform('getMcpPrompt',serverId,async op=>{const reply=await window.reverie.request('getMcpPrompt',{server_id:serverId,name,arguments:args,projectRoot:op.root,operation_id:op.id});if(current(op))setResult({root:op.root,content:reply.mcp});});
  };
  const cancel=async()=>{
    const op=operation.current;if(!op)return;
    try{if(op.authorizationId)await window.reverie.request('cancelConnectorAuthorization',{authorization_id:op.authorizationId});await window.reverie.request('stopPluginOperation',{operation_id:op.id});}
    catch(failure){if(current(op))setError(message(failure));}
  };
  const visible=state?.root===projectRoot?state:null;
  const selected=visible?.management?.servers.find(server=>server.id===draft.serverId)||null;
  return {draft,patch,state:visible,selected,review:review?.root===projectRoot?review:null,oauth:oauth?.root===projectRoot?oauth:null,patchReview:(patch:Pick<ConnectorReview,'acknowledged'>)=>setReview(value=>value?{...value,...patch}:value),patchOAuth:(patch:Partial<Omit<ConnectorOAuthReview,'root'|'discovery'>>)=>setOAuth(value=>value?{...value,...patch,acknowledged:patch.acknowledged??false}:value),closeReview:()=>setReview(null),closeOAuth:()=>setOAuth(null),loading,error,notice,pending,result:result?.root===projectRoot?result.content:null,reload,configure,control,requestReview,confirmReview,discover,authorize,complete,cancelAuthorization,setApiKey,refresh,readResource,getPrompt,cancel};
}
export type ConnectorsController=ReturnType<typeof useConnectors>;
