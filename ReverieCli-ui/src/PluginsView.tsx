import {useRef} from 'react';
import {createPortal} from 'react-dom';
import {Download, Plug, RefreshCw, RotateCcw, Search, ShieldCheck, Square, Trash2, X} from 'lucide-react';
import {useI18n} from './i18n';
import {useDialogFocus} from './dialog-focus';
import {pluginReviewRequirements, type PluginsController, type PluginReview} from './plugin-state';
import type {PluginCandidate, PluginComponent} from './generated/core-types';
import './plugins.css';

const statusLabels:Record<string,string>={candidate:'待激活候选',trust_required:'等待信任',ready:'已启用',disabled:'已禁用'};
const verificationLabels:Record<string,string>={fixed_git:'固定 Git 修订',published_sha256:'已核对发布摘要',candidate_approval_required:'需要批准候选内容'};
const kindLabels:Record<string,string>={directory:'本地目录',archive:'归档文件或 URL',git:'Git 仓库',market:'市场条目'};
const componentLabels:Record<string,string>={skill:'技能',command:'命令',agent:'子代理',mcp:'MCP',hook:'Hooks',lsp:'语言服务',runtime:'运行时',configuration:'配置',app:'平台应用'};
const reviewLabels:Record<PluginReview['kind'],string>={activate:'激活这个版本',trust:'信任这个插件',hooks:'启用这些 Hooks',rollback:'回退到上一版本',remove:'移除这个插件'};

function PluginComponents({components,hooksOnly=false}:{components:PluginComponent[];hooksOnly?:boolean}) {
  const {t}=useI18n();
  return <div className="plugin-components">{components.filter(component=>!hooksOnly||component.kind==='hook').map((component,index)=><article key={`${component.kind}:${component.name}:${index}`}>
    <strong>{t(componentLabels[component.kind]||component.kind)} · {component.name}</strong>{component.description&&<p>{component.description}</p>}
    {component.path&&<code>{component.path}</code>}{component.requires_platform&&<p>{t("需要对应的平台应用")}</p>}
    <pre>{JSON.stringify(component.policy,null,2)}</pre>
  </article>)}</div>;
}
export function PluginCandidateDetails({candidate,hooksOnly=false}:{candidate:PluginCandidate;hooksOnly?:boolean}) {
  const {t}=useI18n();
  return <div className="plugin-candidate-details">
    <dl><div><dt>{t("版本")}</dt><dd>{candidate.version||'—'} · {candidate.bytes.toLocaleString()} {t("字节")}</dd></div>
      <div><dt>SHA-256</dt><dd><code>{candidate.sha256}</code></dd></div><div><dt>{t("完整性依据")}</dt><dd>{t(verificationLabels[candidate.verification]||candidate.verification)}</dd></div>
      <div><dt>{t("发布者签名密钥")}</dt><dd><code>{candidate.signing_key||t("未提供签名")}</code></dd></div>
      <div><dt>{t("执行范围摘要")}</dt><dd><code>{candidate.approval_profile_sha256}</code></dd></div>
      <div><dt>{t("许可证")}</dt><dd>{candidate.license||t("未声明")}{candidate.license_files.length>0&&<ul>{candidate.license_files.map(file=><li key={file}>{file}</li>)}</ul>}</dd></div>
    </dl>
    <details className="plugin-provenance"><summary>{t("来源身份")}</summary><pre>{JSON.stringify(candidate.source,null,2)}</pre></details>
    <details className="plugin-approval-profile"><summary>{t("权限、依赖与条款")}</summary><pre>{JSON.stringify(candidate.approval,null,2)}</pre></details>
    <h3>{t(hooksOnly?'Hooks 事件、入口与权限':'组件清单')}</h3><PluginComponents components={candidate.components} hooksOnly={hooksOnly}/>
  </div>;
}
function PluginReviewDialog({controller:c}:{controller:PluginsController}) {
  const {t}=useI18n(),dialog=useRef<HTMLFormElement>(null);useDialogFocus(dialog,c.closeReview);
  const review=c.review!;const required=pluginReviewRequirements(review),valid=review.acknowledged&&(!required.content||review.contentApproved)&&(!required.profile||review.profileApproved);
  return createPortal(<div className="modal-backdrop" onMouseDown={c.closeReview}>
    <form ref={dialog} className="plugin-review-dialog" role="alertdialog" aria-modal="true" aria-labelledby="plugin-review-title" tabIndex={-1} onMouseDown={event=>event.stopPropagation()} onSubmit={event=>{event.preventDefault();if(valid)void c.confirmReview();}}>
      <header><div><h2 id="plugin-review-title">{t(reviewLabels[review.kind])}</h2><p>{review.inspection.record.name}</p></div><button type="button" className="icon-button" aria-label={t("关闭")} onClick={c.closeReview}><X size={18}/></button></header>
      {review.target&&<PluginCandidateDetails candidate={review.target} hooksOnly={review.kind==='hooks'}/>}
      {required.profile&&<section className="plugin-profile-change"><h3>{t("执行范围发生变化")}</h3><div><strong>{t("当前执行范围")}</strong><pre>{JSON.stringify(review.inspection.active?.approval,null,2)}</pre></div><div><strong>{t("候选执行范围")}</strong><pre>{JSON.stringify(review.target?.approval,null,2)}</pre></div></section>}
      {review.kind==='remove'&&<p>{t("移除插件的激活记录及组件注册。")}</p>}
      {review.kind==='activate'&&<p>{t("激活后仍需单独信任和启用新插件。")}</p>}
      {review.kind==='trust'&&<p>{t("信任绑定上述版本与执行范围；受信任插件默认自动更新。")}</p>}
      {review.kind==='hooks'&&<p>{t("Hooks 可响应上述事件并执行列出的入口。")}</p>}
      <div className="plugin-review-checks">
        {required.content&&<label><input type="checkbox" checked={review.contentApproved} onChange={event=>c.patchReview({contentApproved:event.target.checked})}/>{t("批准上述候选 SHA-256")}</label>}
        {required.profile&&<label><input type="checkbox" checked={review.profileApproved} onChange={event=>c.patchReview({profileApproved:event.target.checked})}/>{t("批准上述执行范围变化")}</label>}
        <label><input type="checkbox" checked={review.acknowledged} onChange={event=>c.patchReview({acknowledged:event.target.checked})}/>{t("我已审阅并确认本次操作")}</label>
      </div>
      <footer><button type="button" className="secondary-button" onClick={c.closeReview}>{t("取消")}</button><button type="submit" className="primary-button" disabled={!valid}>{t("确认操作")}</button></footer>
    </form>
  </div>,document.body);
}
export function PluginsView({controller:c,actions}:{controller:PluginsController;actions?:string[]}) {
  const {t}=useI18n();const {draft,selected,candidate,pending}=c;
  const busy=Boolean(pending)||c.loading,managed=actions===undefined||actions.includes('preparePlugin');
  const visible=c.state?.records.filter(record=>`${record.name} ${record.id} ${record.family}`.toLowerCase().includes(draft.query.toLowerCase()))||[];
  const installed=Boolean(selected?.active_sha256),activeVersion=selected?.candidates?.find(value=>value.sha256===selected.active_sha256)||c.inspection?.active,hasHooks=Boolean(activeVersion?.components.some(component=>component.kind==='hook'));
  return <div className="catalog-page plugins-page">
    <header className="page-header"><div className="page-title-icon"><Plug size={20}/></div><div><h1>{t("插件")}</h1><p>{t("准备并审核版本，管理插件信任、启用和更新。")}</p></div><div className="page-header-action"><button type="button" className="secondary-button" disabled={c.loading} onClick={()=>void c.reload(true)}><RefreshCw size={14}/>{t("重新扫描")}</button></div></header>
    {c.error&&<p className="market-notice error" role="alert">{c.error}</p>}{c.loading&&<p role="status">{t("正在加载…")}</p>}
    {pending&&<div className="market-notice" role="status"><span>{t(pending.operationId?'正在准备插件候选':'正在保存插件状态')} · {pending.label}</span>{pending.operationId&&<button type="button" className="secondary-button" onClick={()=>void c.cancel()}><Square size={13}/>{t("停止")}</button>}</div>}
    <details className="plugin-prepare"><summary><Download size={15}/>{t("从来源准备安装")}</summary>
      {!managed&&<p>{t("当前内核不支持受管插件安装。")}</p>}
      <form onSubmit={event=>{event.preventDefault();void c.prepare();}}><fieldset disabled={busy||!managed}><div className="plugin-source-fields">
        <label>{t("来源类型")}<select value={draft.kind} onChange={event=>c.patch({kind:event.target.value as typeof draft.kind})}>{Object.entries(kindLabels).map(([kind,label])=><option value={kind} key={kind}>{t(label)}</option>)}</select></label>
        <label>{t("来源地址、目录或市场条目 ID")}<input required spellCheck={false} value={draft.location} onChange={event=>c.patch({location:event.target.value})}/></label>
        {draft.kind==='market'&&<label>{t("目录中的 MCP 地址（可选）")}<input spellCheck={false} value={draft.endpoint} onChange={event=>c.patch({endpoint:event.target.value})}/></label>}
      </div><details><summary>{t("固定修订与校验要求")}</summary><div className="plugin-source-fields">
        <label>{t("固定修订（可选）")}<input value={draft.revision} onChange={event=>c.patch({revision:event.target.value})}/></label><label>{t("包内目录（可选）")}<input value={draft.subdirectory} onChange={event=>c.patch({subdirectory:event.target.value})}/></label>
        <label>{t("预期 SHA-256（可选）")}<input spellCheck={false} value={draft.sha256} onChange={event=>c.patch({sha256:event.target.value})}/></label><label>{t("发布者密钥（可选）")}<input spellCheck={false} value={draft.signingKey} onChange={event=>c.patch({signingKey:event.target.value})}/></label>
        <label className="plugin-checkbox"><input type="checkbox" checked={draft.requireSignature} onChange={event=>c.patch({requireSignature:event.target.checked})}/>{t("要求发布者签名")}</label>
      </div></details><button type="submit" className="primary-button" disabled={!draft.location.trim()}><Download size={14}/>{t("准备候选")}</button></fieldset></form>
    </details>
    <div className="plugins-layout"><section className="plugin-selection"><label className="plugin-search"><Search size={14}/><input aria-label={t("筛选插件")} placeholder={t("筛选插件")} value={draft.query} onChange={event=>c.patch({query:event.target.value})}/></label>
      {visible.map(record=><button type="button" className={`plugin-selector ${record.id===selected?.id?'selected':''}`} key={record.id} onClick={()=>c.patch({pluginId:record.id,candidateSha256:''})} aria-pressed={record.id===selected?.id}><strong>{record.name}</strong><small>{record.version||'—'} · {t(statusLabels[record.status]||record.status_label||record.status)}</small></button>)}
      {!visible.length&&!c.loading&&<p className="muted">{t("没有匹配的插件。")}</p>}
    </section><section className="plugin-detail" data-plugin-id={selected?.id}>
      {selected?<><header><div><h2>{selected.name}</h2><code>{selected.id}</code><p>{selected.family} · {t(statusLabels[selected.status]||selected.status_label||selected.status)}</p></div><button type="button" className="secondary-button" disabled={busy} onClick={()=>void c.requestReview('remove',selected)}><Trash2 size={14}/>{t("移除")}</button></header>
        <div className="plugin-control-grid">
          <label><span>{t("信任执行范围")}</span><input type="checkbox" aria-label={t("信任执行范围")} checked={selected.trusted} disabled={busy||(!installed&&!selected.trusted)} onChange={event=>{if(event.target.checked)void c.requestReview('trust',selected);else void c.control('setPluginTrust',selected,false);}}/></label>
          <label><span>{t("在当前项目启用")}</span><input type="checkbox" aria-label={t("在当前项目启用")} checked={selected.enabled} disabled={busy||(!selected.trusted&&!selected.enabled)} onChange={event=>void c.control('setPluginEnabled',selected,event.target.checked)}/></label>
          <label><span>{t("自动更新")}</span><input type="checkbox" aria-label={t("自动更新")} checked={Boolean(selected.auto_update)} disabled={busy||!installed||(!selected.trusted&&!selected.auto_update)} onChange={event=>void c.control('setPluginAutoUpdate',selected,event.target.checked)}/></label>
          <label><span>Hooks</span><input type="checkbox" aria-label="Hooks" checked={Boolean(selected.hooks_enabled)} disabled={busy||!installed||!hasHooks||!selected.trusted} onChange={event=>{if(event.target.checked)void c.requestReview('hooks',selected);else void c.control('setPluginHooks',selected,false);}}/></label>
        </div>
        <div className="plugin-version-actions"><button type="button" className="secondary-button" disabled={busy||!installed||!managed} onClick={()=>void c.update(selected)}><RefreshCw size={14}/>{t("准备更新")}</button><button type="button" className="secondary-button" disabled={busy||!selected.previous_sha256} onClick={()=>void c.requestReview('rollback',selected)}><RotateCcw size={14}/>{t("回退")}</button></div>
        {c.inspecting&&<p role="status">{t("正在读取插件详情")}</p>}
        {selected.candidates?.length?<><label className="plugin-candidate-choice">{t("查看版本候选")}<select aria-label={t("查看版本候选")} value={candidate?.sha256||''} onChange={event=>c.patch({candidateSha256:event.target.value})}>{selected.candidates.map(version=><option key={version.sha256} value={version.sha256}>{version.version||'—'} · {version.sha256.slice(0,12)}{version.sha256===selected.active_sha256?` · ${t("当前版本")}`:''}</option>)}</select></label>
          {candidate&&<><PluginCandidateDetails candidate={candidate}/>{candidate.sha256!==selected.active_sha256&&<button type="button" className="primary-button" disabled={busy||!managed} onClick={()=>void c.requestReview('activate',selected,candidate.sha256)}><ShieldCheck size={14}/>{t("审阅并激活")}</button>}</>}
        </>:activeVersion?<><h3>{t("当前版本")}</h3><PluginCandidateDetails candidate={activeVersion}/></>:<><p>{t("此插件没有受管版本候选。")}</p><code>{selected.install_dir}</code></>}
      </>:<div className="empty-panel"><Plug size={26}/><strong>{t("选择插件或准备安装来源。")}</strong></div>}
    </section></div>
    {c.review&&<PluginReviewDialog controller={c}/>}
  </div>;
}
