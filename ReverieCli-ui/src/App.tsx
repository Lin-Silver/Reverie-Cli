import {
  Activity,
  AlertCircle,
  Archive,
  ArchiveRestore,
  AtSign,
  Bot,
  Brain,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Circle,
  Clock3,
  Code2,
  Command,
  Copy,
  Database,
  Eye,
  EyeOff,
  FileText,
  FileSearch,
  Folder,
  FolderOpen,
  Gamepad2,
  Globe,
  Image,
  ImagePlus,
  Info,
  LayoutGrid,
  List,
  ListFilter,
  MessageSquare,
  Monitor,
  MoreHorizontal,
  Moon,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Paperclip,
  Pencil,
  Plug,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Square,
  SquareTerminal,
  Sun,
  Terminal,
  Trash2,
  Type,
  Wrench,
  X,
  Zap,
} from "lucide-react";
import {
  FormEvent,
  KeyboardEvent,
  ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type {
  CommandRecord,
  ConfigField,
  DesktopPaths,
  DesktopState,
  LiveTurn,
  ModelRecord,
  ModelSource,
  PluginRecord,
  RatsPermission,
  RatsServiceRecord,
  RatsState,
  RatsTaskRecord,
  RecoveryState,
  SessionInfo,
  SessionMessage,
  SessionState,
  SettingItem,
  SubagentRunLog,
  SubagentRunRecord,
  SubagentSpecRecord,
  SubagentsState,
  ToolRecord,
  ViewId,
} from "./types";
import {
  messageReasoningText,
  previousTurnBoundary,
  resolveToolResultNames,
  sessionIsEmpty,
  toolCallRecords,
  visibleSessionMessages,
} from "./session-utils";
import { applyTheme, normalizeTheme, THEME_STORAGE_KEY, type ThemePreference } from "./theme";
import {
  applyUiPreferences,
  backgroundPresetUrl,
  DEFAULT_UI_PREFERENCES,
  effectiveBackgroundUrl,
  normalizeUiPreferences,
  type AccentPreference,
  type BackgroundPreset,
  type FontSizePreference,
  type MessageWidthPreference,
  type UiPreferences,
} from "./preferences";
import {
  normalizeSidebarCollapsed,
  resolveSidebarCollapsed,
  SIDEBAR_AUTO_COLLAPSE_QUERY,
  SIDEBAR_COLLAPSED_STORAGE_KEY,
} from "./layout";
import { I18nProvider, UI_LANGUAGE_OPTIONS, translate, useI18n } from "./i18n";
import {
  LIVE_STREAM_RENDER_INTERVAL_MS,
  emptyLiveTurnBatch,
  mergeLiveTurnBatch,
  type LiveTurnBatch,
} from "./live-stream";
import type { ApprovalDecision } from "./core-protocol";

type Toast = { id: number; kind: "success" | "error" | "info"; message: string };

const RETIRED_MODEL_SOURCE_IDS = new Set(["unlimitedsurf", "unlimited_surf", "unlimited.surf", "us", "ue"]);

function visibleModelSources(sources: ModelSource[]): ModelSource[] {
  return sources.filter((source) => !RETIRED_MODEL_SOURCE_IDS.has(source.id.trim().toLowerCase()));
}
type ComposerAttachment = { name: string; relativePath: string; size: number };

const REVERIE_MARK_URL = new URL("reverie-mark-2.5.png", document.baseURI).href;

const MODES = [
  ["reverie", "Reverie", Code2],
  ["reverie-atlas", "Atlas", FileText],
  ["reverie-gamer", "Gamer", Gamepad2],
  ["spec-driven", "Spec", ListFilter],
  ["spec-vibe", "Spec Vibe", Sparkles],
  ["writer", "Writer", Pencil],
  ["reverie-ant", "Ant", Zap],
  ["computer-controller", "Computer", SquareTerminal],
] as const;

const QUICK_STARTS = [
  { icon: Code2, title: "理解代码库", prompt: "分析这个项目的架构、入口和关键模块，并指出最值得关注的技术风险。" },
  { icon: Wrench, title: "实现功能", prompt: "检查当前工作区，提出并实现一个最有价值且范围明确的改进，完成后运行验证。" },
  { icon: ShieldCheck, title: "审查变更", prompt: "审查当前未提交的改动，重点找出正确性、安全性和回归风险。" },
  { icon: FileText, title: "整理文档", prompt: "检查项目文档与实现是否一致，并修复最重要的文档缺口。" },
];

const THEME_OPTIONS: Array<{
  id: ThemePreference;
  label: string;
  description: string;
  icon: typeof Sun;
}> = [
  { id: "system", label: "跟随系统", description: "自动匹配 Windows 外观", icon: Monitor },
  { id: "dark", label: "深色", description: "低眩光的专注工作台", icon: Moon },
  { id: "light", label: "浅色", description: "明亮清晰的日间外观", icon: Sun },
];

const ACCENT_OPTIONS: Array<{ id: AccentPreference; label: string; color: string }> = [
  { id: "violet", label: "暮光紫", color: "#9678e4" },
  { id: "blue", label: "星海蓝", color: "#4f91e8" },
  { id: "teal", label: "极光青", color: "#35a99a" },
  { id: "rose", label: "晨曦玫", color: "#d56a8a" },
  { id: "amber", label: "琥珀金", color: "#c58a35" },
];

const FONT_SIZE_OPTIONS: Array<{ id: FontSizePreference; label: string; description: string }> = [
  { id: "compact", label: "紧凑", description: "适合高信息密度" },
  { id: "comfortable", label: "舒适", description: "默认阅读尺寸" },
  { id: "large", label: "大字体", description: "更清晰、更易阅读" },
];

const MESSAGE_WIDTH_OPTIONS: Array<{ id: MessageWidthPreference; label: string }> = [
  { id: "focused", label: "聚焦" },
  { id: "balanced", label: "平衡" },
  { id: "wide", label: "宽屏" },
];

const BACKGROUND_OPTIONS: Array<{
  id: Exclude<BackgroundPreset, "custom">;
  label: string;
  description: string;
  icon: typeof Image;
}> = [
  { id: "none", label: "纯净界面", description: "保留主题原生底色", icon: EyeOff },
  { id: "aurora-archive", label: "极光档案", description: "靛蓝、星尘与暮光", icon: Sparkles },
  { id: "moss-library", label: "苔影书库", description: "深青植物与静谧雾光", icon: Image },
  { id: "ember-manuscript", label: "余烬手稿", description: "炭黑纸张与暖铜墨迹", icon: FileText },
];

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function formatTime(value: string, language: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  return sameDay
    ? date.toLocaleTimeString(language, { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString(language, { month: "short", day: "numeric" });
}

function formatTokens(value?: number | null): string {
  if (!value) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(value % 1_000_000 ? 1 : 0)}M`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}K`;
  return String(value);
}

function projectNameFromPath(value: string): string {
  const parts = value.split(/[\\/]/).filter(Boolean);
  return parts.at(-1) || value || "Workspace";
}

function workspaceMention(value: string): string {
  const normalized = String(value || "").replaceAll("\\", "/").trim();
  if (!normalized) return "@";
  return /[\s"']/.test(normalized)
    ? `@"${normalized.replaceAll('"', '\\"')}"`
    : `@${normalized}`;
}

function formatFileSize(value: number): string {
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(value / 1024))} KB`;
}

function messageText(content: unknown, language: "zh-CN" | "en-US" = "zh-CN"): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((item) => {
        const part = asRecord(item);
        if (typeof part.text === "string") return part.text;
        if (part.type === "image_url" || part.type === "image") return translate(language, "[图片]");
        return "";
      })
      .filter(Boolean)
      .join("\n");
  }
  return content == null ? "" : JSON.stringify(content, null, 2);
}

function eventText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value == null) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function eventLabel(event: Record<string, unknown>): { title: string; detail: string; status: string; category: string; meta: string; toolName: string; agentId: string } {
  const type = String(event.type ?? event.kind ?? event.event ?? "activity");
  const eventType = String(event.event ?? type);
  const toolName = String(event.tool_name ?? event.name ?? "");
  const title = String(event.title ?? event.message ?? event.tool_name ?? event.name ?? eventType);
  const detail = eventText(event.detail ?? event.output ?? event.error ?? event.text ?? "");
  const inferredStatus = eventType === "model_request" || eventType === "tool_start"
    ? "working"
    : eventType === "model_response" || (eventType === "tool_result" && event.success !== false)
      ? "success"
      : type.includes("error") || eventType.includes("error") || (eventType === "tool_result" && event.success === false)
        ? "error"
        : "info";
  const rawStatus = String(event.status ?? inferredStatus).toLowerCase();
  const status = ["working", "running", "queued", "pending"].includes(rawStatus)
    ? "working"
    : rawStatus === "completed" || rawStatus === "done" ? "success" : rawStatus;
  const category = String(event.category ?? (eventType.includes("tool") ? "Tool" : eventType.includes("model") ? "Model" : "Activity"));
  const meta = String(event.meta ?? "");
  const agentId = String(event.agent_id ?? "");
  return { title, detail, status, category, meta, toolName, agentId };
}

function IconButton({
  label,
  children,
  onClick,
  active = false,
  disabled = false,
  ariaKeyShortcuts,
}: {
  label: string;
  children: ReactNode;
  onClick?: () => void;
  active?: boolean;
  disabled?: boolean;
  ariaKeyShortcuts?: string;
}) {
  return (
    <button
      type="button"
      className={`icon-button ${active ? "active" : ""}`}
      aria-label={label}
      aria-keyshortcuts={ariaKeyShortcuts}
      title={label}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children: linkChildren }) => (
            <a
              href={href}
              onClick={(event) => {
                event.preventDefault();
                if (href) void window.reverie.openExternal(href);
              }}
            >
              {linkChildren}
            </a>
          ),
          code: ({ className, children: codeChildren }) => (
            <code className={className}>{codeChildren}</code>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`brand ${compact ? "compact" : ""}`}>
      <div className="brand-mark"><img src={REVERIE_MARK_URL} alt="" /></div>
      {!compact && <span>Reverie</span>}
    </div>
  );
}

function LoadingScreen({ message = "正在连接 Reverie 内核" }: { message?: string }) {
  const { t } = useI18n();
  return (
    <div className="loading-screen">
      <BrandMark />
      <div className="loading-orbit"><span /></div>
      <p>{t(message)}</p>
      <small>Electron UI · Reverie CLI Core</small>
    </div>
  );
}

function ErrorScreen({ error, retry }: { error: string; retry: () => void }) {
  const { t } = useI18n();
  return (
    <div className="loading-screen error-screen">
      <div className="error-glyph"><AlertCircle size={28} /></div>
      <h1>{t("无法启动 Reverie")}</h1>
      <p>{error}</p>
      <button type="button" className="primary-button" onClick={retry}>
        <RefreshCw size={15} /> {t("重试")}
      </button>
    </div>
  );
}

function Sidebar({
  state,
  view,
  setView,
  activeSessionId,
  openSession,
  newSession,
  sessionBusy,
  selectWorkspace,
  switchWorkspace,
  openSearch,
  preferences,
  toggleSidebar,
  renameSession,
  toggleArchive,
  deleteSession,
  deleteArchivedSessions,
  deleteProject,
}: {
  state: DesktopState;
  view: ViewId;
  setView: (view: ViewId) => void;
  activeSessionId: string;
  openSession: (id: string) => void;
  newSession: () => void;
  sessionBusy: boolean;
  selectWorkspace: () => void;
  switchWorkspace: (projectRoot: string) => void;
  openSearch: () => void;
  preferences: UiPreferences;
  toggleSidebar: () => void;
  renameSession: (session: SessionInfo) => void;
  toggleArchive: (session: SessionInfo, archived: boolean) => void;
  deleteSession: (session: SessionInfo) => void;
  deleteArchivedSessions: (sessions: SessionInfo[]) => void;
  deleteProject: (project: { root: string; name: string; active: boolean }) => void;
}) {
  const { language, t } = useI18n();
  const [sessionFilter, setSessionFilter] = useState("");
  const [filterOpen, setFilterOpen] = useState(false);
  const [activeProjectOpen, setActiveProjectOpen] = useState(true);
  const [archivedOpen, setArchivedOpen] = useState(false);
  const [archiveMenuOpen, setArchiveMenuOpen] = useState(false);
  const [sessionMenuId, setSessionMenuId] = useState("");
  const [projectMenuRoot, setProjectMenuRoot] = useState("");
  const archivedIds = useMemo(
    () => new Set(preferences.archivedSessions[state.workspace.project_root] ?? []),
    [preferences.archivedSessions, state.workspace.project_root],
  );
  const filteredSessions = state.sessions.items.filter((session) =>
    session.name.toLowerCase().includes(sessionFilter.toLowerCase()),
  );
  const activeSessions = filteredSessions.filter((session) => !archivedIds.has(session.id));
  const archivedSessions = filteredSessions.filter((session) => archivedIds.has(session.id));
  const allArchivedSessions = state.sessions.items.filter((session) => archivedIds.has(session.id));
  const recentProjects = preferences.recentProjects.length
    ? preferences.recentProjects
    : [state.workspace.project_root];

  useEffect(() => {
    const closeMenu = () => {
      setSessionMenuId("");
      setProjectMenuRoot("");
      setArchiveMenuOpen(false);
    };
    const keyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") closeMenu();
    };
    window.addEventListener("pointerdown", closeMenu);
    window.addEventListener("keydown", keyDown);
    return () => {
      window.removeEventListener("pointerdown", closeMenu);
      window.removeEventListener("keydown", keyDown);
    };
  }, []);

  const renderSession = (session: SessionInfo, archived: boolean) => (
    <div className={`session-row ${session.id === activeSessionId ? "active" : ""}`} key={session.id}>
      <button
        type="button"
        className={`session-item ${session.id === activeSessionId ? "active" : ""}`}
        onClick={() => openSession(session.id)}
      >
        <span className="session-title">{session.name}</span>
        <span className="session-meta">{t("session.count", { count: session.message_count, time: formatTime(session.updated_at, language) })}</span>
      </button>
      <button
        type="button"
        className="session-more"
        aria-label={t("session.manage", { name: session.name })}
        aria-expanded={sessionMenuId === session.id}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={(event) => {
          event.stopPropagation();
          setSessionMenuId((current) => current === session.id ? "" : session.id);
        }}
      >
        <MoreHorizontal size={14} />
      </button>
      {sessionMenuId === session.id && (
        <div className="session-menu" onPointerDown={(event) => event.stopPropagation()}>
          <button type="button" onClick={() => { setSessionMenuId(""); renameSession(session); }}>
            <Pencil size={14} /><span>{t("重命名")}</span>
          </button>
          <button type="button" onClick={() => { setSessionMenuId(""); toggleArchive(session, archived); }}>
            {archived ? <ArchiveRestore size={14} /> : <Archive size={14} />}
            <span>{t(archived ? "移出归档" : "归档")}</span>
          </button>
          <div className="session-menu-separator" />
          <button type="button" className="danger" onClick={() => { setSessionMenuId(""); deleteSession(session); }}>
            <Trash2 size={14} /><span>{t("删除")}</span>
          </button>
        </div>
      )}
    </div>
  );

  return (
    <aside className="sidebar">
      <div className="sidebar-drag">
        <BrandMark />
        <button type="button" className="sidebar-collapse-button" aria-label={t("收起左侧栏")} aria-keyshortcuts="Control+B Meta+B" title={`${t("收起左侧栏")} (Ctrl+B)`} onClick={toggleSidebar}>
          <PanelLeftClose size={16} />
        </button>
      </div>
      <div className="sidebar-actions">
        <button type="button" className="new-chat-button" onClick={newSession} disabled={sessionBusy}>
          <Plus size={16} /> {t("新对话")}
          <span>Ctrl N</span>
        </button>
        <button type="button" className="sidebar-action" onClick={openSearch}>
          <Search size={15} /> {t("搜索对话")} <span>Ctrl F</span>
        </button>
      </div>

      <nav className="main-nav" aria-label={t("主导航")}>
        <button type="button" className={view === "chat" ? "active" : ""} onClick={() => setView("chat")}>
          <MessageSquare size={16} /> {t("对话")}
        </button>
        <button type="button" className={view === "tools" ? "active" : ""} onClick={() => setView("tools")}>
          <Wrench size={16} /> {t("工具")}
        </button>
        <button type="button" className={view === "subagents" ? "active" : ""} onClick={() => setView("subagents")}>
          <Bot size={16} /> {t("SubAgents")}
        </button>
        <button type="button" className={view === "rats" ? "active" : ""} onClick={() => setView("rats")}>
          <Database size={16} /> RATS
        </button>
        <button type="button" className={view === "tasks" ? "active" : ""} onClick={() => setView("tasks")}>
          <Clock3 size={16} /> {t("RTP 任务")}
        </button>
        <button type="button" className={view === "plugins" ? "active" : ""} onClick={() => setView("plugins")}>
          <Plug size={16} /> {t("插件")}
        </button>
        <button type="button" className={view === "recovery" ? "active" : ""} onClick={() => setView("recovery")}>
          <ArchiveRestore size={16} /> {t("恢复")}
        </button>
      </nav>

      <div className="project-heading">
        <span>{t("项目与会话")}</span>
        <button type="button" aria-label={t("添加工作区")} onClick={selectWorkspace}><Plus size={14} /></button>
      </div>
      <div className="project-list">
        {recentProjects.map((projectRoot) => {
          const active = projectRoot.toLowerCase() === state.workspace.project_root.toLowerCase();
          const projectName = active ? state.workspace.project_name : projectNameFromPath(projectRoot);
          return (
            <section className={`project-group ${active ? "active" : ""}`} key={projectRoot}>
              <div className="project-row-shell">
                <button
                  type="button"
                  className="project-row"
                  onClick={() => active ? setActiveProjectOpen((value) => !value) : switchWorkspace(projectRoot)}
                >
                  {active && activeProjectOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  <Folder size={15} />
                  <span>{projectName}</span>
                  {active && <small>{state.sessions.items.length}</small>}
                </button>
                <button
                  type="button"
                  className="project-more"
                  aria-label={t("project.manage", { name: projectName })}
                  aria-expanded={projectMenuRoot === projectRoot}
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={(event) => {
                    event.stopPropagation();
                    setProjectMenuRoot((current) => current === projectRoot ? "" : projectRoot);
                  }}
                >
                  <MoreHorizontal size={14} />
                </button>
                {projectMenuRoot === projectRoot && (
                  <div className="project-menu" onPointerDown={(event) => event.stopPropagation()}>
                    <button type="button" onClick={() => { setProjectMenuRoot(""); void window.reverie.reveal(projectRoot); }}>
                      <FolderOpen size={14} /><span>{t("显示项目目录")}</span>
                    </button>
                    <div className="session-menu-separator" />
                    <button type="button" className="danger" onClick={() => { setProjectMenuRoot(""); deleteProject({ root: projectRoot, name: projectName, active }); }}>
                      <Trash2 size={14} /><span>{t("删除项目与记录")}</span>
                    </button>
                  </div>
                )}
              </div>
              {active && activeProjectOpen && (
                <>
                  <div className="project-session-actions">
                    <button type="button" onClick={openSearch}><Search size={13} />{t("搜索")}</button>
                    {state.sessions.items.length > 8 && (
                      <button type="button" className={filterOpen ? "active" : ""} onClick={() => { setFilterOpen((value) => !value); setSessionFilter(""); }}>
                        <ListFilter size={13} />{t("筛选")}
                      </button>
                    )}
                  </div>
                  {filterOpen && (
                    <div className="inline-search project-filter">
                      <Search size={13} />
                      <input autoFocus value={sessionFilter} placeholder={t("筛选当前项目")} onChange={(event) => setSessionFilter(event.target.value)} />
                    </div>
                  )}
                  <div className="session-list">
                    {activeSessions.length === 0 && <div className="sidebar-empty">{t("当前项目还没有活跃会话")}</div>}
                    {activeSessions.map((session) => renderSession(session, false))}
                    {allArchivedSessions.length > 0 && (
                      <div className="archived-sessions">
                        <div className="archived-heading-shell">
                          <button type="button" className="archived-heading" onClick={() => setArchivedOpen((value) => !value)}>
                            {archivedOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                            <Archive size={13} /><span>{t("已归档")}</span><small>{allArchivedSessions.length}</small>
                          </button>
                          <button
                            type="button"
                            className="archived-more"
                            aria-label={t("管理归档会话")}
                            aria-expanded={archiveMenuOpen}
                            onPointerDown={(event) => event.stopPropagation()}
                            onClick={(event) => {
                              event.stopPropagation();
                              setArchiveMenuOpen((current) => !current);
                            }}
                          >
                            <MoreHorizontal size={14} />
                          </button>
                          {archiveMenuOpen && (
                            <div className="project-menu archived-menu" onPointerDown={(event) => event.stopPropagation()}>
                              <button type="button" className="danger" onClick={() => { setArchiveMenuOpen(false); deleteArchivedSessions(allArchivedSessions); }}>
                                <Trash2 size={14} /><span>{t("清空全部归档会话")}</span>
                              </button>
                            </div>
                          )}
                        </div>
                        {archivedOpen && archivedSessions.map((session) => renderSession(session, true))}
                      </div>
                    )}
                  </div>
                </>
              )}
            </section>
          );
        })}
      </div>

      <div className="sidebar-footer">
        <button type="button" className="workspace-button" onClick={selectWorkspace}>
          <div className="workspace-icon"><Folder size={15} /></div>
          <div>
            <strong>{state.workspace.project_name}</strong>
            <span>{state.workspace.project_root}</span>
          </div>
          <MoreHorizontal size={15} />
        </button>
        <button type="button" className={view === "settings" ? "footer-settings active" : "footer-settings"} onClick={() => setView("settings")}>
          <Settings size={16} /> {t("设置")}
        </button>
      </div>
    </aside>
  );
}

function ModelPicker({
  state,
  onSelect,
  close,
}: {
  state: DesktopState;
  onSelect: (source: ModelSource, model: ModelRecord, reasoning?: string) => void;
  close: () => void;
}) {
  const { t } = useI18n();
  const dialogRef = useRef<HTMLDivElement>(null);
  useDialogFocus(dialogRef, close);
  const sources = visibleModelSources(state.models.sources);
  const [sourceId, setSourceId] = useState(
    sources.some((item) => item.id === state.models.active_source)
      ? state.models.active_source
      : sources[0]?.id ?? "",
  );
  const [query, setQuery] = useState("");
  const [pendingSelection, setPendingSelection] = useState<{ source: ModelSource; model: ModelRecord } | null>(null);
  const source = sources.find((item) => item.id === sourceId) ?? sources[0];
  if (!source) return null;
  const models = source.models.filter((model) =>
    `${model.display_name} ${model.id}`.toLowerCase().includes(query.toLowerCase()),
  );
  const pendingReasoning = pendingSelection?.model.reasoning;
  return (
    <div className="popover-backdrop" onMouseDown={close}>
      <div ref={dialogRef} className="model-picker" role="dialog" aria-modal="true" aria-label={t("模型来源")} tabIndex={-1} onMouseDown={(event) => event.stopPropagation()}>
        <div className="model-picker-sources">
          <div className="popover-title">{t("模型来源")}</div>
          {sources.map((item) => (
            <button
              type="button"
              key={item.id}
              className={item.id === source.id ? "active" : ""}
              onClick={() => {
                setSourceId(item.id);
                setQuery("");
                setPendingSelection(null);
              }}
            >
              <span>{item.display_name}</span>
              <small>{item.models.length}</small>
            </button>
          ))}
        </div>
        <div className="model-picker-models">
          {pendingSelection && pendingReasoning && pendingReasoning.options.length > 0 ? (
            <>
              <div className="model-picker-header">
                <div>
                  <strong>{t("选择思考程度")}</strong>
                  <span>{pendingSelection.model.display_name}</span>
                </div>
                <button type="button" className="ghost-button" onClick={() => setPendingSelection(null)}>
                  <ChevronLeft size={14} /> {t("返回模型列表")}
                </button>
              </div>
              <div className="model-option-list" aria-label={t("思考程度")}>
                {pendingReasoning.options.map((option) => (
                  <button
                    type="button"
                    key={option.id}
                    className={option.id === pendingReasoning.value ? "active" : ""}
                    onClick={() => onSelect(pendingSelection.source, pendingSelection.model, option.id)}
                  >
                    <div className="model-option-icon"><Brain size={15} /></div>
                    <div>
                      <strong>{t(option.label)}</strong>
                      <span>{t(option.description || "")}</span>
                    </div>
                    {option.id === pendingReasoning.value && <Check size={16} />}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
          <div className="model-picker-header">
            <div>
              <strong>{source.display_name}</strong>
              <span>{t("选择用于当前工作区的模型")}</span>
            </div>
            <div className="inline-search model-search">
              <Search size={14} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("搜索模型")} autoFocus />
            </div>
          </div>
          <div className="model-option-list">
            {models.map((model) => (
              <button
                type="button"
                key={model.id}
                className={source.active && source.selected_model_id === model.id ? "active" : ""}
                onClick={() => {
                  if (model.reasoning.options.length > 0) {
                    setPendingSelection({ source, model });
                    return;
                  }
                  onSelect(source, model);
                }}
              >
                <div className="model-option-icon">{model.vision ? <Eye size={15} /> : <Brain size={15} />}</div>
                <div>
                  <strong>{model.display_name}</strong>
                  <span>{t(model.description || model.id)}</span>
                  <small>
                    {model.transport || "custom"} · {formatTokens(model.context_length)} context
                    {model.reasoning.control !== "none" ? ` · ${model.reasoning.control}` : ""}
                  </small>
                </div>
                {source.active && source.selected_model_id === model.id && <Check size={16} />}
              </button>
            ))}
            {models.length === 0 && <div className="empty-list">{t("没有匹配的模型")}</div>}
          </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Topbar({
  state,
  sidebarCollapsed,
  toggleSidebar,
  openModelPicker,
  selectReasoning,
  setMode,
  inspectorOpen,
  toggleInspector,
  openCommands,
  theme,
  setTheme,
}: {
  state: DesktopState;
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  openModelPicker: () => void;
  selectReasoning: (value: string) => void;
  setMode: (mode: string) => void;
  inspectorOpen: boolean;
  toggleInspector: () => void;
  openCommands: () => void;
  theme: ThemePreference;
  setTheme: (theme: ThemePreference) => void;
}) {
  const { t } = useI18n();
  const [reasoningOpen, setReasoningOpen] = useState(false);
  const [modeOpen, setModeOpen] = useState(false);
  const [themeOpen, setThemeOpen] = useState(false);
  const activeSource = visibleModelSources(state.models.sources).find((source) => source.active);
  const reasoning = activeSource?.selected_reasoning;
  const reasoningOptions = reasoning?.options ?? [];
  const selectedReasoning = reasoningOptions.find((item) => item.id === reasoning?.value);
  const mode = MODES.find((item) => item[0] === state.workspace.mode) ?? MODES[0];
  const ModeIcon = mode[2];
  const modelSelectionLocked = state.workspace.mode === "computer-controller";
  useEffect(() => {
    const closeMenus = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setReasoningOpen(false);
      setModeOpen(false);
      setThemeOpen(false);
    };
    window.addEventListener("keydown", closeMenus);
    return () => window.removeEventListener("keydown", closeMenus);
  }, []);

  return (
    <header className="topbar">
      <div className="topbar-left">
        {sidebarCollapsed && <IconButton label={`${t("展开左侧栏")} (Ctrl+B)`} ariaKeyShortcuts="Control+B Meta+B" onClick={toggleSidebar}><PanelLeftOpen size={16} /></IconButton>}
        {!modelSelectionLocked && (
          <button type="button" className="model-trigger" onClick={openModelPicker}>
            <span>{activeSource ? state.models.active_model?.display_name || t("选择模型") : t("选择模型")}</span>
            <small>{activeSource?.display_name || t("选择模型来源")}</small>
            <ChevronDown size={14} />
          </button>
        )}
        {reasoning && reasoning.control !== "none" && (
          <div className="relative">
            <button
              type="button"
              className={`reasoning-trigger ${reasoningOptions.length ? "" : "disabled"}`}
              onClick={() => {
                if (!reasoningOptions.length) return;
                setReasoningOpen((value) => !value);
                setModeOpen(false);
                setThemeOpen(false);
              }}
            >
              <Brain size={14} />
              {selectedReasoning?.label ? t(selectedReasoning.label) : t(reasoning.control === "fixed" ? "固定思考" : reasoning.control === "provider-managed" ? "自动思考" : "思考")}
              {reasoningOptions.length > 0 && <ChevronDown size={12} />}
            </button>
            {reasoningOpen && (
              <div className="small-popover reasoning-menu">
                {reasoningOptions.map((option) => (
                  <button
                    type="button"
                    key={option.id}
                    className={option.id === reasoning.value ? "active" : ""}
                    onClick={() => {
                      selectReasoning(option.id);
                      setReasoningOpen(false);
                    }}
                  >
                    <div><strong>{t(option.label)}</strong><span>{t(option.description || "")}</span></div>
                    {option.id === reasoning.value && <Check size={14} />}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      <div className="topbar-center" />
      <div className="topbar-right">
        <div className="relative">
          <button type="button" className="mode-trigger" onClick={() => {
            setModeOpen((value) => !value);
            setReasoningOpen(false);
            setThemeOpen(false);
          }}>
            <ModeIcon size={14} /> {mode[1]} <ChevronDown size={12} />
          </button>
          {modeOpen && (
            <div className="small-popover mode-menu">
              {MODES.map(([id, label, Icon]) => (
                <button
                  type="button"
                  key={id}
                  className={id === state.workspace.mode ? "active" : ""}
                  onClick={() => {
                    setMode(id);
                    setModeOpen(false);
                  }}
                >
                  <Icon size={15} /><span>{t(label)}</span>{id === state.workspace.mode && <Check size={14} />}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="relative">
          <IconButton label={t("切换主题")} onClick={() => {
            setThemeOpen((value) => !value);
            setReasoningOpen(false);
            setModeOpen(false);
          }} active={themeOpen}>
            <Palette size={16} />
          </IconButton>
          {themeOpen && (
            <div className="small-popover theme-menu">
              <div className="popover-title">{t("界面主题")}</div>
              {THEME_OPTIONS.map(({ id, label, description, icon: Icon }) => (
                <button
                  type="button"
                  key={id}
                  className={id === theme ? "active" : ""}
                  aria-pressed={id === theme}
                  onClick={() => {
                    setTheme(id);
                    setThemeOpen(false);
                  }}
                >
                  <Icon size={15} />
                  <div><strong>{t(label)}</strong><span>{t(description)}</span></div>
                  {id === theme && <Check size={14} />}
                </button>
              ))}
            </div>
          )}
        </div>
        <IconButton label={t("命令面板")} onClick={openCommands}><Command size={16} /></IconButton>
        <IconButton label={t(inspectorOpen ? "关闭检查器" : "打开检查器")} onClick={toggleInspector} active={inspectorOpen}>
          {inspectorOpen ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
        </IconButton>
      </div>
    </header>
  );
}

function ActivityItem({ event }: { event: Record<string, unknown> }) {
  const item = eventLabel(event);
  const longDetail = item.detail.length > 160 || item.detail.includes("\n");
  const statusIcon = item.status === "success"
    ? <CheckCircle2 size={14} />
    : item.status === "error" || item.status === "warning"
      ? <AlertCircle size={14} />
      : item.status === "working"
        ? <RefreshCw className="spin" size={13} />
        : <Circle size={9} />;
  const categoryIcon = item.toolName || item.category.toLowerCase().includes("tool")
    ? <ToolGlyph name={item.toolName || item.title} size={13} />
    : item.category.toLowerCase().includes("subagent")
      ? <Bot size={13} />
      : item.category.toLowerCase().includes("model")
        ? <Brain size={13} />
        : <Activity size={13} />;
  return (
    <div className={`activity-item ${item.status}`}>
      <div className="activity-status">{statusIcon}</div>
      <div className="activity-copy">
        <div className="activity-heading"><strong>{item.title}</strong><small>{categoryIcon}{item.category}</small>{item.agentId && item.agentId !== "main" && <code>{item.agentId}</code>}</div>
        {item.detail && (longDetail ? (
          <details className="activity-detail"><summary>{item.detail.replace(/\s+/g, " ").slice(0, 150)}<ChevronDown size={12} /></summary><pre>{item.detail}</pre></details>
        ) : <span className="activity-detail-inline">{item.detail}</span>)}
        {item.meta && <small className="activity-meta">{item.meta}</small>}
      </div>
    </div>
  );
}

function ToolGlyph({ name, size = 14 }: { name: string; size?: number }) {
  const normalized = name.toLowerCase();
  if (normalized.includes("search") || normalized.includes("find") || normalized.includes("grep")) return <FileSearch size={size} />;
  if (normalized.includes("shell") || normalized.includes("terminal") || normalized.includes("command") || normalized.includes("exec")) return <Terminal size={size} />;
  if (normalized.includes("browser") || normalized.includes("web") || normalized.includes("http")) return <Globe size={size} />;
  if (normalized.includes("plugin") || normalized.includes("mcp")) return <Plug size={size} />;
  if (normalized.includes("file") || normalized.includes("read") || normalized.includes("write") || normalized.includes("patch")) return <FileText size={size} />;
  return <Wrench size={size} />;
}

function HistoryToolResult({
  message,
  text,
  defaultExpanded,
}: {
  message: SessionMessage;
  text: string;
  defaultExpanded: boolean;
}) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(defaultExpanded);
  useEffect(() => setExpanded(defaultExpanded), [defaultExpanded]);
  const name = message.name || t("工具结果");
  const error = /^\s*(error|\[error|failed|exception)/i.test(text);
  return (
    <details
      className={`tool-message history-tool-result ${error ? "error" : ""}`}
      open={expanded}
      onToggle={(event) => setExpanded(event.currentTarget.open)}
    >
      <summary>
        <span className="trace-icon"><ToolGlyph name={name} /></span>
        <span className="trace-summary">
          <strong>{name}</strong>
          <small>{t(error ? "执行失败" : "工具结果")}</small>
        </span>
        <span className="trace-preview">{text.slice(0, 140)}</span>
        <ChevronDown size={13} />
      </summary>
      {expanded && <pre>{text}</pre>}
    </details>
  );
}

function HistoryReasoning({ text, defaultExpanded, active = false }: { text: string; defaultExpanded: boolean; active?: boolean }) {
  const { language, t } = useI18n();
  const [expanded, setExpanded] = useState(defaultExpanded);
  useEffect(() => setExpanded(defaultExpanded), [defaultExpanded]);
  const preview = text.replace(/\s+/g, " ").trim().slice(0, 110);
  return (
    <details className={`reasoning-block ${active ? "active" : ""}`} open={expanded} onToggle={(event) => setExpanded(event.currentTarget.open)}>
      <summary>
        <span className="reasoning-icon"><Brain size={14} /></span>
        <span className="reasoning-title"><strong>{t(active ? "正在思考" : "推理记录")}</strong><small>{t(active ? "模型正在生成推理过程" : "模型返回的内部分析")}</small></span>
        <span className="reasoning-preview">{preview}</span>
        <small>{t("reasoning.characters", { count: text.length.toLocaleString(language) })}</small>
        <ChevronDown size={13} />
      </summary>
      {expanded && <div className="reasoning-content"><Markdown>{text}</Markdown></div>}
    </details>
  );
}

function ToolCallList({ message }: { message: SessionMessage }) {
  const { t } = useI18n();
  const calls = toolCallRecords(message);
  if (!calls.length) return null;
  return (
    <div className="tool-call-list">
      {calls.map((call, index) => (
        <details className="tool-call-card" key={`${call.name}-${index}`}>
          <summary>
            <span className="trace-icon"><ToolGlyph name={call.name} /></span>
            <span><strong>{call.name}</strong><small>{t("模型调用")}</small></span>
            {call.arguments && <code>{call.arguments.replace(/\s+/g, " ").slice(0, 90)}</code>}
            <ChevronDown size={13} />
          </summary>
          {call.arguments && <pre>{call.arguments}</pre>}
        </details>
      ))}
    </div>
  );
}

function Message({ message, preferences }: { message: SessionMessage; preferences: UiPreferences }) {
  const { language, t } = useI18n();
  const text = messageText(message.content, language);
  const reasoning = messageReasoningText(message);
  const calls = toolCallRecords(message);
  const visibleReasoning = preferences.showReasoning && Boolean(reasoning);
  const visibleCalls = preferences.showToolCalls && calls.length > 0;
  if (message.role === "system" || (!text && !visibleReasoning && !visibleCalls)) return null;
  if (message.role === "tool") {
    return preferences.showToolResults
      ? <HistoryToolResult message={message} text={text} defaultExpanded={preferences.expandToolResults} />
      : null;
  }
  const user = message.role === "user";
  const technicalOnly = message.role === "assistant" && !text && (visibleReasoning || visibleCalls);
  return (
    <article className={`message ${message.role} ${technicalOnly ? "technical-only" : ""}`}>
      {!technicalOnly && <div className="message-heading">
        <div className="message-avatar">{user ? t("你") : <Sparkles size={15} strokeWidth={1.7} />}</div>
        <strong>{user ? t("你") : "Reverie"}</strong>
      </div>}
      <div className="message-body">
        {visibleReasoning && <HistoryReasoning text={reasoning} defaultExpanded={preferences.expandReasoning} />}
        {visibleCalls && <ToolCallList message={message} />}
        {text && (message.role === "assistant" ? <Markdown>{text}</Markdown> : <div className="user-text">{text}</div>)}
      </div>
    </article>
  );
}

function LiveMessage({ turn, running, preferences }: { turn: LiveTurn; running: boolean; preferences: UiPreferences }) {
  const { t } = useI18n();
  const [clock, setClock] = useState(() => Date.now());
  useEffect(() => {
    setClock(Date.now());
    if (!running) return;
    const timer = window.setInterval(() => setClock(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [running, turn.startedAt]);
  const elapsed = Math.max(0, Math.round((clock - (turn.startedAt ?? clock)) / 1000));
  const liveStatus = turn.error ? t("失败") : running ? t("正在处理") : t("已完成");
  const liveStatusClass = turn.error ? "error" : running ? "working" : "success";
  return (
    <>
      <article className="message user">
        <div className="message-heading"><div className="message-avatar">{t("你")}</div><strong>{t("你")}</strong></div>
        <div className="message-body"><div className="user-text">{turn.userText}</div></div>
      </article>
      <article className="message assistant live-message">
        <div className="message-heading"><div className="message-avatar"><Sparkles size={15} strokeWidth={1.7} /></div><strong>Reverie</strong><span className={`live-status ${liveStatusClass}`}>{liveStatus}</span></div>
        <div className="message-body">
          {preferences.showReasoning && turn.reasoningText && <HistoryReasoning text={turn.reasoningText} defaultExpanded={preferences.expandReasoning} active={running} />}
          {preferences.showLiveActivity && (running || turn.events.length > 0) && (
            <details className="live-run-summary" open={running}>
              <summary><Clock3 size={14} /><strong>{running ? t("live.elapsed", { seconds: elapsed }) : t("本轮活动")}</strong><span>{t("live.activityCount", { count: turn.events.length })}</span><ChevronDown size={13} /></summary>
              <div className="inline-activities">
                {turn.events.length
                  ? turn.events.slice(-12).map((event, index) => <ActivityItem key={index} event={event} />)
                  : <span className="activity-placeholder">{t("正在准备模型与上下文…")}</span>}
              </div>
            </details>
          )}
          {turn.assistantText ? <Markdown>{turn.assistantText}</Markdown> : running ? <div className="typing"><span /><span /><span /></div> : null}
          {turn.error && <div className="inline-error"><AlertCircle size={14} />{turn.error}</div>}
        </div>
      </article>
    </>
  );
}

function EmptyChat({ setPrompt }: { setPrompt: (prompt: string) => void }) {
  const { t } = useI18n();
  return (
    <div className="empty-chat">
      <div className="empty-mark"><img src={REVERIE_MARK_URL} alt="Reverie" /></div>
      <h1>{t("今天想一起做点什么？")}</h1>
      <p>{t("Reverie 可以理解工作区、编写代码、调用工具，并在同一会话中持续完成任务。")}</p>
      <div className="quick-grid">
        {QUICK_STARTS.map(({ icon: Icon, title, prompt }) => (
          <button type="button" key={title} onClick={() => setPrompt(t(prompt))}>
            <Icon size={16} /><strong>{t(title)}</strong><span>{t(prompt)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function MentionPicker({
  items,
  choose,
  open,
  loading,
}: {
  items: Array<Record<string, unknown>>;
  choose: (value: string) => void;
  open: boolean;
  loading: boolean;
}) {
  const { t } = useI18n();
  if (!open) return null;
  return (
    <div className={`mention-picker ${loading ? "is-loading" : ""}`} aria-live="polite" aria-busy={loading}>
      <div className="mention-picker-heading">
        <span><Sparkles size={13} />{t("Context Engine 推荐")}{loading && items.length > 0 && <RefreshCw className="spin mention-picker-refresh" size={12} />}</span>
        <small>{t("结合当前提示、会话、索引与 Git 变更")}</small>
      </div>
      {loading && items.length === 0 && <div className="mention-picker-state"><RefreshCw className="spin" size={14} />{t("正在计算最相关文件…")}</div>}
      {!loading && items.length === 0 && <div className="mention-picker-state">{t("当前工作区没有可推荐的文件")}</div>}
      {items.slice(0, 12).map((item) => {
        const pathValue = String(item.path ?? item.file_path ?? "");
        const line = Number(item.line ?? item.start_line ?? 0);
        const value = `${workspaceMention(pathValue)}${line ? `#L${line}` : ""}`;
        const reason = t(String(item.reason ?? item.summary ?? item.source ?? "工作区匹配"));
        return (
          <button type="button" key={`${String(item.kind ?? "file")}-${value}`} onClick={() => choose(value)}>
            {String(item.kind ?? "file") === "symbol" ? <Code2 size={14} /> : <FileText size={14} />}
            <div><strong>{String(item.name ?? pathValue.split(/[\\/]/).pop() ?? pathValue)}</strong><span>{pathValue}</span><small>{reason}</small></div>
          </button>
        );
      })}
    </div>
  );
}

function Composer({
  value,
  setValue,
  send,
  running,
  cancel,
  mentionItems,
  mentionOpen,
  mentionLoading,
  requestMentions,
  chooseMention,
  attachments,
  selectAttachment,
  removeAttachment,
  modelName,
  disabled = false,
}: {
  value: string;
  setValue: (value: string) => void;
  send: () => void;
  running: boolean;
  cancel: () => void;
  mentionItems: Array<Record<string, unknown>>;
  mentionOpen: boolean;
  mentionLoading: boolean;
  requestMentions: () => void;
  chooseMention: (value: string) => void;
  attachments: ComposerAttachment[];
  selectAttachment: () => void;
  removeAttachment: (attachment: ComposerAttachment) => void;
  modelName: string;
  disabled?: boolean;
}) {
  const { t } = useI18n();
  const textarea = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (!textarea.current) return;
    textarea.current.style.height = "auto";
    textarea.current.style.height = `${Math.min(textarea.current.scrollHeight, 220)}px`;
  }, [value]);

  const keyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (!running && !disabled && value.trim()) send();
    }
  };

  return (
    <div className="composer-shell">
      <MentionPicker items={mentionItems} choose={chooseMention} open={mentionOpen} loading={mentionLoading} />
      <div className="composer">
        {attachments.length > 0 && (
          <div className="attachment-strip">
            {attachments.map((attachment) => (
              <span className="attachment-chip" key={attachment.relativePath}>
                <FileText size={13} />
                <span><strong>{attachment.name}</strong><small>{formatFileSize(attachment.size)}</small></span>
                <button type="button" aria-label={t("attachment.remove", { name: attachment.name })} onClick={() => removeAttachment(attachment)}><X size={12} /></button>
              </span>
            ))}
          </div>
        )}
        <textarea
          ref={textarea}
          aria-label={t("composer.placeholder", { model: modelName || "Reverie" })}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={keyDown}
          placeholder={t("composer.placeholder", { model: modelName || "Reverie" })}
          rows={1}
          disabled={running || disabled}
        />
        <div className="composer-toolbar">
          <div>
            <IconButton label={t("Context Engine 推荐工作区文件")} onClick={requestMentions} disabled={disabled}><AtSign size={16} /></IconButton>
            <IconButton label={t("选择任意文件作为附件")} onClick={selectAttachment} disabled={disabled}><Paperclip size={16} /></IconButton>
          </div>
          <div className="composer-hint">
            {!running && <span>{t("Enter 发送 · Shift Enter 换行")}</span>}
            {running ? (
              <button type="button" className="stop-button" onClick={cancel}><Square size={12} fill="currentColor" /> {t("停止")}</button>
            ) : (
              <button type="button" className="send-button" aria-label={t("发送")} onClick={send} disabled={disabled || !value.trim()}><Send size={15} /></button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ConversationTraceBar({
  messages,
  preferences,
  updatePreferences,
}: {
  messages: SessionMessage[];
  preferences: UiPreferences;
  updatePreferences: (patch: Partial<UiPreferences>) => void;
}) {
  const { language, t } = useI18n();
  const counts = messages.reduce(
    (current, message) => ({
      reasoning: current.reasoning + (messageReasoningText(message) ? 1 : 0),
      calls: current.calls + toolCallRecords(message).length,
      results: current.results + (message.role === "tool" && messageText(message.content, language) ? 1 : 0),
    }),
    { reasoning: 0, calls: 0, results: 0 },
  );
  const hasTrace = counts.reasoning > 0 || counts.calls > 0 || counts.results > 0;
  if (!hasTrace) return null;
  return (
    <div className="conversation-trace-bar">
      <div className="trace-bar-summary">
        <span className="trace-bar-mark"><Sparkles size={13} /></span>
        <span><strong>{t("执行轨迹")}</strong><small>{t("trace.summary", { reasoning: counts.reasoning, calls: counts.calls, results: counts.results })}</small></span>
      </div>
      <div className="trace-bar-controls" aria-label={t("对话技术轨迹显示")}>
        <button
          type="button"
          className={preferences.showReasoning ? "active" : ""}
          aria-pressed={preferences.showReasoning}
          disabled={counts.reasoning === 0}
          title={t(counts.reasoning ? "显示或隐藏推理记录" : "当前会话没有保存推理记录")}
          onClick={() => updatePreferences({
            showReasoning: !preferences.showReasoning,
            ...(!preferences.showReasoning ? { expandReasoning: true } : {}),
          })}
        >
          <Brain size={13} />{t("推理")} <span>{counts.reasoning}</span>
        </button>
        <button
          type="button"
          className={preferences.showToolCalls ? "active" : ""}
          aria-pressed={preferences.showToolCalls}
          disabled={counts.calls === 0}
          onClick={() => updatePreferences({ showToolCalls: !preferences.showToolCalls })}
        >
          <Wrench size={13} />{t("调用")} <span>{counts.calls}</span>
        </button>
        <button
          type="button"
          className={preferences.showToolResults ? "active" : ""}
          aria-pressed={preferences.showToolResults}
          disabled={counts.results === 0}
          onClick={() => updatePreferences({ showToolResults: !preferences.showToolResults })}
        >
          <CheckCircle2 size={13} />{t("结果")} <span>{counts.results}</span>
        </button>
        {preferences.showReasoning && counts.reasoning > 0 && (
          <button
            type="button"
            className={preferences.expandReasoning ? "active subtle" : "subtle"}
            aria-pressed={preferences.expandReasoning}
            onClick={() => updatePreferences({ expandReasoning: !preferences.expandReasoning })}
          >
            <ChevronDown size={13} />{t(preferences.expandReasoning ? "展开中" : "仅摘要")}
          </button>
        )}
        <button
          type="button"
          className="subtle"
          title={t("只显示用户与模型正文")}
          onClick={() => updatePreferences({ showReasoning: false, showToolCalls: false, showToolResults: false })}
        >
          <EyeOff size={13} />{t("专注")}
        </button>
      </div>
    </div>
  );
}

function ChatView({
  session,
  liveTurn,
  running,
  prompt,
  setPrompt,
  send,
  cancel,
  mentionItems,
  mentionOpen,
  mentionLoading,
  requestMentions,
  chooseMention,
  attachments,
  selectAttachment,
  removeAttachment,
  modelName,
  sessionBusy,
  renameSession,
  forkSession,
  rewindSession,
  deleteSession,
  preferences,
  updatePreferences,
}: {
  session: SessionState | null;
  liveTurn: LiveTurn | null;
  running: boolean;
  prompt: string;
  setPrompt: (prompt: string) => void;
  send: () => void;
  cancel: () => void;
  mentionItems: Array<Record<string, unknown>>;
  mentionOpen: boolean;
  mentionLoading: boolean;
  requestMentions: () => void;
  chooseMention: (value: string) => void;
  attachments: ComposerAttachment[];
  selectAttachment: () => void;
  removeAttachment: (attachment: ComposerAttachment) => void;
  modelName: string;
  sessionBusy: boolean;
  renameSession: () => void;
  forkSession: () => void;
  rewindSession: () => void;
  deleteSession: () => void;
  preferences: UiPreferences;
  updatePreferences: (patch: Partial<UiPreferences>) => void;
}) {
  const { t } = useI18n();
  const transcript = useRef<HTMLDivElement>(null);
  const visibleMessages = useMemo(
    () => resolveToolResultNames(visibleSessionMessages(session?.messages ?? [])),
    [session?.messages],
  );
  const canRewind = previousTurnBoundary(session?.messages ?? []) !== null;
  useEffect(() => {
    const container = transcript.current;
    if (!container) return;
    container.scrollTop = container.scrollHeight;
  }, [session?.id, session?.messages.length, liveTurn?.assistantText, liveTurn?.reasoningText, liveTurn?.events.length]);
  return (
    <div className="chat-view">
      {session && (
        <div className="conversation-top">
          <div className="conversation-header">
            <div><strong>{session.name}</strong><span>{t("chat.recordCount", { count: visibleMessages.length })}</span></div>
            <div className="conversation-actions">
              <IconButton label={t("重命名会话")} onClick={renameSession} disabled={running || sessionBusy}><Pencil size={14} /></IconButton>
              <IconButton label={t("分叉会话")} onClick={forkSession} disabled={running || sessionBusy || visibleMessages.length === 0}><Copy size={14} /></IconButton>
              <IconButton label={t("回退上一轮")} onClick={rewindSession} disabled={running || sessionBusy || !canRewind}><RotateCcw size={14} /></IconButton>
              <IconButton label={t("删除会话")} onClick={deleteSession} disabled={running || sessionBusy}><Trash2 size={14} /></IconButton>
            </div>
          </div>
          <ConversationTraceBar messages={visibleMessages} preferences={preferences} updatePreferences={updatePreferences} />
        </div>
      )}
      <div className="transcript" ref={transcript} aria-busy={sessionBusy}>
        {sessionBusy && <div className="session-loading"><RefreshCw className="spin" size={16} />{t("正在切换会话")}</div>}
        {visibleMessages.length === 0 && !liveTurn ? (
          <EmptyChat setPrompt={setPrompt} />
        ) : (
          <div className="message-column">
            {visibleMessages.map((message, index) => <Message key={`${message.role}-${index}`} message={message} preferences={preferences} />)}
            {liveTurn && <LiveMessage turn={liveTurn} running={running} preferences={preferences} />}
          </div>
        )}
      </div>
      <Composer
        value={prompt}
        setValue={setPrompt}
        send={send}
        running={running}
        cancel={cancel}
        mentionItems={mentionItems}
        mentionOpen={mentionOpen}
        mentionLoading={mentionLoading}
        requestMentions={requestMentions}
        chooseMention={chooseMention}
        attachments={attachments}
        selectAttachment={selectAttachment}
        removeAttachment={removeAttachment}
        modelName={modelName}
        disabled={sessionBusy}
      />
    </div>
  );
}

function PageHeader({ icon, title, description, action }: { icon: ReactNode; title: string; description: string; action?: ReactNode }) {
  return (
    <div className="page-header">
      <div className="page-title-icon">{icon}</div>
      <div><h1>{title}</h1><p>{description}</p></div>
      {action && <div className="page-header-action">{action}</div>}
    </div>
  );
}

function ToolsView({ mode }: { mode: string }) {
  const { t } = useI18n();
  const [tools, setTools] = useState<ToolRecord[]>([]);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [layout, setLayout] = useState<"grid" | "list">("grid");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await window.reverie.request("listTools", { mode });
      setTools((response.tools as ToolRecord[]) ?? []);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError));
    } finally {
      setLoading(false);
    }
  }, [mode]);
  useEffect(() => { void load(); }, [load]);
  const categories = useMemo(
    () => [...new Set(tools.map((tool) => tool.category).filter(Boolean))].sort(),
    [tools],
  );
  const filtered = tools.filter((tool) => {
    const matchesCategory = category === "all" || tool.category === category;
    const haystack = `${tool.name} ${tool.description} ${tool.category} ${tool.kind} ${tool.aliases.join(" ")} ${tool.tags.join(" ")}`.toLowerCase();
    return matchesCategory && haystack.includes(query.toLowerCase());
  });
  const builtInCount = tools.filter((tool) => tool.kind === "built-in").length;
  const extensionCount = tools.length - builtInCount;
  return (
    <div className="page-scroll">
      <PageHeader icon={<Wrench size={20} />} title={t("工具")} description={t("tools.description", { mode })} action={<button type="button" className="secondary-button" onClick={() => void load()}><RefreshCw size={14} />{t("刷新")}</button>} />
      <div className="tool-overview">
        <div><Wrench size={17} /><span>{t("可用工具")}<strong>{tools.length}</strong></span></div>
        <div><ShieldCheck size={17} /><span>{t("内置工具")}<strong>{builtInCount}</strong></span></div>
        <div><Plug size={17} /><span>{t("MCP 与插件")}<strong>{extensionCount}</strong></span></div>
      </div>
      <div className="tool-controls">
        <div className="inline-search wide"><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("搜索名称、用途、参数或分类")} /></div>
        <div className="layout-toggle">
          <button type="button" className={layout === "grid" ? "active" : ""} aria-label={t("网格视图")} onClick={() => setLayout("grid")}><LayoutGrid size={14} /></button>
          <button type="button" className={layout === "list" ? "active" : ""} aria-label={t("列表视图")} onClick={() => setLayout("list")}><List size={14} /></button>
        </div>
      </div>
      <div className="category-filter">
        <button type="button" className={category === "all" ? "active" : ""} onClick={() => setCategory("all")}>{t("全部")} <span>{tools.length}</span></button>
        {categories.map((item) => (
          <button type="button" key={item} className={category === item ? "active" : ""} onClick={() => setCategory(item)}>
            {item}<span>{tools.filter((tool) => tool.category === item).length}</span>
          </button>
        ))}
      </div>
      {loading ? <div className="page-loading"><RefreshCw className="spin" size={18} />{t("读取工具目录")}</div> : error ? <div className="page-loading error"><AlertCircle size={18} />{error}</div> : (
        <div className={`tool-catalog ${layout}`}>
          {filtered.map((tool) => (
            <details className="tool-catalog-card" key={tool.name}>
              <summary>
                <div className="tool-card-icon"><ToolGlyph name={tool.name} size={17} /></div>
                <div className="tool-card-main">
                  <div><strong>{tool.name}</strong><span>{t(tool.description || "该工具未提供说明。")}</span></div>
                  <div className="tag-row">
                    <span>{tool.category}</span>
                    <span>{t(tool.kind === "built-in" ? "内置" : tool.kind === "mcp" ? "MCP" : tool.kind === "rats" ? "RATS" : "插件")}</span>
                    {tool.traits.slice(0, 2).map((trait) => <span key={trait}>{trait}</span>)}
                  </div>
                </div>
                <ChevronDown size={14} />
              </summary>
              <div className="tool-card-details">
                <div><span>{t("用途")}</span><p>{t(tool.description || "暂无说明")}</p></div>
                <div><span>{t("参数")}</span><p>{tool.properties.length ? tool.properties.join(" · ") : t("无参数")}</p></div>
                {tool.required.length > 0 && <div><span>{t("必填")}</span><p>{tool.required.join(" · ")}</p></div>}
                {tool.aliases.length > 0 && <div><span>{t("别名")}</span><p>{tool.aliases.join(" · ")}</p></div>}
                {tool.supported_modes.length > 0 && <div><span>{t("模式")}</span><p>{tool.supported_modes.join(" · ")}</p></div>}
              </div>
            </details>
          ))}
          {filtered.length === 0 && <div className="empty-panel"><Search size={24} /><strong>{t("没有匹配的工具")}</strong><span>{t("尝试更换关键词或分类。")}</span></div>}
        </div>
      )}
    </div>
  );
}

function Toggle({ checked, onChange, disabled = false }: { checked: boolean; onChange: (checked: boolean) => void; disabled?: boolean }) {
  return <button type="button" role="switch" aria-checked={checked} className={`toggle ${checked ? "on" : ""}`} onClick={() => onChange(!checked)} disabled={disabled}><span /></button>;
}

function PluginsView({
  plugins,
  updatePlugin,
  refresh,
}: {
  plugins: PluginRecord[];
  updatePlugin: (action: "setPluginEnabled" | "setPluginTrust", plugin: PluginRecord, value: boolean) => void;
  refresh: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="page-scroll">
      <PageHeader icon={<Plug size={20} />} title={t("插件")} description={t("管理运行时插件的启用状态与可执行信任。插件能力由同一个 Reverie 内核加载。")} action={<button type="button" className="secondary-button" onClick={refresh}><RefreshCw size={14} />{t("重新扫描")}</button>} />
      <div className="plugin-list">
        {plugins.map((plugin) => (
          <div className="plugin-card" key={plugin.id}>
            <div className="plugin-icon"><Plug size={18} /></div>
            <div className="plugin-main">
              <div className="plugin-title"><strong>{plugin.name}</strong><span className={`status-pill ${plugin.status}`}>{t(plugin.status_label || plugin.status)}</span></div>
              <p>{plugin.family} · v{plugin.version || "—"}</p>
              <div className="plugin-stats"><span>{plugin.tool_count} tools</span><span>{plugin.command_count} commands</span><span>{plugin.skill_count} skills</span></div>
            </div>
            <div className="plugin-toggles">
              <label><span>{t("信任执行")}</span><Toggle checked={plugin.trusted} onChange={(value) => updatePlugin("setPluginTrust", plugin, value)} /></label>
              <label><span>{t("启用")}</span><Toggle checked={plugin.enabled} onChange={(value) => updatePlugin("setPluginEnabled", plugin, value)} /></label>
            </div>
          </div>
        ))}
        {plugins.length === 0 && <div className="empty-panel"><Plug size={26} /><strong>{t("没有发现运行时插件")}</strong><span>{t("将插件放入 Reverie 插件目录后重新扫描。")}</span></div>}
      </div>
    </div>
  );
}

function RecoveryView({ recovery, rollback }: { recovery: RecoveryState; rollback: (checkpointId: string) => void }) {
  const { language, t } = useI18n();
  const total = Number(recovery.summary.total_operations ?? recovery.operations.length);
  const files = (recovery.summary.modified_files as string[] | undefined) ?? [];
  return (
    <div className="page-scroll">
      <PageHeader icon={<ArchiveRestore size={20} />} title={t("恢复与历史")} description={t("检查操作记录和自动检查点，并在明确确认后恢复会话与文件。")} />
      <div className="metric-grid">
        <div><Database size={16} /><span>{t("操作记录")}</span><strong>{total}</strong></div>
        <div><FileText size={16} /><span>{t("已修改文件")}</span><strong>{files.length}</strong></div>
        <div><RotateCcw size={16} /><span>{t("检查点")}</span><strong>{recovery.checkpoints.length}</strong></div>
      </div>
      <section className="page-section">
        <div className="section-heading"><div><h2>{t("检查点")}</h2><p>{t("恢复会同时回退检查点之后受跟踪的文件和会话消息。")}</p></div></div>
        <div className="recovery-list">
          {recovery.checkpoints.map((checkpoint) => (
            <div className="recovery-item" key={checkpoint.id}>
              <div className="timeline-dot"><Clock3 size={13} /></div>
              <div><strong>{t(checkpoint.description)}</strong><span>{formatTime(checkpoint.created_at, language)} · {t("recovery.checkpointMeta", { messages: checkpoint.message_count, files: checkpoint.file_checkpoints.length })}</span></div>
              <button type="button" className="secondary-button danger-ghost" onClick={() => rollback(checkpoint.id)}><RotateCcw size={13} />{t("恢复")}</button>
            </div>
          ))}
          {recovery.checkpoints.length === 0 && <div className="empty-row">{t("当前工作区还没有检查点")}</div>}
        </div>
      </section>
      <section className="page-section">
        <div className="section-heading"><div><h2>{t("最近操作")}</h2><p>{t("内核记录的提问、工具调用和文件操作。")}</p></div></div>
        <div className="operation-list">
          {recovery.operations.slice().reverse().slice(0, 100).map((operation) => (
            <div key={operation.id}><span className="operation-type">{operation.operation_type.replaceAll("_", " ")}</span><strong>{t(operation.description)}</strong><time>{formatTime(operation.timestamp, language)}</time></div>
          ))}
          {recovery.operations.length === 0 && <div className="empty-row">{t("还没有操作历史")}</div>}
        </div>
      </section>
    </div>
  );
}

function SettingControl({ item, update }: { item: SettingItem; update: (key: string, value: unknown) => void }) {
  const { t } = useI18n();
  if (item.kind === "bool" || item.kind === "workspace" || item.kind === "plugin-bool") {
    return <Toggle checked={Boolean(item.value)} onChange={(value) => update(item.key, value)} />;
  }
  if (item.kind === "choice") {
    const labels = item.labels ?? {};
    return (
      <select value={String(item.value ?? "")} onChange={(event) => update(item.key, event.target.value)}>
        {(item.choices ?? []).map((choice) => {
          const raw = String(choice);
          return <option key={raw} value={raw}>{t(labels[raw] ?? raw)}</option>;
        })}
      </select>
    );
  }
  if (item.kind === "int") {
    return <input type="number" value={Number(item.value ?? 0)} min={item.min} max={item.max} step={item.step ?? 1} onChange={(event) => update(item.key, Number(event.target.value))} />;
  }
  if (item.kind === "rules") {
    return <RulesEditor item={item} update={update} />;
  }
  return <span className="setting-readonly">{String(item.value ?? "—")}</span>;
}

function RulesEditor({ item, update }: { item: SettingItem; update: (key: string, value: unknown) => void }) {
  const { t } = useI18n();
  const savedValue = String(item.value ?? "");
  const [value, setValue] = useState(savedValue);
  useEffect(() => setValue(savedValue), [savedValue]);
  const changed = value !== savedValue;
  return (
    <div className="rules-editor">
      <textarea value={value} rows={6} onChange={(event) => setValue(event.target.value)} />
      <div>
        {changed && <span>{t("有未保存的更改")}</span>}
        <button type="button" className="secondary-button" onClick={() => setValue(savedValue)} disabled={!changed}>{t("撤销")}</button>
        <button type="button" className="primary-button" onClick={() => update(item.key, value)} disabled={!changed}>{t("保存规则")}</button>
      </div>
    </div>
  );
}

function ProviderFieldControl({ field, value, configured, update }: { field: ConfigField; value: unknown; configured: boolean; update: (key: string, value: unknown) => void }) {
  const { t } = useI18n();
  const [visible, setVisible] = useState(false);
  if (field.kind === "bool") return <Toggle checked={Boolean(value)} onChange={(checked) => update(field.key, checked)} />;
  if (field.kind === "choice") return <select value={String(value ?? "")} onChange={(event) => update(field.key, event.target.value)}>{(field.choices ?? []).map((choice) => <option key={choice} value={choice}>{choice}</option>)}</select>;
  const type = field.kind === "secret" && !visible ? "password" : field.kind === "int" || field.kind === "float" ? "number" : "text";
  return (
    <div className="field-input-wrap">
      <input
        type={type}
        value={String(value ?? "")}
        min={field.min}
        max={field.max}
        step={field.kind === "float" ? "0.1" : undefined}
        placeholder={field.kind === "secret" && configured ? t("已配置；留空保持不变") : field.optional ? t("可选") : ""}
        onChange={(event) => update(field.key, type === "number" ? Number(event.target.value) : event.target.value)}
      />
      {field.kind === "secret" && <button type="button" onClick={() => setVisible((shown) => !shown)}>{visible ? <EyeOff size={14} /> : <Eye size={14} />}</button>}
    </div>
  );
}

function ProviderSettings({
  state,
  selectModel,
  saveProvider,
  addStandard,
  deleteStandard,
}: {
  state: DesktopState;
  selectModel: (source: ModelSource, model: ModelRecord) => void;
  saveProvider: (source: ModelSource, patch: Record<string, unknown>) => void;
  addStandard: () => void;
  deleteStandard: (index: number) => void;
}) {
  const { t } = useI18n();
  const [sourceId, setSourceId] = useState(state.models.active_source);
  const sources = visibleModelSources(state.models.sources);
  const source = sources.find((item) => item.id === sourceId) ?? sources[0];
  const [patch, setPatch] = useState<Record<string, unknown>>({});
  useEffect(() => setPatch({}), [source?.id]);
  if (!source) return null;
  const valueFor = (field: ConfigField) => field.key in patch ? patch[field.key] : source.config?.values[field.key];
  const sourceDescription = source.id === "standard"
    ? t("管理任意 OpenAI、Anthropic、Responses 或请求兼容模型。")
    : source.id === "agnes" && source.modalities
      ? t("provider.liveCatalog", { llm: source.modalities.llm, tti: source.modalities.tti, ttv: source.modalities.ttv, catalog: t(source.modalities.live ? "官方实时目录" : "内置回退目录") })
      : t("provider.modelCount", { count: source.models.length });
  return (
    <div className="provider-settings">
      <div className="provider-tabs">
        {sources.map((item) => <button type="button" key={item.id} className={item.id === source.id ? "active" : ""} onClick={() => setSourceId(item.id)}>{item.display_name}{item.active && <span />}</button>)}
      </div>
      <div className="provider-content">
        <div className="section-heading">
          <div><h2>{source.display_name}</h2><p>{sourceDescription}</p></div>
          {source.id === "standard" && <button type="button" className="primary-button small" onClick={addStandard}><Plus size={14} />{t("添加模型")}</button>}
        </div>
        <div className="settings-model-grid">
          {source.models.map((model) => (
            <div className={`settings-model-card ${source.active && source.selected_model_id === model.id ? "active" : ""}`} key={model.id}>
              <button type="button" className="model-card-main" onClick={() => selectModel(source, model)}>
                <div><strong>{model.display_name}</strong><span>{model.id}</span></div>
                {source.active && source.selected_model_id === model.id ? <CheckCircle2 size={16} /> : <Circle size={14} />}
              </button>
              <p>{t(model.description)}</p>
              <div className="tag-row"><span>{formatTokens(model.context_length)} ctx</span>{model.vision && <span>vision</span>}{model.tool_calling && <span>tools</span>}{model.reasoning.control !== "none" && <span>{model.reasoning.control}</span>}</div>
              {source.id === "standard" && <button type="button" className="delete-model" onClick={() => deleteStandard(Number(model.id))}><Trash2 size={13} /></button>}
            </div>
          ))}
          {source.models.length === 0 && <div className="empty-panel compact"><Database size={22} /><strong>{t("还没有标准模型")}</strong><span>{t("添加一个模型后即可用于 TUI、命令行和 GUI。")}</span></div>}
        </div>
        {source.config_fields.length > 0 && (
          <div className="provider-config">
            <div className="section-heading"><div><h2>{t("连接配置")}</h2><p>{t("密钥仅写入 Reverie 内核配置，不会回传到界面。")}</p></div><button type="button" className="primary-button small" onClick={() => saveProvider(source, patch)} disabled={!Object.keys(patch).length}>{t("保存")}</button></div>
            <div className="form-grid">
              {source.config_fields.map((field) => (
                <label key={field.key}><span>{t(field.label)}{field.optional && <small>{t("可选")}</small>}</span><ProviderFieldControl field={field} value={valueFor(field)} configured={Boolean(source.config?.configured_secrets[field.key])} update={(key, value) => setPatch((current) => ({ ...current, [key]: value }))} /></label>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SettingsView({
  state,
  updateSetting,
  selectModel,
  saveProvider,
  addStandard,
  deleteStandard,
  paths,
  selectCoreData,
  theme,
  setTheme,
  preferences,
  updatePreferences,
  selectBackground,
  clearBackground,
}: {
  state: DesktopState;
  updateSetting: (key: string, value: unknown) => void;
  selectModel: (source: ModelSource, model: ModelRecord) => void;
  saveProvider: (source: ModelSource, patch: Record<string, unknown>) => void;
  addStandard: () => void;
  deleteStandard: (index: number) => void;
  paths: DesktopPaths | null;
  selectCoreData: () => void;
  theme: ThemePreference;
  setTheme: (theme: ThemePreference) => void;
  preferences: UiPreferences;
  updatePreferences: (patch: Partial<UiPreferences>) => void;
  selectBackground: () => void;
  clearBackground: () => void;
}) {
  const { t } = useI18n();
  const [tab, setTab] = useState<"general" | "appearance" | "conversation" | "models" | "about">("general");
  const items = state.settings.items.filter((item) => !item.key.startsWith("plugin_enabled:") && !["active_model_source", "active_model_index"].includes(item.key));
  const activeBackgroundUrl = effectiveBackgroundUrl(preferences);
  const activeBackgroundLabel = preferences.backgroundPreset === "custom"
    ? preferences.backgroundName || t("导入图片")
    : t(BACKGROUND_OPTIONS.find((option) => option.id === preferences.backgroundPreset)?.label || "纯净界面");
  return (
    <div className="settings-page">
      <div className="settings-nav">
        <div><h1>{t("设置")}</h1><p>Reverie Desktop</p></div>
        <button type="button" className={tab === "general" ? "active" : ""} onClick={() => setTab("general")}><SlidersHorizontal size={15} />{t("通用")}</button>
        <button type="button" className={tab === "appearance" ? "active" : ""} onClick={() => setTab("appearance")}><Palette size={15} />{t("外观")}</button>
        <button type="button" className={tab === "conversation" ? "active" : ""} onClick={() => setTab("conversation")}><MessageSquare size={15} />{t("对话显示")}</button>
        <button type="button" className={tab === "models" ? "active" : ""} onClick={() => setTab("models")}><Brain size={15} />{t("模型与提供商")}</button>
        <button type="button" className={tab === "about" ? "active" : ""} onClick={() => setTab("about")}><Info size={15} />{t("关于")}</button>
      </div>
      <div className="settings-content">
        {tab === "general" && (
          <>
            <PageHeader icon={<SlidersHorizontal size={20} />} title={t("通用设置")} description={t("这些设置由 CLI 内核持久化，TUI 和 GUI 会同步使用。")} />
            <section className="preference-section language-section">
              <div className="preference-heading"><div><h2>{t("界面语言")}</h2><p>{t("选择 Reverie GUI 使用的语言，切换后立即生效。")}</p></div></div>
              <div className="preference-row">
                <div><Globe size={17} /><span><strong>{t("语言")}</strong><small>{t("选择 Reverie GUI 使用的语言，切换后立即生效。")}</small></span></div>
                <div className="segmented-control language-control">
                  {UI_LANGUAGE_OPTIONS.map((option) => <button type="button" key={option.id} className={preferences.language === option.id ? "active" : ""} aria-pressed={preferences.language === option.id} onClick={() => updatePreferences({ language: option.id })}>{t(option.label)}</button>)}
                </div>
              </div>
            </section>
            <section className="preference-section">
              <div className="preference-heading"><div><h2>{t("默认启动方式")}</h2><p>{t("选择双击 Reverie 时打开图形界面或终端界面；命令行参数仍可临时覆盖。")}</p></div></div>
              <div className="preference-row">
                <div><SquareTerminal size={17} /><span><strong>{t("启动界面")}</strong><small>{t("设置将在下次启动时生效")}</small></span></div>
                <div className="segmented-control">
                  <button type="button" className={preferences.startupMode === "gui" ? "active" : ""} aria-pressed={preferences.startupMode === "gui"} onClick={() => updatePreferences({ startupMode: "gui" })}><Monitor size={14} />{t("图形界面")}</button>
                  <button type="button" className={preferences.startupMode === "tui" ? "active" : ""} aria-pressed={preferences.startupMode === "tui"} onClick={() => updatePreferences({ startupMode: "tui" })}><Terminal size={14} />{t("终端界面")}</button>
                </div>
              </div>
            </section>
            {paths && <div className="core-data-card"><div className="core-data-heading"><Database size={18} /><div><strong>{t("CLI 数据与历史")}</strong><p>{t("GUI 会直接读取此目录中的配置、会话、检查点和插件状态。")}</p></div></div><code>{paths.coreAppRoot}</code><div><button type="button" className="secondary-button" onClick={() => void window.reverie.reveal(paths.coreAppRoot)}><FolderOpen size={14} />{t("显示目录")}</button><button type="button" className="secondary-button" onClick={selectCoreData}><Folder size={14} />{t("切换数据目录")}</button></div></div>}
            <div className="setting-list">
              {items.map((item) => {
                const hint = item.descriptions?.[String(item.value ?? "")] ?? "";
                return (
                  <div className={`setting-row ${item.kind === "rules" ? "stacked" : ""}`} key={item.key}>
                    <div>
                      <strong>{t(item.name)}</strong>
                      <p>{t(item.description)}</p>
                      {hint && <p className="setting-hint">{t(hint)}</p>}
                    </div>
                    <SettingControl item={item} update={updateSetting} />
                  </div>
                );
              })}
            </div>
          </>
        )}
        {tab === "appearance" && (
          <>
            <PageHeader icon={<Palette size={20} />} title={t("外观")} description={t("调整主题、强调色、阅读尺度与工作区背景；所有设置会立即预览。")} />
            <section className="appearance-panel preference-section">
              <div className="appearance-copy">
                <div><h2>{t("界面主题")}</h2><p>{t("跟随系统会在 Windows 深色与浅色模式之间自动切换。")}</p></div>
                <span>{t("appearance.current", { value: t(THEME_OPTIONS.find((option) => option.id === theme)?.label || "") })}</span>
              </div>
              <div className="theme-grid">
                {THEME_OPTIONS.map(({ id, label, description, icon: Icon }) => (
                  <button type="button" key={id} className={`theme-card ${id === theme ? "active" : ""}`} aria-pressed={id === theme} onClick={() => setTheme(id)}>
                    <div className="theme-card-copy">
                      <span className="theme-card-icon"><Icon size={15} /></span>
                      <div><strong>{t(label)}</strong><small>{t(description)}</small></div>
                      {id === theme && <CheckCircle2 size={17} />}
                    </div>
                  </button>
                ))}
              </div>
            </section>
            <section className="preference-section">
              <div className="preference-heading"><div><h2>{t("强调色")}</h2><p>{t("用于焦点、选中状态、图标和技术活动。")}</p></div></div>
              <div className="accent-grid">
                {ACCENT_OPTIONS.map((option) => (
                  <button type="button" key={option.id} className={preferences.accent === option.id ? "active" : ""} aria-pressed={preferences.accent === option.id} onClick={() => updatePreferences({ accent: option.id })}>
                    <span style={{ backgroundColor: option.color }} /><strong>{t(option.label)}</strong>{preferences.accent === option.id && <Check size={14} />}
                  </button>
                ))}
              </div>
            </section>
            <section className="preference-section">
              <div className="preference-heading"><div><h2>{t("文字与阅读宽度")}</h2><p>{t("同时调整导航、正文和技术轨迹的字号与回答行长。")}</p></div></div>
              <div className="preference-row">
                <div><Type size={17} /><span><strong>{t("字体大小")}</strong><small>{t("选择整体界面阅读尺度")}</small></span></div>
                <div className="segmented-control">
                  {FONT_SIZE_OPTIONS.map((option) => <button type="button" key={option.id} className={preferences.fontSize === option.id ? "active" : ""} onClick={() => updatePreferences({ fontSize: option.id })}>{t(option.label)}</button>)}
                </div>
              </div>
              <div className="preference-row">
                <div><PanelRightOpen size={17} /><span><strong>{t("回答宽度")}</strong><small>{t("控制长回答和代码块占用的宽度")}</small></span></div>
                <div className="segmented-control">
                  {MESSAGE_WIDTH_OPTIONS.map((option) => <button type="button" key={option.id} className={preferences.messageWidth === option.id ? "active" : ""} onClick={() => updatePreferences({ messageWidth: option.id })}>{t(option.label)}</button>)}
                </div>
              </div>
            </section>
            <section className="preference-section">
              <div className="preference-heading">
                <div><h2>{t("工作区背景")}</h2><p>{t("选择 Reverie 原创背景，或导入自己的图片；自定义图片会复制到便携版数据目录。")}</p></div>
                <div className="preference-actions">
                  {preferences.backgroundPreset === "custom" && preferences.backgroundUrl && <button type="button" className="secondary-button" onClick={clearBackground}>{t("删除导入")}</button>}
                  <button type="button" className="primary-button" onClick={selectBackground}><ImagePlus size={14} />{t("导入图片")}</button>
                </div>
              </div>
              <div className="background-picker">
                {BACKGROUND_OPTIONS.map((option) => {
                  const OptionIcon = option.icon;
                  const url = backgroundPresetUrl(option.id);
                  return (
                    <button
                      type="button"
                      key={option.id}
                      className={preferences.backgroundPreset === option.id ? "active" : ""}
                      aria-pressed={preferences.backgroundPreset === option.id}
                      style={url ? { backgroundImage: `url("${url}")` } : undefined}
                      onClick={() => updatePreferences({
                        backgroundPreset: option.id,
                        ...(option.id !== "none" && preferences.backgroundOpacity < 0.72 ? { backgroundOpacity: 0.9 } : {}),
                      })}
                    >
                      <span className="background-card-overlay" />
                      <span className="background-card-copy"><OptionIcon size={15} /><strong>{t(option.label)}</strong><small>{t(option.description)}</small></span>
                      {preferences.backgroundPreset === option.id && <CheckCircle2 size={17} />}
                    </button>
                  );
                })}
                {preferences.backgroundUrl && (
                  <button
                    type="button"
                    className={preferences.backgroundPreset === "custom" ? "active" : ""}
                    aria-pressed={preferences.backgroundPreset === "custom"}
                    style={{ backgroundImage: `url("${preferences.backgroundUrl}")` }}
                    onClick={() => updatePreferences({ backgroundPreset: "custom" })}
                  >
                    <span className="background-card-overlay" />
                    <span className="background-card-copy"><ImagePlus size={15} /><strong>{t("我的图片")}</strong><small>{preferences.backgroundName}</small></span>
                    {preferences.backgroundPreset === "custom" && <CheckCircle2 size={17} />}
                  </button>
                )}
              </div>
              <div className={`background-preview ${activeBackgroundUrl ? "has-image" : ""}`} style={activeBackgroundUrl ? { backgroundImage: `url("${activeBackgroundUrl}")` } : undefined}>
                {activeBackgroundUrl ? <span>{activeBackgroundLabel}</span> : <div><Image size={22} /><strong>{t("纯净主题背景")}</strong><span>{t("选择上方背景即可立即预览")}</span></div>}
              </div>
              <div className="range-grid">
                <label><span>{t("照片强度")} <strong>{Math.round(preferences.backgroundOpacity * 100)}%</strong></span><input type="range" min="0" max="1" step="0.01" value={preferences.backgroundOpacity} onChange={(event) => updatePreferences({ backgroundOpacity: Number(event.target.value) })} /></label>
                <label><span>{t("模糊")} <strong>{preferences.backgroundBlur}px</strong></span><input type="range" min="0" max="24" step="1" value={preferences.backgroundBlur} onChange={(event) => updatePreferences({ backgroundBlur: Number(event.target.value) })} /></label>
                <label><span>{t("压暗")} <strong>{Math.round(preferences.backgroundDim * 100)}%</strong></span><input type="range" min="0" max="0.8" step="0.01" value={preferences.backgroundDim} onChange={(event) => updatePreferences({ backgroundDim: Number(event.target.value) })} /></label>
              </div>
            </section>
          </>
        )}
        {tab === "conversation" && (
          <>
            <PageHeader icon={<MessageSquare size={20} />} title={t("对话显示")} description={t("决定思考记录、模型调用、工具结果和实时活动在对话中如何呈现。")} />
            <section className="preference-section conversation-presets">
              <div className="preference-heading"><div><h2>{t("显示预设")}</h2><p>{t("选择预设后仍可单独调整每一项。")}</p></div></div>
              <div className="preset-grid">
                <button type="button" className={!preferences.showReasoning && !preferences.showToolCalls && !preferences.showToolResults ? "active" : ""} onClick={() => updatePreferences({ showReasoning: false, showToolCalls: false, showToolResults: false, showLiveActivity: false })}><MessageSquare size={16} /><strong>{t("纯净对话")}</strong><span>{t("只显示用户与模型正文")}</span></button>
                <button type="button" className={!preferences.showReasoning && preferences.showToolCalls && !preferences.showToolResults ? "active" : ""} onClick={() => updatePreferences({ showReasoning: false, showToolCalls: true, showToolResults: false, showLiveActivity: true })}><Wrench size={16} /><strong>{t("调用优先")}</strong><span>{t("显示模型调用了什么")}</span></button>
                <button type="button" className={!preferences.showReasoning && !preferences.showToolCalls && preferences.showToolResults ? "active" : ""} onClick={() => updatePreferences({ showReasoning: false, showToolCalls: false, showToolResults: true, showLiveActivity: false })}><CheckCircle2 size={16} /><strong>{t("结果优先")}</strong><span>{t("只保留工具返回结果")}</span></button>
                <button type="button" className={preferences.showReasoning && preferences.showToolCalls && preferences.showToolResults ? "active" : ""} onClick={() => updatePreferences({ showReasoning: true, expandReasoning: true, showToolCalls: true, showToolResults: true, showLiveActivity: true })}><Brain size={16} /><strong>{t("完整轨迹")}</strong><span>{t("展开推理并显示全部技术细节")}</span></button>
              </div>
            </section>
            <section className="preference-section">
              <div className="preference-row"><div><Brain size={17} /><span><strong>{t("推理记录")}</strong><small>{t("显示模型返回并保存在会话中的思考内容")}</small></span></div><Toggle checked={preferences.showReasoning} onChange={(value) => updatePreferences({ showReasoning: value, ...(value ? { expandReasoning: true } : {}) })} /></div>
              <div className="preference-row"><div><ChevronDown size={17} /><span><strong>{t("默认展开推理")}</strong><small>{t("开启后直接显示推理正文，而不是只显示摘要栏")}</small></span></div><Toggle checked={preferences.expandReasoning} disabled={!preferences.showReasoning} onChange={(value) => updatePreferences({ expandReasoning: value })} /></div>
              <div className="preference-row"><div><Wrench size={17} /><span><strong>{t("工具调用")}</strong><small>{t("显示工具名称与调用参数")}</small></span></div><Toggle checked={preferences.showToolCalls} onChange={(value) => updatePreferences({ showToolCalls: value })} /></div>
              <div className="preference-row"><div><CheckCircle2 size={17} /><span><strong>{t("工具结果")}</strong><small>{t("显示工具实际返回的内容")}</small></span></div><Toggle checked={preferences.showToolResults} onChange={(value) => updatePreferences({ showToolResults: value })} /></div>
              <div className="preference-row"><div><ChevronDown size={17} /><span><strong>{t("默认展开结果")}</strong><small>{t("打开会话时直接展开工具输出")}</small></span></div><Toggle checked={preferences.expandToolResults} disabled={!preferences.showToolResults} onChange={(value) => updatePreferences({ expandToolResults: value })} /></div>
              <div className="preference-row"><div><Clock3 size={17} /><span><strong>{t("实时活动")}</strong><small>{t("运行期间显示进度、工具事件和审批状态")}</small></span></div><Toggle checked={preferences.showLiveActivity} onChange={(value) => updatePreferences({ showLiveActivity: value })} /></div>
            </section>
            <section className="conversation-display-preview">
              <div className="preview-title"><Eye size={15} /><span>{t("当前呈现预览")}</span></div>
              {preferences.showReasoning && <div className="preview-trace reasoning"><Brain size={14} /><span>{t("推理记录")}</span><small>{t(preferences.expandReasoning ? "直接展开正文" : "显示摘要栏")}</small></div>}
              {preferences.showToolCalls && <div className="preview-trace"><Wrench size={14} /><span>read_file</span><small>{t("模型调用")}</small></div>}
              {preferences.showToolResults && <div className="preview-trace result"><CheckCircle2 size={14} /><span>read_file</span><small>{t("工具结果")}</small></div>}
              {!preferences.showReasoning && !preferences.showToolCalls && !preferences.showToolResults && <p>{t("技术轨迹已隐藏，对话中只显示正文。")}</p>}
            </section>
          </>
        )}
        {tab === "models" && (
          <>
            <PageHeader icon={<Brain size={20} />} title={t("模型与提供商")} description={t("选择模型、配置凭据，并检查模型级思考与多模态能力。")} />
            <ProviderSettings state={state} selectModel={selectModel} saveProvider={saveProvider} addStandard={addStandard} deleteStandard={deleteStandard} />
          </>
        )}
        {tab === "about" && (
          <>
            <PageHeader icon={<Info size={20} />} title={t("关于 Reverie")} description={t("Electron 仅承载界面；所有 AI、工具和会话逻辑都由嵌入的 Reverie CLI exe 执行。")} />
            <div className="about-card"><div className="about-mark"><img src={REVERIE_MARK_URL} alt="Reverie" /></div><div><h2>Reverie {state.core.version}</h2><p>Core Interface {state.core.interface_version} · {state.core.release_status}</p></div></div>
            <div className="path-list"><button type="button" onClick={() => void window.reverie.reveal(state.workspace.config_path)}><span>{t("配置文件")}</span><code>{state.workspace.config_path}</code><FolderOpen size={14} /></button><button type="button" onClick={() => void window.reverie.reveal(state.workspace.project_data_dir)}><span>{t("工作区数据")}</span><code>{state.workspace.project_data_dir}</code><FolderOpen size={14} /></button>{paths && <button type="button" onClick={() => void window.reverie.reveal(paths.kernelPath)}><span>{t("CLI 内核")}</span><code>{paths.kernelPath}</code><FolderOpen size={14} /></button>}</div>
          </>
        )}
      </div>
    </div>
  );
}

function Inspector({
  state,
  liveTurn,
  indexWorkspace,
  compactContext,
  compactDisabled,
}: {
  state: DesktopState;
  liveTurn: LiveTurn | null;
  indexWorkspace: () => void;
  compactContext: () => void;
  compactDisabled: boolean;
}) {
  const { t } = useI18n();
  const [tab, setTab] = useState<"context" | "activity">("context");
  const permission = state.settings.items.find((item) => item.key === "permission_level")?.value;
  const events = liveTurn?.events ?? [];
  const contextEngine = state.workspace.context_engine;
  const contextLabel = contextEngine?.indexing
    ? t("context.indexing", { progress: Math.round(contextEngine.progress) })
    : contextEngine?.ready
      ? t("自动检索已启用")
      : t("正在按需预热");
  return (
    <aside className="inspector">
      <div className="inspector-tabs"><button type="button" className={tab === "context" ? "active" : ""} onClick={() => setTab("context")}>{t("上下文")}</button><button type="button" className={tab === "activity" ? "active" : ""} onClick={() => setTab("activity")}>{t("活动")} {events.length > 0 && <span>{events.length}</span>}</button></div>
      {tab === "context" ? (
        <div className="inspector-content">
          <section><div className="inspector-heading"><span>{t("工作区")}</span><div className="inspector-actions"><button type="button" onClick={compactContext} disabled={compactDisabled} aria-label={t("压缩上下文")} title={t("压缩上下文")}><Archive size={13} /></button><button type="button" onClick={indexWorkspace} title={t("重新索引")}><RefreshCw className={contextEngine?.indexing ? "spin" : ""} size={13} /></button></div></div><div className="context-card"><Folder size={15} /><div><strong>{state.workspace.project_name}</strong><span>{state.workspace.project_root}</span></div></div><div className="context-engine-card"><div><span className="context-engine-orbit"><Sparkles size={14} /></span><span><strong>Context Engine</strong><small>{contextLabel}</small></span></div><div className="context-engine-metrics"><span><strong>{contextEngine?.files ?? 0}</strong> {t("文件")}</span><span><strong>{contextEngine?.symbols ?? 0}</strong> {t("符号")}</span></div>{contextEngine?.indexing && <div className="context-progress"><span style={{ width: `${Math.max(3, contextEngine.progress)}%` }} /></div>}</div></section>
          <section><div className="inspector-heading"><span>{t("运行时")}</span></div><div className="context-line"><span>{t("模型")}</span><strong>{state.models.active_model?.display_name || t("未配置")}</strong></div><div className="context-line"><span>Source</span><strong>{visibleModelSources(state.models.sources).find((item) => item.active)?.display_name}</strong></div><div className="context-line"><span>{t("模式")}</span><strong>{state.workspace.mode}</strong></div><div className="context-line"><span>{t("权限")}</span><strong>{String(permission ?? "workspace_write")}</strong></div></section>
          <section><div className="inspector-heading"><span>{t("恢复")}</span></div><div className="context-line"><span>{t("检查点")}</span><strong>{state.recovery.checkpoints.length}</strong></div><div className="context-line"><span>{t("操作")}</span><strong>{String(state.recovery.summary.total_operations ?? state.recovery.operations.length)}</strong></div></section>
          <section><div className="inspector-heading"><span>{t("快捷提示")}</span></div><div className="hint-card"><AtSign size={14} /><span><kbd>@</kbd> {t("会用 Context Engine 推荐当前任务最相关的文件。")}</span></div><div className="hint-card"><Paperclip size={14} /><span>{t("回形针可选择任意文件，并安全复制到工作区附件区。")}</span></div><div className="hint-card"><Command size={14} /><span><kbd>Ctrl K</kbd> {t("打开完整命令目录。")}</span></div></section>
        </div>
      ) : (
        <div className="inspector-content activity-feed">{events.length ? events.map((event, index) => <ActivityItem key={index} event={event} />) : <div className="empty-panel compact"><Clock3 size={22} /><strong>{t("暂无实时活动")}</strong><span>{t("模型调用工具时会在这里显示。")}</span></div>}</div>
      )}
    </aside>
  );
}

function CommandPalette({ commands, close, choose }: { commands: CommandRecord[]; close: () => void; choose: (command: CommandRecord) => void }) {
  const { t } = useI18n();
  const dialogRef = useRef<HTMLDivElement>(null);
  useDialogFocus(dialogRef, close);
  const [query, setQuery] = useState("");
  const filtered = commands.filter((item) => `${item.command} ${item.summary} ${item.section}`.toLowerCase().includes(query.toLowerCase())).slice(0, 30);
  return (
    <div className="modal-backdrop" onMouseDown={close}>
      <div ref={dialogRef} className="command-palette" role="dialog" aria-modal="true" aria-label={t("命令面板")} tabIndex={-1} onMouseDown={(event) => event.stopPropagation()}>
        <div className="command-search"><Search size={17} /><input autoFocus aria-label={t("搜索命令、工具和功能…")} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("搜索命令、工具和功能…")} /><kbd>Esc</kbd></div>
        <div className="command-results">{filtered.map((item) => <button type="button" key={item.id} onClick={() => choose(item)}><div className="command-icon"><Command size={14} /></div><div><strong>{item.command}</strong><span>{t(item.summary)}</span></div><small>{t(item.section)}</small></button>)}</div>
        <div className="command-footer"><span><kbd>↵</kbd> {t("插入命令参考")}</span><span>{t("完整功能可直接通过 GUI 页面或自然语言调用")}</span></div>
      </div>
    </div>
  );
}

function SessionSearch({ close, openSession }: { close: () => void; openSession: (id: string) => void }) {
  const { t } = useI18n();
  const dialogRef = useRef<HTMLDivElement>(null);
  useDialogFocus(dialogRef, close);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Array<Record<string, unknown>>>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [completedQuery, setCompletedQuery] = useState("");
  useEffect(() => {
    const normalized = query.trim();
    if (!normalized) { setResults([]); setSearching(false); setError(""); setCompletedQuery(""); return; }
    let cancelled = false;
    setSearching(true);
    setError("");
    const timer = window.setTimeout(async () => {
      try {
        const response = await window.reverie.request("searchSessions", { query: normalized });
        if (!cancelled) {
          setResults(response.results);
          setCompletedQuery(normalized);
        }
      } catch (searchError) {
        if (!cancelled) setError(searchError instanceof Error ? searchError.message : String(searchError));
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, 220);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [query]);
  return (
    <div className="modal-backdrop" onMouseDown={close}>
      <div ref={dialogRef} className="command-palette session-search-modal" role="dialog" aria-modal="true" aria-label={t("搜索所有会话内容…")} tabIndex={-1} onMouseDown={(event) => event.stopPropagation()}>
        <div className="command-search"><Search size={17} /><input autoFocus aria-label={t("搜索所有会话内容…")} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("搜索所有会话内容…")} /><button type="button" aria-label={t("关闭")} onClick={close}><X size={15} /></button></div>
        <div className="session-search-results">
          {searching && <div className="empty-row"><RefreshCw className="spin" size={14} />{t("正在搜索")}</div>}
          {error && <div className="empty-row error"><AlertCircle size={14} />{error}</div>}
          {!searching && !error && results.map((result) => <button type="button" key={`${result.session_id}-${result.message_index}`} onClick={() => { openSession(String(result.session_id)); close(); }}><MessageSquare size={14} /><div><strong>{String(result.session_name)}</strong><span>{String(result.text)}</span></div><small>{Number(result.message_index) < 0 ? t("标题") : `#${Number(result.message_index) + 1}`}</small></button>)}
          {!searching && !error && completedQuery === query.trim() && results.length === 0 && <div className="empty-row">{t("没有匹配的会话内容")}</div>}
        </div>
      </div>
    </div>
  );
}

function RenameSessionModal({ session, close, save }: { session: { id: string; name: string }; close: () => void; save: (name: string) => void }) {
  const { t } = useI18n();
  const dialogRef = useRef<HTMLFormElement>(null);
  useDialogFocus(dialogRef, close);
  const [name, setName] = useState(session.name);
  const valid = Boolean(name.trim());
  return (
    <div className="modal-backdrop" onMouseDown={close}>
      <form ref={dialogRef} className="form-modal rename-session-modal" role="dialog" aria-modal="true" aria-labelledby="rename-session-title" tabIndex={-1} onMouseDown={(event) => event.stopPropagation()} onSubmit={(event) => { event.preventDefault(); if (valid) save(name.trim()); }}>
        <div className="form-modal-header"><div><h2 id="rename-session-title">{t("重命名会话")}</h2><p>{t("使用一个容易辨认的标题，历史记录会立即同步更新。")}</p></div><IconButton label={t("关闭")} onClick={close}><X size={16} /></IconButton></div>
        <div className="form-grid single"><label><span>{t("会话标题")}</span><input autoFocus value={name} maxLength={120} onChange={(event) => setName(event.target.value)} /></label></div>
        <div className="form-modal-footer"><button type="button" className="secondary-button" onClick={close}>{t("取消")}</button><button type="submit" className="primary-button" disabled={!valid}>{t("保存")}</button></div>
      </form>
    </div>
  );
}

function StandardModelModal({ close, save }: { close: () => void; save: (model: Record<string, unknown>) => void }) {
  const { t } = useI18n();
  const dialogRef = useRef<HTMLFormElement>(null);
  useDialogFocus(dialogRef, close);
  const [model, setModel] = useState<Record<string, unknown>>({ provider: "openai-chat", supports_vision: false, max_context_tokens: 128000 });
  const update = (key: string, value: unknown) => setModel((current) => ({ ...current, [key]: value }));
  const valid = Boolean(model.model && model.model_display_name && model.base_url);
  return (
    <div className="modal-backdrop" onMouseDown={close}>
      <form ref={dialogRef} className="form-modal" role="dialog" aria-modal="true" aria-labelledby="standard-model-title" tabIndex={-1} onMouseDown={(event) => event.stopPropagation()} onSubmit={(event) => { event.preventDefault(); if (valid) save(model); }}>
        <div className="form-modal-header"><div><h2 id="standard-model-title">{t("添加标准模型")}</h2><p>{t("该模型会同时出现在 TUI、命令行和 GUI 中。")}</p></div><IconButton label={t("关闭")} onClick={close}><X size={16} /></IconButton></div>
        <div className="form-grid single"><label><span>{t("模型 ID")}</span><input autoFocus value={String(model.model ?? "")} onChange={(event) => update("model", event.target.value)} placeholder={t("例如 gpt-5.4")} /></label><label><span>{t("显示名称")}</span><input value={String(model.model_display_name ?? "")} onChange={(event) => update("model_display_name", event.target.value)} placeholder={t("例如 GPT-5.4")} /></label><label><span>Provider</span><select value={String(model.provider)} onChange={(event) => update("provider", event.target.value)}><option value="openai-chat">OpenAI Chat Completions</option><option value="openai-responses">OpenAI Responses</option><option value="anthropic">Anthropic</option><option value="request">Generic Request</option><option value="curl">cURL</option></select></label><label><span>Base URL</span><input value={String(model.base_url ?? "")} onChange={(event) => update("base_url", event.target.value)} placeholder="https://api.example.com/v1" /></label><label><span>API Key</span><input type="password" value={String(model.api_key ?? "")} onChange={(event) => update("api_key", event.target.value)} /></label><label><span>{t("上下文长度")}</span><input type="number" value={Number(model.max_context_tokens)} onChange={(event) => update("max_context_tokens", Number(event.target.value))} /></label><label className="inline-toggle"><span>{t("支持视觉")}</span><Toggle checked={Boolean(model.supports_vision)} onChange={(value) => update("supports_vision", value)} /></label></div>
        <div className="form-modal-footer"><button type="button" className="secondary-button" onClick={close}>{t("取消")}</button><button type="submit" className="primary-button" disabled={!valid}>{t("添加模型")}</button></div>
      </form>
    </div>
  );
}

function ConfirmModal({ title, message, confirmLabel, danger = false, close, confirm }: { title: string; message: string; confirmLabel: string; danger?: boolean; close: () => void; confirm: () => void }) {
  const { t } = useI18n();
  const dialogRef = useRef<HTMLDivElement>(null);
  useDialogFocus(dialogRef, close);
  return (
    <div className="modal-backdrop" onMouseDown={close}>
      <div ref={dialogRef} className="confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="confirmation-title" aria-describedby="confirmation-message" tabIndex={-1} onMouseDown={(event) => event.stopPropagation()}>
        <div className={`confirm-icon ${danger ? "danger" : ""}`}>{danger ? <AlertCircle size={20} /> : <Info size={20} />}</div>
        <h2 id="confirmation-title">{title}</h2>
        <p id="confirmation-message">{message}</p>
        <div><button type="button" className="secondary-button" onClick={close}>{t("取消")}</button><button type="button" className={danger ? "danger-button" : "primary-button"} onClick={confirm}>{confirmLabel}</button></div>
      </div>
    </div>
  );
}

const RATS_PERMISSION_OPTIONS: RatsPermission[] = ["read", "project", "edit", "asset", "run", "build", "ai"];

function normalizeRatsState(next: RatsState): RatsState {
  if (Array.isArray(next.enabledProviders)) return next;
  const legacy = Array.isArray(next.enabledEngines) ? next.enabledEngines : [];
  return {
    ...next,
    enabledProviders: legacy.map((selection) => ({
      providerId: "reverie.engine",
      executable: selection.executable,
      permissions: selection.permissions,
    })),
  };
}

function RatsView() {
  const { t } = useI18n();
  const [state, setState] = useState<RatsState | null>(null);
  const [permissionDrafts, setPermissionDrafts] = useState<Record<string, RatsPermission[]>>({});
  const [definitions, setDefinitions] = useState<Record<string, Record<string, unknown>>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [logsOpen, setLogsOpen] = useState(false);

  const acceptState = useCallback((next: RatsState) => {
    const normalized = normalizeRatsState(next);
    setState(normalized);
    setPermissionDrafts((current) => {
      const updated = { ...current };
      for (const service of normalized.services) {
        if (!updated[service.executable]) updated[service.executable] = service.permissions;
      }
      for (const selection of normalized.enabledProviders ?? []) updated[selection.executable] = selection.permissions;
      return updated;
    });
  }, []);

  const load = useCallback(async (foreground = false) => {
    if (foreground) setLoading(true);
    try {
      const response = await window.reverie.request("ratsState", {});
      acceptState(response.rats);
      setError("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError));
    } finally {
      setLoading(false);
    }
  }, [acceptState]);

  useEffect(() => {
    void load(true);
    const timer = window.setInterval(() => void load(false), 2500);
    return () => window.clearInterval(timer);
  }, [load]);

  const registerProvider = useCallback(async () => {
    setBusy("add");
    try {
      const providerId = state?.supportedProviders[0]?.providerId;
      if (!providerId) throw new Error("No supported RATS provider is registered.");
      const executable = await window.reverie.selectRatsProvider(providerId);
      if (executable) {
        const response = await window.reverie.request("ratsRegisterProvider", { providerId, executable });
        acceptState(response.rats);
      }
      setError("");
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : String(actionError));
    } finally {
      setBusy("");
    }
  }, [acceptState, state?.supportedProviders]);

  const setEnabled = useCallback(async (service: RatsServiceRecord, enabled: boolean, permissions?: RatsPermission[]) => {
    setBusy(service.serviceId);
    try {
      const selected = permissions ?? permissionDrafts[service.executable] ?? ["read"];
      const response = await window.reverie.request("ratsSetProviderEnabled", {
        providerId: service.providerId,
        executable: service.executable,
        enabled,
        permissions: selected,
      });
      acceptState(response.rats);
      setError("");
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : String(actionError));
    } finally {
      setBusy("");
    }
  }, [acceptState, permissionDrafts]);

  const togglePermission = useCallback((service: RatsServiceRecord, permission: RatsPermission) => {
    const current = permissionDrafts[service.executable] ?? service.permissions;
    let next = current.includes(permission)
      ? current.filter((item) => item !== permission)
      : [...current, permission];
    if (!next.length) next = ["read"];
    next = [...new Set(next)].sort() as RatsPermission[];
    setPermissionDrafts((drafts) => ({ ...drafts, [service.executable]: next }));
    if (service.enabled) void setEnabled(service, true, next);
  }, [permissionDrafts, setEnabled]);

  const inspectTool = useCallback(async (service: RatsServiceRecord, name: string) => {
    const key = `${service.serviceId}:${name}`;
    setBusy(key);
    try {
      const response = await window.reverie.request("ratsDescribe", { serviceId: service.serviceId, names: [name] });
      setDefinitions((current) => ({ ...current, [key]: response.definitions[0] ?? { name, schema_available: false } }));
      setError("");
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : String(actionError));
    } finally {
      setBusy("");
    }
  }, []);

  const removeRoot = useCallback(async (root: string) => {
    setBusy(root);
    try {
      const response = await window.reverie.request("ratsRemoveRoot", { root });
      acceptState(response.rats);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : String(actionError));
    } finally {
      setBusy("");
    }
  }, [acceptState]);

  const connected = state?.services.filter((service) => service.connection === "connected").length ?? 0;
  const available = state?.services.filter((service) => service.connection !== "unreachable").length ?? 0;
  const toolCount = state?.services.reduce((total, service) => total + service.tools.length, 0) ?? 0;
  const diagnostics = state ? [...state.diagnostics].reverse() : [];
  const offlineSelections = state?.enabledProviders?.filter((selection) =>
    !state.services.some((service) =>
      service.providerId.toLowerCase() === selection.providerId.toLowerCase()
      && service.executable.toLowerCase() === selection.executable.toLowerCase()
    )) ?? [];

  return (
    <div className="page-scroll rats-page">
      <PageHeader
        icon={<Database size={20} />}
        title="RATS"
        description={t("RATS 支持多个经过批准的 Reverie/Rilance 提供者；当前主动选择列表中只有 Reverie Engine 已实现并验证。")}
        action={<div className="header-action-row"><button type="button" className="secondary-button" aria-expanded={logsOpen} aria-controls="rats-diagnostic-panel" onClick={() => setLogsOpen((open) => !open)}><FileText size={14} />{t("RTP 日志")}</button><button type="button" className="secondary-button" onClick={() => void load(true)} disabled={loading}><RefreshCw className={loading ? "spin" : ""} size={14} />{t("刷新")}</button><button type="button" className="primary-button" onClick={() => void registerProvider()} disabled={busy === "add"}><Plus size={14} />{t("登记提供者应用")}</button></div>}
      />
      <div className="tool-overview rats-overview">
        <div><Globe size={17} /><span>{t("发现服务")}<strong>{state?.services.length ?? 0}</strong></span></div>
        <div><ShieldCheck size={17} /><span>{t("已连接会话")}<strong>{connected}</strong></span></div>
        <div><Wrench size={17} /><span>{t("已公开工具")}<strong>{toolCount}</strong></span></div>
      </div>
      <div className="rats-security-note">
        <ShieldCheck size={18} />
        <div><strong>{t("受支持提供者，工具默认关闭")}</strong><span>{t("只显示已登记、正在运行并通过身份握手的 Reverie 提供者；未知或离线条目仅写入本地诊断日志。控制令牌和 RTP 会话令牌不会发送到页面或写入设置。")}</span></div>
      </div>
      {logsOpen && <section id="rats-diagnostic-panel" className="rats-log-panel" aria-labelledby="rats-log-title">
        <div className="rats-log-header"><div><h2 id="rats-log-title">{t("RTP 检索日志")}</h2><p>{t("记录发现、拒绝、握手、超时与目录请求；不记录令牌或工具参数。")}</p></div><button type="button" aria-label={t("关闭 RTP 日志")} onClick={() => setLogsOpen(false)}><X size={15} /></button></div>
        <div className="rats-log-summary">
          <div><span>{t("最近扫描")}</span><strong>{state?.scanDurationMs ?? 0} ms</strong></div>
          <div><span>{t("已拒绝条目")}</span><strong>{state?.rejectedDescriptorCount ?? 0}</strong></div>
          <code title={state?.diagnosticsPath}>{state?.diagnosticsPath || t("等待日志路径")}</code>
        </div>
        <div className="rats-log-list">
          {diagnostics.map((entry, index) => {
            const context = [entry.providerId, entry.serviceId, entry.operation, entry.reason, entry.path].filter(Boolean).join(" · ");
            return <div className={`rats-log-row ${entry.level}`} key={`${entry.timestampUtc}:${entry.event}:${index}`}>
              <time>{entry.timestampUtc.replace("T", " ").replace("Z", " UTC")}</time>
              <div><strong>{entry.event}</strong>{context && <span title={context}>{context}</span>}</div>
              <code>{entry.durationMs === undefined ? "—" : `${entry.durationMs} ms`}</code>
            </div>;
          })}
          {diagnostics.length === 0 && <div className="rats-log-empty">{t("刷新后将在这里显示 RATS 检索与 RTP 请求记录。")}</div>}
        </div>
      </section>}
      {error && <div className="page-loading error"><AlertCircle size={18} />{error}</div>}
      {loading && !state ? <div className="page-loading"><RefreshCw className="spin" size={18} />{t("扫描本地 RATS 服务")}</div> : (
        <>
          <div className="rats-section-heading"><div><h2>{t("受支持提供者")}</h2><p>{t("从每个提供者可执行文件旁的本地 RATS 发现目录实时读取。")}</p></div><span>{available}/{state?.services.length ?? 0}</span></div>
          <div className="rats-service-grid">
            {state?.services.map((service) => {
              const selectedPermissions = permissionDrafts[service.executable] ?? service.permissions;
              const statusLabel = service.connection === "connected" ? t("已连接") : service.connection === "available" ? t("可用") : t("不可达");
              return (
                <section className={`rats-service-card ${service.connection}`} key={service.serviceId}>
                  <div className="rats-service-header">
                    <div className="rats-service-emblem"><Sparkles size={20} /></div>
                    <div><h3>{service.product}</h3><p>{service.productVersion || service.protocol}</p></div>
                    <span className={`rats-status ${service.connection}`}><Circle size={8} fill="currentColor" />{statusLabel}</span>
                    <Toggle checked={service.enabled} disabled={busy === service.serviceId} onChange={(enabled) => void setEnabled(service, enabled)} />
                  </div>
                  <div className="rats-service-meta">
                    <div><span>{t("提供者")}</span><code>{service.providerId}</code></div>
                    <div><span>{t("端点")}</span><code>{service.endpoint}</code></div>
                    <div><span>{t("进程")}</span><code>PID {service.pid}</code></div>
                    <div><span>{t("服务 ID")}</span><code>{service.serviceId}</code></div>
                    <div><span>{t("身份握手")}</span><code>{service.probeLatencyMs} ms</code></div>
                    <div className="wide"><span>{t("提供者可执行文件")}</span><code title={service.executable}>{service.executable}</code></div>
                  </div>
                  <div className="rats-permissions">
                    <div><strong>{t("会话权限")}</strong><span>{t("修改已启用服务的权限会立即轮换会话令牌。")}</span></div>
                    <div className="permission-chips">
                      {RATS_PERMISSION_OPTIONS.map((permission) => (
                        <button type="button" key={permission} className={selectedPermissions.includes(permission) ? "active" : ""} onClick={() => togglePermission(service, permission)} disabled={busy === service.serviceId}>{permission}</button>
                      ))}
                    </div>
                  </div>
                  {service.error && <div className="rats-inline-error"><AlertCircle size={14} />{service.error}</div>}
                  <div className="rats-catalog-heading"><div><strong>{t("RTP 紧凑目录")}</strong><span>{service.tools.length ? t("按需展开定义，不把全部 schema 注入提示词。") : t(service.enabled ? "正在等待工具目录" : "启用服务后读取工具目录")}</span></div><span>{service.tools.length}/{service.nativeToolCount}</span></div>
                  {service.tools.length > 0 && <div className="rats-tool-list">
                    {service.tools.map((tool) => {
                      const definitionKey = `${service.serviceId}:${tool.name}`;
                      return <details key={tool.name} className="rats-tool-row">
                        <summary><div><strong>{tool.name}</strong><span>{tool.summary || t("暂无说明")}</span></div><span>{tool.permission}</span><ChevronDown size={14} /></summary>
                        <div className="rats-tool-detail">
                          <div className="tag-row"><span>{tool.category}</span>{tool.flags.map((flag) => <span key={flag}>{flag}</span>)}</div>
                          <button type="button" className="secondary-button" onClick={() => void inspectTool(service, tool.name)} disabled={busy === definitionKey}>{busy === definitionKey ? <RefreshCw className="spin" size={13} /> : <FileSearch size={13} />}{t("检查完整定义")}</button>
                          {definitions[definitionKey] && <pre>{JSON.stringify(definitions[definitionKey], null, 2)}</pre>}
                        </div>
                      </details>;
                    })}
                  </div>}
                </section>
              );
            })}
            {state?.services.length === 0 && <div className="empty-panel rats-empty"><Database size={28} /><strong>{t("尚未发现正在运行的 RATS 服务")}</strong><span>{t("启动已支持的提供者应用，或登记其可执行文件以检查固定的本地服务目录；拒绝原因可在 RTP 日志中审查。")}</span><button type="button" className="primary-button" onClick={() => void registerProvider()}><Plus size={14} />{t("登记提供者应用")}</button></div>}
          </div>
          {offlineSelections.length > 0 && <section className="rats-offline-panel"><div className="rats-section-heading"><div><h2>{t("已保存但离线")}</h2><p>{t("这些提供者下次启动时会自动建立已授权会话。")}</p></div></div>{offlineSelections.map((selection) => <div className="rats-offline-row" key={`${selection.providerId}:${selection.executable}`}><Database size={15} /><div><strong>{selection.providerId}</strong><code>{selection.executable}</code></div><span>{selection.permissions.join(" · ")}</span></div>)}</section>}
          {state && state.configuredDiscoveryRoots.length > 0 && <section className="rats-roots-panel"><div className="rats-section-heading"><div><h2>{t("已登记发现目录")}</h2><p>{t("设置实时保存在 Reverie CLI 可执行文件旁的 .reverie/rats 目录中。")}</p></div><code title={state.statePath}>{state.statePath}</code></div>{state.configuredDiscoveryRoots.map((root) => <div className="rats-root-row" key={root}><Folder size={15} /><code>{root}</code><button type="button" aria-label={t("移除发现目录")} onClick={() => void removeRoot(root)} disabled={busy === root}><X size={14} /></button></div>)}</section>}
        </>
      )}
    </div>
  );
}

const ACTIVE_SUBAGENT_STATUSES = new Set(["queued", "running", "cancelling"]);

function subagentStatusLabel(status: string, t: (key: string) => string): string {
  const normalized = status.trim().toLowerCase();
  if (normalized === "queued") return t("排队中");
  if (normalized === "running") return t("运行中");
  if (normalized === "cancelling") return t("正在取消");
  if (normalized === "cancelled") return t("已取消");
  if (normalized === "failed") return t("失败");
  if (normalized === "completed") return t("已完成");
  return status || t("未知");
}

function subagentModelName(agent: SubagentSpecRecord): string {
  return String(agent.model_ref.display_name ?? agent.model_ref.model ?? agent.model_ref.source ?? "—");
}

function SubagentsView() {
  const { language, t } = useI18n();
  const [snapshot, setSnapshot] = useState<SubagentsState | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState("all");
  const [selectedRunId, setSelectedRunId] = useState("");
  const [runLog, setRunLog] = useState<SubagentRunLog | null>(null);
  const [runFilter, setRunFilter] = useState("");
  const [detailTab, setDetailTab] = useState<"timeline" | "output">("timeline");
  const [loading, setLoading] = useState(true);
  const [logLoading, setLogLoading] = useState(false);
  const [error, setError] = useState("");
  const loadInFlight = useRef(false);
  const logSequence = useRef(0);

  const load = useCallback(async (foreground = false) => {
    if (loadInFlight.current) return;
    loadInFlight.current = true;
    if (foreground) setLoading(true);
    try {
      const response = await window.reverie.request("getSubagents", {});
      setSnapshot(response.subagents);
      setError("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError));
    } finally {
      setLoading(false);
      loadInFlight.current = false;
    }
  }, []);

  useEffect(() => { void load(true); }, [load]);

  const hasActiveRuns = snapshot?.runs.some((run) => ACTIVE_SUBAGENT_STATUSES.has(run.status.toLowerCase())) ?? false;
  useEffect(() => {
    const timer = window.setInterval(() => void load(false), hasActiveRuns ? 1_500 : 6_000);
    return () => window.clearInterval(timer);
  }, [hasActiveRuns, load]);

  const filteredRuns = useMemo(() => {
    const needle = runFilter.trim().toLowerCase();
    return (snapshot?.runs ?? []).filter((run) => {
      if (selectedAgentId !== "all" && run.subagent_id !== selectedAgentId) return false;
      if (!needle) return true;
      return [run.run_id, run.task_id, run.subagent_id, run.status, run.summary, run.error]
        .some((value) => value.toLowerCase().includes(needle));
    });
  }, [runFilter, selectedAgentId, snapshot?.runs]);

  useEffect(() => {
    if (selectedRunId && filteredRuns.some((run) => run.run_id === selectedRunId)) return;
    setSelectedRunId(filteredRuns[0]?.run_id ?? "");
  }, [filteredRuns, selectedRunId]);

  const selectedRun = filteredRuns.find((run) => run.run_id === selectedRunId) ?? null;
  useEffect(() => {
    const sequence = ++logSequence.current;
    if (!selectedRunId) {
      setRunLog(null);
      return;
    }
    setLogLoading(true);
    void window.reverie.request("getSubagentRunLog", { runId: selectedRunId }).then((response) => {
      if (sequence === logSequence.current) setRunLog(response.log);
    }).catch((logError) => {
      if (sequence === logSequence.current) {
        setRunLog(null);
        setError(logError instanceof Error ? logError.message : String(logError));
      }
    }).finally(() => {
      if (sequence === logSequence.current) setLogLoading(false);
    });
  }, [selectedRunId, selectedRun?.ended_at, selectedRun?.status]);

  const agents = snapshot?.agents ?? [];
  const runs = snapshot?.runs ?? [];
  const activeCount = runs.filter((run) => ACTIVE_SUBAGENT_STATUSES.has(run.status.toLowerCase())).length;
  const completedCount = runs.filter((run) => run.status.toLowerCase() === "completed").length;
  const failedCount = runs.filter((run) => run.status.toLowerCase() === "failed").length;
  const selectedAgent = agents.find((agent) => agent.id === selectedRun?.subagent_id);
  const runStatus = selectedRun?.status.toLowerCase() ?? "";
  const runOutput = selectedRun?.error || selectedRun?.summary || runLog?.run.error || runLog?.run.summary || "";

  return (
    <div className="page-scroll subagents-page">
      <PageHeader
        icon={<Bot size={20} />}
        title={t("SubAgents")}
        description={t("集中查看委派代理、运行状态、执行时间线与脱敏日志。")}
        action={<button type="button" className="secondary-button" onClick={() => void load(true)} disabled={loading}><RefreshCw className={loading ? "spin" : ""} size={14} />{t("刷新")}</button>}
      />
      <div className="tool-overview subagent-overview">
        <div><Bot size={17} /><span>{t("已配置代理")}<strong>{agents.length}</strong></span></div>
        <div><Activity size={17} /><span>{t("正在执行")}<strong>{activeCount}</strong></span></div>
        <div><CheckCircle2 size={17} /><span>{t("已完成运行")}<strong>{completedCount}</strong></span></div>
        <div><AlertCircle size={17} /><span>{t("失败运行")}<strong>{failedCount}</strong></span></div>
      </div>
      {error && <div className="page-loading error"><AlertCircle size={18} />{error}</div>}
      {snapshot && !snapshot.available ? (
        <div className="empty-panel subagent-empty"><Bot size={30} /><strong>{t("当前模式不支持 SubAgents")}</strong><span>{t("请切换到 Reverie 或 Computer 模式后再查看。")}</span></div>
      ) : (
        <div className="subagent-dashboard">
          <section className="subagent-agent-panel" aria-labelledby="subagent-agents-title">
            <div className="subagent-panel-heading"><div><h2 id="subagent-agents-title">{t("代理")}</h2><p>{t("按代理筛选运行记录")}</p></div><span>{agents.length}</span></div>
            <div className="subagent-agent-list">
              <button type="button" className={selectedAgentId === "all" ? "active" : ""} onClick={() => setSelectedAgentId("all")}>
                <span className="subagent-avatar all"><Bot size={16} /></span>
                <span><strong>{t("全部代理")}</strong><small>{t("subagent.runCount", { count: runs.length })}</small></span>
              </button>
              {agents.map((agent) => {
                const agentRuns = runs.filter((run) => run.subagent_id === agent.id);
                const agentActive = agentRuns.some((run) => ACTIVE_SUBAGENT_STATUSES.has(run.status.toLowerCase()));
                return (
                  <button type="button" className={selectedAgentId === agent.id ? "active" : ""} key={agent.id} onClick={() => setSelectedAgentId(agent.id)}>
                    <span className={`subagent-avatar ${agentActive ? "working" : ""}`} style={{ color: agent.color, borderColor: agent.color }}><Bot size={16} /></span>
                    <span><strong>{agent.name || agent.id}</strong><small>{subagentModelName(agent)}</small></span>
                    <code>{agentRuns.length}</code>
                  </button>
                );
              })}
              {!agents.length && !loading && <div className="subagent-list-empty"><Bot size={22} /><span>{t("尚未配置 SubAgent")}</span><small>{t("可在对话中让 Reverie 创建并委派代理。")}</small></div>}
            </div>
          </section>

          <section className="subagent-runs-panel" aria-labelledby="subagent-runs-title">
            <div className="subagent-panel-heading runs"><div><h2 id="subagent-runs-title">{t("运行记录")}</h2><p>{t(hasActiveRuns ? "活动运行每 1.5 秒自动刷新" : "显示当前工作区的历史运行")}</p></div><span>{filteredRuns.length}</span></div>
            <label className="subagent-run-search"><Search size={14} /><input value={runFilter} onChange={(event) => setRunFilter(event.target.value)} placeholder={t("筛选运行、状态或摘要")} /></label>
            <div className="subagent-run-list">
              {filteredRuns.map((run) => {
                const status = run.status.toLowerCase();
                const running = ACTIVE_SUBAGENT_STATUSES.has(status);
                const agent = agents.find((item) => item.id === run.subagent_id);
                return (
                  <button type="button" className={`subagent-run-row ${selectedRunId === run.run_id ? "active" : ""}`} key={run.run_id} onClick={() => setSelectedRunId(run.run_id)}>
                    <span className={`subagent-run-state ${status}`}>{running ? <RefreshCw className="spin" size={13} /> : status === "completed" ? <Check size={13} /> : <AlertCircle size={13} />}</span>
                    <span className="subagent-run-copy"><strong>{agent?.name || run.subagent_id}</strong><small>{run.summary || run.error || run.task_id}</small></span>
                    <span className={`subagent-status ${status}`}>{subagentStatusLabel(run.status, t)}</span>
                    <time>{formatTime(run.started_at, language)}</time>
                  </button>
                );
              })}
              {!filteredRuns.length && <div className="subagent-list-empty"><Clock3 size={22} /><span>{t("暂无运行记录")}</span><small>{t("SubAgent 开始工作后会在这里显示。")}</small></div>}
            </div>
          </section>

          <section className="subagent-detail-panel" aria-labelledby="subagent-detail-title">
            {!selectedRun ? (
              <div className="subagent-detail-empty"><Bot size={28} /><strong>{t("选择一条运行查看日志")}</strong><span>{t("时间线会把模型等待、工具调用和完成状态分开呈现。")}</span></div>
            ) : (
              <>
                <div className="subagent-detail-header">
                  <div><p>{selectedAgent?.name || selectedRun.subagent_id}</p><h2 id="subagent-detail-title">{selectedRun.task_id || selectedRun.run_id}</h2></div>
                  <span className={`subagent-status ${runStatus}`}>{subagentStatusLabel(selectedRun.status, t)}</span>
                </div>
                <div className="subagent-detail-meta">
                  <div><span>{t("模型")}</span><strong>{runLog?.model.display_name || runLog?.model.model || (selectedAgent ? subagentModelName(selectedAgent) : "—")}</strong></div>
                  <div><span>{t("开始时间")}</span><strong>{new Date(selectedRun.started_at).toLocaleString(language)}</strong></div>
                  <div><span>{t("运行 ID")}</span><code>{selectedRun.run_id}</code></div>
                </div>
                {runLog?.assignment && <div className="subagent-assignment"><span>{t("委派任务")}</span><p>{runLog.assignment}</p></div>}
                <div className="subagent-detail-tabs" role="tablist" aria-label={t("SubAgent 日志视图")}>
                  <button type="button" role="tab" aria-selected={detailTab === "timeline"} className={detailTab === "timeline" ? "active" : ""} onClick={() => setDetailTab("timeline")}><Activity size={14} />{t("时间线")}<span>{runLog?.events.length ?? 0}</span></button>
                  <button type="button" role="tab" aria-selected={detailTab === "output"} className={detailTab === "output" ? "active" : ""} onClick={() => setDetailTab("output")}><FileText size={14} />{t("输出")}</button>
                </div>
                <div className="subagent-detail-body">
                  {logLoading ? <div className="subagent-log-loading"><RefreshCw className="spin" size={15} />{t("正在读取日志")}</div> : detailTab === "timeline" ? (
                    <div className="subagent-timeline">
                      {runLog?.events.length ? runLog.events.map((event, index) => <ActivityItem key={`${String(event.event ?? event.message ?? "event")}-${index}`} event={event} />) : <div className="subagent-log-empty"><Activity size={22} /><span>{t("该运行没有保存结构化事件")}</span></div>}
                    </div>
                  ) : (
                    <div className={`subagent-output ${selectedRun.error ? "error" : ""}`}>
                      {runOutput ? <Markdown>{runOutput}</Markdown> : <div className="subagent-log-empty"><FileText size={22} /><span>{t("正在等待代理输出")}</span></div>}
                    </div>
                  )}
                </div>
                {runLog && <details className="subagent-raw-log"><summary><Code2 size={13} />{t("查看脱敏原始日志")}<ChevronDown size={13} /></summary><pre>{JSON.stringify(runLog, null, 2)}</pre></details>}
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function taskKey(task: RatsTaskRecord): string {
  return `${task.provider_id}:${task.service_id}:${task.task_id}`;
}

const RTP_TASK_LOG_HISTORY_LIMIT = 64 * 1024;

function appendTaskLogHistory(previous: string, incoming: string): string {
  const combined = `${previous}${incoming}`;
  return combined.length > RTP_TASK_LOG_HISTORY_LIMIT
    ? combined.slice(-RTP_TASK_LOG_HISTORY_LIMIT)
    : combined;
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function taskRunning(task: RatsTaskRecord, status: Record<string, unknown>): boolean {
  const output = recordValue(status.output);
  if (typeof status.running === "boolean") return status.running;
  if (typeof output.running === "boolean") return output.running;
  return Boolean(recordValue(task.status).running);
}

function taskStatusLabel(task: RatsTaskRecord, status: Record<string, unknown>, t: (key: string) => string): string {
  if (taskRunning(task, status)) return t("运行中");
  if (Boolean(status.cancelled ?? task.cancelled)) return t("已取消");
  if (status.error || task.error) return t("失败");
  return t("已完成");
}

function RtpTasksView() {
  const { t } = useI18n();
  const [state, setState] = useState<RatsState | null>(null);
  const [tasks, setTasks] = useState<RatsTaskRecord[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [detail, setDetail] = useState<{ status: Record<string, unknown>; events: Array<Record<string, unknown>>; logs: string; logCursor: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const requestSequence = useRef(0);
  const loadInFlight = useRef(false);
  const selectedKeyRef = useRef("");
  const eventHistory = useRef<Record<string, Array<Record<string, unknown>>>>({});
  const logHistory = useRef<Record<string, string>>({});
  const logCursors = useRef<Record<string, number>>({});
  const cancelledTasks = useRef(new Set<string>());
  const selectTask = useCallback((key: string) => {
    selectedKeyRef.current = key;
    setSelectedKey(key);
  }, []);
  const retainTaskCacheKeys = useCallback((validKeys: Set<string>) => {
    for (const key of Object.keys(eventHistory.current)) {
      if (!validKeys.has(key)) delete eventHistory.current[key];
    }
    for (const key of Object.keys(logHistory.current)) {
      if (!validKeys.has(key)) delete logHistory.current[key];
    }
    for (const key of Object.keys(logCursors.current)) {
      if (!validKeys.has(key)) delete logCursors.current[key];
    }
    for (const key of cancelledTasks.current) {
      if (!validKeys.has(key)) cancelledTasks.current.delete(key);
    }
  }, []);

  const load = useCallback(async (foreground = false) => {
    if (loadInFlight.current) return;
    loadInFlight.current = true;
    const sequence = ++requestSequence.current;
    if (foreground) setLoading(true);
    try {
      const stateResponse = await window.reverie.request("ratsState", {});
      const nextState = stateResponse.rats;
      if (sequence !== requestSequence.current) return;
      setState(nextState);
      const connectedServices = nextState.services.filter((item) => item.connection === "connected" && item.sessionActive);
      if (!connectedServices.length) {
        retainTaskCacheKeys(new Set<string>());
        setTasks([]);
        selectTask("");
        setDetail(null);
        setError("");
        return;
      }
      const tasksResponse = await window.reverie.request("ratsTasks", {});
      const taskRecords = (Array.isArray(tasksResponse.tasks) ? tasksResponse.tasks : []) as RatsTaskRecord[];
      if (sequence !== requestSequence.current) return;
      retainTaskCacheKeys(new Set(taskRecords.map(taskKey)));
      const nextTasks = taskRecords.map((task) =>
        cancelledTasks.current.has(taskKey(task)) ? { ...task, cancelled: true } : task,
      );
      setTasks(nextTasks);
      const currentKey = selectedKeyRef.current;
      const nextKey = currentKey && nextTasks.some((task) => taskKey(task) === currentKey)
        ? currentKey
        : nextTasks[0] ? taskKey(nextTasks[0]) : "";
      selectTask(nextKey);
      if (!nextKey || !nextTasks.some((task) => taskKey(task) === nextKey)) {
        setDetail(null);
        setError("");
        return;
      }
      const task = nextTasks.find((item) => taskKey(item) === nextKey) as RatsTaskRecord;
      const eventCursor = Number(recordValue(task.status).next_cursor ?? task.cursor ?? 0) || 0;
      const logCursor = logCursors.current[nextKey] ?? 0;
      const [statusResult, eventsResult, logsResult] = await Promise.allSettled([
        window.reverie.request("ratsTaskStatus", { providerId: task.provider_id, serviceId: task.service_id, taskId: task.task_id, deadlineMs: 5_000 }),
        window.reverie.request("ratsTaskEvents", { providerId: task.provider_id, serviceId: task.service_id, taskId: task.task_id, cursor: eventCursor, limit: 32, deadlineMs: 5_000 }),
        window.reverie.request("ratsTaskLogs", { providerId: task.provider_id, serviceId: task.service_id, taskId: task.task_id, cursor: logCursor, limit: 8_192, deadlineMs: 5_000 }),
      ]);
      if (sequence !== requestSequence.current || selectedKeyRef.current !== nextKey) return;
      const failedResult = [statusResult, eventsResult, logsResult].find((result) => result.status === "rejected");
      if (failedResult?.status === "rejected") {
        setDetail(null);
        const reason = failedResult.reason;
        setError(reason instanceof Error ? reason.message : String(reason));
        return;
      }
      if (statusResult.status !== "fulfilled" || eventsResult.status !== "fulfilled" || logsResult.status !== "fulfilled") return;
      const statusResponse = statusResult.value;
      const eventsResponse = eventsResult.value;
      const logsResponse = logsResult.value;
      const status = statusResponse?.result ?? recordValue(task.status);
      const eventResult = eventsResponse?.result ?? {};
      const incomingEvents = Array.isArray(eventResult.events) ? eventResult.events as Array<Record<string, unknown>> : [];
      const previousEvents = [
        ...(eventHistory.current[nextKey] ?? []),
        ...(Array.isArray(task.events) ? task.events : []),
      ];
      const mergedEvents = [...previousEvents, ...incomingEvents].filter((event, index, all) => {
        const identity = `${String(event.sequence ?? "")}:${String(event.type ?? "")}:${String(event.timestamp_utc ?? "")}`;
        return all.findIndex((candidate) => `${String(candidate.sequence ?? "")}:${String(candidate.type ?? "")}:${String(candidate.timestamp_utc ?? "")}` === identity) === index;
      }).slice(-128);
      eventHistory.current[nextKey] = mergedEvents;
      const logResult = logsResponse?.result ?? {};
      const logText = String(logResult.text ?? "");
      if (logText) logHistory.current[nextKey] = appendTaskLogHistory(logHistory.current[nextKey] ?? "", logText);
      const nextLogCursor = Number(logResult.next_cursor ?? logCursor) || logCursor;
      logCursors.current[nextKey] = nextLogCursor;
      setDetail({ status: recordValue(status), events: mergedEvents, logs: logHistory.current[nextKey] ?? "", logCursor: nextLogCursor });
      setError("");
    } catch (loadError) {
      if (sequence === requestSequence.current) setError(loadError instanceof Error ? loadError.message : String(loadError));
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
      loadInFlight.current = false;
    }
  }, [retainTaskCacheKeys, selectTask]);

  useEffect(() => {
    let stopped = false;
    let timer: number | null = null;
    const poll = async (foreground: boolean) => {
      await load(foreground);
      if (!stopped) timer = window.setTimeout(() => void poll(false), 1500);
    };
    void poll(true);
    return () => {
      stopped = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [load]);

  const selectedTask = tasks.find((task) => taskKey(task) === selectedKey) ?? null;
  const status = detail?.status ?? recordValue(selectedTask?.status);
  const output = recordValue(status.output);
  const progressValue = typeof status.progress === "number" ? status.progress : typeof output.progress === "number" ? output.progress : null;
  const progress = progressValue !== null && Number.isFinite(progressValue)
    ? Math.max(0, Math.min(1, progressValue)) * 100
    : null;
  const connected = state?.services.filter((service) => service.connection === "connected" && service.sessionActive).length ?? 0;

  const cancel = useCallback(async () => {
    if (!selectedTask) return;
    const key = taskKey(selectedTask);
    setBusy(key);
    try {
      await window.reverie.request("ratsTaskCancel", {
        providerId: selectedTask.provider_id,
        serviceId: selectedTask.service_id,
        taskId: selectedTask.task_id,
        deadlineMs: 5_000,
      });
      cancelledTasks.current.add(key);
      await load(true);
    } catch (cancelError) {
      setError(cancelError instanceof Error ? cancelError.message : String(cancelError));
    } finally {
      setBusy("");
    }
  }, [load, selectedTask]);

  return (
    <div className="page-scroll rats-tasks-page">
      <PageHeader
        icon={<Clock3 size={20} />}
        title={t("RTP 任务")}
        description={t("实时查看已授权 Reverie Engine 任务的状态、事件游标、日志和取消结果。")}
        action={<button type="button" className="secondary-button" onClick={() => void load(true)} disabled={loading}><RefreshCw className={loading ? "spin" : ""} size={14} />{t("刷新")}</button>}
      />
      <div className="tool-overview rats-task-overview">
        <div><Activity size={17} /><span>{t("已连接服务")}<strong>{connected}</strong></span></div>
        <div><Clock3 size={17} /><span>{t("活动任务")}<strong>{tasks.filter((task) => taskRunning(task, recordValue(task.status))).length}</strong></span></div>
        <div><FileText size={17} /><span>{t("事件记录")}<strong>{detail?.events.length ?? 0}</strong></span></div>
      </div>
      {error && <div className="page-loading error"><AlertCircle size={18} />{error}</div>}
      {connected === 0 && !loading ? (
        <div className="empty-panel rats-task-empty"><ShieldCheck size={28} /><strong>{t("尚未启用 RTP 服务")}</strong><span>{t("先在 RATS 页面显式启用 Reverie Engine，运行中的任务会在这里自动出现。")}</span></div>
      ) : (
        <div className="rats-task-layout">
          <section className="rats-task-list-panel" aria-labelledby="rats-task-list-title">
            <div className="rats-task-panel-heading"><div><h2 id="rats-task-list-title">{t("任务列表")}</h2><p>{t("每 1.5 秒从已连接服务同步状态")}</p></div><span>{tasks.length}</span></div>
            <div className="rats-task-list">
              {tasks.map((task) => {
                const itemStatus = recordValue(task.status);
                const itemKey = taskKey(task);
                return <button type="button" className={`rats-task-row ${itemKey === selectedKey ? "active" : ""}`} key={itemKey} onClick={() => { selectTask(itemKey); setDetail(null); void load(true); }}>
                  <span className={`rats-task-dot ${taskRunning(task, itemStatus) ? "running" : "done"}`} />
                  <span className="rats-task-row-main"><strong>{task.tool || t("原生任务")}</strong><code>{task.task_id}</code></span>
                  <span className={`rats-status ${taskRunning(task, itemStatus) ? "connected" : "available"}`}>{taskStatusLabel(task, itemStatus, t)}</span>
                </button>;
              })}
              {!tasks.length && <div className="rats-task-list-empty"><Clock3 size={20} /><span>{t("暂无活动任务")}</span><small>{t("由 AI 或工具调用启动的长任务会自动同步到这里。")}</small></div>}
            </div>
          </section>
          <section className="rats-task-detail" aria-labelledby="rats-task-detail-title">
            {!selectedTask ? <div className="rats-task-detail-empty"><Clock3 size={24} /><strong>{t("选择一个任务查看详情")}</strong></div> : <>
              <div className="rats-task-detail-header"><div><p>{t("RTP 任务详情")}</p><h2 id="rats-task-detail-title">{selectedTask.tool || t("原生任务")}</h2></div><div className="rats-task-detail-actions"><span className={`rats-status ${taskRunning(selectedTask, status) ? "connected" : "available"}`}>{taskStatusLabel(selectedTask, status, t)}</span>{taskRunning(selectedTask, status) && <button type="button" className="danger-button" onClick={() => void cancel()} disabled={busy === taskKey(selectedTask)}><Square size={13} />{t("取消任务")}</button>}</div></div>
              <div className="rats-task-meta"><div><span>{t("任务 ID")}</span><code>{selectedTask.task_id}</code></div><div><span>{t("提供者")}</span><code>{selectedTask.provider_id}</code></div><div><span>{t("事件游标")}</span><code>{String(status.next_cursor ?? selectedTask.cursor ?? 0)}</code></div><div><span>{t("截止时间")}</span><code>{String(selectedTask.deadline_msec ?? 0)} ms</code></div></div>
              {progress !== null && <div className="rats-task-progress"><div><span>{t("进度")}</span><strong>{Math.round(progress)}%</strong></div><div className="rats-task-progress-track"><span style={{ width: `${progress}%` }} /></div></div>}
              <div className="rats-task-detail-grid">
                <section className="rats-task-stream" aria-labelledby="rats-task-events-title"><div className="rats-task-subheading"><div><h3 id="rats-task-events-title">{t("版本化事件")}</h3><span>reverie.rtp.task/1</span></div><span>{detail?.events.length ?? 0}</span></div><div className="rats-task-events">{detail?.events.map((event, index) => <div className="rats-task-event" key={`${String(event.sequence ?? "")}:${String(event.type ?? "")}:${index}`}><div><strong>{String(event.type ?? t("事件"))}</strong><span>{String(event.timestamp_utc ?? event.timestamp ?? "")}</span></div><code>{event.sequence === undefined ? "—" : `#${String(event.sequence)}`}</code><pre>{JSON.stringify(event.payload ?? event.output ?? {}, null, 2)}</pre></div>)}{!detail?.events.length && <div className="rats-task-empty-inline">{t("等待事件")}</div>}</div></section>
                <section className="rats-task-stream" aria-labelledby="rats-task-logs-title"><div className="rats-task-subheading"><div><h3 id="rats-task-logs-title">{t("任务日志")}</h3><span>{t("实时增量读取")}</span></div><code>{detail?.logCursor ?? 0}</code></div><pre className="rats-task-log-output">{detail?.logs || t("等待日志")}</pre></section>
              </div>
            </>}
          </section>
        </div>
      )}
    </div>
  );
}

function ApprovalModal({ approval, resolve }: { approval: Record<string, unknown>; resolve: (decision: ApprovalDecision, message?: string) => void }) {
  const { t } = useI18n();
  const dialogRef = useRef<HTMLDivElement>(null);
  const [message, setMessage] = useState("");
  const [showReply, setShowReply] = useState(false);
  useDialogFocus(dialogRef);
  const risk = String(approval.risk ?? "").trim();
  const concerns = Array.isArray(approval.concerns) ? approval.concerns.map(String) : [];
  const reviewer = String(approval.review_source ?? "").trim();
  const riskLabel = risk ? risk : "";
  const riskClass = riskLabel ? `risk-badge risk-${riskLabel}` : "risk-badge";
  return (
    <div className="modal-backdrop">
      <div ref={dialogRef} className="approval-modal" role="alertdialog" aria-modal="true" aria-labelledby="approval-title" aria-describedby="approval-message" tabIndex={-1}>
        <div className="approval-header">
          <div className="confirm-icon"><ShieldCheck size={20} /></div>
          <div>
            <h2 id="approval-title">{t("工具请求更高权限")}</h2>
            <p>{t(String(approval.permission_mode === "strict" ? "Strict 模式：每次工具调用都需要你的批准。" : "Reverie 内核暂停执行，等待你的决定。"))}</p>
          </div>
        </div>
        <div className="approval-tool"><Wrench size={15} /><strong>{String(approval.tool ?? "tool")}</strong>{riskLabel && <span className={riskClass}>{riskLabel}</span>}</div>
        <p id="approval-message" className="approval-message">{t(String(approval.message ?? "此工具超出当前权限级别。"))}</p>
        {concerns.length > 0 && <div className="approval-concerns">{concerns.map((tag) => <span key={tag} className="concern-tag">{tag}</span>)}</div>}
        {reviewer && reviewer !== "policy" && <div className="approval-reviewer"><Sparkles size={12} />{t("审查")}: {reviewer}</div>}
        {showReply ? (
          <div className="approval-reply">
            <textarea autoFocus rows={2} value={message} onChange={(e) => setMessage(e.target.value)} placeholder={t("给模型写一条消息，例如：先解释清楚再执行……")} />
            <div className="approval-actions">
              <button type="button" className="secondary-button" onClick={() => setShowReply(false)}>{t("返回")}</button>
              <button type="button" className="primary-button" disabled={!message.trim()} onClick={() => resolve("message", message.trim())}>{t("发送给模型")}</button>
            </div>
          </div>
        ) : (
          <div className="approval-actions">
            <button type="button" className="danger-button" onClick={() => resolve("deny")}>{t("拒绝")}</button>
            <button type="button" className="secondary-button" onClick={() => setShowReply(true)}>{t("个性化回复")}</button>
            <button type="button" className="secondary-button" onClick={() => resolve("once")}>{t("仅本次允许")}</button>
            <button type="button" className="primary-button" onClick={() => resolve("session")}>{t("本会话允许")}</button>
          </div>
        )}
      </div>
    </div>
  );
}

function Toasts({ items }: { items: Toast[] }) {
  return <div className="toast-stack">{items.map((toast) => <div className={`toast ${toast.kind}`} key={toast.id}>{toast.kind === "success" ? <CheckCircle2 size={15} /> : toast.kind === "error" ? <AlertCircle size={15} /> : <Info size={15} />}<span>{toast.message}</span></div>)}</div>;
}

export default function App() {
  const [state, setState] = useState<DesktopState | null>(null);
  const [desktopPaths, setDesktopPaths] = useState<DesktopPaths | null>(null);
  const [bootError, setBootError] = useState("");
  const [view, setView] = useState<ViewId>("chat");
  const [session, setSession] = useState<SessionState | null>(null);
  const [sessionBusy, setSessionBusy] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [running, setRunning] = useState(false);
  const [liveTurn, setLiveTurn] = useState<LiveTurn | null>(null);
  const pendingLiveBatch = useRef<LiveTurnBatch>(emptyLiveTurnBatch());
  const liveBatchTimer = useRef<number | null>(null);
  const acceptLiveEvents = useRef(false);
  const [sidebarPreferenceCollapsed, setSidebarPreferenceCollapsed] = useState(() =>
    normalizeSidebarCollapsed(localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY)),
  );
  const [compactViewport, setCompactViewport] = useState(() =>
    window.matchMedia(SIDEBAR_AUTO_COLLAPSE_QUERY).matches,
  );
  const [sidebarViewportOverride, setSidebarViewportOverride] = useState<boolean | null>(null);
  const sidebarCollapsed = resolveSidebarCollapsed(
    sidebarPreferenceCollapsed,
    compactViewport,
    sidebarViewportOverride,
  );
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [sessionSearchOpen, setSessionSearchOpen] = useState(false);
  const [standardModelOpen, setStandardModelOpen] = useState(false);
  const [renameSessionTarget, setRenameSessionTarget] = useState<{ id: string; name: string } | null>(null);
  const [approval, setApproval] = useState<Record<string, unknown> | null>(null);
  const [mentionItems, setMentionItems] = useState<Array<Record<string, unknown>>>([]);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionLoading, setMentionLoading] = useState(false);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [confirmation, setConfirmation] = useState<{ title: string; message: string; label: string; danger?: boolean; action: () => void } | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [theme, setTheme] = useState<ThemePreference>(() => normalizeTheme(localStorage.getItem(THEME_STORAGE_KEY)));
  const [systemDark, setSystemDark] = useState(() => window.matchMedia("(prefers-color-scheme: dark)").matches);
  const [uiPreferences, setUiPreferences] = useState<UiPreferences>(DEFAULT_UI_PREFERENCES);
  const t = useMemo(
    () => (key: string, values?: Record<string, string | number>) => translate(uiPreferences.language, key, values),
    [uiPreferences.language],
  );
  const toastId = useRef(0);
  const sessionRequestSequence = useRef(0);
  const mentionRequestSequence = useRef(0);
  const initializeSequence = useRef(0);
  const themeRequestSequence = useRef(0);
  const uiPreferenceRequestSequence = useRef(0);
  const drafts = useRef<Record<string, string>>({});

  const toggleSidebar = useCallback(() => {
    if (compactViewport) {
      setSidebarViewportOverride((current) => !resolveSidebarCollapsed(
        sidebarPreferenceCollapsed,
        true,
        current,
      ));
      return;
    }
    setSidebarViewportOverride(null);
    setSidebarPreferenceCollapsed((current) => !current);
  }, [compactViewport, sidebarPreferenceCollapsed]);

  useEffect(() => {
    applyTheme(theme, systemDark);
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [systemDark, theme]);

  useEffect(() => {
    applyUiPreferences(uiPreferences);
  }, [uiPreferences]);

  useEffect(() => {
    localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(sidebarPreferenceCollapsed));
  }, [sidebarPreferenceCollapsed]);

  useEffect(() => {
    const media = window.matchMedia(SIDEBAR_AUTO_COLLAPSE_QUERY);
    const updateCompactViewport = (event: MediaQueryListEvent) => {
      setCompactViewport(event.matches);
      setSidebarViewportOverride(null);
    };
    media.addEventListener("change", updateCompactViewport);
    return () => media.removeEventListener("change", updateCompactViewport);
  }, []);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const updateSystemTheme = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    media.addEventListener("change", updateSystemTheme);
    const stopAppearanceEvents = window.reverie.onAppearance((appearance) => {
      setTheme(normalizeTheme(appearance.theme));
      setSystemDark(appearance.resolved === "dark");
    });
    const requestSequence = themeRequestSequence.current;
    void window.reverie.appearance().then((appearance) => {
      if (requestSequence !== themeRequestSequence.current) return;
      setTheme(normalizeTheme(appearance.theme));
      setSystemDark(appearance.resolved === "dark");
    });
    void window.reverie.uiPreferences().then((preferences) => {
      setUiPreferences(normalizeUiPreferences(preferences));
    });
    return () => {
      media.removeEventListener("change", updateSystemTheme);
      stopAppearanceEvents();
    };
  }, []);

  const toast = useCallback((message: string, kind: Toast["kind"] = "info") => {
    const id = ++toastId.current;
    setToasts((items) => [...items, { id, kind, message }]);
    window.setTimeout(() => setToasts((items) => items.filter((item) => item.id !== id)), 3600);
  }, []);

  const changeTheme = useCallback((nextTheme: ThemePreference) => {
    const previousTheme = theme;
    const requestSequence = ++themeRequestSequence.current;
    setTheme(nextTheme);
    void window.reverie.setAppearance(nextTheme).then((appearance) => {
      if (requestSequence !== themeRequestSequence.current) return;
      setTheme(normalizeTheme(appearance.theme));
      setSystemDark(appearance.resolved === "dark");
    }).catch((error) => {
      if (requestSequence !== themeRequestSequence.current) return;
      setTheme(previousTheme);
      toast(error instanceof Error ? error.message : String(error), "error");
    });
  }, [theme, toast]);

  const updateUiPreferences = useCallback((patch: Partial<UiPreferences>) => {
    const requestSequence = ++uiPreferenceRequestSequence.current;
    setUiPreferences((current) => normalizeUiPreferences({ ...current, ...patch }));
    void window.reverie.setUiPreferences(patch).then((preferences) => {
      if (requestSequence !== uiPreferenceRequestSequence.current) return;
      setUiPreferences(normalizeUiPreferences(preferences));
    }).catch((error) => {
      if (requestSequence !== uiPreferenceRequestSequence.current) return;
      void window.reverie.uiPreferences().then((preferences) => setUiPreferences(normalizeUiPreferences(preferences)));
      toast(error instanceof Error ? error.message : String(error), "error");
    });
  }, [toast]);

  const selectBackground = useCallback(async () => {
    try {
      const preferences = await window.reverie.selectBackground();
      if (preferences) {
        setUiPreferences(normalizeUiPreferences(preferences));
        toast(t("工作区背景已更新"), "success");
      }
    } catch (error) {
      toast(error instanceof Error ? error.message : String(error), "error");
    }
  }, [t, toast]);

  const clearBackground = useCallback(async () => {
    try {
      const preferences = await window.reverie.clearBackground();
      setUiPreferences(normalizeUiPreferences(preferences));
      toast(t("工作区背景已清除"), "success");
    } catch (error) {
      toast(error instanceof Error ? error.message : String(error), "error");
    }
  }, [t, toast]);

  const initialize = useCallback(async (projectRoot?: string) => {
    const requestSequence = ++initializeSequence.current;
    setBootError("");
    try {
      const [paths, preferences] = await Promise.all([
        window.reverie.paths(),
        window.reverie.uiPreferences(),
      ]);
      if (requestSequence !== initializeSequence.current) return;
      setDesktopPaths(paths);
      setUiPreferences(normalizeUiPreferences(preferences));
      const response = await window.reverie.request("initialize", { projectRoot: projectRoot ?? paths.projectRoot });
      if (requestSequence !== initializeSequence.current) return;
      let nextState = response.state;
      let nextSession: SessionState | null = null;
      const currentId = nextState.sessions.current_session_id || nextState.sessions.items[0]?.id;
      if (currentId) {
        const sessionResponse = await window.reverie.request("getSession", { sessionId: currentId });
        if (requestSequence !== initializeSequence.current) return;
        nextSession = sessionResponse.session;
        nextState = { ...nextState, sessions: sessionResponse.sessions };
      }
      setState(nextState);
      setSession(nextSession);
    } catch (error) {
      if (requestSequence === initializeSequence.current) setBootError(error instanceof Error ? error.message : String(error));
    }
  }, []);

  useEffect(() => { void initialize(); }, [initialize]);

  useEffect(() => {
    const contextEngine = state?.workspace.context_engine;
    if (!state || (contextEngine?.ready && !contextEngine.indexing)) return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const response = await window.reverie.request("getContextStatus", {});
        if (cancelled) return;
        const nextContext = response.context_engine;
        setState((current) => current ? {
          ...current,
          workspace: { ...current.workspace, index_ready: Boolean(nextContext?.ready), context_engine: nextContext },
        } : current);
      } catch {
        // Context status is advisory; initialization and prompts remain usable.
      }
    }, 900);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [state]);

  const flushLiveBatch = useCallback(() => {
    liveBatchTimer.current = null;
    const batch = pendingLiveBatch.current;
    pendingLiveBatch.current = emptyLiveTurnBatch();
    if (!batch.assistantText && !batch.reasoningText && batch.events.length === 0) return;
    setLiveTurn((current) => current ? mergeLiveTurnBatch(current, batch) : current);
  }, []);

  const resetLiveBatch = useCallback(() => {
    if (liveBatchTimer.current !== null) {
      window.clearTimeout(liveBatchTimer.current);
      liveBatchTimer.current = null;
    }
    pendingLiveBatch.current = emptyLiveTurnBatch();
  }, []);

  useEffect(() => {
    const unsubscribe = window.reverie.onEvent((message) => {
      const event = asRecord(message.event);
      const type = String(event.type ?? "");
      if (!acceptLiveEvents.current) return;
      if (type === "approval.request") setApproval(event);

      const batch = pendingLiveBatch.current;
      if (type === "assistant.delta") batch.assistantText += String(event.text ?? "");
      else if (type === "reasoning.delta") batch.reasoningText += String(event.text ?? "");
      else if (type === "ui.event") batch.events.push(asRecord(event.event));
      else if (type === "run.auto_followup" || type === "approval.request") batch.events.push(event);
      else return;

      if (liveBatchTimer.current === null) {
        liveBatchTimer.current = window.setTimeout(flushLiveBatch, LIVE_STREAM_RENDER_INTERVAL_MS);
      }
    });
    return () => {
      unsubscribe();
      resetLiveBatch();
    };
  }, [flushLiveBatch, resetLiveBatch]);

  useEffect(() => {
    const shortcuts = (event: globalThis.KeyboardEvent) => {
      const modifier = event.ctrlKey || event.metaKey;
      if (modifier && event.key.toLowerCase() === "k") { event.preventDefault(); setCommandOpen(true); }
      if (modifier && event.key.toLowerCase() === "n") { event.preventDefault(); void createSession(); }
      if (modifier && event.key.toLowerCase() === "f") { event.preventDefault(); setSessionSearchOpen(true); }
      if (modifier && event.key.toLowerCase() === "b") { event.preventDefault(); toggleSidebar(); }
      if (event.key === "Escape") {
        setModelPickerOpen(false);
        setCommandOpen(false);
        setSessionSearchOpen(false);
        setStandardModelOpen(false);
        setRenameSessionTarget(null);
        setConfirmation(null);
        mentionRequestSequence.current += 1;
        setMentionLoading(false);
        setMentionOpen(false);
      }
    };
    window.addEventListener("keydown", shortcuts);
    return () => window.removeEventListener("keydown", shortcuts);
  });

  const openSession = useCallback(async (id: string) => {
    if (running || id === session?.id) return;
    if (session) drafts.current[session.id] = prompt;
    const requestSequence = ++sessionRequestSequence.current;
    setSessionBusy(true);
    try {
      const response = await window.reverie.request("getSession", { sessionId: id });
      if (requestSequence !== sessionRequestSequence.current) return;
      const nextSession = response.session;
      setSession(nextSession);
      setState((current) => current ? { ...current, sessions: response.sessions } : current);
      setView("chat");
      setLiveTurn(null);
      setPrompt(drafts.current[nextSession.id] ?? "");
      setAttachments([]);
      setMentionOpen(false);
    } catch (error) {
      if (requestSequence === sessionRequestSequence.current) toast(error instanceof Error ? error.message : String(error), "error");
    } finally {
      if (requestSequence === sessionRequestSequence.current) setSessionBusy(false);
    }
  }, [prompt, running, session, toast]);

  const createSession = useCallback(async () => {
    if (running || sessionBusy) return;
    if (session && sessionIsEmpty(session)) {
      setView("chat");
      return;
    }
    if (session) drafts.current[session.id] = prompt;
    const requestSequence = ++sessionRequestSequence.current;
    setSessionBusy(true);
    try {
      const response = await window.reverie.request("createSession", {});
      if (requestSequence !== sessionRequestSequence.current) return;
      const nextSession = response.session;
      setSession(nextSession);
      setState((current) => current ? { ...current, sessions: response.sessions } : current);
      setView("chat");
      setLiveTurn(null);
      setPrompt(drafts.current[nextSession.id] ?? "");
      setAttachments([]);
      setMentionOpen(false);
    } catch (error) {
      if (requestSequence === sessionRequestSequence.current) toast(error instanceof Error ? error.message : String(error), "error");
    } finally {
      if (requestSequence === sessionRequestSequence.current) setSessionBusy(false);
    }
  }, [prompt, running, session, sessionBusy, toast]);

  const compactContext = useCallback(async (focus = "") => {
    if (running || sessionBusy || !state) return;
    const requestSequence = ++sessionRequestSequence.current;
    setSessionBusy(true);
    try {
      let activeSession = session;
      if (!activeSession) {
        const created = await window.reverie.request("createSession", {});
        if (requestSequence !== sessionRequestSequence.current) return;
        activeSession = created.session;
        setSession(activeSession);
        setState((current) => current ? { ...current, sessions: created.sessions } : current);
      }
      const response = await window.reverie.request("compactContext", {
        sessionId: activeSession.id,
        focus: focus || undefined,
        projectRoot: state.workspace.project_root,
      });
      if (requestSequence !== sessionRequestSequence.current) return;
      setSession(response.session);
      setState((current) => current ? {
        ...current,
        sessions: response.sessions,
        recovery: response.recovery,
        workspace: { ...current.workspace, context_engine: response.context_engine },
      } : current);
      setMentionItems([]);
      setMentionOpen(false);
      toast(response.message, "success");
    } catch (error) {
      if (requestSequence === sessionRequestSequence.current) toast(error instanceof Error ? error.message : String(error), "error");
    } finally {
      if (requestSequence === sessionRequestSequence.current) setSessionBusy(false);
    }
  }, [running, session, sessionBusy, state, toast]);

  const sendPrompt = useCallback(async () => {
    const text = prompt.trim();
    if (!text || running || sessionBusy || !state) return;
    const compactMatch = /^\/compact(?:\s+([\s\S]*))?$/i.exec(text);
    if (compactMatch) {
      setPrompt("");
      setMentionItems([]);
      setMentionOpen(false);
      await compactContext((compactMatch[1] || "").trim());
      return;
    }
    setPrompt("");
    setMentionItems([]);
    setMentionOpen(false);
    setRunning(true);
    resetLiveBatch();
    acceptLiveEvents.current = true;
    setLiveTurn({ userText: text, assistantText: "", reasoningText: "", events: [], error: "", startedAt: Date.now() });
    try {
      let activeSession = session;
      if (!activeSession) {
        const created = await window.reverie.request("createSession", {});
        activeSession = created.session;
        setSession(activeSession);
        setState((current) => current ? { ...current, sessions: created.sessions } : current);
      }
      drafts.current[activeSession.id] = "";
      const response = await window.reverie.request("runPrompt", {
        prompt: text,
        sessionId: activeSession.id,
        mode: state.workspace.mode,
        stream: true,
      });
      const result = response.result;
      acceptLiveEvents.current = false;
      // The final result is authoritative and already contains every emitted
      // delta, so discard an unpainted tail before replacing the live text.
      resetLiveBatch();
      setLiveTurn((current) => current ? {
        ...current,
        assistantText: result.output_text || current.assistantText,
        reasoningText: result.thinking_text || current.reasoningText,
        error: result.error,
      } : current);
      setState((current) => current ? {
        ...current,
        sessions: response.sessions,
        recovery: response.recovery,
      } : current);
      const refreshed = await window.reverie.request("getSession", { sessionId: result.session_id || activeSession.id });
      setSession(refreshed.session);
      setState((current) => current ? { ...current, sessions: refreshed.sessions } : current);
      setLiveTurn(null);
      setAttachments([]);
      if (!result.success) toast(result.error || t("请求失败"), "error");
    } catch (error) {
      acceptLiveEvents.current = false;
      const message = error instanceof Error ? error.message : String(error);
      setLiveTurn((current) => current ? { ...current, error: message } : current);
      if (!message.includes("cancel")) toast(message, "error");
    } finally {
      setRunning(false);
    }
  }, [compactContext, prompt, resetLiveBatch, running, session, sessionBusy, state, t, toast]);

  const cancelPrompt = useCallback(async () => {
    const retryText = liveTurn?.userText ?? "";
    acceptLiveEvents.current = false;
    try {
      await window.reverie.cancel();
      if (session) {
        const refreshed = await window.reverie.request("getSession", { sessionId: session.id });
        setSession(refreshed.session);
        setState((current) => current ? { ...current, sessions: refreshed.sessions } : current);
      }
      setPrompt((current) => current || retryText);
      resetLiveBatch();
      setLiveTurn(null);
      setApproval(null);
      toast(t("已停止当前任务，提示已保留"), "info");
    } catch (error) {
      toast(error instanceof Error ? error.message : String(error), "error");
    } finally {
      setRunning(false);
    }
  }, [liveTurn?.userText, resetLiveBatch, session, t, toast]);

  const renameSession = useCallback(async (name: string) => {
    if (!renameSessionTarget || running || sessionBusy) return;
    try {
      const response = await window.reverie.request("renameSession", { sessionId: renameSessionTarget.id, name });
      const activeSession = response.session ?? null;
      if (activeSession) setSession(activeSession);
      setState((current) => current ? { ...current, sessions: response.sessions } : current);
      setRenameSessionTarget(null);
      toast(t("会话标题已更新"), "success");
    } catch (error) {
      toast(error instanceof Error ? error.message : String(error), "error");
    }
  }, [renameSessionTarget, running, sessionBusy, t, toast]);

  const toggleSessionArchive = useCallback((target: SessionInfo, archived: boolean) => {
    if (!state) return;
    const projectRoot = state.workspace.project_root;
    const currentIds = uiPreferences.archivedSessions[projectRoot] ?? [];
    const nextIds = archived
      ? currentIds.filter((id) => id !== target.id)
      : [...new Set([...currentIds, target.id])];
    updateUiPreferences({
      archivedSessions: {
        ...uiPreferences.archivedSessions,
        [projectRoot]: nextIds,
      },
    });
    toast(t(archived ? "会话已移出归档" : "会话已归档"), "success");
  }, [state, t, toast, uiPreferences.archivedSessions, updateUiPreferences]);

  const forkActiveSession = useCallback(async () => {
    if (!session || running || sessionBusy) return;
    drafts.current[session.id] = prompt;
    const requestSequence = ++sessionRequestSequence.current;
    setSessionBusy(true);
    try {
      const response = await window.reverie.request("forkSession", { sessionId: session.id, messageCount: session.messages.length });
      if (requestSequence !== sessionRequestSequence.current) return;
      const forked = response.session;
      setSession(forked);
      setState((current) => current ? { ...current, sessions: response.sessions } : current);
      setPrompt("");
      setLiveTurn(null);
      setView("chat");
      toast(t("已创建独立会话分支"), "success");
    } catch (error) {
      if (requestSequence === sessionRequestSequence.current) toast(error instanceof Error ? error.message : String(error), "error");
    } finally {
      if (requestSequence === sessionRequestSequence.current) setSessionBusy(false);
    }
  }, [prompt, running, session, sessionBusy, t, toast]);

  const rewindActiveSession = useCallback(() => {
    if (!session || running || sessionBusy) return;
    const messageCount = previousTurnBoundary(session.messages);
    if (messageCount === null) return;
    setConfirmation({
      title: t("回退上一轮对话？"),
      message: t("上一轮用户消息、回答及工具活动会从当前会话移除；完整记录仍由内核归档，可通过恢复功能找回。"),
      label: t("确认回退"),
      danger: true,
      action: () => { void (async () => {
        setSessionBusy(true);
        try {
          const response = await window.reverie.request("rewindSession", { sessionId: session.id, messageCount, confirmed: true });
          setSession(response.session);
          setState((current) => current ? { ...current, sessions: response.sessions } : current);
          setLiveTurn(null);
          toast(t("已回退上一轮对话"), "success");
        } catch (error) {
          toast(error instanceof Error ? error.message : String(error), "error");
        } finally {
          setSessionBusy(false);
        }
      })(); },
    });
  }, [running, session, sessionBusy, t, toast]);

  const deleteSession = useCallback((target: { id: string; name: string }) => {
    if (running || sessionBusy) return;
    setConfirmation({
      title: t("删除这个会话？"),
      message: t("delete.sessionMessage", { name: target.name }),
      label: t("删除会话"),
      danger: true,
      action: () => { void (async () => {
        setSessionBusy(true);
        try {
          const response = await window.reverie.request("deleteSession", { sessionId: target.id, confirmed: true });
          delete drafts.current[target.id];
          const nextSession = response.session ?? null;
          setSession(nextSession);
          setState((current) => current ? { ...current, sessions: response.sessions } : current);
          setPrompt(nextSession ? drafts.current[nextSession.id] ?? "" : "");
          setLiveTurn(null);
          if (state) {
            const projectRoot = state.workspace.project_root;
            const archived = uiPreferences.archivedSessions[projectRoot] ?? [];
            if (archived.includes(target.id)) {
              updateUiPreferences({
                archivedSessions: {
                  ...uiPreferences.archivedSessions,
                  [projectRoot]: archived.filter((id) => id !== target.id),
                },
              });
            }
          }
          toast(t("会话已删除"), "success");
        } catch (error) {
          toast(error instanceof Error ? error.message : String(error), "error");
        } finally {
          setSessionBusy(false);
        }
      })(); },
    });
  }, [running, sessionBusy, state, t, toast, uiPreferences.archivedSessions, updateUiPreferences]);

  const deleteArchivedSessions = useCallback((targets: SessionInfo[]) => {
    if (running || sessionBusy || !state || targets.length === 0) return;
    const projectRoot = state.workspace.project_root;
    const targetIds = [...new Set(targets.map((target) => target.id).filter(Boolean))];
    if (targetIds.length === 0) return;
    setConfirmation({
      title: t("清空全部归档会话？"),
      message: t("delete.archiveMessage", { count: targetIds.length }),
      label: t("清空归档"),
      danger: true,
      action: () => { void (async () => {
        setSessionBusy(true);
        try {
          const response = await window.reverie.request("deleteSessions", { sessionIds: targetIds, confirmed: true });
          const deletedIds = Array.isArray(response.deleted_session_ids)
            ? response.deleted_session_ids.map((value) => String(value))
            : targetIds;
          deletedIds.forEach((sessionId) => { delete drafts.current[sessionId]; });
          const nextSession = response.session ?? null;
          setSession(nextSession);
          setState((current) => current ? { ...current, sessions: response.sessions } : current);
          setPrompt(nextSession ? drafts.current[nextSession.id] ?? "" : "");
          setLiveTurn(null);
          updateUiPreferences({
            archivedSessions: {
              ...uiPreferences.archivedSessions,
              [projectRoot]: [],
            },
          });
          toast(t("archive.deleted", { count: deletedIds.length }), "success");
        } catch (error) {
          toast(error instanceof Error ? error.message : String(error), "error");
        } finally {
          setSessionBusy(false);
        }
      })(); },
    });
  }, [running, sessionBusy, state, t, toast, uiPreferences.archivedSessions, updateUiPreferences]);

  const resolveApproval = useCallback(async (decision: ApprovalDecision, message?: string) => {
    if (!approval) return;
    try {
      await window.reverie.request("resolveApproval", {
        approvalId: approval.approval_id,
        decision,
        ...(decision === "message" && message ? { message } : {}),
      });
      setApproval(null);
      toast(
        t(decision === "deny" ? "已拒绝工具执行" : decision === "message" ? "已发送个性化回复给模型" : "权限已授予"),
        decision === "deny" ? "info" : "success"
      );
    } catch (error) {
      setApproval(null);
      toast(error instanceof Error ? error.message : String(error), "error");
    }
  }, [approval, t, toast]);

  const selectModel = useCallback(async (source: ModelSource, model: ModelRecord, selectedReasoning?: string) => {
    try {
      const reasoning = selectedReasoning ?? (
        model.reasoning.options.some((option) => option.id === model.reasoning.value)
          ? model.reasoning.value
          : model.reasoning.options[0]?.id
      );
      const response = await window.reverie.request("selectModel", { source: source.id, modelId: model.id, ...(reasoning ? { reasoning } : {}) });
      setState((current) => current ? { ...current, models: response.models, workspace: response.workspace } : current);
      setModelPickerOpen(false);
      toast(t("model.switched", { name: model.display_name }), "success");
    } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); }
  }, [t, toast]);

  const openModelPicker = useCallback(() => {
    if (state?.workspace.mode === "computer-controller") return;
    setModelPickerOpen(true);
    void window.reverie.request("refreshModelSources", {}).then((response) => {
      if (!response.models) return;
      setState((current) => current ? { ...current, models: response.models } : current);
    }).catch(() => {
      // Keep the initialized fallback catalog available when live discovery fails.
    });
  }, [state?.workspace.mode]);

  useEffect(() => {
    if (state?.workspace.mode === "computer-controller") setModelPickerOpen(false);
  }, [state?.workspace.mode]);

  const selectReasoning = useCallback(async (reasoning: string) => {
    if (!state) return;
    const source = visibleModelSources(state.models.sources).find((item) => item.active);
    if (!source) return;
    try {
      const response = await window.reverie.request("selectModel", { source: source.id, modelId: source.selected_model_id, reasoning });
      setState((current) => current ? { ...current, models: response.models, workspace: response.workspace } : current);
      toast(t("思考设置已更新"), "success");
    } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); }
  }, [state, t, toast]);

  const updateSetting = useCallback(async (key: string, value: unknown) => {
    try {
      const response = await window.reverie.request("setSetting", { key, value });
      if (response.success === false) throw new Error(String(response.message ?? t("设置未保存")));
      const settings = response.settings;
      setState((current) => current ? { ...current, settings, models: response.models, workspace: response.workspace } : current);
      toast(t("设置已保存"), "success");
    } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); }
  }, [t, toast]);

  const saveProvider = useCallback(async (source: ModelSource, patch: Record<string, unknown>) => {
    try {
      const response = await window.reverie.request("setProviderConfig", { source: source.id, patch });
      setState((current) => current ? { ...current, models: response.models, workspace: response.workspace } : current);
      toast(t("provider.saved", { name: source.display_name }), "success");
    } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); }
  }, [t, toast]);

  const addStandard = useCallback(async (model: Record<string, unknown>) => {
    try {
      const response = await window.reverie.request("addStandardModel", { model });
      setState((current) => current ? { ...current, models: response.models, workspace: response.workspace } : current);
      setStandardModelOpen(false);
      toast(t("标准模型已添加"), "success");
    } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); }
  }, [t, toast]);

  const deleteStandard = useCallback((index: number) => {
    setConfirmation({ title: t("删除标准模型？"), message: t("这会从 Reverie 内核配置中移除该模型，但不会删除任何远端数据。"), label: t("删除模型"), danger: true, action: () => { void (async () => { try { const response = await window.reverie.request("deleteStandardModel", { index }); setState((current) => current ? { ...current, models: response.models, workspace: response.workspace } : current); toast(t("模型已删除"), "success"); } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); } })(); } });
  }, [t, toast]);

  const updatePlugin = useCallback(async (action: "setPluginEnabled" | "setPluginTrust", plugin: PluginRecord, value: boolean) => {
    try {
      const response = action === "setPluginEnabled"
        ? await window.reverie.request("setPluginEnabled", { pluginId: plugin.id, enabled: value })
        : await window.reverie.request("setPluginTrust", { pluginId: plugin.id, trusted: value });
      const plugins = response.plugins;
      setState((current) => current ? { ...current, plugins, settings: response.settings } : current);
      toast(t("plugin.updated", { name: plugin.name }), "success");
    } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); }
  }, [t, toast]);

  const refreshPlugins = useCallback(async () => {
    try {
      const response = await window.reverie.request("refreshPlugins", {});
      setState((current) => current ? { ...current, plugins: response.plugins } : current);
      toast(t("插件目录已刷新"), "success");
    } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); }
  }, [t, toast]);

  const indexWorkspace = useCallback(async () => {
    toast(t("工作区索引已开始"), "info");
    try {
      const response = await window.reverie.request("indexWorkspace", {});
      setState((current) => current ? { ...current, workspace: response.workspace } : current);
      toast(t("工作区索引完成"), "success");
    } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); }
  }, [t, toast]);

  const rollback = useCallback((checkpointId: string) => {
    setConfirmation({ title: t("恢复到这个检查点？"), message: t("Reverie 将恢复会话消息，并回退该检查点之后被操作历史跟踪的文件。建议先提交当前改动。"), label: t("确认恢复"), danger: true, action: () => { void (async () => { try { const response = await window.reverie.request("rollbackCheckpoint", { checkpointId, confirmed: true }); setState((current) => current ? { ...current, recovery: response.recovery } : current); if (session) await openSession(session.id); toast(t("检查点恢复完成"), "success"); } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); } })(); } });
  }, [openSession, session, t, toast]);

  const requestMentions = useCallback(async () => {
    if (mentionOpen) {
      mentionRequestSequence.current += 1;
      setMentionOpen(false);
      setMentionLoading(false);
      return;
    }
    const requestSequence = ++mentionRequestSequence.current;
    setMentionOpen(true);
    setMentionLoading(true);
    try {
      const response = await window.reverie.request("workspaceMentions", { query: prompt.trim(), limit: 24 });
      if (requestSequence !== mentionRequestSequence.current) return;
      setMentionItems(response.items);
      const nextContext = response.context_engine;
      setState((current) => current ? {
        ...current,
        workspace: { ...current.workspace, index_ready: Boolean(nextContext?.ready), context_engine: nextContext },
      } : current);
    } catch (error) {
      if (requestSequence !== mentionRequestSequence.current) return;
      setMentionOpen(false);
      toast(error instanceof Error ? error.message : String(error), "error");
    } finally {
      if (requestSequence === mentionRequestSequence.current) setMentionLoading(false);
    }
  }, [mentionOpen, prompt, toast]);

  const selectAttachment = useCallback(async () => {
    try {
      const attachment = await window.reverie.selectAttachment();
      if (!attachment) return;
      const mention = workspaceMention(attachment.relativePath);
      setAttachments((current) => current.some((item) => item.relativePath === attachment.relativePath)
        ? current
        : [...current, attachment]);
      setPrompt((current) => `${current}${current && !/\s$/.test(current) ? " " : ""}${mention} `);
      setMentionOpen(false);
      toast(t("attachment.added", { name: attachment.name }), "success");
    } catch (error) {
      toast(error instanceof Error ? error.message : String(error), "error");
    }
  }, [t, toast]);

  const removeAttachment = useCallback((attachment: ComposerAttachment) => {
    const mention = workspaceMention(attachment.relativePath);
    setAttachments((current) => current.filter((item) => item.relativePath !== attachment.relativePath));
    setPrompt((current) => current.replace(mention, "").replace(/[ \t]{2,}/g, " ").trimStart());
  }, []);

  const selectWorkspace = useCallback(async () => {
    if (running || sessionBusy) return;
    setSessionBusy(true);
    try {
      if (session) drafts.current[session.id] = prompt;
      const projectRoot = await window.reverie.selectWorkspace();
      if (projectRoot) {
        sessionRequestSequence.current += 1;
        drafts.current = {};
        setPrompt("");
        setAttachments([]);
        setMentionOpen(false);
        await initialize(projectRoot);
      }
    } catch (error) {
      toast(error instanceof Error ? error.message : String(error), "error");
    } finally {
      setSessionBusy(false);
    }
  }, [initialize, prompt, running, session, sessionBusy, toast]);

  const switchWorkspace = useCallback(async (projectRoot: string) => {
    if (running || sessionBusy || projectRoot.toLowerCase() === state?.workspace.project_root.toLowerCase()) return;
    try {
      if (session) drafts.current[session.id] = prompt;
      setSessionBusy(true);
      const selectedRoot = await window.reverie.switchWorkspace(projectRoot);
      if (!selectedRoot) return;
      sessionRequestSequence.current += 1;
      drafts.current = {};
      setPrompt("");
      setAttachments([]);
      setMentionOpen(false);
      await initialize(selectedRoot);
    } catch (error) {
      toast(error instanceof Error ? error.message : String(error), "error");
    } finally {
      setSessionBusy(false);
    }
  }, [initialize, prompt, running, session, sessionBusy, state?.workspace.project_root, toast]);

  const deleteProject = useCallback((target: { root: string; name: string; active: boolean }) => {
    if (running || sessionBusy) return;
    setConfirmation({
      title: t("project.deleteTitle", { name: target.name }),
      message: t("该项目的全部会话、完整转录、记忆、检查点、Context Engine 缓存和已导入附件将永久删除。源码与普通项目文件不会被删除。"),
      label: t("删除项目与记录"),
      danger: true,
      action: () => { void (async () => {
        setSessionBusy(true);
        try {
          const result = await window.reverie.deleteWorkspace(target.root);
          if (!result) return;
          setUiPreferences(normalizeUiPreferences(result.preferences));
          if (target.active) {
            sessionRequestSequence.current += 1;
            drafts.current = {};
            setPrompt("");
            setAttachments([]);
            setMentionOpen(false);
            await initialize(result.projectRoot);
          }
          toast(t("project.deleted", { count: result.deletedSessions }), "success");
        } catch (error) {
          toast(error instanceof Error ? error.message : String(error), "error");
        } finally {
          setSessionBusy(false);
        }
      })(); },
    });
  }, [initialize, running, sessionBusy, t, toast]);

  const selectCoreData = useCallback(async () => {
    if (running || sessionBusy) return;
    try {
      const coreAppRoot = await window.reverie.selectCoreData();
      if (!coreAppRoot) return;
      sessionRequestSequence.current += 1;
      drafts.current = {};
      setState(null);
      setSession(null);
      setPrompt("");
      await initialize(desktopPaths?.projectRoot);
    } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); }
  }, [desktopPaths?.projectRoot, initialize, running, sessionBusy, toast]);

  const chooseCommand = useCallback((command: CommandRecord) => {
    setCommandOpen(false);
    const navigation: Record<string, ViewId> = { "/model": "settings", "/settings": "settings", "/setting": "settings", "/tools": "tools", "/rats": "rats", "/tasks": "tasks", "/operations": "tasks", "/plugins": "plugins", "/checkpoints": "recovery", "/rollback": "recovery" };
    const target = navigation[command.command];
    if (target) { setView(target); return; }
    setView("chat");
    setPrompt(command.examples?.[0] || command.command);
    toast(t("command.inserted", { command: command.command }), "info");
  }, [t, toast]);

  const activeSessionId = session?.id ?? state?.sessions.current_session_id ?? "";
  const page = useMemo(() => {
    if (!state) return null;
    if (view === "tools") return <ToolsView mode={state.workspace.mode} />;
    if (view === "rats") return <RatsView />;
    if (view === "tasks") return <RtpTasksView />;
    if (view === "subagents") return <SubagentsView />;
    if (view === "plugins") return <PluginsView plugins={state.plugins.records} updatePlugin={updatePlugin} refresh={refreshPlugins} />;
    if (view === "recovery") return <RecoveryView recovery={state.recovery} rollback={rollback} />;
    if (view === "settings") return <SettingsView state={state} updateSetting={updateSetting} selectModel={selectModel} saveProvider={saveProvider} addStandard={() => setStandardModelOpen(true)} deleteStandard={deleteStandard} paths={desktopPaths} selectCoreData={() => void selectCoreData()} theme={theme} setTheme={changeTheme} preferences={uiPreferences} updatePreferences={updateUiPreferences} selectBackground={() => void selectBackground()} clearBackground={() => void clearBackground()} />;
    return <ChatView session={session} liveTurn={liveTurn} running={running} prompt={prompt} setPrompt={setPrompt} send={() => void sendPrompt()} cancel={() => void cancelPrompt()} mentionItems={mentionItems} mentionOpen={mentionOpen} mentionLoading={mentionLoading} requestMentions={() => void requestMentions()} chooseMention={(value) => { setPrompt((current) => `${current}${current && !current.endsWith(" ") ? " " : ""}${value} `); setMentionOpen(false); }} attachments={attachments} selectAttachment={() => void selectAttachment()} removeAttachment={removeAttachment} modelName={state.models.active_model?.display_name ?? "Reverie"} sessionBusy={sessionBusy} renameSession={() => { if (session) setRenameSessionTarget({ id: session.id, name: session.name }); }} forkSession={() => void forkActiveSession()} rewindSession={rewindActiveSession} deleteSession={() => { if (session) deleteSession(session); }} preferences={uiPreferences} updatePreferences={updateUiPreferences} />;
  }, [state, view, updatePlugin, refreshPlugins, rollback, updateSetting, selectModel, saveProvider, deleteStandard, desktopPaths, selectCoreData, theme, changeTheme, uiPreferences, updateUiPreferences, selectBackground, clearBackground, session, liveTurn, running, prompt, mentionItems, mentionOpen, mentionLoading, attachments, selectAttachment, removeAttachment, sendPrompt, cancelPrompt, requestMentions, sessionBusy, forkActiveSession, rewindActiveSession, deleteSession]);

  if (bootError) return <I18nProvider language={uiPreferences.language}><ErrorScreen error={bootError} retry={() => void initialize()} /></I18nProvider>;
  if (!state) return <I18nProvider language={uiPreferences.language}><LoadingScreen /></I18nProvider>;

  return (
    <I18nProvider language={uiPreferences.language}>
    <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""} ${inspectorOpen ? "with-inspector" : ""}`}>
      <Sidebar state={state} view={view} setView={setView} activeSessionId={activeSessionId} openSession={(id) => void openSession(id)} newSession={() => void createSession()} sessionBusy={sessionBusy} selectWorkspace={() => void selectWorkspace()} switchWorkspace={(projectRoot) => void switchWorkspace(projectRoot)} openSearch={() => setSessionSearchOpen(true)} preferences={uiPreferences} toggleSidebar={toggleSidebar} renameSession={(target) => setRenameSessionTarget({ id: target.id, name: target.name })} toggleArchive={toggleSessionArchive} deleteSession={deleteSession} deleteArchivedSessions={deleteArchivedSessions} deleteProject={deleteProject} />
      <main className="main-area">
        <Topbar state={state} sidebarCollapsed={sidebarCollapsed} toggleSidebar={toggleSidebar} openModelPicker={openModelPicker} selectReasoning={(value) => void selectReasoning(value)} setMode={(mode) => void updateSetting("mode", mode)} inspectorOpen={inspectorOpen} toggleInspector={() => setInspectorOpen((value) => !value)} openCommands={() => setCommandOpen(true)} theme={theme} setTheme={changeTheme} />
        <div className="content-area">{page}</div>
      </main>
      {inspectorOpen && <Inspector state={state} liveTurn={liveTurn} indexWorkspace={() => void indexWorkspace()} compactContext={() => void compactContext()} compactDisabled={running || sessionBusy} />}
      {modelPickerOpen && state.workspace.mode !== "computer-controller" && <ModelPicker state={state} onSelect={(source, model, reasoning) => void selectModel(source, model, reasoning)} close={() => setModelPickerOpen(false)} />}
      {commandOpen && <CommandPalette commands={state.commands.items} close={() => setCommandOpen(false)} choose={chooseCommand} />}
      {sessionSearchOpen && <SessionSearch close={() => setSessionSearchOpen(false)} openSession={(id) => void openSession(id)} />}
      {renameSessionTarget && <RenameSessionModal session={renameSessionTarget} close={() => setRenameSessionTarget(null)} save={(name) => void renameSession(name)} />}
      {standardModelOpen && <StandardModelModal close={() => setStandardModelOpen(false)} save={(model) => void addStandard(model)} />}
      {approval && <ApprovalModal approval={approval} resolve={(decision, message) => void resolveApproval(decision, message)} />}
      {confirmation && <ConfirmModal title={confirmation.title} message={confirmation.message} confirmLabel={confirmation.label} danger={confirmation.danger} close={() => setConfirmation(null)} confirm={() => { const action = confirmation.action; setConfirmation(null); action(); }} />}
      <Toasts items={toasts} />
    </div>
    </I18nProvider>
  );
}

const DIALOG_FOCUSABLE = [
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[href]",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function useDialogFocus(
  dialogRef: { current: HTMLElement | null },
  close?: () => void,
): void {
  const closeRef = useRef(close);
  closeRef.current = close;
  const restoreFocus = useRef<HTMLElement | null>(
    typeof document !== "undefined" && document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null,
  );

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const focusable = () => Array.from(dialog.querySelectorAll<HTMLElement>(DIALOG_FOCUSABLE))
      .filter((element) => !element.hidden && element.getAttribute("aria-hidden") !== "true");
    const initial = dialog.querySelector<HTMLElement>("[autofocus]") ?? focusable()[0] ?? dialog;
    initial.focus();

    const keyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape" && closeRef.current) {
        event.preventDefault();
        event.stopPropagation();
        closeRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const elements = focusable();
      if (!elements.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    dialog.addEventListener("keydown", keyDown);
    return () => {
      dialog.removeEventListener("keydown", keyDown);
      restoreFocus.current?.focus();
    };
  }, [dialogRef]);
}
