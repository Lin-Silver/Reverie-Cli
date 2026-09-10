import { useEffect, useState } from "react";
import { FileText, RefreshCw } from "lucide-react";
import { useI18n } from "./i18n";
import type { FileChange } from "./types";

export function FileChanges({ sessionId, running, revision }: { sessionId: string; running: boolean; revision: unknown }) {
  const { t } = useI18n();
  const [changes, setChanges] = useState<FileChange[]>([]);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => { setChanges([]); setError(""); }, [sessionId]);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      if (!sessionId) return;
      try {
        const response = await window.reverie.request("getFileChanges", { sessionId });
        if (!cancelled) { setChanges(response.changes); setError(""); }
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : String(cause));
      } finally {
        if (!cancelled && running) timer = setTimeout(load, 1000);
      }
    }
    void load();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [sessionId, running, revision, refresh]);
  const totals = changes.reduce(
    (summary, change) => ({
      additions: summary.additions + (Number(change.additions) || 0),
      deletions: summary.deletions + (Number(change.deletions) || 0),
    }),
    { additions: 0, deletions: 0 },
  );
  return (
    <div className="inspector-content file-changes">
      <div className="inspector-heading">
        <span>{t("AI 文件改动")} · {changes.length}</span>
        <span className="file-change-total" aria-label={`+${totals.additions} −${totals.deletions}`}><b>+{totals.additions}</b> <i>−{totals.deletions}</i></span>
        <button type="button" aria-label={t("刷新改动")} onClick={() => setRefresh((value) => value + 1)}><RefreshCw size={13} /></button>
      </div>
      <p className="changes-note">{t("显示当前会话在本次运行中通过文件编辑工具记录的改动。")}</p>
      {error && <div role="alert" className="changes-error">{error}</div>}
      {!error && changes.length === 0 && <div className="empty-panel compact"><FileText size={22} /><strong>{t("暂无文件改动")}</strong><span>{t("AI 编辑文件后，差异会自动显示在这里。")}</span></div>}
      {changes.map((change) => (
        <details className="file-change" key={change.path} open>
          <summary><FileText size={14} /><span title={change.path}>{change.path.replaceAll("\\", "/").split("/").pop()}<small>{change.path}</small></span><em>{t(change.operation === "create" ? "新增" : change.operation === "delete" ? "删除" : "修改")}</em><code><b>+{change.additions}</b> <i>−{change.deletions}</i></code></summary>
          {change.unavailable ? <p className="changes-note">{t("二进制、大文件或缺少快照，无法显示文本差异。")}</p> : <pre className="change-diff" aria-label={change.path}>{change.diff.split("\n").map((line, index) => <span key={index} className={line.startsWith("@@") ? "hunk" : line.startsWith("+") ? "added" : line.startsWith("-") ? "removed" : ""}>{line || " "}{"\n"}</span>)}</pre>}
          {change.truncated && <p className="changes-note">{t("差异过长，已截断预览；行数仅统计预览部分。")}</p>}
        </details>
      ))}
    </div>
  );
}
