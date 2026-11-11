import { afterEach, expect, it, vi } from 'vitest';

vi.mock('electron',()=>({powerMonitor:{getSystemIdleTime:()=>10}}));
vi.mock('./aio-window',()=>({AiOWindow:class {enqueue=vi.fn();stop=()=>[];}}));
import { AiOHost } from './aio-host';

afterEach(()=>vi.restoreAllMocks());

it('processes a persisted reply that arrives during judgment without a second observation',async()=>{
  const signals:Record<string,unknown>[]=[{event_id:'first',type:'task.result'}];
  const state={enabled:true,paused:false,proactive:false};
  const request=vi.fn(async(action:string,payload:Record<string,unknown>)=>{
    if(action==='aioState')return {aio:state};
    if(action==='aioPendingSignals')return {signals:[...signals]};
    if(action==='aioAcknowledgeSignal'){signals.splice(signals.findIndex(item=>item.event_id===payload.eventId),1);return {saved:true};}
    if(action==='aioMessages')return {messages:[]};
    throw new Error(`Unexpected action ${action}`);
  });
  let finish:()=>void=()=>{};
  const gate=new Promise<void>(resolve=>{finish=resolve;});
  const decide=vi.fn(async(_action:string,payload:Record<string,unknown>)=>{
    if((payload.observation as Record<string,unknown>).event_id==='first')await gate;
    return {decision:{tasks:[]}};
  });
  const host=new AiOHost(request,decide,vi.fn(),()=>[],vi.fn(),vi.fn());
  const running=host.tick(undefined,true);
  await vi.waitFor(()=>expect(decide).toHaveBeenCalledTimes(1));
  signals.push({event_id:'reply',type:'user.reply'});
  await host.tick(undefined,true);
  finish();await running;
  expect(decide).toHaveBeenCalledTimes(2);
  expect(signals).toEqual([]);
  expect(request.mock.calls.some(([action])=>action==='aioObserve')).toBe(false);
});

it('retains a failed judgment for recovery and does not retry in a busy loop',async()=>{
  const signal={event_id:'reply',type:'user.reply'};
  const request=vi.fn(async(action:string)=>action==='aioState'?{aio:{enabled:true,paused:false,proactive:false}}:{signals:[signal]});
  const decide=vi.fn(async()=>{throw new Error('rate limited');});
  const host=new AiOHost(request,decide,vi.fn(),()=>[],vi.fn(),vi.fn());
  await expect(host.tick(undefined,true)).rejects.toThrow('rate limited');
  expect(decide).toHaveBeenCalledTimes(1);
  expect(request.mock.calls.some(([action])=>action==='aioAcknowledgeSignal')).toBe(false);
});

it('cancels an active observation decision when proactive assistance is disabled',async()=>{
  const state={enabled:true,paused:false,proactive:true};
  const request=vi.fn(async(action:string)=>{
    if(action==='aioState')return {aio:state};
    if(action==='aioPendingSignals')return {signals:[]};
    if(action==='aioPendingTasks')return {tasks:[]};
    if(action==='aioMessages')return {messages:[]};
    if(action==='aioObserve')return {observation:{source:'qualification'}};
    throw new Error(`Unexpected action ${action}`);
  });
  let reject:(error:Error)=>void=()=>{};
  const decide=vi.fn(()=>new Promise<Record<string,unknown>>((_resolve,fail)=>{reject=fail;}));
  const cancel=vi.fn(async()=>{reject(new Error('Cancelled observation'));});
  const execute=vi.fn();
  const report=vi.fn();
  const host=new AiOHost(request,decide,execute,()=>[],vi.fn(),report,cancel);
  const running=host.tick();
  await vi.waitFor(()=>expect(decide).toHaveBeenCalledTimes(1));
  state.proactive=false;
  await host.controlsChanged();
  await running;
  host.stop();
  expect(cancel).toHaveBeenCalledTimes(1);
  expect(execute).not.toHaveBeenCalled();
  expect(report).not.toHaveBeenCalled();
  expect(decide).toHaveBeenCalledTimes(1);
});
