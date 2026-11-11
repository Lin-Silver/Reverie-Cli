import {useCallback,useEffect,useState} from 'react';
import type {AiOState} from './core-protocol';

export function AiOPanel({open}:{open:(id:string,workspace?:string)=>void}){
  const [state,setState]=useState<AiOState|null>(null);
  const [memories,setMemories]=useState<Record<string,unknown>[]>([]);
  const [error,setError]=useState('');
  const refresh=useCallback(async()=>{try{const response=await window.reverie.request('aioState',{assistantId:'aio'});setState(response.aio);}catch(error){setError(String(error));}},[]);
  useEffect(()=>{void refresh();},[refresh]);
  const control=async(changes:{enabled?:boolean;proactive?:boolean;paused?:boolean},enable=false)=>{
    try{const response=await window.reverie.request('aioControl',{assistantId:'aio',enable,changes});setState(response.aio);setError('');}catch(error){setError(String(error));}
  };
  const memory=async(memoryId?:string,content?:string)=>{
    try{const response=await window.reverie.request('aioMemory',{assistantId:'aio',memoryId,content});setMemories(response.memories);setError('');}catch(error){setError(String(error));}
  };
  return <section className="settings-card" aria-label="AiO">
    <h2>AiO · 长期自主助手</h2>
    <p>切换工作区时保留同一个助手主线，任务在各自工作区开展。首次启用继承当前模型，之后可在 AiO 对话中独立选择模型。</p>
    <div className="settings-row">
      <button onClick={()=>void control({enabled:!state?.enabled},!state?.enabled)}>{state?.enabled?'停止 AiO':'启用 AiO'}</button>
      {state?.enabled && <><button onClick={()=>open(state.mainline_id)}>打开 AiO 对话</button><button onClick={()=>void control({paused:!state.paused})}>{state.paused?'恢复':'暂停'}</button></>}
    </div>
    <label><input type="checkbox" checked={state?.proactive ?? false} disabled={!state?.enabled} onChange={event=>void control({proactive:event.target.checked})}/> 主动发言与电脑观察</label>
    <p>关闭后停止主动观察、相关判断和发言窗，已开始的任务继续，结果保留在对话中。关闭主窗口可收进托盘；退出应用会保存状态并结束所属进程。</p>
    {state?.tasks.map(task=><div key={task.id}><button onClick={()=>open(task.branch,task.workspace)}>{task.branch}</button> · {task.state}</div>)}
    <button onClick={()=>void memory()}>查看长期记忆</button>
    {memories.map(item=><MemoryRow key={String(item.id)} item={item} save={content=>void memory(String(item.id),content)} remove={()=>void memory(String(item.id))}/>)}
    {error && <p role="alert">{error}</p>}
  </section>;
}

function MemoryRow({item,save,remove}:{item:Record<string,unknown>;save:(content:string)=>void;remove:()=>void}){
  const [text,setText]=useState(String(item.content || ''));
  return <div><small>{String(item.provenance || '')} · {String(item.confidence || '')}</small><textarea aria-label="记忆内容" value={text} onChange={event=>setText(event.target.value)}/><button onClick={()=>save(text)}>纠正</button><button onClick={remove}>删除</button></div>;
}
