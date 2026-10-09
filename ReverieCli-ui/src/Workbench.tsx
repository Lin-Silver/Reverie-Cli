import { useCallback, useEffect, useRef, useState } from "react";
import { FileText, GitBranch, PanelRightClose, RefreshCw, Search, ShieldCheck, X } from "lucide-react";
import type { DiffScope, FilePatch, GitFile, GitSnapshot, PushPlan } from "../electron/workbench";
import { useI18n } from "./i18n";

import { FileBrowser } from "./FileBrowser";
export { parseFileLink } from "./file-links";

const statusLabels: Record<string, string> = { M: "已修改", A: "已新增", D: "已删除", R: "已重命名", C: "已复制", "?": "未跟踪", U: "冲突" };

export interface Finding { priority: string; title: string; path: string; line: number; trigger: string; expected: string; actual: string; evidence: string; viewed?: boolean; resolved?: boolean }
export interface ReviewRecord { id: string; version: string; scope: string; createdAt: string; output: string; findings: Finding[]; formatError?: string }
const labels:Record<DiffScope,string>={working:"未暂存",staged:"已暂存",commit:"提交",branch:"分支比较",round:"AI 轮次"};
class StaleRequest extends Error {}

export function reviewLocations(diff:string):Set<number> {
  const lines=new Set<number>();let old=0;let next=0;let hunk=false;
  for(const line of diff.split("\n")) {
    const header=/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(line);
    if(header){old=Number(header[1]);next=Number(header[2]);hunk=true;continue;}
    if(!hunk || !/^[ +\-]/.test(line) || line.startsWith("+++") || line.startsWith("---"))continue;
    if(line.startsWith("-")){if(old>0)lines.add(old);old++;}
    else if(line.startsWith("+")){if(next>0)lines.add(next);next++;}
    else {if(next>0)lines.add(next);old++;next++;}
  }
  return lines;
}

export function parseReviewFindings(output:string,locations:Map<string,Set<number>>):{findings:Finding[];formatError?:string} {
  try {
    const parsed:unknown=JSON.parse(output.trim().replace(/^```(?:json)?\s*/,"").replace(/```\s*$/,""));
    if(!Array.isArray(parsed))return {findings:[],formatError:"Expected a JSON array of findings."};
    const findings:Finding[]=[];let rejected=0;
    for(const value of parsed) {
      if(!value || typeof value!=="object"){rejected++;continue;}
      const item=value as Finding;
      const valid=["title","path","trigger","expected","actual","evidence"].every(key=>typeof (item as unknown as Record<string,unknown>)[key]==="string" && String((item as unknown as Record<string,unknown>)[key]).trim());
      const path=typeof item.path==="string" ? item.path.replace(/\\/g,"/").replace(/^\.\//,"") : "";
      if(valid && ["P0","P1","P2","P3"].includes(item.priority) && Number.isInteger(item.line) && locations.get(path)?.has(item.line))findings.push({...item,path});
      else rejected++;
    }
    return {findings,...(rejected?{formatError:`${rejected} findings had invalid fields or locations outside the captured diff.`}:{})};
  }catch{return {findings:[],formatError:"The model response was not valid review JSON."};}
}

function patchRows(text:string,seed:FilePatch) {
  let old=seed.oldLine || 0;let next=seed.newLine || 0;let hunk=seed.hunkIndex ?? -1;
  return text.split("\n").map((line,index)=>{const header=/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(line);if(header){old=Number(header[1]);next=Number(header[2]);hunk++;return {line,index,hunk,old:0,next:0};}
    const metadata=/^(diff |index |--- |\+\+\+ |new file|deleted file|rename |similarity |Binary |GIT binary)/.test(line);
    const row={line,index,hunk,old:metadata || line.startsWith("+") ? 0 : old++,next:metadata || line.startsWith("-") ? 0 : next++};return row;});
}
export function Workbench({root,sessionId,running,onDraft,onReview,children,open:controlledOpen,onOpenChange,changesPanel,contextPanel,activityPanel}:{root:string;sessionId:string;running:boolean;onDraft:(value:string)=>void;onReview:(text:string)=>Promise<string>;children?:React.ReactNode;open?:boolean;onOpenChange?:(open:boolean)=>void;changesPanel?:React.ReactNode;contextPanel?:React.ReactNode;activityPanel?:React.ReactNode}) {
  const {t}=useI18n();
  const [localOpen,setLocalOpen]=useState(false);const open=controlledOpen ?? localOpen;const setOpen=useCallback((value:boolean)=>{if(onOpenChange)onOpenChange(value);else setLocalOpen(value);},[onOpenChange]);const [tab,setTab]=useState("git");const [fileVisited,setFileVisited]=useState(false);const [requestedFile,setRequestedFile]=useState<{path:string;line:number;sequence:number;owner:string}|null>(null);const [requestedSessionTab,setRequestedSessionTab]=useState("");
  const [scope,setScope]=useState<DiffScope>("working");const [base,setBase]=useState("main");
  const [snapshot,setSnapshot]=useState<GitSnapshot|null>(null);const [patch,setPatch]=useState<FilePatch|null>(null);
  const [selected,setSelected]=useState<GitFile|null>(null);const [search,setSearch]=useState("");const [filter,setFilter]=useState("");
  const [error,setError]=useState("");const [busy,setBusy]=useState(false);const [notice,setNotice]=useState("");
  const [split,setSplit]=useState(false);const [wrap,setWrap]=useState(false);const [ignore,setIgnore]=useState(false);
  const [message,setMessage]=useState("");const [push,setPush]=useState<PushPlan|null>(null);const [remote,setRemote]=useState("");const [target,setTarget]=useState("");
  const [confirmation,setConfirmation]=useState<{description:string;action:()=>Promise<void>}|null>(null);
  const [rounds,setRounds]=useState<Array<{id:string;createdAt:string;beforeRef:string;afterRef:string}>>([]);const [roundId,setRoundId]=useState("");const round=rounds.find(item=>item.id===roundId);
  const [reviewFile,setReviewFile]=useState("");const [reviews,setReviews]=useState<ReviewRecord[]>([]);const [reviewBusy,setReviewBusy]=useState(false);const [reviewStopped,setReviewStopped]=useState(false);
  const ownerKey=`${root}\0${sessionId}`;const owner=useRef({key:ownerKey});if(owner.current.key!==ownerKey)owner.current={key:ownerKey};const requestId=useRef(0);const patchRequest=useRef(0);const [refreshing,setRefreshing]=useState(false);const actionLock=useRef(false);
  const call=useCallback(async<T,>(operation:string,payload:Record<string,unknown>={})=>{const expected=owner.current;if(expected.key!==ownerKey)throw new StaleRequest();const result=await window.reverie.workbench(operation,{...payload,projectRoot:root,sessionId}) as T;if(owner.current!==expected)throw new StaleRequest();return result;},[root,sessionId,ownerKey]);
  const action=useCallback(async(fn:()=>Promise<void>)=>{if(actionLock.current)return;const expected=owner.current;actionLock.current=true;setBusy(true);setError("");try{await fn();}catch(e){if(owner.current===expected && !(e instanceof StaleRequest))setError(e instanceof Error?e.message:String(e));}finally{if(owner.current===expected){actionLock.current=false;setBusy(false);}}},[]);
  const refresh=useCallback(async()=>{const expected=owner.current;const current=++requestId.current;setRefreshing(true);try{const result=await call<GitSnapshot>("snapshot",{scope,base,before:round?.beforeRef,after:round?.afterRef});if(owner.current===expected && current===requestId.current){setSnapshot(result);setError("");}}catch(e){if(owner.current===expected && current===requestId.current){setSnapshot(null);setError(e instanceof Error?e.message:String(e));}}finally{if(owner.current===expected && current===requestId.current)setRefreshing(false);}},[call,scope,base,round?.beforeRef,round?.afterRef]);
  const loadPatch=useCallback(async(item:GitFile,offset=0)=>{
    if(actionLock.current)return;
    const expected=owner.current;const current=++patchRequest.current;setSelected(item);setPatch(null);setError("");
    if(item.directory)return;
    setBusy(true);
    try{const result=await call<FilePatch>("patch",{scope,base,before:round?.beforeRef,after:round?.afterRef,file:item.path,oldPath:item.oldPath,offset,ignoreWhitespace:ignore});if(owner.current===expected && current===patchRequest.current)setPatch(result);}
    catch(e){if(owner.current===expected && current===patchRequest.current)setError(e instanceof Error?e.message:String(e));}
    finally{if(owner.current===expected && current===patchRequest.current)setBusy(false);}
  },[call,scope,base,round,ignore]);
  useEffect(()=>{patchRequest.current++;setPatch(null);setSelected(null);setBusy(false);},[root,sessionId,scope,base,ignore,roundId]);
  const loadFile=useCallback(async(path:string,start=1)=>{setOpen(true);setTab("file");setFileVisited(true);setRequestedFile(current=>({path,line:start,sequence:(current?.sequence || 0)+1,owner:ownerKey}));},[setOpen,ownerKey]);
  useEffect(()=>{const expected=owner.current;actionLock.current=false;setBusy(false);setReviewBusy(false);setSnapshot(null);setPatch(null);setRequestedFile(null);setRoundId("");setRounds([]);setSelected(null);setPush(null);setConfirmation(null);setError("");setNotice("");setReviews([]);setReviewFile("");setRefreshing(false);requestId.current++;patchRequest.current++;void call<{reviews:ReviewRecord[]}>("reviews").then(value=>setReviews(value.reviews)).catch(e=>{if(owner.current===expected && !(e instanceof StaleRequest))setError(String(e));});return()=>{requestId.current++;patchRequest.current++;if(owner.current===expected)owner.current={key:ownerKey};};},[call,ownerKey]);
  useEffect(()=>{if(!open || !["git","review"].includes(tab))return;const expected=owner.current;void call<{runs:typeof rounds}>("runs").then(value=>{const available=value.runs.filter(item=>item.beforeRef && item.afterRef);setRounds(available);setRoundId(current=>current || available[0]?.id || "");}).catch(e=>{if(owner.current===expected && !(e instanceof StaleRequest))setError(String(e));});let active=true;let timer:ReturnType<typeof setTimeout>;const poll=async()=>{await refresh();if(active)timer=setTimeout(()=>void poll(),15000);};void poll();return()=>{active=false;clearTimeout(timer);requestId.current++;};},[open,tab,refresh]);
  useEffect(()=>{const show=(event:Event)=>{const detail=(event as CustomEvent).detail || {};if(detail.sessionTab)setRequestedSessionTab(detail.sessionTab);if(detail.reviewFile!==undefined)setReviewFile(String(detail.reviewFile).replace(/\\/g,"/"));if(detail.scope)setScope(detail.scope);if(detail.base)setBase(detail.base);if(detail.path)void loadFile(detail.path,detail.line || 1);else{setOpen(true);setTab(detail.tab || "git");}};window.addEventListener("reverie:file-open",show);window.addEventListener("reverie:workbench",show);return()=>{window.removeEventListener("reverie:file-open",show);window.removeEventListener("reverie:workbench",show);};},[loadFile,setOpen]);
  useEffect(()=>{if(open && tab==="session" && requestedSessionTab){window.dispatchEvent(new CustomEvent("reverie:session-tab",{detail:{tab:requestedSessionTab}}));setRequestedSessionTab("");}},[open,tab,requestedSessionTab]);

  const mutate=async(operation:"stage"|"unstage"|"revert"|"delete",hunk?:number)=>{if(!selected || !patch)return;const item=selected;const version=patch.version;const execute=async()=>{await action(async()=>{await call("mutate",{operation,file:item.path,oldPath:item.oldPath,version,hunk,confirmed:true});setNotice(`${t("操作完成")}: ${item.path}`);await refresh();const result=await call<FilePatch>("patch",{scope,base,before:round?.beforeRef,after:round?.afterRef,file:item.path,offset:0});setPatch(result);});};if(operation==="revert" || operation==="delete")setConfirmation({description:`${t(operation==="delete"?"永久删除未跟踪文件？":"撤销这些改动？")}\n${item.path}${hunk!==undefined?`\n${patch.hunks[hunk]}`:""}\n${version}`,action:execute});else await execute();};
  const beginReview=async()=>{if(running || reviewBusy || !snapshot)return;setReviewBusy(true);setError("");setReviewStopped(false);const captured=snapshot;const expected=owner.current;try{let diff="";const locations=new Map<string,Set<number>>();const files=captured.files.filter(item=>!item.directory && (!reviewFile || item.path===reviewFile));if(reviewFile && !files.length)throw new Error(t("指定文件不在当前审查差异中"));for(const item of files){let offset=0;let fileDiff="";do{const result=await call<FilePatch>("patch",{scope,base,before:round?.beforeRef,after:round?.afterRef,file:item.path,oldPath:item.oldPath,offset});if(result.version!==captured.version)throw new Error(t("差异已变化，请刷新"));fileDiff+=result.text+"\n";diff+=result.text+"\n";if(diff.length>500000)throw new Error(t("审查范围过大，请缩小到指定文件"));if(result.next===null)break;offset=result.next;}while(true);locations.set(item.path.replace(/\\/g,"/"),reviewLocations(fileDiff));}
      const output=await onReview(`Read-only code review. Do not modify files or run commands. Scope: ${scope}; file: ${reviewFile || "all"}; base: ${base}; version: ${captured.version}. Return only a JSON array of concrete actionable findings with priority (P0-P3), title, path, line (positive integer), trigger, expected, actual, evidence. If none return []. Review the complete selected diff:\n${diff}`);
      if(owner.current!==expected)return;const parsed=parseReviewFindings(output,locations);
      const record:ReviewRecord={id:crypto.randomUUID(),version:captured.version,scope,createdAt:new Date().toISOString(),output,...parsed};const next=[record,...reviews];await call("save-reviews",{reviews:next});setReviews(next);
    }catch(e){if(owner.current===expected && !(e instanceof StaleRequest))setError(e instanceof Error?e.message:String(e));}finally{if(owner.current===expected)setReviewBusy(false);}};
  const updateFinding=async(review:ReviewRecord,index:number,key:"viewed"|"resolved")=>{const next=reviews.map(value=>value.id===review.id?{...value,findings:value.findings.map((finding,i)=>i===index?{...finding,[key]:!finding[key]}:finding)}:value);await action(async()=>{await call("save-reviews",{reviews:next});setReviews(next);});};
  useEffect(()=>{const saved=(event:Event)=>{if((event as CustomEvent).detail?.root===root && open && tab==="git")void refresh();};window.addEventListener("reverie:file-saved",saved);return()=>window.removeEventListener("reverie:file-saved",saved);},[root,open,tab,refresh]);
  const close=()=>{setOpen(false);requestAnimationFrame(()=>document.querySelector<HTMLTextAreaElement>(".composer textarea")?.focus());};
  return <>
    {controlledOpen===undefined && <button type="button" className="workbench-trigger" aria-label={t("工作面板")} aria-expanded={open} onClick={()=>setOpen(!open)}><GitBranch size={15}/>{t("工作面板")}</button>}
    <section className={`workbench-panel inspector ${open?"open":""}`} aria-label={t("工作面板")} aria-hidden={!open || undefined} inert={!open || undefined} onKeyDown={event=>{if(event.key==="Escape" && !confirmation){event.stopPropagation();close();}}}>
      <header className="workbench-header"><nav aria-label={t("工作面板")} onKeyDown={event=>{if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;const buttons=[...event.currentTarget.querySelectorAll<HTMLButtonElement>("button")];const current=buttons.indexOf(document.activeElement as HTMLButtonElement);const next=event.key==="Home"?0:event.key==="End"?buttons.length-1:(current+(event.key==="ArrowRight"?1:-1)+buttons.length)%buttons.length;event.preventDefault();buttons[next]?.focus();buttons[next]?.click();}}>
        {[ ["git","Git 改动"],["file","文件"],["review","只读审查"],["session","运行与终端"],...(changesPanel?[["changes","AI 改动"]]:[]),...(contextPanel?[["context","上下文"]]:[]),...(activityPanel?[["activity","活动"]]:[]) ].map(([value,label])=><button type="button" key={value} className={tab===value?"active":""} aria-pressed={tab===value} onClick={()=>{setTab(value);if(value==="file")setFileVisited(true);}}>{t(label)}</button>)}
      </nav><button type="button" className="icon-button" aria-label={t("收起右侧栏")} onClick={close}><PanelRightClose size={16}/></button></header>

      {error && <div role="alert" className="persistent-error">{error}<button type="button" onClick={()=>void refresh()}>{t("重试")}</button></div>}
      {(busy || refreshing) && ["git","review"].includes(tab) && <div role="status" className="workbench-loading"><RefreshCw className="spin" size={14}/>{t("正在加载")}</div>}
      {notice && <div role="status" className="composer-status">{notice}</div>}
      {tab==="git" && <>
        <div className="workbench-toolbar"><select aria-label={t("差异范围")} value={scope} onChange={e=>{setScope(e.target.value as DiffScope);setPatch(null);setSelected(null);}}>{Object.entries(labels).map(([value,label])=><option key={value} value={value}>{t(label)}</option>)}</select>
          {scope==="round" && <select aria-label={t("AI 轮次")} value={roundId} onChange={e=>{setRoundId(e.target.value);setPatch(null);}}>{rounds.map(item=><option key={item.id} value={item.id}>{item.createdAt} · {item.id.slice(0,8)}</option>)}</select>}
          {["branch","commit"].includes(scope) && <input aria-label={t("比较基准")} value={base} onChange={e=>setBase(e.target.value)}/>}
          <button type="button" disabled={busy} onClick={()=>void refresh()} aria-label={t("刷新")}><RefreshCw size={14}/></button>
          <details className="diff-options"><summary>{t("显示选项")}</summary><div><label><input type="checkbox" checked={split} onChange={e=>setSplit(e.target.checked)}/>{t("并排")}</label><label><input type="checkbox" checked={wrap} onChange={e=>setWrap(e.target.checked)}/>{t("换行")}</label><label><input type="checkbox" checked={ignore} onChange={e=>{setIgnore(e.target.checked);setPatch(null);}}/>{t("忽略空白")}</label></div></details>
        </div>
        {snapshot?.conflicts.length ? <div role="alert" className="persistent-error">{t("存在冲突")}: {snapshot.conflicts.join(" · ")}</div>:null}
        <div className="workbench-diff-layout"><aside className="workbench-tree"><div className="workbench-search"><Search size={14}/><input aria-label={t("搜索文件")} placeholder={t("搜索文件")} value={search} onChange={e=>setSearch(e.target.value)}/></div><select aria-label={t("筛选文件状态")} value={filter} onChange={e=>setFilter(e.target.value)}><option value="">{t("全部状态")}</option>{Object.entries(statusLabels).map(([value,label])=><option key={value} value={value}>{t(label)} · {value}</option>)}</select>
          {snapshot?.files.filter(item=>item.path.toLowerCase().includes(search.toLowerCase()) && (!filter || item.status.startsWith(filter))).map(item=><button type="button" className={selected?.path===item.path?"active":""} key={item.path} onClick={()=>void loadPatch(item)} title={item.oldPath?`${item.oldPath} → ${item.path}`:item.path}><small title={t(statusLabels[item.status[0]] || item.status)}>{t(statusLabels[item.status[0]] || item.status)}</small><span>{item.path}</span><small>{item.directory?t("目录"):item.binary?t("二进制"):`+${item.additions} −${item.deletions}`}</small></button>)}
          {snapshot && !snapshot.files.length && <p>{t("没有改动")}</p>}
        </aside><div className="workbench-diff" style={{whiteSpace:wrap?"pre-wrap":"pre"}}>
          {selected && patch ? <><div className="workbench-toolbar"><strong>{selected.path}</strong><button type="button" onClick={()=>void loadFile(selected.path)}><FileText size={14}/>{t("预览")}</button>{["working","staged"].includes(scope) && <><button type="button" disabled={busy || running || snapshot?.conflicts.includes(selected.path)} onClick={()=>void mutate(scope==="staged"?"unstage":"stage")}>{t(scope==="staged"?"取消暂存文件":"暂存文件")}</button>{scope==="working" && <button type="button" disabled={busy || running} onClick={()=>void mutate(selected.status==="?"?"delete":"revert")}>{t(selected.status==="?"?"删除未跟踪文件":"撤销文件")}</button>}</>}</div>
            <p className="version-label" title={patch.version}>{patch.totalLines} {t("行")}{patch.next!==null?` · ${t("分块显示")}`:""}</p>
            {patch.binary?<p>{t("二进制变更不提供行级操作")}</p>:<div className={split?"patch-lines split":"patch-lines"}>{patchRows(patch.text,patch).map(row=><div className={`patch-line ${row.line.startsWith("+")?"added":row.line.startsWith("-")?"removed":row.line.startsWith("@@")?"hunk":""}`} key={row.index}>
              {row.line.startsWith("@@") ? <><code>{row.line}</code>{["working","staged"].includes(scope) && !ignore && selected.status!=="?" && <span><button type="button" disabled={busy || running} onClick={()=>void mutate(scope==="staged"?"unstage":"stage",row.hunk)}>{t(scope==="staged"?"取消暂存区块":"暂存区块")}</button>{scope==="working" && <button type="button" disabled={busy || running} onClick={()=>void mutate("revert",row.hunk)}>{t("撤销区块")}</button>}</span>}</>:<><button className="line-number" type="button" disabled={!row.old && !row.next} title={t("行反馈加入草稿")} onClick={()=>onDraft(`${selected.path}:${row.next || row.old} (${scope}, ${patch.version})\n${row.line}\n${t("请检查这一行")}`)}>{row.old || ""}</button><button className="line-number" type="button" disabled={!row.next} title={t("行反馈加入草稿")} onClick={()=>onDraft(`${selected.path}:${row.next} (${scope}, ${patch.version})\n${row.line}\n${t("请检查这一行")}`)}>{row.next || ""}</button>{split?<><code className="patch-left">{row.line.startsWith("+")?"":row.line}</code><code className="patch-right">{row.line.startsWith("-")?"":row.line}</code></>:<code>{row.line}</code>}</>}
            </div>)}</div>}
            {patch.offset>0 && <button type="button" onClick={()=>void loadPatch(selected,Math.max(0,patch.offset-2000))}>{t("上一块")}</button>}{patch.next!==null && <button type="button" onClick={()=>void loadPatch(selected,patch.next!)}>{t("下一块")}</button>}
          </>:<div className="workbench-empty"><GitBranch size={24}/><p>{t(selected?.directory ? "这是嵌套仓库，请作为项目打开" : snapshot?.files.length ? "选择文件查看完整差异" : "工作区没有待查看的改动")}</p>{selected?.directory && <button type="button" onClick={()=>window.dispatchEvent(new CustomEvent("reverie:workspace-open",{detail:{root:snapshot!.root + "/" + selected.path}}))}>{t("打开并创建会话")}</button>}</div>}
        </div></div>
        {scope==="staged" && <div className="commit-form"><p>{t("提交包含当前整个暂存区")}: {snapshot?.files.map(item=>item.path).join(" · ") || t("没有改动")}</p><textarea aria-label={t("提交说明")} placeholder={t("提交说明")} value={message} onChange={e=>setMessage(e.target.value)}/><button type="button" disabled={busy || running || !message.trim() || !snapshot?.files.length} onClick={()=>setConfirmation({description:`${t("提交整个暂存区？")}\n${snapshot!.files.map(item=>item.path).join("\n")}\n${message}`,action:async()=>{await action(async()=>{const result=await call<{head:string;output:string}>("commit",{message,version:snapshot!.version});setNotice(`${result.head}\n${result.output}`);setMessage("");await refresh();});}})}>{t("提交")}</button></div>}
        <details className="push-form"><summary>{t("普通推送")}</summary><input aria-label={t("远端名称")} placeholder="origin" value={remote} onChange={e=>{setRemote(e.target.value);setPush(null);}}/><input aria-label={t("目标分支")} placeholder={snapshot?.branch} value={target} onChange={e=>{setTarget(e.target.value);setPush(null);}}/><button type="button" disabled={busy || running} onClick={()=>void action(async()=>setPush(await call<PushPlan>("push-plan",{remote,target})))}>{t("查看推送计划")}</button>{push && <><pre>{push.remote} · {push.url}\n{push.branch} → {push.target}\nHEAD {push.head}\n{push.commits.join("\n") || t("没有待推送提交")}</pre><button type="button" disabled={busy || running} onClick={()=>setConfirmation({description:`${t("确认普通推送？")}\n${push.remote}\n${push.url}\n${push.target}\n${push.head}\n${push.commits.join("\n")}`,action:async()=>{await action(async()=>{const result=await call<{remoteHead:string;output:string}>("push",{plan:push,confirmed:true});setNotice(`${t("远端引用已核对")} ${result.remoteHead}\n${result.output}`);setPush(null);});}})}>{t("推送")}</button></>}</details>
      </>}
      {fileVisited && <div className="workbench-file-view" hidden={tab!=="file"} inert={tab!=="file" || undefined}><FileBrowser key={ownerKey} root={root} running={running} requested={requestedFile?.owner===ownerKey?requestedFile:null} onDraft={onDraft}/></div>}
      {tab==="review" && <div className="review-panel"><div className="workbench-toolbar"><ShieldCheck size={16}/><strong>{t("只读审查")}</strong><select aria-label={t("审查范围")} value={scope} onChange={e=>setScope(e.target.value as DiffScope)}>{Object.entries(labels).map(([value,label])=><option key={value} value={value}>{t(label)}</option>)}</select><input aria-label={t("比较基准")} value={base} onChange={e=>setBase(e.target.value)}/><button type="button" disabled={running || reviewBusy} onClick={()=>void action(async()=>{await refresh();setNotice(t("范围已刷新，可开始审查"));})}>{t("刷新范围")}</button><select aria-label={t("选择审查文件")} value={reviewFile} onChange={e=>setReviewFile(e.target.value)}><option value="">{t("全部文件")}</option>{snapshot?.files.map(item=><option key={item.path} value={item.path}>{item.path}</option>)}</select><button type="button" disabled={running || reviewBusy || !snapshot} onClick={()=>void beginReview()}>{t("开始只读审查")}</button>{reviewBusy && <button type="button" onClick={()=>void window.reverie.request("stopPrompt",{projectRoot:root,sessionId}).then(()=>setReviewStopped(true))}>{t("停止")}</button>}</div><p>{t("只开放内核审计的文件读取与检索；写入、命令、Git 和插件工具均被后端禁止。")}</p>{reviewStopped && <p role="status">{t("正在停止，等待当前操作结束")}</p>}
        {reviews.map(review=><article className="review-record" key={review.id}><header><strong>{review.scope}</strong><small>{review.createdAt} · {review.version.slice(0,12)}</small>{snapshot && review.version!==snapshot.version && <span>{t("发现已过期")}</span>}</header>{review.formatError && <p role="alert">{t("审查输出格式无效，请查看原文或重新审查")}</p>}{review.findings.length?review.findings.map((finding,index)=><div className="finding" key={index}><strong>{finding.priority} · {finding.title}</strong><button type="button" onClick={()=>void loadFile(finding.path,finding.line)}>{finding.path}:{finding.line}</button><p>{finding.trigger}</p><p>{t("预期")}: {finding.expected}</p><p>{t("实际")}: {finding.actual}</p><p>{t("依据")}: {finding.evidence}</p><button type="button" disabled={busy} onClick={()=>void updateFinding(review,index,"viewed")}>{t(finding.viewed?"已查看":"标为已查看")}</button><button type="button" disabled={busy} onClick={()=>void updateFinding(review,index,"resolved")}>{t(finding.resolved?"已解决":"标为已解决")}</button><button type="button" onClick={()=>onDraft(`${t("修复这个审查发现")}: ${finding.priority} ${finding.title}\n${finding.path}:${finding.line}\n${finding.trigger}\nExpected: ${finding.expected}\nActual: ${finding.actual}\nEvidence: ${finding.evidence}\nReview version: ${review.version}`)}>{t("修复加入下一轮")}</button></div>):<pre>{review.output}</pre>}{review.formatError && review.findings.length>0 && <details><summary>{t("审查原始输出")}</summary><pre>{review.output}</pre></details>}</article>)}
      </div>}
      {tab==="session" && children}
      {tab==="changes" && changesPanel}
      {tab==="context" && contextPanel}
      {tab==="activity" && activityPanel}
      {confirmation && <div className="workbench-confirm" role="alertdialog" aria-label={t("确认操作")} aria-modal="true" onKeyDown={e=>{if(e.key==="Escape"){e.stopPropagation();setConfirmation(null);}}}><pre>{confirmation.description}</pre><button type="button" autoFocus onClick={()=>setConfirmation(null)}>{t("取消")}</button><button type="button" disabled={busy} onClick={()=>{const current=confirmation;setConfirmation(null);void current.action();}}>{t("确认")}</button></div>}
    </section>
  </>;
}
