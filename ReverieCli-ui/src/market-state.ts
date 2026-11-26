import {useCallback, useEffect, useRef, useState} from 'react';
import type {CoreResponse} from './core-protocol';
import type {MarketKind, MarketsState} from './generated/core-types';

type MarketPage = CoreResponse<'queryMarket'>;
export interface MarketDraft {name:string;kind:MarketKind;location:string;manifestPath:string;marketId:string;query:string;offset:number;remoteEndpoints:Record<string,string>}
const initialDraft:MarketDraft={name:'',kind:'git',location:'',manifestPath:'',marketId:'',query:'',offset:0,remoteEndpoints:{}};
function message(error:unknown){return error instanceof Error?error.message:String(error);}

export function useMarkets(active:boolean) {
  const [draft,setDraft]=useState(initialDraft);
  const [state,setState]=useState<MarketsState|null>(null);
  const [page,setPage]=useState<MarketPage|null>(null);
  const [loading,setLoading]=useState(false);
  const [queryLoading,setQueryLoading]=useState(false);
  const [pending,setPending]=useState<{id:string;kind:'refresh'|'change'}|null>(null);
  const [error,setError]=useState('');
  const alive=useRef(true), latest=useRef(draft), currentState=useRef(state), queryGeneration=useRef(0), operation=useRef(false);
  latest.current=draft;currentState.current=state;
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;queryGeneration.current++;};},[]);
  const accept=useCallback((value:MarketsState)=>{if(alive.current)setState(current=>!current||value.revision>=current.revision?value:current);},[]);
  const patch=useCallback((value:Partial<MarketDraft>)=>setDraft(current=>({...current,...value})),[]);
  const refresh=useCallback(async()=>{
    setLoading(true);setError('');
    try {
      const response=await window.reverie.request('listMarkets',{});
      if(!alive.current)return;
      accept(response.markets);
      setDraft(current=>response.markets.sources.some(source=>source.id===current.marketId)?current:{...current,marketId:response.markets.sources[0]?.id||'',query:'',offset:0});
    }catch(failure){if(alive.current)setError(message(failure));}
    finally{if(alive.current)setLoading(false);}
  },[accept]);
  useEffect(()=>{if(active)void refresh();},[active,refresh]);
  useEffect(()=>{
    const generation=++queryGeneration.current;
    if(!active||!draft.marketId){setQueryLoading(false);return;}
    setQueryLoading(true);
    const timer=setTimeout(()=>{
      void window.reverie.request('queryMarket',{market_id:draft.marketId,query:draft.query,offset:draft.offset,limit:30}).then(response=>{
        if(!alive.current||generation!==queryGeneration.current)return;
        setPage(response);accept(response.markets);
      }).catch(failure=>{if(alive.current&&generation===queryGeneration.current)setError(message(failure));}).finally(()=>{if(alive.current&&generation===queryGeneration.current)setQueryLoading(false);});
    },120);
    return()=>clearTimeout(timer);
  },[active,draft.marketId,draft.query,draft.offset,state?.revision,accept]);
  const mutate=async(id:string,kind:'refresh'|'change',work:()=>Promise<{markets:MarketsState}>)=>{
    if(operation.current)return;
    operation.current=true;setPending({id,kind});setError('');
    try {const result=await work();accept(result.markets);}
    catch(failure){await refresh();if(alive.current)setError(message(failure));}
    finally{operation.current=false;if(alive.current)setPending(null);}
  };
  const add=()=>{
    const submitted={...latest.current};
    return mutate('add','change',async()=>{
      const response=await window.reverie.request('addMarket',{name:submitted.name.trim(),kind:submitted.kind,location:submitted.location.trim(),manifest_path:submitted.manifestPath.trim()||undefined,expected_revision:currentState.current?.revision});
      if(alive.current)setDraft(current=>({...current,marketId:response.source.id,query:'',offset:0,...(current.name===submitted.name&&current.location===submitted.location&&current.manifestPath===submitted.manifestPath?{name:'',location:'',manifestPath:''}:{})}));
      return response;
    });
  };
  const remove=(id:string)=>mutate(id,'change',async()=>{
    const response=await window.reverie.request('removeMarket',{market_id:id,expected_revision:currentState.current?.revision});
    if(alive.current)setDraft(current=>current.marketId===id?{...current,marketId:response.markets.sources[0]?.id||'',query:'',offset:0}:current);
    return response;
  });
  const enable=(id:string,enabled:boolean)=>mutate(id,'change',()=>window.reverie.request('setMarketEnabled',{market_id:id,enabled,expected_revision:currentState.current?.revision}));
  const fetch=(id:string,cursor?:string)=>mutate(id,'refresh',()=>window.reverie.request('refreshMarket',{market_id:id,cursor,expected_revision:currentState.current?.revision}));
  const cancel=async()=>{
    if(pending?.kind!=='refresh')return;
    try {await window.reverie.request('stopMarketRefresh',{market_id:pending.id});}
    catch(failure){if(alive.current)setError(message(failure));}
  };
  return {draft,patch,state,page,loading,queryLoading,pending,error,refresh,add,remove,enable,fetch,cancel};
}
export type MarketsController=ReturnType<typeof useMarkets>;
