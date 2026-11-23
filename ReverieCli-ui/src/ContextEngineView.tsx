import {useCallback,useEffect,useRef,useState} from 'react';
import {Database,FolderOpen,RefreshCw,Square,Trash2} from 'lucide-react';
import type {SemanticDevice,SemanticResourcesState} from './generated/core-types';
import type {CoreAction,CorePayload,CoreResponse} from './core-protocol';
import type {WorkspaceState} from './types';
import {useI18n} from './i18n';
import './context-engine.css';

export interface ContextResourceDraft {directory:string;digest:string;device:SemanticDevice;threads:number;query:string;strategy:'auto'|'basic'|'hybrid';results:CoreResponse<'queryContext'>['results']}
export const DEFAULT_CONTEXT_DRAFT:ContextResourceDraft={directory:'',digest:'',device:'cpu',threads:6,query:'',strategy:'auto',results:[]};
function object(value:unknown):Record<string,unknown> {return value&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{};}

export function ContextEngineView({projectRoot,engine,draft,updateDraft,updateEngine}:{projectRoot:string;engine:WorkspaceState['context_engine'];draft:ContextResourceDraft;updateDraft:(draft:ContextResourceDraft)=>void;updateEngine:(engine:NonNullable<WorkspaceState['context_engine']>)=>void}) {
  const {t}=useI18n();
  const [resources,setResources]=useState<SemanticResourcesState|null>(null);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [loading,setLoading]=useState(true);
  const [operation,setOperation]=useState('');
  const [automaticOperation,setAutomaticOperation]=useState('');
  const [watching,setWatching]=useState(false);
  const [watchSaving,setWatchSaving]=useState(false);
  const [phase,setPhase]=useState('');
  const [progress,setProgress]=useState<{completed:number;total:number}|null>(null);
  const [remove,setRemove]=useState<string|null>(null);
  const owner=useRef(projectRoot);owner.current=projectRoot;
  const callbacks=useRef({updateDraft,updateEngine});callbacks.current={updateDraft,updateEngine};
  const latestDraft=useRef(draft);latestDraft.current=draft;
  const patch=(value:Partial<ContextResourceDraft>)=>callbacks.current.updateDraft({...latestDraft.current,...value});
  const refresh=useCallback(async()=>{
    try {
      const [response,context,settings]=await Promise.all([window.reverie.request('getSemanticResources',{projectRoot}),window.reverie.request('getContextStatus',{projectRoot}),window.reverie.request('listSettings',{projectRoot})]);
      if(owner.current!==projectRoot)return;
      setResources(response.semantic);callbacks.current.updateEngine(context.context_engine);
      setWatching(settings.settings.items.find(item=>item.key==='auto_index')?.value===true);
    } catch(failure) {if(owner.current===projectRoot)setError(failure instanceof Error?failure.message:String(failure));}
    finally {if(owner.current===projectRoot)setLoading(false);}
  },[projectRoot]);
  useEffect(()=>{owner.current=projectRoot;setLoading(true);setResources(null);setError('');setNotice('');setAutomaticOperation('');setWatchSaving(false);void refresh();return()=>{owner.current='';};},[refresh,projectRoot]);
  useEffect(()=>window.reverie.onEvent(message=>{
    const event=object(message.event);
    if(event.type!=='context.progress'||event.project_root!==projectRoot)return;
    const finished=['finished','error','cancelled'].includes(String(event.phase));
    if(event.automatic===true)setAutomaticOperation(finished?'':String(event.operation_id||''));
    if(operation&&event.operation_id!==operation)return;
    setPhase(String(event.phase||''));setProgress({completed:Number(event.completed)||0,total:Number(event.total)||0});
    if(finished)void refresh();
  }),[operation,projectRoot,refresh]);
  const serverOperation=resources?.operations?.find(item=>item.project_root===projectRoot);
  const activeOperation=operation||automaticOperation||serverOperation?.operation_id||'';
  useEffect(()=>{
    if(!activeOperation)return;
    const timer=window.setInterval(()=>void refresh(),750);
    return ()=>window.clearInterval(timer);
  },[activeOperation,refresh]);
  async function execute<Action extends CoreAction>(action:Action,payload:CorePayload<Action>):Promise<CoreResponse<Action>|null> {
    const id=crypto.randomUUID();setOperation(id);setError('');setNotice('');setPhase('working');setProgress(null);
    try {
      const response=await window.reverie.request(action,Object.assign({},payload,{operationId:id,projectRoot}));
      if(owner.current!==projectRoot)return null;
      const fields=object(response);
      if(fields.semantic)setResources(fields.semantic as SemanticResourcesState);
      if(fields.context_engine)callbacks.current.updateEngine(fields.context_engine as NonNullable<WorkspaceState['context_engine']>);
      setNotice(fields.pending_restart?t("资源已停用，重启内核后可完成删除。"):t("操作完成"));
      return response;
    } catch(failure) {if(owner.current===projectRoot)setError(failure instanceof Error?failure.message:String(failure));return null;}
    finally {if(owner.current===projectRoot){setOperation('');setPhase('');setProgress(null);void refresh();}}
  }
  const selection={expectedRevision:resources?.revision,device:draft.device,threads:draft.threads};
  const models=object(resources?.models);
  const statusText=resources?.status==='resource_not_installed'?t("未安装语义资源"):resources?.status==='ready'?t("已预热"):resources?.status==='busy'||resources?.status==='verifying'?t("运行中"):resources?.status==='error'?t("不可用"):t("按需加载");
  const phaseText=phase==='structure'?t("正在建立结构索引"):phase==='embedding'?t("正在建立语义索引"):phase==='loading'||phase==='verifying_and_loading'?t("正在校验和加载资源"):phase==='finished'?t("操作完成"):t("运行中");
  const canInstall=/^[a-f0-9]{64}$/.test(draft.digest.trim().toLowerCase())&&draft.directory.trim()&&draft.threads>=1&&draft.threads<=256;
  const choose=async()=>{try {const directory=await window.reverie.selectSemanticBundle();if(directory&&owner.current===projectRoot)patch({directory});}catch(failure){setError(String(failure));}};
  async function setWatch(enabled:boolean) {
    setWatchSaving(true);setError('');
    try {await window.reverie.request('setSetting',{projectRoot,key:'auto_index',value:enabled});await refresh();}
    catch(failure){if(owner.current===projectRoot)setError(failure instanceof Error?failure.message:String(failure));}
    finally{if(owner.current===projectRoot)setWatchSaving(false);}
  }
  return <div className="catalog-page context-engine-page">
    <header className="page-header"><div className="page-title-icon"><Database size={20}/></div><div><h1>{t("上下文引擎")}</h1><p>{t("结构检索与语义重排在本机运行。")}</p></div><div className="page-header-action"><button type="button" className="secondary-button" onClick={()=>void refresh()}><RefreshCw size={14}/>{t("刷新")}</button></div></header>
    {loading&&<p role="status">{t("正在加载…")}</p>}
    {error&&<p role="alert" className="context-notice error">{error}</p>}
    {resources?.error&&<p role="alert" className="context-notice error">{resources.error}</p>}
    {engine?.watcher?.error&&<p role="alert" className="context-notice error">{engine.watcher.error}</p>}
    {engine?.semantic_index_error&&<p role="alert" className="context-notice error">{engine.semantic_index_error}</p>}
    {notice&&<p role="status" className="context-notice">{notice}</p>}
    {activeOperation&&<div className="context-notice" role="status"><span>{phaseText}{progress?.total?` · ${progress.completed}/${progress.total}`:''}</span>{progress&&progress.total>0&&<progress value={progress.completed} max={progress.total}/>}<button type="button" className="secondary-button" onClick={()=>void window.reverie.request('stopContextOperation',{operationId:activeOperation,projectRoot}).catch(failure=>setError(String(failure)))}><Square size={13}/>{t("停止")}</button></div>}
    <section className="context-section"><h2>{t("工作区索引")}</h2><label><input type="checkbox" checked={watching} disabled={loading||watchSaving} onChange={event=>void setWatch(event.target.checked)}/>{t("自动更新索引")}</label><p>{t("文件变化后自动更新结构索引和本地语义索引。")}{engine?.watcher?.status==='watching'?` · ${t("正在监听文件变化")}`:''}</p><dl className="context-metrics"><div><dt>{t("文件")}</dt><dd>{engine?.files??0}</dd></div><div><dt>{t("符号")}</dt><dd>{engine?.symbols??0}</dd></div><div><dt>{t("语义片段")}</dt><dd>{engine?.semantic_index?.vectors??0}</dd></div></dl><p>{engine?.semantic_index&&engine.semantic_index.revision!==engine.revision?t("语义索引正在追赶工作区修订，检索会过滤过期内容。"):engine?.ready?t("已建立索引"):t("尚未索引")}</p><div className="context-actions"><button type="button" className="secondary-button" disabled={Boolean(activeOperation)} onClick={()=>void execute('indexWorkspace',{})}>{t("更新结构索引")}</button><button type="button" className="secondary-button" disabled={Boolean(activeOperation)||!resources?.active} onClick={()=>void execute('indexSemanticWorkspace',{})}>{t("更新语义索引")}</button></div></section>
    <section className="context-section"><h2>{t("本地语义资源")}</h2><p>{statusText}{resources?.active?` · ${resources.active.version}`:''}{models.effective_device?` · ${String(models.effective_device)}`:''}</p>{typeof models.fallback_reason==='string'&&<p className="context-notice">{t("加速不可用，已回退 CPU。")} {models.fallback_reason}</p>}<div className="context-fields"><label>{t("资源包目录")}<span className="context-directory"><input value={draft.directory} onChange={event=>patch({directory:event.target.value})}/><button type="button" aria-label={t("选择语义资源包目录")} onClick={()=>void choose()}><FolderOpen size={16}/></button></span></label><label>{t("资源清单 SHA-256")}<input value={draft.digest} spellCheck={false} onChange={event=>patch({digest:event.target.value})}/></label><label>{t("计算设备")}<select value={draft.device} onChange={event=>patch({device:event.target.value as SemanticDevice})}><option value="cpu">CPU</option>{['win32','linux'].includes(window.reverie.platform)&&<option value="cuda">CUDA</option>}{window.reverie.platform==='win32'&&<option value="direct_ml">DirectML</option>}{window.reverie.platform==='darwin'&&<option value="core_ml">CoreML</option>}</select></label><label>{t("CPU 线程数")}<input type="number" min={1} max={256} value={draft.threads} onChange={event=>patch({threads:Number(event.target.value)})}/></label></div><p>{t("使用资源发行页提供的清单摘要；安装时校验完整内容并测试模型。")}</p><div className="context-actions"><button type="button" className="primary-button" disabled={!canInstall||Boolean(activeOperation)} onClick={()=>void execute('installSemanticResources',{...selection,directory:draft.directory.trim(),manifestSha256:draft.digest.trim().toLowerCase()})}>{t("安装并启用")}</button><button type="button" className="secondary-button" disabled={!resources?.active||Boolean(activeOperation)} onClick={()=>void execute('warmSemanticResources',{})}>{t("预热模型")}</button><button type="button" className="secondary-button" disabled={!resources?.active||Boolean(activeOperation)} onClick={()=>void execute('unloadSemanticModels',{})}>{t("释放模型内存")}</button><button type="button" className="secondary-button" disabled={!resources?.previous||Boolean(activeOperation)} onClick={()=>void execute('rollbackSemanticResources',{expectedRevision:resources?.revision})}>{t("回退上一版本")}</button><button type="button" className="secondary-button" disabled={!resources?.active||Boolean(activeOperation)} onClick={()=>void execute('disableSemanticResources',{expectedRevision:resources?.revision})}>{t("停用语义资源")}</button></div>
      <div className="context-resources">{resources?.records?.map(record=><article key={record.manifest_sha256}><div><strong>{record.version}</strong><small>{record.platform} · {record.architecture} · {(record.bytes/1048576).toFixed(1)} MiB{record.active?` · ${t("当前使用")}`:''}{record.removal_pending?` · ${t("等待内核重启")}`:''}</small><code>{record.manifest_sha256}</code></div><div className="context-actions"><button type="button" className="secondary-button" disabled={Boolean(activeOperation)||record.removal_pending} onClick={()=>void execute('selectSemanticResources',{...selection,manifestSha256:record.manifest_sha256})}>{record.active?t("应用设备设置"):t("启用")}</button><button type="button" className="secondary-button" aria-label={`${t("删除资源")} ${record.version}`} disabled={Boolean(activeOperation)} onClick={()=>setRemove(record.manifest_sha256)}><Trash2 size={14}/>{t("删除")}</button></div></article>)}</div>{resources?.inventory_errors?.map((message,index)=><p key={index} role="alert" className="context-notice error">{message}</p>)}
    </section>
    <section className="context-section"><h2>{t("检索工作区")}</h2><form onSubmit={event=>{event.preventDefault();void execute('queryContext',{query:draft.query,strategy:draft.strategy}).then(response=>{if(response)patch({results:response.results});});}}><div className="context-query"><label>{t("检索问题")}<textarea rows={3} value={draft.query} onChange={event=>patch({query:event.target.value})}/></label><label>{t("检索方式")}<select value={draft.strategy} onChange={event=>patch({strategy:event.target.value as ContextResourceDraft['strategy']})}><option value="auto">{t("自动")}</option><option value="basic">{t("基础检索")}</option><option value="hybrid">{t("混合检索与重排")}</option></select></label><button type="submit" className="primary-button" disabled={!draft.query.trim()||Boolean(operation)}>{t("检索")}</button></div></form><div className="context-evidence">{draft.results.map((hit,index)=><details key={`${hit.file_path}:${hit.start_line}:${index}`} open={index===0}><summary>{hit.file_path}:{hit.start_line}–{hit.end_line}<small>{hit.sources.join(' · ')}</small></summary><pre>{hit.content}</pre><small>{hit.content_hash}</small></details>)}</div></section>
    {remove&&<dialog className="context-remove" aria-labelledby="context-remove-title" ref={element=>{if(element&&!element.open)element.showModal();}} onCancel={()=>setRemove(null)}><h2 id="context-remove-title">{t("删除这个语义资源包？")}</h2><p>{t("正在使用它的任务会受到保护；已加载的运行库需要重启后才能删除。")}</p><div className="context-actions"><button type="button" className="secondary-button" autoFocus onClick={()=>setRemove(null)}>{t("取消")}</button><button type="button" className="primary-button" onClick={()=>{const digest=remove;setRemove(null);void execute('removeSemanticResources',{manifestSha256:digest,confirmed:true,expectedRevision:resources?.revision});}}>{t("确认删除")}</button></div></dialog>}
  </div>;
}
