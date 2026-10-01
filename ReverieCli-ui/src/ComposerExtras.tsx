import { createContext, useContext, useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Copy, RefreshCw, X } from "lucide-react";
import type { ComposerAttachment } from "../electron/attachments";
import type { QueuedMessage } from "./execution-state";
import { useI18n } from "./i18n";
import type { Goal } from "../electron/session-workspace";
import type { Preview } from "../electron/workbench";

export interface InputControls {
  projectRoot: string;
  sessionId: string;
  behavior: "queue" | "steer";
  setBehavior: (value: "queue" | "steer") => void;
  paste: () => void;
  moveAttachment: (index: number, direction: number) => void;
  retryAttachment: (item: ComposerAttachment, copy?: boolean) => void;
  closeMentions: () => void;
  error: string;
  status: string;
  queue: QueuedMessage[];
  queuePaused: boolean;
  editQueue: (index: number, text: string, attachments: ComposerAttachment[]) => void;
  moveQueue: (index: number, direction: number) => void;
  deleteQueue: (index: number) => void;
  resumeQueue: () => void;
  forceStop: () => void;
  vision: boolean | undefined;
  running: boolean;
  approval: boolean;
  sessionStates: Record<string, string>;
  steer: () => void;
}
export const InputContext = createContext<InputControls | null>(null);
export const useInputControls = () => useContext(InputContext);

export function GoalSummary() {
  const controls=useInputControls();const {t}=useI18n();const [goal,setGoal]=useState<Goal|null>(null);const [error,setError]=useState("");
  useEffect(()=>{let active=true;const refresh=()=>{if(!controls?.sessionId || !window.reverie.workbench){setGoal(null);return;}void window.reverie.workbench("goal",{projectRoot:controls.projectRoot,sessionId:controls.sessionId}).then(value=>{if(active){setGoal((value as {goal:Goal|null}).goal);setError("");}}).catch(e=>{if(active)setError(String(e));});};refresh();window.addEventListener("reverie:goal-changed",refresh);return()=>{active=false;window.removeEventListener("reverie:goal-changed",refresh);};},[controls?.projectRoot,controls?.sessionId]);
  if(!goal && !error)return null;
  return <div className="goal-summary">{error?<span role="alert">{error}</span>:<><strong>{goal!.title}</strong><span>{goal!.steps.filter(step=>step.state==="verified").length}/{goal!.steps.length} {t("验证通过")}</span><small>{goal!.steps.find(step=>step.state!=="verified")?.text}</small></>}<button type="button" onClick={()=>window.dispatchEvent(new CustomEvent("reverie:workbench",{detail:{tab:"session",sessionTab:"goal"}}))}>{t("目标与计划")}</button></div>;
}

export function QueueStrip() {
  const controls = useInputControls();
  const { t } = useI18n();
  const [editing, setEditing] = useState<{ id: string; text: string; attachments: ComposerAttachment[] } | null>(null);
  if (!controls?.queue.length) return null;
  return <section className="queue-strip" aria-label={t("下一轮消息")}>
    <header><strong>{t("下一轮消息")} · {controls.queue.length}</strong><span>{controls.queuePaused ? t("队列已暂停") : t("当前轮结束后执行")}</span>{controls.queuePaused && <button type="button" onClick={controls.resumeQueue}>{t("继续队列")}</button>}</header>
    {controls.queue.map((item, index) => <div className="queue-row" key={item.id}>
      <button type="button" className="queue-summary" onClick={() => setEditing({ id: item.id, text: item.text, attachments: item.attachments })} title={`${item.projectRoot}\n${item.sessionId}`}>{item.text || t("纯附件消息")}<small>{item.attachments.map(a => a.name).join(" · ")}</small></button>
      <button type="button" aria-label={t("上移排队消息")} disabled={!index} onClick={() => controls.moveQueue(index, -1)}><ArrowUp size={14} /></button>
      <button type="button" aria-label={t("下移排队消息")} disabled={index === controls.queue.length - 1} onClick={() => controls.moveQueue(index, 1)}><ArrowDown size={14} /></button>
      <button type="button" aria-label={t("删除排队消息")} onClick={() => controls.deleteQueue(index)}><X size={14} /></button>
    </div>)}
    {editing && <div className="queue-editor"><textarea autoFocus aria-label={t("编辑排队消息")} value={editing.text} onChange={event => setEditing({ ...editing, text: event.target.value })} onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); setEditing(null); } }} />{editing.attachments.map((item, index) => <button type="button" key={item.id || item.relativePath} onClick={() => setEditing({ ...editing, attachments: editing.attachments.filter((_, i) => i !== index) })}>{item.name} ×</button>)}<button type="button" disabled={!editing.text.trim() && !editing.attachments.length} onClick={() => { const index = controls.queue.findIndex(item => item.id === editing.id); if (index >= 0) controls.editQueue(index, editing.text, editing.attachments); setEditing(null); }}>{t("保存")}</button><button type="button" onClick={() => setEditing(null)}>{t("取消")}</button></div>}
  </section>;
}

export function AttachmentCards({ items, remove }: { items: ComposerAttachment[]; remove: (item: ComposerAttachment) => void }) {
  const controls = useInputControls();
  const { t } = useI18n();
  const [preview, setPreview] = useState<ComposerAttachment | null>(null);
  const [previewImage, setPreviewImage] = useState<Preview | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const dialog = useRef<HTMLElement>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  const [dragIndex, setDragIndex] = useState(-1);
  const previewOpen = Boolean(preview);
  useEffect(() => {
    if (!previewOpen) return;
    dialog.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => { if (opener.current?.isConnected) opener.current.focus(); };
  }, [previewOpen]);
  useEffect(() => {
    let active = true;
    setPreviewImage(null); setPreviewError(""); setPreviewLoading(false);
    if (!preview?.thumbnail || !controls?.projectRoot || !window.reverie.workbench) return;
    setPreviewLoading(true);
    void window.reverie.workbench("preview", { projectRoot: controls.projectRoot, file: preview.relativePath }).then(value => {
      if (!active) return;
      const image = value as Preview;
      if (preview.kind === "copy" && preview.version && image.version !== preview.version) throw new Error(t("保留导入版本") + ": " + t("请重新导入附件"));
      setPreviewImage(image); setPreviewLoading(false);
    }).catch(error => { if (active) { setPreviewError(String(error)); setPreviewLoading(false); } });
    return () => { active = false; };
  }, [preview, controls?.projectRoot, t]);
  if (!items.length) return null;
  return <>
    <div className="attachment-strip" aria-label={t("待发送附件")}>
      {items.map((item, index) => <div className={`attachment-card ${item.status === "failed" || item.status === "cancelled" ? "failed" : ""}`} key={item.id || item.relativePath} draggable onDragStart={(event) => { event.stopPropagation(); setDragIndex(index); }} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); event.stopPropagation(); if (dragIndex >= 0 && dragIndex !== index) controls?.moveAttachment(dragIndex, index - dragIndex); setDragIndex(-1); }}>
        <button className="attachment-preview" type="button" onClick={event => { opener.current = event.currentTarget; setPreview(item); }} title={item.relativePath || item.sourcePath}>
          {item.thumbnail && <img src={item.thumbnail} alt={item.name} />}
          <span><strong>{item.name}</strong><small>{t(item.kind === "reference" ? "工作区引用" : "附件副本")} · {(item.size / 1024).toFixed(1)} KiB{item.width ? ` · ${item.width}×${item.height}` : ""}</small><small className="attachment-path">{item.relativePath || item.sourcePath}</small></span>
        </button>
        {item.status === "pending" && <span role="status">{t("正在导入")}</span>}
        {item.error && <div role="alert" className="persistent-error">{item.error}</div>}
        <div className="attachment-actions">
          <button type="button" aria-label={t("上移附件")} disabled={!index} onClick={() => controls?.moveAttachment(index, -1)}><ArrowUp size={12} /></button>
          <button type="button" aria-label={t("下移附件")} disabled={index === items.length - 1} onClick={() => controls?.moveAttachment(index, 1)}><ArrowDown size={12} /></button>
          {item.kind === "reference" && <button type="button" aria-label={t("固定为附件副本")} onClick={() => controls?.retryAttachment(item, true)}><Copy size={12} /></button>}
          {item.status === "failed" || item.status === "cancelled" ? <button type="button" aria-label={t("重试附件")} onClick={() => controls?.retryAttachment(item)}><RefreshCw size={12} /></button> : null}
          <button type="button" aria-label={t("attachment.remove", { name: item.name })} onClick={() => remove(item)}><X size={12} /></button>
        </div>
      </div>)}
    </div>
    {preview && <div className="modal-backdrop" onClick={() => setPreview(null)}><section ref={dialog} className="modal attachment-dialog" role="dialog" aria-modal="true" aria-label={t("附件预览")} onClick={event => event.stopPropagation()} onKeyDown={event => {
      if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return;
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); setPreview(null); }
      if (event.key === "Tab") {
        const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));
        const target = event.shiftKey ? buttons[buttons.length - 1] : buttons[0];
        if (document.activeElement === (event.shiftKey ? buttons[0] : buttons[buttons.length - 1])) { event.preventDefault(); target?.focus(); }
      }
    }}>
      <header><strong>{preview.name}</strong><button autoFocus type="button" aria-label={t("关闭")} onClick={() => setPreview(null)}><X size={16} /></button></header>
      {previewLoading && <p role="status">{t("正在加载")}</p>}
      {previewError && <p className="persistent-error" role="alert">{previewError}</p>}
      {preview.thumbnail && !previewError && <img src={previewImage?.url || preview.thumbnail} alt={preview.name} />}
      <p>{preview.relativePath || preview.sourcePath}</p><p>{t(preview.kind === "reference" ? "发送时读取当前文件" : "保留导入版本")}</p>
      {(previewImage?.version || preview.version) && <code>SHA256 {previewImage?.version || preview.version}</code>}
      <button type="button" onClick={() => { window.dispatchEvent(new CustomEvent("reverie:file-open", { detail: { path: preview.relativePath, line: preview.line } })); setPreview(null); }}>{t("打开文件预览")}</button>
    </section></div>}
  </>;
}
