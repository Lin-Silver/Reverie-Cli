import {useCallback, useEffect, useRef, useState} from 'react';
import type {CorePayload, PluginInspection} from './core-protocol';
import type {PluginCandidate, PluginSourceKind, PluginSourceRequest} from './generated/core-types';
import type {PluginRecord, PluginsState, SettingsState} from './types';

export interface PluginDraft {kind:PluginSourceKind;location:string;endpoint:string;revision:string;subdirectory:string;sha256:string;signingKey:string;requireSignature:boolean;pluginId:string;candidateSha256:string;query:string}
const initialDraft:PluginDraft={kind:'directory',location:'',endpoint:'',revision:'',subdirectory:'',sha256:'',signingKey:'',requireSignature:false,pluginId:'',candidateSha256:'',query:''};
export type PluginReviewKind='activate'|'trust'|'hooks'|'rollback'|'remove';
export interface PluginReview {kind:PluginReviewKind;inspection:PluginInspection;target:PluginCandidate|null;projectRoot:string;acknowledged:boolean;contentApproved:boolean;profileApproved:boolean}
export function pluginReviewRequirements(review:PluginReview) {
  return {content:review.kind==='activate'&&Boolean(review.target?.approval_required),profile:(review.kind==='activate'||review.kind==='rollback')&&review.inspection.record.trusted&&review.target?.approval_profile_sha256!==review.inspection.active?.approval_profile_sha256};
}
type PluginChangeAction='activatePlugin'|'setPluginTrust'|'setPluginHooks'|'rollbackPlugin'|'removePlugin';
type StateReply={plugins:PluginsState;settings?:SettingsState;plugin_id?:string;candidate?:PluginCandidate};
function message(error:unknown){return error instanceof Error?error.message:String(error);}

export function usePlugins(active:boolean,projectRoot:string,publish:(plugins:PluginsState,settings:SettingsState|undefined,projectRoot:string)=>void) {
  const [draft,setDraft]=useState(initialDraft),[state,setState]=useState<PluginsState|null>(null),[inspection,setInspection]=useState<PluginInspection|null>(null);
  const [review,setReview]=useState<PluginReview|null>(null),[loading,setLoading]=useState(false),[inspecting,setInspecting]=useState(false),[error,setError]=useState('');
  const [pending,setPending]=useState<{action:string;label:string;operationId?:string;projectRoot:string}|null>(null);
  const alive=useRef(true),scope=useRef(projectRoot),loadedRoot=useRef(''),latest=useRef(draft),store=useRef(state),publishRef=useRef(publish),operation=useRef(false),generation=useRef(0);
  scope.current=projectRoot;latest.current=draft;publishRef.current=publish;
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;generation.current++;};},[]);
  const patch=useCallback((value:Partial<PluginDraft>)=>setDraft(current=>({...current,...value})),[]);
  const accept=useCallback((plugins:PluginsState,root:string,settings?:SettingsState)=>{
    if(!alive.current||scope.current!==root)return;
    if(loadedRoot.current===root&&store.current?.revision!==undefined&&plugins.revision!==undefined&&plugins.revision<store.current.revision)return;
    loadedRoot.current=root;store.current=plugins;setState(plugins);publishRef.current(plugins,settings,root);
    setDraft(current=>plugins.records.some(record=>record.id===current.pluginId)?current:{...current,pluginId:plugins.records[0]?.id||'',candidateSha256:''});
  },[]);
  const reload=useCallback(async(scan=false)=>{
    const root=scope.current;if(!root)return null;
    setLoading(true);setError('');
    try {const response=await window.reverie.request(scan?'refreshPlugins':'listPlugins',{projectRoot:root});accept(response.plugins,root);return response.plugins;}
    catch(failure){if(alive.current&&scope.current===root)setError(message(failure));return null;}
    finally{if(alive.current&&scope.current===root)setLoading(false);}
  },[accept]);
  useEffect(()=>{if(active&&projectRoot)void reload();},[active,projectRoot,reload]);
  useEffect(()=>{
    const current=++generation.current,root=projectRoot;
    if(!active||!root||!draft.pluginId){setInspecting(false);return;}
    setInspecting(true);
    void window.reverie.request('inspectPlugin',{pluginId:draft.pluginId,projectRoot:root}).then(detail=>{if(alive.current&&current===generation.current)setInspection(detail);})
      .catch(failure=>{if(alive.current&&current===generation.current)setError(message(failure));})
      .finally(()=>{if(alive.current&&current===generation.current)setInspecting(false);});
  },[active,projectRoot,draft.pluginId,state?.revision]);
  const mutate=async(action:string,label:string,work:()=>Promise<StateReply>,operationId?:string)=>{
    if(operation.current)return;
    const root=scope.current;operation.current=true;setPending({action,label,operationId,projectRoot:root});setError('');
    try {
      const response=await work();accept(response.plugins,root,response.settings);
      if(response.candidate&&response.plugin_id&&alive.current&&scope.current===root)patch({pluginId:response.plugin_id,candidateSha256:response.candidate.sha256});
      await reload();return response;
    }catch(failure){await reload();if(alive.current)setError(message(failure));}
    finally{operation.current=false;if(alive.current)setPending(null);}
  };
  const prepare=async(source?:PluginSourceRequest,label?:string)=>{
    if(operation.current)return;
    const submitted={...latest.current};
    const resolved:PluginSourceRequest=source||{kind:submitted.kind,location:submitted.kind==='market'?submitted.endpoint.trim()||undefined:submitted.location.trim(),entry_id:submitted.kind==='market'?submitted.location.trim():undefined,revision:submitted.revision.trim()||undefined,subdirectory:submitted.subdirectory.trim()||undefined,sha256:submitted.sha256.trim()||undefined,signing_key:submitted.signingKey.trim()||undefined,require_signature:submitted.requireSignature};
    operation.current=true;let current:PluginsState|null;
    try{current=await reload();}finally{operation.current=false;}
    if(!current)return;
    const operationId=crypto.randomUUID();
    await mutate('preparePlugin',label||resolved.location||resolved.entry_id||'',()=>window.reverie.request('preparePlugin',{source:resolved,operation_id:operationId,expected_revision:current.revision}),operationId);
  };
  const update=async(record:PluginRecord)=>{
    const operationId=crypto.randomUUID();
    await mutate('updatePlugin',record.name,()=>window.reverie.request('updatePlugin',{pluginId:record.id,operation_id:operationId,expected_revision:store.current?.revision}),operationId);
  };
  const control=(action:'setPluginEnabled'|'setPluginTrust'|'setPluginHooks'|'setPluginAutoUpdate',record:PluginRecord,value:boolean)=>{
    const field=action==='setPluginEnabled'?'enabled':action==='setPluginTrust'?'trusted':action==='setPluginHooks'?'hooks_enabled':'auto_update';
    return mutate(action,record.name,()=>window.reverie.request(action,{pluginId:record.id,projectRoot:scope.current,[field]:value,expected_revision:store.current?.revision}));
  };
  const requestReview=async(kind:PluginReviewKind,record:PluginRecord,sha256?:string)=>{
    if(operation.current)return;setError('');
    try {
      const root=scope.current;await reload();
      const detail=await window.reverie.request('inspectPlugin',{pluginId:record.id,projectRoot:root});
      const hash=kind==='activate'?sha256:kind==='rollback'?detail.record.previous_sha256:detail.record.active_sha256;
      const target=kind==='remove'?null:detail.record.candidates?.find(candidate=>candidate.sha256===hash)||detail.active;
      if(kind!=='remove'&&(!hash||!target||target.sha256!==hash))throw new Error('Inspect a managed version before approving this operation.');
      if(kind==='hooks'&&!target?.components.some(component=>component.kind==='hook'))throw new Error('This version has no inspected Hooks.');
      if(!alive.current||scope.current!==root)return;
      setReview({kind,inspection:detail,target,projectRoot:root,acknowledged:false,contentApproved:false,profileApproved:false});
    }catch(failure){if(alive.current)setError(message(failure));}
  };
  const confirmReview=async()=>{
    if(!review||operation.current)return;
    const required=pluginReviewRequirements(review);
    if(!review.acknowledged||(required.content&&!review.contentApproved)||(required.profile&&!review.profileApproved))return;
    if(scope.current!==review.projectRoot||store.current?.revision!==undefined&&store.current.revision!==review.inspection.revision){setError('Plugin state changed. Inspect this version again before approving it.');setReview(null);return;}
    const {record}=review.inspection;let action:PluginChangeAction,payload:CorePayload<PluginChangeAction>;
    if(review.kind==='activate') {
      action='activatePlugin';payload={plugin_id:record.id,candidate_sha256:review.target!.sha256,expected_revision:review.inspection.revision};
      if(required.content)payload.approved_sha256=review.target!.sha256;
      if(required.profile)payload.approved_profile_sha256=review.target!.approval_profile_sha256;
    } else {
      action=review.kind==='trust'?'setPluginTrust':review.kind==='hooks'?'setPluginHooks':review.kind==='rollback'?'rollbackPlugin':'removePlugin';
      payload={pluginId:record.id,projectRoot:review.projectRoot,expected_revision:review.inspection.revision};
      if(review.kind==='trust'){payload.trusted=true;payload.candidate_sha256=review.target!.sha256;payload.approval_profile_sha256=review.target!.approval_profile_sha256;}
      if(review.kind==='hooks'){payload.hooks_enabled=true;payload.approval_profile_sha256=review.target!.approval_profile_sha256;}
      if(review.kind==='rollback'&&required.profile)payload.approval_profile_sha256=review.target!.approval_profile_sha256;
      if(review.kind==='remove')payload.confirmed=true;
    }
    setReview(null);await mutate(action,record.name,()=>window.reverie.request(action,payload));
  };
  const cancel=async()=>{if(!pending?.operationId)return;try{await window.reverie.request('stopPluginOperation',{operation_id:pending.operationId});}catch(failure){if(alive.current)setError(message(failure));}};
  const current=loadedRoot.current===projectRoot?state:null;
  const selected=current?.records.find(record=>record.id===draft.pluginId)||null;
  const candidate=selected?.candidates?.find(value=>value.sha256===draft.candidateSha256)||selected?.candidates?.find(value=>value.sha256===selected.active_sha256)||selected?.candidates?.[0]||null;
  return {draft,patch,state:current,selected,candidate,inspection:inspection?.record.id===selected?.id?inspection:null,review,patchReview:(value:Partial<Pick<PluginReview,'acknowledged'|'contentApproved'|'profileApproved'>>)=>setReview(current=>current?{...current,...value}:current),closeReview:()=>setReview(null),loading,inspecting,error,pending,reload,prepare,update,control,requestReview,confirmReview,cancel};
}
export type PluginsController=ReturnType<typeof usePlugins>;
