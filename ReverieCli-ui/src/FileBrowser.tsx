import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { ChevronRight, FileText, Folder, FolderOpen, RefreshCw, Save } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { DirectoryListing, EditorFile, Preview } from "../electron/workbench";
import { useI18n } from "./i18n";
import { parseFileLink } from "./file-links";

const PdfPreview = lazy(() => import("./PdfPreview").then(module => ({ default: module.PdfPreview })));
const drafts = new Map<string, { version: string; text: string }>();

function isolatedHtml(text: string): string {
  const parsed = new DOMParser().parseFromString(text, "text/html");
  parsed.querySelectorAll("script,iframe,object,embed,link,meta,base,form").forEach(node => node.remove());
  parsed.querySelectorAll("*").forEach(node => {
    for (const attribute of [...node.attributes]) if (attribute.name.startsWith("on") || ["href", "action", "formaction", "srcdoc"].includes(attribute.name) || attribute.name === "src" && !attribute.value.startsWith("data:image/")) node.removeAttribute(attribute.name);
  });
  return `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">${parsed.documentElement.outerHTML}`;
}

export function FileBrowser({ root, running, requested, onDraft }: {
  root: string; running: boolean; requested: { path: string; line: number; sequence: number } | null; onDraft: (value: string) => void;
}) {
  const { t } = useI18n();
  const [directories, setDirectories] = useState<Record<string, DirectoryListing>>({});
  const [expanded, setExpanded] = useState(new Set(["."]));
  const [loading, setLoading] = useState(new Set<string>());
  const [preview, setPreview] = useState<Preview | null>(null);
  const [document, setDocument] = useState<EditorFile | null>(null);
  const [text, setText] = useState("");
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editorNote, setEditorNote] = useState("");
  const [notice, setNotice] = useState("");
  const [line, setLine] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [pending, setPending] = useState<{ path: string; line: number } | null>(null);
  const sequence = useRef(0); const mounted = useRef(true); const saving = useRef(false);
  const source = useRef<HTMLTextAreaElement>(null);
  const dirty = Boolean(document && text !== document.text);
  const draftKey = document ? `${root}\0${document.relativePath}` : "";
  const latest = useRef({ dirty, text, document }); latest.current = { dirty, text, document };
  const call = useCallback(<T,>(operation: string, payload: Record<string, unknown> = {}) => window.reverie.workbench(operation, { ...payload, projectRoot: root }) as Promise<T>, [root]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; sequence.current++; }; }, []);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (drafts.size) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn);
  }, []);
  const loadDirectory = useCallback(async (directory: string) => {
    setLoading(current => new Set(current).add(directory));
    try {
      const listing = await call<DirectoryListing>("list-directory", { directory });
      if (mounted.current) setDirectories(current => ({ ...current, [directory]: listing }));
    } catch (cause) { if (mounted.current) setError(String(cause instanceof Error ? cause.message : cause)); }
    finally { if (mounted.current) setLoading(current => { const next = new Set(current); next.delete(directory); return next; }); }
  }, [call]);
  useEffect(() => { void loadDirectory("."); }, [loadDirectory]);
  const open = useCallback(async (path: string, start = 1, offset = 0) => {
    const request = ++sequence.current; setBusy(true); setError(""); setNotice(""); setEditorNote("");
    try {
      const value = await call<Preview>("preview", { file: path, offset });
      let editable: EditorFile | null = null; let note = "";
      if (["text", "markdown", "html"].includes(value.kind)) {
        try { editable = await call<EditorFile>("read-file", { file: value.relativePath }); }
        catch (cause) { note = cause instanceof Error ? cause.message : String(cause); }
      }
      if (!mounted.current || request !== sequence.current) return;
      const key = `${root}\0${value.relativePath}`;
      let draft = drafts.get(key);
      if (editable && draft?.text === editable.text) { drafts.delete(key); draft = undefined; }
      setPreview(value); setDocument(editable && draft ? { ...editable, version: draft.version } : editable);
      setText(draft?.text ?? editable?.text ?? ""); setEditing(Boolean(editable && (value.kind === "text" || draft)));
      setEditorNote(note); setLine(start); setZoom(1);
      requestAnimationFrame(() => {
        if (source.current && editable) {
          const position = editable.text.split("\n").slice(0, start - 1).reduce((sum, part) => sum + part.length + 1, 0);
          source.current.setSelectionRange(position, position); source.current.scrollTop = Math.max(0, start - 4) * 22;
        }
      });
    } catch (cause) { if (mounted.current && request === sequence.current) setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { if (mounted.current && request === sequence.current) setBusy(false); }
  }, [call, root]);
  const select = useCallback((path: string, start = 1) => {
    if (saving.current) return;
    if (latest.current.dirty) {
      if (latest.current.document?.relativePath === path) { setLine(start); source.current?.focus(); }
      else setPending({ path, line: start });
    }
    else void open(path, start);
  }, [open]);
  useEffect(() => { if (requested) select(requested.path, requested.line); }, [requested, select]);
  const save = async (): Promise<boolean> => {
    if (!document || !dirty || running || saving.current) return false;
    saving.current = true; setBusy(true); setError(""); const submitted = text; const request = sequence.current;
    try {
      const saved = await call<EditorFile>("save-file", { file: document.relativePath, text: submitted, version: document.version });
      if (!mounted.current || request !== sequence.current) return false;
      setDocument(saved);
      if (latest.current.text === submitted) drafts.delete(draftKey);
      else drafts.set(draftKey, { version: saved.version, text: latest.current.text });
      setNotice(t("文件已保存"));
      window.dispatchEvent(new CustomEvent("reverie:file-saved", { detail: { root, path: saved.relativePath } }));
      return latest.current.text === submitted;
    } catch (cause) { if (mounted.current) setError(cause instanceof Error ? cause.message : String(cause)); return false; }
    finally { saving.current = false; if (mounted.current) setBusy(false); }
  };
  const discard = () => { drafts.delete(draftKey); setText(document?.text || ""); };
  const nodes = (directory: string, depth = 0): React.ReactNode => <ul role={depth ? "group" : "tree"} aria-label={depth ? undefined : t("工作区文件")}>
    {directories[directory]?.entries.map(entry => <li key={entry.path} role="none">
      <button type="button" role="treeitem" aria-expanded={entry.directory ? expanded.has(entry.path) : undefined} aria-selected={!entry.directory && preview?.relativePath === entry.path} disabled={entry.outside} title={entry.outside ? t("链接指向工作区之外，无法打开") : entry.path} className={preview?.relativePath === entry.path ? "active" : ""} style={{ paddingLeft: 8 + depth * 14 }} onKeyDown={event => {
        if (event.key === "ArrowRight" && entry.directory && !expanded.has(entry.path) || event.key === "ArrowLeft" && entry.directory && expanded.has(entry.path)) { event.preventDefault(); event.currentTarget.click(); }
        else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault(); const items = [...event.currentTarget.closest(".file-explorer")!.querySelectorAll<HTMLButtonElement>('button[role="treeitem"]:not(:disabled)')];
          items[items.indexOf(event.currentTarget) + (event.key === "ArrowDown" ? 1 : -1)]?.focus();
        }
      }} onClick={() => {
        if (!entry.directory) { select(entry.path); return; }
        setExpanded(current => { const next = new Set(current); if (next.has(entry.path)) next.delete(entry.path); else next.add(entry.path); return next; });
        if (!directories[entry.path] && !loading.has(entry.path)) void loadDirectory(entry.path);
      }}>
        {entry.directory ? <><ChevronRight size={12} className={expanded.has(entry.path) ? "expanded" : ""} />{expanded.has(entry.path) ? <FolderOpen size={14} /> : <Folder size={14} />}</> : <><span className="tree-indent" /><FileText size={14} /></>}
        <span>{entry.name}</span>{loading.has(entry.path) && <RefreshCw size={12} className="spin" />}
      </button>
      {entry.directory && expanded.has(entry.path) && nodes(entry.path, depth + 1)}
    </li>)}
    {directories[directory]?.truncated && <li role="none" className="tree-note">{t("目录条目超过 2000 项，请缩小目录")}</li>}
    {directories[directory] && !directories[directory].entries.length && <li role="none" className="tree-note">{t("空目录")}</li>}
  </ul>;

  return <div className="file-browser" onKeyDown={event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") { event.preventDefault(); void save(); } }}>
    <aside className="file-explorer" aria-label={t("文件资源管理器")}><header><strong>{t("文件")}</strong><button type="button" aria-label={t("刷新文件列表")} onClick={() => { setError(""); for (const directory of expanded) void loadDirectory(directory); }}><RefreshCw size={13} /></button></header>{nodes(".")}</aside>
    <div className="file-editor-pane">
      {error && <div className="persistent-error" role="alert">{error}</div>}
      {notice && <div className="composer-status" role="status">{notice}</div>}
      {preview ? <>
        <header className="file-editor-header"><strong title={preview.relativePath}>{preview.relativePath}</strong>{dirty && <span className="unsaved-indicator">{t("未保存")}</span>}{busy && <RefreshCw size={13} className="spin" />}
          {document && <button type="button" disabled={busy || !dirty || running} title={running ? t("任务运行期间暂不可保存") : "Ctrl+S"} onClick={() => void save()}><Save size={13} />{t("保存文件")}</button>}
        </header>
        <div className="workbench-toolbar file-editor-tools">
          {document && <button type="button" aria-pressed={editing} onClick={() => setEditing(!editing)}>{t(editing ? "预览" : "编辑文件")}</button>}
          <button type="button" disabled={busy} onClick={() => dirty ? setPending({ path: preview.relativePath, line }) : void open(preview.relativePath, line, preview.offset)}>{t("重新加载")}</button>
          <button type="button" onClick={() => void call<{ error: string }>("open-editor", { file: preview.relativePath }).then(result => { if (result.error) setError(result.error); }).catch(cause => setError(String(cause)))}>{t("系统打开")}</button>
          {preview.kind === "image" && <><button type="button" onClick={() => setZoom(Math.max(.1, zoom - .25))}>−</button><span>{Math.round(zoom * 100)}%</span><button type="button" onClick={() => setZoom(Math.min(8, zoom + .25))}>+</button></>}
          <small>{document ? `UTF-8 · ${document.newline.toUpperCase()}` : `${preview.kind} · ${preview.size} B`}</small>
        </div>
        {editorNote && <p className="editor-note" role="status">{editorNote}</p>}
        {editing && document ? <textarea ref={source} className="file-text-editor" aria-label={t("文件编辑内容")} spellCheck={false} wrap="off" value={text} onChange={event => { const value = event.target.value; setText(value); if (value === document.text) drafts.delete(draftKey); else drafts.set(draftKey, { version: document.version, text: value }); }} /> : <div className="file-preview">
          {preview.kind === "image" ? <img src={preview.url} alt={preview.relativePath} style={{ width: `${zoom * 100}%`, maxWidth: "none" }} /> : preview.kind === "pdf" ? <Suspense fallback={<p role="status">{t("正在加载")}</p>}><PdfPreview url={preview.url!} page={line} onPage={setLine} /></Suspense> : preview.kind === "html" ? <iframe title={preview.relativePath} sandbox="" srcDoc={isolatedHtml(document ? text : preview.text || "")} /> : preview.kind === "markdown" ? <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} urlTransform={value => parseFileLink(value) || /^https?:\/\//i.test(value) ? value : ""} components={{ a: ({ href, children }) => <a href={href} onClick={event => { event.preventDefault(); if (!href) return; const link = parseFileLink(href); if (link) select(/^(?:[A-Za-z]:|[\\/])/.test(link.path) ? link.path : preview.relativePath.replace(/[^/\\]+$/, "") + link.path, link.line); else if (/^https?:\/\//i.test(href)) void window.reverie.openExternal(href); }}>{children}</a>, img: ({ alt }) => <span>{alt || t("图片")}</span> }}>{document ? text : preview.text || ""}</ReactMarkdown></div> : preview.kind === "unsupported" ? <p>{t("此格式可使用系统打开")}</p> : <div className="source-lines">{(document ? text : preview.text)?.split("\n").map((value, index) => <div className={`source-line ${index + preview.offset + 1 === line ? "selected" : ""}`} key={index}><button type="button" onClick={() => onDraft(`${preview.relativePath}:${index + preview.offset + 1}\n${value}\n${t("请检查这一行")}`)}>{index + preview.offset + 1}</button><code>{value}</code></div>)}</div>}
        </div>}
        {!document && preview.offset > 0 && <button type="button" onClick={() => void open(preview.relativePath, line, Math.max(0, preview.offset - 2000))}>{t("上一块")}</button>}
        {!document && preview.next !== null && <button type="button" onClick={() => void open(preview.relativePath, line, preview.next!)}>{t("下一块")}</button>}
      </> : <div className="workbench-empty"><FileText size={24} /><strong>{t("选择一个文件")}</strong><span>{t("展开左侧目录，点击文件即可查看或编辑。")}</span></div>}
    </div>
    {pending && <div className="workbench-confirm" role="alertdialog" aria-label={t("文件尚未保存")} onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); setPending(null); } }}>
      <h3>{t("文件尚未保存")}</h3><p>{t("保存当前修改后再打开，或者放弃修改。")}</p>
      <button type="button" autoFocus onClick={() => setPending(null)}>{t("取消")}</button>
      <button type="button" disabled={busy} onClick={() => { discard(); const next = pending; setPending(null); void open(next.path, next.line); }}>{t("放弃修改")}</button>
      <button type="button" disabled={busy || running} onClick={() => void save().then(success => { if (success) { const next = pending; setPending(null); void open(next.path, next.line); } })}>{t("保存并打开")}</button>
    </div>}
  </div>;
}
