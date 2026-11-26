import {Globe, Plus, RefreshCw, Search, Square, Trash2} from 'lucide-react';
import {useI18n} from './i18n';
import type {MarketEntry,MarketKind} from './generated/core-types';
import type {MarketsController} from './market-state';
import './markets.css';

const statusLabels:Record<string,string>={not_loaded:'尚未加载',ready:'已更新',cached:'使用缓存',cached_error:'更新失败，保留缓存',error:'无法加载',disabled:'已禁用'};
const kindLabels:Record<MarketKind,string>={git:'Git 仓库',directory:'本地目录',manifest:'清单 URL',mcp_registry:'MCP Registry'};

export function registryEndpoints(entry:MarketEntry):Array<{url:string;type:string}> {
  if(entry.source_kind!=='mcp_registry'||!entry.manifest||typeof entry.manifest!=='object'||Array.isArray(entry.manifest))return [];
  const remotes=entry.manifest.remotes;if(!Array.isArray(remotes))return [];
  return remotes.flatMap(remote=>remote&&typeof remote==='object'&&!Array.isArray(remote)&&typeof remote.url==='string'?[{url:remote.url,type:typeof remote.type==='string'?remote.type:''}]:[]);
}
export function MarketsView({controller:c,preparePlugin,pluginBusy=false}:{controller:MarketsController;preparePlugin?:(entry:MarketEntry,endpoint?:string)=>void;pluginBusy?:boolean}) {
  const {t}=useI18n();
  const {draft,patch,state,page,pending}=c;
  const selected=state?.sources.find(source=>source.id===draft.marketId);
  const currentPage=page?.source.id===selected?.id?page:null;
  const busy=Boolean(pending);
  return <div className="catalog-page markets-page">
    <header className="page-header"><div className="page-title-icon"><Globe size={20}/></div><div><h1>{t("扩展市场")}</h1><p>{t("管理来源并浏览插件、技能和 MCP 服务。")}</p></div><div className="page-header-action"><button type="button" className="secondary-button" onClick={()=>void c.refresh()} disabled={c.loading}><RefreshCw size={14}/>{t("刷新来源列表")}</button></div></header>
    {c.loading&&<p role="status">{t("正在加载…")}</p>}
    {c.error&&<p role="alert" className="market-notice error">{c.error}</p>}
    {pending&&<div role="status" className="market-notice"><span>{pending.kind==='refresh'?`${t("正在刷新目录")} · ${state?.sources.find(source=>source.id===pending.id)?.name||pending.id}`:t("正在保存来源")}</span>{pending.kind==='refresh'&&<button type="button" className="secondary-button" onClick={()=>void c.cancel()}><Square size={13}/>{t("停止")}</button>}</div>}
    <section className="market-section" aria-labelledby="market-sources-title">
      <h2 id="market-sources-title">{t("市场来源")}</h2>
      <div className="market-sources">{state?.sources.map(source=><article key={source.id} className={source.id===selected?.id?'selected':''} data-market-id={source.id}>
        <div className="market-source-info"><button type="button" className="market-source-name" onClick={()=>patch({marketId:source.id,query:'',offset:0})} aria-pressed={source.id===selected?.id}>{source.name}</button><small>{t(kindLabels[source.kind])} · {t(source.builtin?'内置来源':'手动来源')} · {t(statusLabels[source.status]||source.status)} · {source.entry_count} {t("条目")}</small><code>{source.location}</code>{source.error&&<p className="market-source-error">{source.error}</p>}</div>
        <div className="market-actions"><label><input type="checkbox" aria-label={`${t("启用来源")} ${source.name}`} checked={source.enabled} disabled={busy} onChange={event=>void c.enable(source.id,event.target.checked)}/>{t("启用")}</label><button type="button" className="secondary-button" aria-label={`${t("刷新目录")} ${source.name}`} disabled={busy||!source.enabled} onClick={()=>void c.fetch(source.id)}><RefreshCw size={13}/>{t("刷新目录")}</button>{!source.builtin&&<button type="button" className="secondary-button" aria-label={`${t("移除来源")} ${source.name}`} disabled={busy} onClick={()=>void c.remove(source.id)}><Trash2 size={13}/></button>}</div>
      </article>)}</div>
      <details className="market-add"><summary><Plus size={15}/>{t("添加市场来源")}</summary><form onSubmit={event=>{event.preventDefault();void c.add();}}><fieldset disabled={busy}>
        <div className="market-fields"><label>{t("来源名称")}<input required value={draft.name} onChange={event=>patch({name:event.target.value})}/></label><label>{t("来源类型")}<select value={draft.kind} onChange={event=>patch({kind:event.target.value as MarketKind})}>{Object.entries(kindLabels).map(([kind,label])=><option key={kind} value={kind}>{t(label)}</option>)}</select></label><label className="market-wide-field">{t("来源地址或目录")}<input required value={draft.location} spellCheck={false} onChange={event=>patch({location:event.target.value})}/></label><label className="market-wide-field">{t("清单相对路径（可选）")}<input value={draft.manifestPath} spellCheck={false} onChange={event=>patch({manifestPath:event.target.value})}/></label></div>
        <button type="submit" className="primary-button" disabled={!draft.name.trim()||!draft.location.trim()}><Plus size={14}/>{t("添加来源")}</button>
      </fieldset></form></details>
    </section>
    <section className="market-section" aria-labelledby="market-catalog-title">
      <div className="market-catalog-header"><h2 id="market-catalog-title">{selected?.name||t("目录")}</h2><label className="market-search"><Search size={14}/><input aria-label={t("搜索已缓存的扩展")} value={draft.query} onChange={event=>patch({query:event.target.value,offset:0})} placeholder={t("搜索已缓存的扩展")}/></label></div>
      {selected&&<details className="market-identity"><summary>{t("来源版本与内容身份")}</summary><dl><div><dt>{t("来源标识")}</dt><dd>{selected.id}</dd></div>{selected.source_commit&&<div><dt>Git commit</dt><dd>{selected.source_commit}</dd></div>}{selected.content_sha256&&<div><dt>SHA-256</dt><dd>{selected.content_sha256}</dd></div>}{selected.manifest_path&&<div><dt>{t("清单路径")}</dt><dd>{selected.manifest_path}</dd></div>}</dl></details>}
      {c.queryLoading&&<p role="status">{t("正在查询目录")}</p>}
      {!c.queryLoading&&!currentPage?.items.length&&<p className="market-empty">{selected?.status==='not_loaded'?t("刷新这个来源以加载目录。"):t("当前缓存中没有匹配条目。")}</p>}
      <div className="market-entries" aria-busy={c.queryLoading}>{currentPage?.items.map(entry=>{
        const endpoints=registryEndpoints(entry),registry=entry.source_kind==='mcp_registry';
        const endpoint=draft.remoteEndpoints[entry.id]||(endpoints.length===1?endpoints[0].url:'');
        return <article key={entry.id}><h3>{entry.name}{entry.version&&<small>{entry.version}</small>}</h3>{entry.description&&<p>{entry.description}</p>}<details><summary>{t("查看来源与组件清单")}</summary><code>{entry.id}</code><pre>{JSON.stringify(entry.manifest,null,2)}</pre><small>SHA-256 · {entry.catalog_sha256}</small></details>
          {preparePlugin&&<div className="market-install-actions">{registry&&(endpoints.length?<label>{t("MCP 远端地址")}<select aria-label={`${t("MCP 远端地址")} ${entry.name}`} value={endpoint} onChange={event=>patch({remoteEndpoints:{...draft.remoteEndpoints,[entry.id]:event.target.value}})}><option value="">{t("选择目录中的远端地址")}</option>{endpoints.map((remote,index)=><option value={remote.url} key={`${remote.url}:${index}`}>{remote.type} · {remote.url}</option>)}</select></label>:<p>{t("此条目需先配置外部包运行时。")}</p>)}<button type="button" className="secondary-button" aria-label={`${t("准备安装")} ${entry.name}`} disabled={pluginBusy||busy||registry&&!endpoint} onClick={()=>preparePlugin(entry,endpoint||undefined)}>{t("准备安装")}</button></div>}
        </article>;
      })}</div>
      <div className="market-pagination"><span>{currentPage?`${currentPage.offset+Math.min(1,currentPage.items.length)}–${currentPage.offset+currentPage.items.length} / ${currentPage.total}`:'0'}</span><button type="button" className="secondary-button" disabled={draft.offset===0||c.queryLoading} onClick={()=>patch({offset:Math.max(0,draft.offset-30)})}>{t("上一页")}</button><button type="button" className="secondary-button" disabled={currentPage?.next_offset==null||c.queryLoading} onClick={()=>patch({offset:currentPage?.next_offset??0})}>{t("下一页")}</button>{selected?.next_cursor&&<button type="button" className="secondary-button" disabled={busy||!selected.enabled} onClick={()=>void c.fetch(selected.id,selected.next_cursor)}>{t("加载更多远端条目")}</button>}</div>
    </section>
  </div>;
}
