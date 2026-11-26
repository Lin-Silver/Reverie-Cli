// @vitest-environment jsdom
import {useState} from 'react';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {MarketsView} from './MarketsView';
import {useMarkets} from './market-state';
import type {MarketEntry, MarketSource, MarketsState} from './generated/core-types';

afterEach(cleanup);
const source:MarketSource={id:'local',name:'Local fixture',kind:'directory',location:'workspace/catalog',manifest_path:'marketplace.json',builtin:false,enabled:true,status:'cached',error:'',content_sha256:'a'.repeat(64),source_commit:'',entry_count:40,next_cursor:''};
function setup(held=false){
  let state:MarketsState={revision:1,sources:[{...source}]};
  const entries:MarketEntry[]=Array.from({length:40},(_,index)=>({id:`local:entry-${index}`,market_id:'local',name:`entry-${index}`,description:`Native extension ${index}`,version:'1.0',source_kind:'relative',manifest:{source:`./plugins/entry-${index}`},catalog_sha256:'a'.repeat(64)}));
  let rejectRefresh:((error:Error)=>void)|undefined;
  const request=vi.fn(async(action:string,payload:Record<string,unknown>)=>{
    if(action==='listMarkets')return {type:'markets',markets:state};
    if(action==='queryMarket'){
      const items=entries.filter(entry=>`${entry.name} ${entry.description}`.includes(String(payload.query||''))),offset=Number(payload.offset||0);
      return {type:'market.entries',source:state.sources.find(item=>item.id===payload.market_id),items:items.slice(offset,offset+30),total:items.length,offset,next_offset:offset+30<items.length?offset+30:null,markets:state};
    }
    if(action==='refreshMarket'&&held)return await new Promise((_resolve,reject)=>{rejectRefresh=reject;});
    if(action==='stopMarketRefresh'){rejectRefresh?.(new Error('Download cancelled'));return {type:'market.control',market_id:payload.market_id,cancelled:true};}
    if(action==='addMarket'){
      const added={...source,id:'added',name:String(payload.name),location:String(payload.location),kind:payload.kind as MarketSource['kind'],status:'not_loaded',entry_count:0};
      state={revision:state.revision+1,sources:[...state.sources,added]};return {type:'market.updated',source:added,markets:state};
    }
    if(action==='setMarketEnabled'){
      state={revision:state.revision+1,sources:state.sources.map(item=>item.id===payload.market_id?{...item,enabled:Boolean(payload.enabled),status:payload.enabled?'cached':'disabled'}:item)};
      return {type:'market.updated',source:state.sources.find(item=>item.id===payload.market_id),markets:state};
    }
    throw new Error(`Unexpected request ${action}`);
  });
  window.reverie={request} as unknown as typeof window.reverie;
  function Harness(){const [visible,setVisible]=useState(true);const controller=useMarkets(visible);return <><button onClick={()=>setVisible(current=>!current)}>切页</button>{visible&&<MarketsView controller={controller}/>}</>;}
  return {request,Harness};
}
it('loads cached rows lazily, pages and filters them, and preserves the add draft on navigation',async()=>{
  const {request,Harness}=setup();render(<Harness/>);
  await screen.findByRole('heading',{name:/^entry-0/});
  expect(request.mock.calls.some(([action])=>action==='refreshMarket')).toBe(false);
  fireEvent.click(screen.getByRole('button',{name:'下一页'}));
  await screen.findByRole('heading',{name:/^entry-39/});
  expect(screen.queryByRole('heading',{name:/^entry-0/})).toBeNull();
  fireEvent.change(screen.getByLabelText('搜索已缓存的扩展'),{target:{value:'entry-39'}});
  await waitFor(()=>expect(document.querySelectorAll('.market-entries article')).toHaveLength(1));
  fireEvent.change(screen.getByLabelText('来源名称'),{target:{value:'Retained draft'}});
  fireEvent.change(screen.getByLabelText('来源地址或目录'),{target:{value:'retained/directory'}});
  fireEvent.click(screen.getByRole('button',{name:'切页'}));fireEvent.click(screen.getByRole('button',{name:'切页'}));
  expect((screen.getByLabelText('来源名称') as HTMLInputElement).value).toBe('Retained draft');
  expect((screen.getByLabelText('来源地址或目录') as HTMLInputElement).value).toBe('retained/directory');
  expect((screen.getByLabelText('搜索已缓存的扩展') as HTMLInputElement).value).toBe('entry-39');
});
it('keeps a running refresh and cancellation after leaving and returning to the page',async()=>{
  const {request,Harness}=setup(true);render(<Harness/>);await screen.findByRole('heading',{name:/^entry-0/});
  fireEvent.click(screen.getByRole('button',{name:'刷新目录 Local fixture'}));
  await screen.findByRole('button',{name:'停止'});
  fireEvent.click(screen.getByRole('button',{name:'切页'}));fireEvent.click(screen.getByRole('button',{name:'切页'}));
  fireEvent.click(screen.getByRole('button',{name:'停止'}));
  await waitFor(()=>expect(request).toHaveBeenCalledWith('stopMarketRefresh',{market_id:'local'}));
  await waitFor(()=>expect(screen.queryByRole('button',{name:'停止'})).toBeNull());
  expect(screen.getByRole('alert').textContent).toBe('Download cancelled');
  await screen.findByRole('heading',{name:/^entry-0/});
});
it('submits only an explicit complete source and retains the returned identity',async()=>{
  const {request,Harness}=setup();render(<Harness/>);await screen.findByRole('heading',{name:/^entry-0/});
  fireEvent.change(screen.getByLabelText('来源名称'),{target:{value:'New source'}});
  fireEvent.change(screen.getByLabelText('来源类型'),{target:{value:'directory'}});
  fireEvent.change(screen.getByLabelText('来源地址或目录'),{target:{value:'new/directory'}});
  expect(request.mock.calls.some(([action])=>action==='addMarket')).toBe(false);
  fireEvent.click(screen.getByRole('button',{name:'添加来源'}));
  await waitFor(()=>expect(request).toHaveBeenCalledWith('addMarket',{name:'New source',kind:'directory',location:'new/directory',manifest_path:undefined,expected_revision:1}));
  await screen.findByRole('button',{name:'New source'});
  expect((screen.getByLabelText('来源名称') as HTMLInputElement).value).toBe('');
  await act(async()=>{});
});
it('requires an explicit endpoint for a Registry entry with multiple remotes and preserves that choice',async()=>{
  const registrySource={...source,id:'registry',kind:'mcp_registry' as const,name:'Registry fixture'};
  const state:MarketsState={revision:1,sources:[registrySource]};
  const entry:MarketEntry={id:'registry:entry',market_id:'registry',name:'Remote fixture',description:'Two choices',version:'1.0',source_kind:'mcp_registry',catalog_sha256:'a'.repeat(64),manifest:{remotes:[{type:'streamable-http',url:'https://example.invalid/one'},{type:'sse',url:'https://example.invalid/two'}]}};
  const prepare=vi.fn();
  const request=vi.fn(async(action:string)=>action==='listMarkets'?{type:'markets',markets:state}:{type:'market.entries',source:registrySource,items:[entry],total:1,offset:0,next_offset:null,markets:state});
  window.reverie={request} as unknown as typeof window.reverie;
  function Harness(){const [visible,setVisible]=useState(true);const controller=useMarkets(visible);return <><button onClick={()=>setVisible(current=>!current)}>切页</button>{visible&&<MarketsView controller={controller} preparePlugin={prepare}/>}</>;}
  render(<Harness/>);await screen.findByRole('heading',{name:/^Remote fixture/});
  expect((screen.getByRole('button',{name:'准备安装 Remote fixture'}) as HTMLButtonElement).disabled).toBe(true);
  expect(prepare).not.toHaveBeenCalled();
  fireEvent.change(screen.getByRole('combobox',{name:'MCP 远端地址 Remote fixture'}),{target:{value:'https://example.invalid/two'}});
  fireEvent.click(screen.getByRole('button',{name:'切页'}));fireEvent.click(screen.getByRole('button',{name:'切页'}));
  expect((screen.getByRole('combobox',{name:'MCP 远端地址 Remote fixture'}) as HTMLSelectElement).value).toBe('https://example.invalid/two');
  fireEvent.click(screen.getByRole('button',{name:'准备安装 Remote fixture'}));
  expect(prepare).toHaveBeenCalledWith(entry,'https://example.invalid/two');
});
