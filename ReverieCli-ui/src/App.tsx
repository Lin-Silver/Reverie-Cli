import {
  AlertCircle,
  Archive,
  ArchiveRestore,
  AtSign,
  Brain,
  Check,
  CheckCircle2,
  ChevronDown,
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
  PromptResult,
  RecoveryState,
  SessionInfo,
  SessionMessage,
  SessionState,
  SettingItem,
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
import { normalizeSidebarCollapsed, SIDEBAR_COLLAPSED_STORAGE_KEY } from "./layout";

type CoreResponse = Record<string, unknown>;
type Toast = { id: number; kind: "success" | "error" | "info"; message: string };
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

function formatTime(value: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  return sameDay
    ? date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString([], { month: "short", day: "numeric" });
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

function messageText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((item) => {
        const part = asRecord(item);
        if (typeof part.text === "string") return part.text;
        if (part.type === "image_url" || part.type === "image") return "[图片]";
        return "";
      })
      .filter(Boolean)
      .join("\n");
  }
  return content == null ? "" : JSON.stringify(content, null, 2);
}

function eventLabel(event: Record<string, unknown>): { title: string; detail: string; status: string } {
  const type = String(event.type ?? event.kind ?? "activity");
  const title = String(event.title ?? event.name ?? event.tool_name ?? event.message ?? type);
  const detail = String(event.detail ?? event.output ?? event.error ?? "");
  const status = String(event.status ?? (type.includes("error") ? "error" : "info"));
  return { title, detail, status };
}

function IconButton({
  label,
  children,
  onClick,
  active = false,
  disabled = false,
}: {
  label: string;
  children: ReactNode;
  onClick?: () => void;
  active?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className={`icon-button ${active ? "active" : ""}`}
      aria-label={label}
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
  return (
    <div className="loading-screen">
      <BrandMark />
      <div className="loading-orbit"><span /></div>
      <p>{message}</p>
      <small>Electron UI · Reverie CLI Core</small>
    </div>
  );
}

function ErrorScreen({ error, retry }: { error: string; retry: () => void }) {
  return (
    <div className="loading-screen error-screen">
      <div className="error-glyph"><AlertCircle size={28} /></div>
      <h1>无法启动 Reverie</h1>
      <p>{error}</p>
      <button type="button" className="primary-button" onClick={retry}>
        <RefreshCw size={15} /> 重试
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
  renameSession: (session: SessionInfo) => void;
  toggleArchive: (session: SessionInfo, archived: boolean) => void;
  deleteSession: (session: SessionInfo) => void;
  deleteArchivedSessions: (sessions: SessionInfo[]) => void;
  deleteProject: (project: { root: string; name: string; active: boolean }) => void;
}) {
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
        <span className="session-meta">{session.message_count} 条 · {formatTime(session.updated_at)}</span>
      </button>
      <button
        type="button"
        className="session-more"
        aria-label={`管理会话 ${session.name}`}
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
            <Pencil size={14} /><span>重命名</span>
          </button>
          <button type="button" onClick={() => { setSessionMenuId(""); toggleArchive(session, archived); }}>
            {archived ? <ArchiveRestore size={14} /> : <Archive size={14} />}
            <span>{archived ? "移出归档" : "归档"}</span>
          </button>
          <div className="session-menu-separator" />
          <button type="button" className="danger" onClick={() => { setSessionMenuId(""); deleteSession(session); }}>
            <Trash2 size={14} /><span>删除</span>
          </button>
        </div>
      )}
    </div>
  );

  return (
    <aside className="sidebar">
      <div className="sidebar-drag"><BrandMark /></div>
      <div className="sidebar-actions">
        <button type="button" className="new-chat-button" onClick={newSession} disabled={sessionBusy}>
          <Plus size={16} /> 新对话
          <span>Ctrl N</span>
        </button>
        <button type="button" className="sidebar-action" onClick={openSearch}>
          <Search size={15} /> 搜索对话 <span>Ctrl F</span>
        </button>
      </div>

      <nav className="main-nav" aria-label="主导航">
        <button type="button" className={view === "chat" ? "active" : ""} onClick={() => setView("chat")}>
          <MessageSquare size={16} /> 对话
        </button>
        <button type="button" className={view === "tools" ? "active" : ""} onClick={() => setView("tools")}>
          <Wrench size={16} /> 工具
        </button>
        <button type="button" className={view === "plugins" ? "active" : ""} onClick={() => setView("plugins")}>
          <Plug size={16} /> 插件
        </button>
        <button type="button" className={view === "recovery" ? "active" : ""} onClick={() => setView("recovery")}>
          <ArchiveRestore size={16} /> 恢复
        </button>
      </nav>

      <div className="project-heading">
        <span>项目与会话</span>
        <button type="button" aria-label="添加工作区" onClick={selectWorkspace}><Plus size={14} /></button>
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
                  aria-label={`管理项目 ${projectName}`}
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
                      <FolderOpen size={14} /><span>显示项目目录</span>
                    </button>
                    <div className="session-menu-separator" />
                    <button type="button" className="danger" onClick={() => { setProjectMenuRoot(""); deleteProject({ root: projectRoot, name: projectName, active }); }}>
                      <Trash2 size={14} /><span>删除项目与记录</span>
                    </button>
                  </div>
                )}
              </div>
              {active && activeProjectOpen && (
                <>
                  <div className="project-session-actions">
                    <button type="button" onClick={openSearch}><Search size={13} />搜索</button>
                    {state.sessions.items.length > 8 && (
                      <button type="button" className={filterOpen ? "active" : ""} onClick={() => { setFilterOpen((value) => !value); setSessionFilter(""); }}>
                        <ListFilter size={13} />筛选
                      </button>
                    )}
                  </div>
                  {filterOpen && (
                    <div className="inline-search project-filter">
                      <Search size={13} />
                      <input autoFocus value={sessionFilter} placeholder="筛选当前项目" onChange={(event) => setSessionFilter(event.target.value)} />
                    </div>
                  )}
                  <div className="session-list">
                    {activeSessions.length === 0 && <div className="sidebar-empty">当前项目还没有活跃会话</div>}
                    {activeSessions.map((session) => renderSession(session, false))}
                    {allArchivedSessions.length > 0 && (
                      <div className="archived-sessions">
                        <div className="archived-heading-shell">
                          <button type="button" className="archived-heading" onClick={() => setArchivedOpen((value) => !value)}>
                            {archivedOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                            <Archive size={13} /><span>已归档</span><small>{allArchivedSessions.length}</small>
                          </button>
                          <button
                            type="button"
                            className="archived-more"
                            aria-label="管理归档会话"
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
                                <Trash2 size={14} /><span>清空全部归档会话</span>
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
          <Settings size={16} /> 设置
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
  onSelect: (source: ModelSource, model: ModelRecord) => void;
  close: () => void;
}) {
  const [sourceId, setSourceId] = useState(state.models.active_source);
  const [query, setQuery] = useState("");
  const source = state.models.sources.find((item) => item.id === sourceId) ?? state.models.sources[0];
  const models = source.models.filter((model) =>
    `${model.display_name} ${model.id}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <div className="popover-backdrop" onMouseDown={close}>
      <div className="model-picker" onMouseDown={(event) => event.stopPropagation()}>
        <div className="model-picker-sources">
          <div className="popover-title">模型来源</div>
          {state.models.sources.map((item) => (
            <button
              type="button"
              key={item.id}
              className={item.id === source.id ? "active" : ""}
              onClick={() => {
                setSourceId(item.id);
                setQuery("");
              }}
            >
              <span>{item.display_name}</span>
              <small>{item.models.length}</small>
            </button>
          ))}
        </div>
        <div className="model-picker-models">
          <div className="model-picker-header">
            <div>
              <strong>{source.display_name}</strong>
              <span>选择用于当前工作区的模型</span>
            </div>
            <div className="inline-search model-search">
              <Search size={14} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索模型" autoFocus />
            </div>
          </div>
          <div className="model-option-list">
            {models.map((model) => (
              <button
                type="button"
                key={model.id}
                className={source.active && source.selected_model_id === model.id ? "active" : ""}
                onClick={() => onSelect(source, model)}
              >
                <div className="model-option-icon">{model.vision ? <Eye size={15} /> : <Brain size={15} />}</div>
                <div>
                  <strong>{model.display_name}</strong>
                  <span>{model.description || model.id}</span>
                  <small>
                    {model.transport || "custom"} · {formatTokens(model.context_length)} context
                    {model.reasoning.control !== "none" ? ` · ${model.reasoning.control}` : ""}
                  </small>
                </div>
                {source.active && source.selected_model_id === model.id && <Check size={16} />}
              </button>
            ))}
            {models.length === 0 && <div className="empty-list">没有匹配的模型</div>}
          </div>
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
  const [reasoningOpen, setReasoningOpen] = useState(false);
  const [modeOpen, setModeOpen] = useState(false);
  const [themeOpen, setThemeOpen] = useState(false);
  const activeSource = state.models.sources.find((source) => source.active);
  const reasoning = activeSource?.selected_reasoning;
  const reasoningOptions = reasoning?.options ?? [];
  const selectedReasoning = reasoningOptions.find((item) => item.id === reasoning?.value);
  const mode = MODES.find((item) => item[0] === state.workspace.mode) ?? MODES[0];
  const ModeIcon = mode[2];
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
        <IconButton label={sidebarCollapsed ? "展开左侧栏" : "收起左侧栏"} onClick={toggleSidebar}>
          {sidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </IconButton>
        <button type="button" className="model-trigger" onClick={openModelPicker}>
          <span>{state.models.active_model?.display_name || "选择模型"}</span>
          <small>{activeSource?.display_name || state.models.active_source}</small>
          <ChevronDown size={14} />
        </button>
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
              {selectedReasoning?.label || (reasoning.control === "fixed" ? "固定思考" : reasoning.control === "provider-managed" ? "自动思考" : "思考")}
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
                    <div><strong>{option.label}</strong><span>{option.description}</span></div>
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
                  <Icon size={15} /><span>{label}</span>{id === state.workspace.mode && <Check size={14} />}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="relative">
          <IconButton label="切换主题" onClick={() => {
            setThemeOpen((value) => !value);
            setReasoningOpen(false);
            setModeOpen(false);
          }} active={themeOpen}>
            <Palette size={16} />
          </IconButton>
          {themeOpen && (
            <div className="small-popover theme-menu">
              <div className="popover-title">界面主题</div>
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
                  <div><strong>{label}</strong><span>{description}</span></div>
                  {id === theme && <Check size={14} />}
                </button>
              ))}
            </div>
          )}
        </div>
        <IconButton label="命令面板" onClick={openCommands}><Command size={16} /></IconButton>
        <IconButton label={inspectorOpen ? "关闭检查器" : "打开检查器"} onClick={toggleInspector} active={inspectorOpen}>
          {inspectorOpen ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
        </IconButton>
      </div>
    </header>
  );
}

function ActivityItem({ event }: { event: Record<string, unknown> }) {
  const item = eventLabel(event);
  return (
    <div className={`activity-item ${item.status}`}>
      <div className="activity-status">
        {item.status === "success" ? <CheckCircle2 size={14} /> : item.status === "error" ? <AlertCircle size={14} /> : <Circle size={9} />}
      </div>
      <div><strong>{item.title}</strong>{item.detail && <span>{item.detail}</span>}</div>
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
  const [expanded, setExpanded] = useState(defaultExpanded);
  useEffect(() => setExpanded(defaultExpanded), [defaultExpanded]);
  const name = message.name || "工具结果";
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
          <small>{error ? "执行失败" : "工具结果"}</small>
        </span>
        <span className="trace-preview">{text.slice(0, 140)}</span>
        <ChevronDown size={13} />
      </summary>
      {expanded && <pre>{text}</pre>}
    </details>
  );
}

function HistoryReasoning({ text, defaultExpanded }: { text: string; defaultExpanded: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  useEffect(() => setExpanded(defaultExpanded), [defaultExpanded]);
  const preview = text.replace(/\s+/g, " ").trim().slice(0, 110);
  return (
    <details className="reasoning-block" open={expanded} onToggle={(event) => setExpanded(event.currentTarget.open)}>
      <summary>
        <span className="reasoning-icon"><Brain size={14} /></span>
        <span className="reasoning-title"><strong>推理记录</strong><small>模型返回的内部分析</small></span>
        <span className="reasoning-preview">{preview}</span>
        <small>{text.length.toLocaleString()} 字符</small>
        <ChevronDown size={13} />
      </summary>
      {expanded && <div className="reasoning-content"><Markdown>{text}</Markdown></div>}
    </details>
  );
}

function ToolCallList({ message }: { message: SessionMessage }) {
  const calls = toolCallRecords(message);
  if (!calls.length) return null;
  return (
    <div className="tool-call-list">
      {calls.map((call, index) => (
        <details className="tool-call-card" key={`${call.name}-${index}`}>
          <summary>
            <span className="trace-icon"><ToolGlyph name={call.name} /></span>
            <span><strong>{call.name}</strong><small>模型调用</small></span>
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
  const text = messageText(message.content);
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
        <div className="message-avatar">{user ? "你" : <Sparkles size={15} strokeWidth={1.7} />}</div>
        <strong>{user ? "你" : "Reverie"}</strong>
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
  const elapsed = Math.max(0, Math.round((Date.now() - (turn.startedAt ?? Date.now())) / 1000));
  return (
    <>
      <article className="message user">
        <div className="message-heading"><div className="message-avatar">你</div><strong>你</strong></div>
        <div className="message-body"><div className="user-text">{turn.userText}</div></div>
      </article>
      <article className="message assistant live-message">
        <div className="message-heading"><div className="message-avatar"><Sparkles size={15} strokeWidth={1.7} /></div><strong>Reverie</strong><span className="live-status">正在处理</span></div>
        <div className="message-body">
          {preferences.showReasoning && turn.reasoningText && <HistoryReasoning text={turn.reasoningText} defaultExpanded={preferences.expandReasoning} />}
          {preferences.showLiveActivity && (running || turn.events.length > 0) && (
            <details className="live-run-summary" open={running && !turn.assistantText}>
              <summary><Clock3 size={14} /><strong>{running ? `已工作 ${elapsed} 秒` : "本轮活动"}</strong><span>{turn.events.length} 项活动</span><ChevronDown size={13} /></summary>
              <div className="inline-activities">
                {turn.events.length
                  ? turn.events.slice(-12).map((event, index) => <ActivityItem key={index} event={event} />)
                  : <span className="activity-placeholder">正在准备模型与上下文…</span>}
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
  return (
    <div className="empty-chat">
      <div className="empty-mark"><img src={REVERIE_MARK_URL} alt="Reverie" /></div>
      <h1>今天想一起做点什么？</h1>
      <p>Reverie 可以理解工作区、编写代码、调用工具，并在同一会话中持续完成任务。</p>
      <div className="quick-grid">
        {QUICK_STARTS.map(({ icon: Icon, title, prompt }) => (
          <button type="button" key={title} onClick={() => setPrompt(prompt)}>
            <Icon size={16} /><strong>{title}</strong><span>{prompt}</span>
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
  if (!open) return null;
  return (
    <div className="mention-picker" aria-live="polite">
      <div className="mention-picker-heading">
        <span><Sparkles size={13} />Context Engine 推荐</span>
        <small>结合当前提示、会话、索引与 Git 变更</small>
      </div>
      {loading && <div className="mention-picker-state"><RefreshCw className="spin" size={14} />正在计算最相关文件…</div>}
      {!loading && items.length === 0 && <div className="mention-picker-state">当前工作区没有可推荐的文件</div>}
      {items.slice(0, 12).map((item, index) => {
        const pathValue = String(item.path ?? item.file_path ?? "");
        const line = Number(item.line ?? item.start_line ?? 0);
        const value = `${workspaceMention(pathValue)}${line ? `#L${line}` : ""}`;
        const reason = String(item.reason ?? item.summary ?? item.source ?? "工作区匹配");
        return (
          <button type="button" key={`${value}-${index}`} onClick={() => choose(value)}>
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
                <button type="button" aria-label={`移除附件 ${attachment.name}`} onClick={() => removeAttachment(attachment)}><X size={12} /></button>
              </span>
            ))}
          </div>
        )}
        <textarea
          ref={textarea}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={keyDown}
          placeholder={`向 ${modelName || "Reverie"} 提问，或输入 @ 引用文件…`}
          rows={1}
          disabled={running || disabled}
        />
        <div className="composer-toolbar">
          <div>
            <IconButton label="Context Engine 推荐工作区文件" onClick={requestMentions} disabled={disabled}><AtSign size={16} /></IconButton>
            <IconButton label="选择任意文件作为附件" onClick={selectAttachment} disabled={disabled}><Paperclip size={16} /></IconButton>
          </div>
          <div className="composer-hint">
            {!running && <span>Enter 发送 · Shift Enter 换行</span>}
            {running ? (
              <button type="button" className="stop-button" onClick={cancel}><Square size={12} fill="currentColor" /> 停止</button>
            ) : (
              <button type="button" className="send-button" onClick={send} disabled={disabled || !value.trim()}><Send size={15} /></button>
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
  const counts = messages.reduce(
    (current, message) => ({
      reasoning: current.reasoning + (messageReasoningText(message) ? 1 : 0),
      calls: current.calls + toolCallRecords(message).length,
      results: current.results + (message.role === "tool" && messageText(message.content) ? 1 : 0),
    }),
    { reasoning: 0, calls: 0, results: 0 },
  );
  const hasTrace = counts.reasoning > 0 || counts.calls > 0 || counts.results > 0;
  if (!hasTrace) return null;
  return (
    <div className="conversation-trace-bar">
      <div className="trace-bar-summary">
        <span className="trace-bar-mark"><Sparkles size={13} /></span>
        <span><strong>执行轨迹</strong><small>{counts.reasoning} 段推理 · {counts.calls} 次调用 · {counts.results} 个结果</small></span>
      </div>
      <div className="trace-bar-controls" aria-label="对话技术轨迹显示">
        <button
          type="button"
          className={preferences.showReasoning ? "active" : ""}
          aria-pressed={preferences.showReasoning}
          disabled={counts.reasoning === 0}
          title={counts.reasoning ? "显示或隐藏推理记录" : "当前会话没有保存推理记录"}
          onClick={() => updatePreferences({
            showReasoning: !preferences.showReasoning,
            ...(!preferences.showReasoning ? { expandReasoning: true } : {}),
          })}
        >
          <Brain size={13} />推理 <span>{counts.reasoning}</span>
        </button>
        <button
          type="button"
          className={preferences.showToolCalls ? "active" : ""}
          aria-pressed={preferences.showToolCalls}
          disabled={counts.calls === 0}
          onClick={() => updatePreferences({ showToolCalls: !preferences.showToolCalls })}
        >
          <Wrench size={13} />调用 <span>{counts.calls}</span>
        </button>
        <button
          type="button"
          className={preferences.showToolResults ? "active" : ""}
          aria-pressed={preferences.showToolResults}
          disabled={counts.results === 0}
          onClick={() => updatePreferences({ showToolResults: !preferences.showToolResults })}
        >
          <CheckCircle2 size={13} />结果 <span>{counts.results}</span>
        </button>
        {preferences.showReasoning && counts.reasoning > 0 && (
          <button
            type="button"
            className={preferences.expandReasoning ? "active subtle" : "subtle"}
            aria-pressed={preferences.expandReasoning}
            onClick={() => updatePreferences({ expandReasoning: !preferences.expandReasoning })}
          >
            <ChevronDown size={13} />{preferences.expandReasoning ? "展开中" : "仅摘要"}
          </button>
        )}
        <button
          type="button"
          className="subtle"
          title="只显示用户与模型正文"
          onClick={() => updatePreferences({ showReasoning: false, showToolCalls: false, showToolResults: false })}
        >
          <EyeOff size={13} />专注
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
            <div><strong>{session.name}</strong><span>{visibleMessages.length} 条记录</span></div>
            <div className="conversation-actions">
              <IconButton label="重命名会话" onClick={renameSession} disabled={running || sessionBusy}><Pencil size={14} /></IconButton>
              <IconButton label="分叉会话" onClick={forkSession} disabled={running || sessionBusy || visibleMessages.length === 0}><Copy size={14} /></IconButton>
              <IconButton label="回退上一轮" onClick={rewindSession} disabled={running || sessionBusy || !canRewind}><RotateCcw size={14} /></IconButton>
              <IconButton label="删除会话" onClick={deleteSession} disabled={running || sessionBusy}><Trash2 size={14} /></IconButton>
            </div>
          </div>
          <ConversationTraceBar messages={visibleMessages} preferences={preferences} updatePreferences={updatePreferences} />
        </div>
      )}
      <div className="transcript" ref={transcript} aria-busy={sessionBusy}>
        {sessionBusy && <div className="session-loading"><RefreshCw className="spin" size={16} />正在切换会话</div>}
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
      <PageHeader icon={<Wrench size={20} />} title="工具" description={`当前 ${mode} 模式可供模型调用的原生、MCP 与插件工具。`} action={<button type="button" className="secondary-button" onClick={() => void load()}><RefreshCw size={14} />刷新</button>} />
      <div className="tool-overview">
        <div><Wrench size={17} /><span>可用工具<strong>{tools.length}</strong></span></div>
        <div><ShieldCheck size={17} /><span>内置工具<strong>{builtInCount}</strong></span></div>
        <div><Plug size={17} /><span>MCP 与插件<strong>{extensionCount}</strong></span></div>
      </div>
      <div className="tool-controls">
        <div className="inline-search wide"><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索名称、用途、参数或分类" /></div>
        <div className="layout-toggle">
          <button type="button" className={layout === "grid" ? "active" : ""} aria-label="网格视图" onClick={() => setLayout("grid")}><LayoutGrid size={14} /></button>
          <button type="button" className={layout === "list" ? "active" : ""} aria-label="列表视图" onClick={() => setLayout("list")}><List size={14} /></button>
        </div>
      </div>
      <div className="category-filter">
        <button type="button" className={category === "all" ? "active" : ""} onClick={() => setCategory("all")}>全部 <span>{tools.length}</span></button>
        {categories.map((item) => (
          <button type="button" key={item} className={category === item ? "active" : ""} onClick={() => setCategory(item)}>
            {item}<span>{tools.filter((tool) => tool.category === item).length}</span>
          </button>
        ))}
      </div>
      {loading ? <div className="page-loading"><RefreshCw className="spin" size={18} />读取工具目录</div> : error ? <div className="page-loading error"><AlertCircle size={18} />{error}</div> : (
        <div className={`tool-catalog ${layout}`}>
          {filtered.map((tool) => (
            <details className="tool-catalog-card" key={tool.name}>
              <summary>
                <div className="tool-card-icon"><ToolGlyph name={tool.name} size={17} /></div>
                <div className="tool-card-main">
                  <div><strong>{tool.name}</strong><span>{tool.description || "该工具未提供说明。"}</span></div>
                  <div className="tag-row">
                    <span>{tool.category}</span>
                    <span>{tool.kind === "built-in" ? "内置" : tool.kind === "mcp" ? "MCP" : "插件"}</span>
                    {tool.traits.slice(0, 2).map((trait) => <span key={trait}>{trait}</span>)}
                  </div>
                </div>
                <ChevronDown size={14} />
              </summary>
              <div className="tool-card-details">
                <div><span>用途</span><p>{tool.description || "暂无说明"}</p></div>
                <div><span>参数</span><p>{tool.properties.length ? tool.properties.join(" · ") : "无参数"}</p></div>
                {tool.required.length > 0 && <div><span>必填</span><p>{tool.required.join(" · ")}</p></div>}
                {tool.aliases.length > 0 && <div><span>别名</span><p>{tool.aliases.join(" · ")}</p></div>}
                {tool.supported_modes.length > 0 && <div><span>模式</span><p>{tool.supported_modes.join(" · ")}</p></div>}
              </div>
            </details>
          ))}
          {filtered.length === 0 && <div className="empty-panel"><Search size={24} /><strong>没有匹配的工具</strong><span>尝试更换关键词或分类。</span></div>}
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
  return (
    <div className="page-scroll">
      <PageHeader icon={<Plug size={20} />} title="插件" description="管理运行时插件的启用状态与可执行信任。插件能力由同一个 Reverie 内核加载。" action={<button type="button" className="secondary-button" onClick={refresh}><RefreshCw size={14} />重新扫描</button>} />
      <div className="plugin-list">
        {plugins.map((plugin) => (
          <div className="plugin-card" key={plugin.id}>
            <div className="plugin-icon"><Plug size={18} /></div>
            <div className="plugin-main">
              <div className="plugin-title"><strong>{plugin.name}</strong><span className={`status-pill ${plugin.status}`}>{plugin.status_label || plugin.status}</span></div>
              <p>{plugin.family} · v{plugin.version || "—"}</p>
              <div className="plugin-stats"><span>{plugin.tool_count} tools</span><span>{plugin.command_count} commands</span><span>{plugin.skill_count} skills</span></div>
            </div>
            <div className="plugin-toggles">
              <label><span>信任执行</span><Toggle checked={plugin.trusted} onChange={(value) => updatePlugin("setPluginTrust", plugin, value)} /></label>
              <label><span>启用</span><Toggle checked={plugin.enabled} onChange={(value) => updatePlugin("setPluginEnabled", plugin, value)} /></label>
            </div>
          </div>
        ))}
        {plugins.length === 0 && <div className="empty-panel"><Plug size={26} /><strong>没有发现运行时插件</strong><span>将插件放入 Reverie 插件目录后重新扫描。</span></div>}
      </div>
    </div>
  );
}

function RecoveryView({ recovery, rollback }: { recovery: RecoveryState; rollback: (checkpointId: string) => void }) {
  const total = Number(recovery.summary.total_operations ?? recovery.operations.length);
  const files = (recovery.summary.modified_files as string[] | undefined) ?? [];
  return (
    <div className="page-scroll">
      <PageHeader icon={<ArchiveRestore size={20} />} title="恢复与历史" description="检查操作记录和自动检查点，并在明确确认后恢复会话与文件。" />
      <div className="metric-grid">
        <div><Database size={16} /><span>操作记录</span><strong>{total}</strong></div>
        <div><FileText size={16} /><span>已修改文件</span><strong>{files.length}</strong></div>
        <div><RotateCcw size={16} /><span>检查点</span><strong>{recovery.checkpoints.length}</strong></div>
      </div>
      <section className="page-section">
        <div className="section-heading"><div><h2>检查点</h2><p>恢复会同时回退检查点之后受跟踪的文件和会话消息。</p></div></div>
        <div className="recovery-list">
          {recovery.checkpoints.map((checkpoint) => (
            <div className="recovery-item" key={checkpoint.id}>
              <div className="timeline-dot"><Clock3 size={13} /></div>
              <div><strong>{checkpoint.description}</strong><span>{formatTime(checkpoint.created_at)} · {checkpoint.message_count} 条消息 · {checkpoint.file_checkpoints.length} 个文件快照</span></div>
              <button type="button" className="secondary-button danger-ghost" onClick={() => rollback(checkpoint.id)}><RotateCcw size={13} />恢复</button>
            </div>
          ))}
          {recovery.checkpoints.length === 0 && <div className="empty-row">当前工作区还没有检查点</div>}
        </div>
      </section>
      <section className="page-section">
        <div className="section-heading"><div><h2>最近操作</h2><p>内核记录的提问、工具调用和文件操作。</p></div></div>
        <div className="operation-list">
          {recovery.operations.slice().reverse().slice(0, 100).map((operation) => (
            <div key={operation.id}><span className="operation-type">{operation.operation_type.replaceAll("_", " ")}</span><strong>{operation.description}</strong><time>{formatTime(operation.timestamp)}</time></div>
          ))}
          {recovery.operations.length === 0 && <div className="empty-row">还没有操作历史</div>}
        </div>
      </section>
    </div>
  );
}

function SettingControl({ item, update }: { item: SettingItem; update: (key: string, value: unknown) => void }) {
  if (item.kind === "bool" || item.kind === "workspace" || item.kind === "plugin-bool") {
    return <Toggle checked={Boolean(item.value)} onChange={(value) => update(item.key, value)} />;
  }
  if (item.kind === "choice") {
    return (
      <select value={String(item.value ?? "")} onChange={(event) => update(item.key, event.target.value)}>
        {(item.choices ?? []).map((choice) => <option key={String(choice)} value={String(choice)}>{String(choice)}</option>)}
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
  const savedValue = String(item.value ?? "");
  const [value, setValue] = useState(savedValue);
  useEffect(() => setValue(savedValue), [savedValue]);
  const changed = value !== savedValue;
  return (
    <div className="rules-editor">
      <textarea value={value} rows={6} onChange={(event) => setValue(event.target.value)} />
      <div>
        {changed && <span>有未保存的更改</span>}
        <button type="button" className="secondary-button" onClick={() => setValue(savedValue)} disabled={!changed}>撤销</button>
        <button type="button" className="primary-button" onClick={() => update(item.key, value)} disabled={!changed}>保存规则</button>
      </div>
    </div>
  );
}

function ProviderFieldControl({ field, value, configured, update }: { field: ConfigField; value: unknown; configured: boolean; update: (key: string, value: unknown) => void }) {
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
        placeholder={field.kind === "secret" && configured ? "已配置；留空保持不变" : field.optional ? "可选" : ""}
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
  const [sourceId, setSourceId] = useState(state.models.active_source);
  const source = state.models.sources.find((item) => item.id === sourceId) ?? state.models.sources[0];
  const [patch, setPatch] = useState<Record<string, unknown>>({});
  useEffect(() => setPatch({}), [source.id]);
  const valueFor = (field: ConfigField) => field.key in patch ? patch[field.key] : source.config?.values[field.key];
  const sourceDescription = source.id === "standard"
    ? "管理任意 OpenAI、Anthropic、Responses 或请求兼容模型。"
    : source.id === "agnes" && source.modalities
      ? `LLM ${source.modalities.llm} · TTI ${source.modalities.tti} · TTV ${source.modalities.ttv}；${source.modalities.live ? "官方实时目录" : "内置回退目录"}。`
      : `${source.models.length} 个内核原生模型；能力和思考选项来自 CLI 源代码。`;
  return (
    <div className="provider-settings">
      <div className="provider-tabs">
        {state.models.sources.map((item) => <button type="button" key={item.id} className={item.id === source.id ? "active" : ""} onClick={() => setSourceId(item.id)}>{item.display_name}{item.active && <span />}</button>)}
      </div>
      <div className="provider-content">
        <div className="section-heading">
          <div><h2>{source.display_name}</h2><p>{sourceDescription}</p></div>
          {source.id === "standard" && <button type="button" className="primary-button small" onClick={addStandard}><Plus size={14} />添加模型</button>}
        </div>
        <div className="settings-model-grid">
          {source.models.map((model) => (
            <div className={`settings-model-card ${source.active && source.selected_model_id === model.id ? "active" : ""}`} key={model.id}>
              <button type="button" className="model-card-main" onClick={() => selectModel(source, model)}>
                <div><strong>{model.display_name}</strong><span>{model.id}</span></div>
                {source.active && source.selected_model_id === model.id ? <CheckCircle2 size={16} /> : <Circle size={14} />}
              </button>
              <p>{model.description}</p>
              <div className="tag-row"><span>{formatTokens(model.context_length)} ctx</span>{model.vision && <span>vision</span>}{model.tool_calling && <span>tools</span>}{model.reasoning.control !== "none" && <span>{model.reasoning.control}</span>}</div>
              {source.id === "standard" && <button type="button" className="delete-model" onClick={() => deleteStandard(Number(model.id))}><Trash2 size={13} /></button>}
            </div>
          ))}
          {source.models.length === 0 && <div className="empty-panel compact"><Database size={22} /><strong>还没有标准模型</strong><span>添加一个模型后即可用于 TUI、命令行和 GUI。</span></div>}
        </div>
        {source.config_fields.length > 0 && (
          <div className="provider-config">
            <div className="section-heading"><div><h2>连接配置</h2><p>密钥仅写入 Reverie 内核配置，不会回传到界面。</p></div><button type="button" className="primary-button small" onClick={() => saveProvider(source, patch)} disabled={!Object.keys(patch).length}>保存</button></div>
            <div className="form-grid">
              {source.config_fields.map((field) => (
                <label key={field.key}><span>{field.label}{field.optional && <small>可选</small>}</span><ProviderFieldControl field={field} value={valueFor(field)} configured={Boolean(source.config?.configured_secrets[field.key])} update={(key, value) => setPatch((current) => ({ ...current, [key]: value }))} /></label>
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
  const [tab, setTab] = useState<"general" | "appearance" | "conversation" | "models" | "about">("general");
  const items = state.settings.items.filter((item) => !item.key.startsWith("plugin_enabled:") && !["active_model_source", "active_model_index"].includes(item.key));
  const activeBackgroundUrl = effectiveBackgroundUrl(preferences);
  const activeBackgroundLabel = preferences.backgroundPreset === "custom"
    ? preferences.backgroundName || "导入图片"
    : BACKGROUND_OPTIONS.find((option) => option.id === preferences.backgroundPreset)?.label || "纯净界面";
  return (
    <div className="settings-page">
      <div className="settings-nav">
        <div><h1>设置</h1><p>Reverie Desktop</p></div>
        <button type="button" className={tab === "general" ? "active" : ""} onClick={() => setTab("general")}><SlidersHorizontal size={15} />通用</button>
        <button type="button" className={tab === "appearance" ? "active" : ""} onClick={() => setTab("appearance")}><Palette size={15} />外观</button>
        <button type="button" className={tab === "conversation" ? "active" : ""} onClick={() => setTab("conversation")}><MessageSquare size={15} />对话显示</button>
        <button type="button" className={tab === "models" ? "active" : ""} onClick={() => setTab("models")}><Brain size={15} />模型与提供商</button>
        <button type="button" className={tab === "about" ? "active" : ""} onClick={() => setTab("about")}><Info size={15} />关于</button>
      </div>
      <div className="settings-content">
        {tab === "general" && (
          <>
            <PageHeader icon={<SlidersHorizontal size={20} />} title="通用设置" description="这些设置由 CLI 内核持久化，TUI 和 GUI 会同步使用。" />
            {paths && <div className="core-data-card"><div className="core-data-heading"><Database size={18} /><div><strong>CLI 数据与历史</strong><p>GUI 会直接读取此目录中的配置、会话、检查点和插件状态。</p></div></div><code>{paths.coreAppRoot}</code><div><button type="button" className="secondary-button" onClick={() => void window.reverie.reveal(paths.coreAppRoot)}><FolderOpen size={14} />显示目录</button><button type="button" className="secondary-button" onClick={selectCoreData}><Folder size={14} />切换数据目录</button></div></div>}
            <div className="setting-list">
              {items.map((item) => <div className={`setting-row ${item.kind === "rules" ? "stacked" : ""}`} key={item.key}><div><strong>{item.name}</strong><p>{item.description}</p></div><SettingControl item={item} update={updateSetting} /></div>)}
            </div>
          </>
        )}
        {tab === "appearance" && (
          <>
            <PageHeader icon={<Palette size={20} />} title="外观" description="调整主题、强调色、阅读尺度与工作区背景；所有设置会立即预览。" />
            <section className="appearance-panel preference-section">
              <div className="appearance-copy">
                <div><h2>界面主题</h2><p>跟随系统会在 Windows 深色与浅色模式之间自动切换。</p></div>
                <span>当前：{THEME_OPTIONS.find((option) => option.id === theme)?.label}</span>
              </div>
              <div className="theme-grid">
                {THEME_OPTIONS.map(({ id, label, description, icon: Icon }) => (
                  <button type="button" key={id} className={`theme-card ${id === theme ? "active" : ""}`} aria-pressed={id === theme} onClick={() => setTheme(id)}>
                    <div className="theme-card-copy">
                      <span className="theme-card-icon"><Icon size={15} /></span>
                      <div><strong>{label}</strong><small>{description}</small></div>
                      {id === theme && <CheckCircle2 size={17} />}
                    </div>
                  </button>
                ))}
              </div>
            </section>
            <section className="preference-section">
              <div className="preference-heading"><div><h2>强调色</h2><p>用于焦点、选中状态、图标和技术活动。</p></div></div>
              <div className="accent-grid">
                {ACCENT_OPTIONS.map((option) => (
                  <button type="button" key={option.id} className={preferences.accent === option.id ? "active" : ""} aria-pressed={preferences.accent === option.id} onClick={() => updatePreferences({ accent: option.id })}>
                    <span style={{ backgroundColor: option.color }} /><strong>{option.label}</strong>{preferences.accent === option.id && <Check size={14} />}
                  </button>
                ))}
              </div>
            </section>
            <section className="preference-section">
              <div className="preference-heading"><div><h2>文字与阅读宽度</h2><p>同时调整导航、正文和技术轨迹的字号与回答行长。</p></div></div>
              <div className="preference-row">
                <div><Type size={17} /><span><strong>字体大小</strong><small>选择整体界面阅读尺度</small></span></div>
                <div className="segmented-control">
                  {FONT_SIZE_OPTIONS.map((option) => <button type="button" key={option.id} className={preferences.fontSize === option.id ? "active" : ""} onClick={() => updatePreferences({ fontSize: option.id })}>{option.label}</button>)}
                </div>
              </div>
              <div className="preference-row">
                <div><PanelRightOpen size={17} /><span><strong>回答宽度</strong><small>控制长回答和代码块占用的宽度</small></span></div>
                <div className="segmented-control">
                  {MESSAGE_WIDTH_OPTIONS.map((option) => <button type="button" key={option.id} className={preferences.messageWidth === option.id ? "active" : ""} onClick={() => updatePreferences({ messageWidth: option.id })}>{option.label}</button>)}
                </div>
              </div>
            </section>
            <section className="preference-section">
              <div className="preference-heading">
                <div><h2>工作区背景</h2><p>选择 Reverie 原创背景，或导入自己的图片；自定义图片会复制到便携版数据目录。</p></div>
                <div className="preference-actions">
                  {preferences.backgroundPreset === "custom" && preferences.backgroundUrl && <button type="button" className="secondary-button" onClick={clearBackground}>删除导入</button>}
                  <button type="button" className="primary-button" onClick={selectBackground}><ImagePlus size={14} />导入图片</button>
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
                      <span className="background-card-copy"><OptionIcon size={15} /><strong>{option.label}</strong><small>{option.description}</small></span>
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
                    <span className="background-card-copy"><ImagePlus size={15} /><strong>我的图片</strong><small>{preferences.backgroundName}</small></span>
                    {preferences.backgroundPreset === "custom" && <CheckCircle2 size={17} />}
                  </button>
                )}
              </div>
              <div className={`background-preview ${activeBackgroundUrl ? "has-image" : ""}`} style={activeBackgroundUrl ? { backgroundImage: `url("${activeBackgroundUrl}")` } : undefined}>
                {activeBackgroundUrl ? <span>{activeBackgroundLabel}</span> : <div><Image size={22} /><strong>纯净主题背景</strong><span>选择上方背景即可立即预览</span></div>}
              </div>
              <div className="range-grid">
                <label><span>照片强度 <strong>{Math.round(preferences.backgroundOpacity * 100)}%</strong></span><input type="range" min="0" max="1" step="0.01" value={preferences.backgroundOpacity} onChange={(event) => updatePreferences({ backgroundOpacity: Number(event.target.value) })} /></label>
                <label><span>模糊 <strong>{preferences.backgroundBlur}px</strong></span><input type="range" min="0" max="24" step="1" value={preferences.backgroundBlur} onChange={(event) => updatePreferences({ backgroundBlur: Number(event.target.value) })} /></label>
                <label><span>压暗 <strong>{Math.round(preferences.backgroundDim * 100)}%</strong></span><input type="range" min="0" max="0.8" step="0.01" value={preferences.backgroundDim} onChange={(event) => updatePreferences({ backgroundDim: Number(event.target.value) })} /></label>
              </div>
            </section>
          </>
        )}
        {tab === "conversation" && (
          <>
            <PageHeader icon={<MessageSquare size={20} />} title="对话显示" description="决定思考记录、模型调用、工具结果和实时活动在对话中如何呈现。" />
            <section className="preference-section conversation-presets">
              <div className="preference-heading"><div><h2>显示预设</h2><p>选择预设后仍可单独调整每一项。</p></div></div>
              <div className="preset-grid">
                <button type="button" className={!preferences.showReasoning && !preferences.showToolCalls && !preferences.showToolResults ? "active" : ""} onClick={() => updatePreferences({ showReasoning: false, showToolCalls: false, showToolResults: false, showLiveActivity: false })}><MessageSquare size={16} /><strong>纯净对话</strong><span>只显示用户与模型正文</span></button>
                <button type="button" className={!preferences.showReasoning && preferences.showToolCalls && !preferences.showToolResults ? "active" : ""} onClick={() => updatePreferences({ showReasoning: false, showToolCalls: true, showToolResults: false, showLiveActivity: true })}><Wrench size={16} /><strong>调用优先</strong><span>显示模型调用了什么</span></button>
                <button type="button" className={!preferences.showReasoning && !preferences.showToolCalls && preferences.showToolResults ? "active" : ""} onClick={() => updatePreferences({ showReasoning: false, showToolCalls: false, showToolResults: true, showLiveActivity: false })}><CheckCircle2 size={16} /><strong>结果优先</strong><span>只保留工具返回结果</span></button>
                <button type="button" className={preferences.showReasoning && preferences.showToolCalls && preferences.showToolResults ? "active" : ""} onClick={() => updatePreferences({ showReasoning: true, expandReasoning: true, showToolCalls: true, showToolResults: true, showLiveActivity: true })}><Brain size={16} /><strong>完整轨迹</strong><span>展开推理并显示全部技术细节</span></button>
              </div>
            </section>
            <section className="preference-section">
              <div className="preference-row"><div><Brain size={17} /><span><strong>推理记录</strong><small>显示模型返回并保存在会话中的思考内容</small></span></div><Toggle checked={preferences.showReasoning} onChange={(value) => updatePreferences({ showReasoning: value, ...(value ? { expandReasoning: true } : {}) })} /></div>
              <div className="preference-row"><div><ChevronDown size={17} /><span><strong>默认展开推理</strong><small>开启后直接显示推理正文，而不是只显示摘要栏</small></span></div><Toggle checked={preferences.expandReasoning} disabled={!preferences.showReasoning} onChange={(value) => updatePreferences({ expandReasoning: value })} /></div>
              <div className="preference-row"><div><Wrench size={17} /><span><strong>工具调用</strong><small>显示工具名称与调用参数</small></span></div><Toggle checked={preferences.showToolCalls} onChange={(value) => updatePreferences({ showToolCalls: value })} /></div>
              <div className="preference-row"><div><CheckCircle2 size={17} /><span><strong>工具结果</strong><small>显示工具实际返回的内容</small></span></div><Toggle checked={preferences.showToolResults} onChange={(value) => updatePreferences({ showToolResults: value })} /></div>
              <div className="preference-row"><div><ChevronDown size={17} /><span><strong>默认展开结果</strong><small>打开会话时直接展开工具输出</small></span></div><Toggle checked={preferences.expandToolResults} disabled={!preferences.showToolResults} onChange={(value) => updatePreferences({ expandToolResults: value })} /></div>
              <div className="preference-row"><div><Clock3 size={17} /><span><strong>实时活动</strong><small>运行期间显示进度、工具事件和审批状态</small></span></div><Toggle checked={preferences.showLiveActivity} onChange={(value) => updatePreferences({ showLiveActivity: value })} /></div>
            </section>
            <section className="conversation-display-preview">
              <div className="preview-title"><Eye size={15} /><span>当前呈现预览</span></div>
              {preferences.showReasoning && <div className="preview-trace reasoning"><Brain size={14} /><span>推理记录</span><small>{preferences.expandReasoning ? "直接展开正文" : "显示摘要栏"}</small></div>}
              {preferences.showToolCalls && <div className="preview-trace"><Wrench size={14} /><span>read_file</span><small>模型调用</small></div>}
              {preferences.showToolResults && <div className="preview-trace result"><CheckCircle2 size={14} /><span>read_file</span><small>工具结果</small></div>}
              {!preferences.showReasoning && !preferences.showToolCalls && !preferences.showToolResults && <p>技术轨迹已隐藏，对话中只显示正文。</p>}
            </section>
          </>
        )}
        {tab === "models" && (
          <>
            <PageHeader icon={<Brain size={20} />} title="模型与提供商" description="选择模型、配置凭据，并检查模型级思考与多模态能力。" />
            <ProviderSettings state={state} selectModel={selectModel} saveProvider={saveProvider} addStandard={addStandard} deleteStandard={deleteStandard} />
          </>
        )}
        {tab === "about" && (
          <>
            <PageHeader icon={<Info size={20} />} title="关于 Reverie" description="Electron 仅承载界面；所有 AI、工具和会话逻辑都由嵌入的 Reverie CLI exe 执行。" />
            <div className="about-card"><div className="about-mark"><img src={REVERIE_MARK_URL} alt="Reverie" /></div><div><h2>Reverie {state.core.version}</h2><p>Core Interface {state.core.interface_version} · {state.core.release_status}</p></div></div>
            <div className="path-list"><button type="button" onClick={() => void window.reverie.reveal(state.workspace.config_path)}><span>配置文件</span><code>{state.workspace.config_path}</code><FolderOpen size={14} /></button><button type="button" onClick={() => void window.reverie.reveal(state.workspace.project_data_dir)}><span>工作区数据</span><code>{state.workspace.project_data_dir}</code><FolderOpen size={14} /></button>{paths && <button type="button" onClick={() => void window.reverie.reveal(paths.kernelPath)}><span>CLI 内核</span><code>{paths.kernelPath}</code><FolderOpen size={14} /></button>}</div>
          </>
        )}
      </div>
    </div>
  );
}

function Inspector({ state, liveTurn, indexWorkspace }: { state: DesktopState; liveTurn: LiveTurn | null; indexWorkspace: () => void }) {
  const [tab, setTab] = useState<"context" | "activity">("context");
  const permission = state.settings.items.find((item) => item.key === "permission_level")?.value;
  const events = liveTurn?.events ?? [];
  const contextEngine = state.workspace.context_engine;
  const contextLabel = contextEngine?.indexing
    ? `索引中 ${Math.round(contextEngine.progress)}%`
    : contextEngine?.ready
      ? "自动检索已启用"
      : "正在按需预热";
  return (
    <aside className="inspector">
      <div className="inspector-tabs"><button type="button" className={tab === "context" ? "active" : ""} onClick={() => setTab("context")}>上下文</button><button type="button" className={tab === "activity" ? "active" : ""} onClick={() => setTab("activity")}>活动 {events.length > 0 && <span>{events.length}</span>}</button></div>
      {tab === "context" ? (
        <div className="inspector-content">
          <section><div className="inspector-heading"><span>工作区</span><button type="button" onClick={indexWorkspace} title="重新索引"><RefreshCw className={contextEngine?.indexing ? "spin" : ""} size={13} /></button></div><div className="context-card"><Folder size={15} /><div><strong>{state.workspace.project_name}</strong><span>{state.workspace.project_root}</span></div></div><div className="context-engine-card"><div><span className="context-engine-orbit"><Sparkles size={14} /></span><span><strong>Context Engine</strong><small>{contextLabel}</small></span></div><div className="context-engine-metrics"><span><strong>{contextEngine?.files ?? 0}</strong> 文件</span><span><strong>{contextEngine?.symbols ?? 0}</strong> 符号</span></div>{contextEngine?.indexing && <div className="context-progress"><span style={{ width: `${Math.max(3, contextEngine.progress)}%` }} /></div>}</div></section>
          <section><div className="inspector-heading"><span>运行时</span></div><div className="context-line"><span>模型</span><strong>{state.models.active_model?.display_name || "未配置"}</strong></div><div className="context-line"><span>Source</span><strong>{state.models.sources.find((item) => item.active)?.display_name}</strong></div><div className="context-line"><span>模式</span><strong>{state.workspace.mode}</strong></div><div className="context-line"><span>权限</span><strong>{String(permission ?? "workspace_write")}</strong></div></section>
          <section><div className="inspector-heading"><span>恢复</span></div><div className="context-line"><span>检查点</span><strong>{state.recovery.checkpoints.length}</strong></div><div className="context-line"><span>操作</span><strong>{String(state.recovery.summary.total_operations ?? state.recovery.operations.length)}</strong></div></section>
          <section><div className="inspector-heading"><span>快捷提示</span></div><div className="hint-card"><AtSign size={14} /><span><kbd>@</kbd> 会用 Context Engine 推荐当前任务最相关的文件。</span></div><div className="hint-card"><Paperclip size={14} /><span>回形针可选择任意文件，并安全复制到工作区附件区。</span></div><div className="hint-card"><Command size={14} /><span><kbd>Ctrl K</kbd> 打开完整命令目录。</span></div></section>
        </div>
      ) : (
        <div className="inspector-content activity-feed">{events.length ? events.map((event, index) => <ActivityItem key={index} event={event} />) : <div className="empty-panel compact"><Clock3 size={22} /><strong>暂无实时活动</strong><span>模型调用工具时会在这里显示。</span></div>}</div>
      )}
    </aside>
  );
}

function CommandPalette({ commands, close, choose }: { commands: CommandRecord[]; close: () => void; choose: (command: CommandRecord) => void }) {
  const [query, setQuery] = useState("");
  const filtered = commands.filter((item) => `${item.command} ${item.summary} ${item.section}`.toLowerCase().includes(query.toLowerCase())).slice(0, 30);
  useEffect(() => {
    const handler = (event: globalThis.KeyboardEvent) => { if (event.key === "Escape") close(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [close]);
  return (
    <div className="modal-backdrop" onMouseDown={close}>
      <div className="command-palette" onMouseDown={(event) => event.stopPropagation()}>
        <div className="command-search"><Search size={17} /><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索命令、工具和功能…" /><kbd>Esc</kbd></div>
        <div className="command-results">{filtered.map((item) => <button type="button" key={item.id} onClick={() => choose(item)}><div className="command-icon"><Command size={14} /></div><div><strong>{item.command}</strong><span>{item.summary}</span></div><small>{item.section}</small></button>)}</div>
        <div className="command-footer"><span><kbd>↵</kbd> 插入命令参考</span><span>完整功能可直接通过 GUI 页面或自然语言调用</span></div>
      </div>
    </div>
  );
}

function SessionSearch({ close, openSession }: { close: () => void; openSession: (id: string) => void }) {
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
          setResults((response.results as Array<Record<string, unknown>>) ?? []);
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
      <div className="command-palette session-search-modal" onMouseDown={(event) => event.stopPropagation()}>
        <div className="command-search"><Search size={17} /><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索所有会话内容…" /><button type="button" onClick={close}><X size={15} /></button></div>
        <div className="session-search-results">
          {searching && <div className="empty-row"><RefreshCw className="spin" size={14} />正在搜索</div>}
          {error && <div className="empty-row error"><AlertCircle size={14} />{error}</div>}
          {!searching && !error && results.map((result) => <button type="button" key={`${result.session_id}-${result.message_index}`} onClick={() => { openSession(String(result.session_id)); close(); }}><MessageSquare size={14} /><div><strong>{String(result.session_name)}</strong><span>{String(result.text)}</span></div><small>{Number(result.message_index) < 0 ? "标题" : `#${Number(result.message_index) + 1}`}</small></button>)}
          {!searching && !error && completedQuery === query.trim() && results.length === 0 && <div className="empty-row">没有匹配的会话内容</div>}
        </div>
      </div>
    </div>
  );
}

function RenameSessionModal({ session, close, save }: { session: { id: string; name: string }; close: () => void; save: (name: string) => void }) {
  const [name, setName] = useState(session.name);
  const valid = Boolean(name.trim());
  return (
    <div className="modal-backdrop" onMouseDown={close}>
      <form className="form-modal rename-session-modal" onMouseDown={(event) => event.stopPropagation()} onSubmit={(event) => { event.preventDefault(); if (valid) save(name.trim()); }}>
        <div className="form-modal-header"><div><h2>重命名会话</h2><p>使用一个容易辨认的标题，历史记录会立即同步更新。</p></div><IconButton label="关闭" onClick={close}><X size={16} /></IconButton></div>
        <div className="form-grid single"><label><span>会话标题</span><input autoFocus value={name} maxLength={120} onChange={(event) => setName(event.target.value)} /></label></div>
        <div className="form-modal-footer"><button type="button" className="secondary-button" onClick={close}>取消</button><button type="submit" className="primary-button" disabled={!valid}>保存</button></div>
      </form>
    </div>
  );
}

function StandardModelModal({ close, save }: { close: () => void; save: (model: Record<string, unknown>) => void }) {
  const [model, setModel] = useState<Record<string, unknown>>({ provider: "openai-chat", supports_vision: false, max_context_tokens: 128000 });
  const update = (key: string, value: unknown) => setModel((current) => ({ ...current, [key]: value }));
  const valid = Boolean(model.model && model.model_display_name && model.base_url);
  return (
    <div className="modal-backdrop" onMouseDown={close}>
      <form className="form-modal" onMouseDown={(event) => event.stopPropagation()} onSubmit={(event) => { event.preventDefault(); if (valid) save(model); }}>
        <div className="form-modal-header"><div><h2>添加标准模型</h2><p>该模型会同时出现在 TUI、命令行和 GUI 中。</p></div><IconButton label="关闭" onClick={close}><X size={16} /></IconButton></div>
        <div className="form-grid single"><label><span>模型 ID</span><input autoFocus value={String(model.model ?? "")} onChange={(event) => update("model", event.target.value)} placeholder="例如 gpt-5.4" /></label><label><span>显示名称</span><input value={String(model.model_display_name ?? "")} onChange={(event) => update("model_display_name", event.target.value)} placeholder="例如 GPT-5.4" /></label><label><span>Provider</span><select value={String(model.provider)} onChange={(event) => update("provider", event.target.value)}><option value="openai-chat">OpenAI Chat Completions</option><option value="openai-responses">OpenAI Responses</option><option value="anthropic">Anthropic</option><option value="request">Generic Request</option><option value="curl">cURL</option></select></label><label><span>Base URL</span><input value={String(model.base_url ?? "")} onChange={(event) => update("base_url", event.target.value)} placeholder="https://api.example.com/v1" /></label><label><span>API Key</span><input type="password" value={String(model.api_key ?? "")} onChange={(event) => update("api_key", event.target.value)} /></label><label><span>上下文长度</span><input type="number" value={Number(model.max_context_tokens)} onChange={(event) => update("max_context_tokens", Number(event.target.value))} /></label><label className="inline-toggle"><span>支持视觉</span><Toggle checked={Boolean(model.supports_vision)} onChange={(value) => update("supports_vision", value)} /></label></div>
        <div className="form-modal-footer"><button type="button" className="secondary-button" onClick={close}>取消</button><button type="submit" className="primary-button" disabled={!valid}>添加模型</button></div>
      </form>
    </div>
  );
}

function ConfirmModal({ title, message, confirmLabel, danger = false, close, confirm }: { title: string; message: string; confirmLabel: string; danger?: boolean; close: () => void; confirm: () => void }) {
  return <div className="modal-backdrop" onMouseDown={close}><div className="confirm-modal" onMouseDown={(event) => event.stopPropagation()}><div className={`confirm-icon ${danger ? "danger" : ""}`}>{danger ? <AlertCircle size={20} /> : <Info size={20} />}</div><h2>{title}</h2><p>{message}</p><div><button type="button" className="secondary-button" onClick={close}>取消</button><button type="button" className={danger ? "danger-button" : "primary-button"} onClick={confirm}>{confirmLabel}</button></div></div></div>;
}

function ApprovalModal({ approval, resolve }: { approval: Record<string, unknown>; resolve: (decision: "once" | "session" | "deny") => void }) {
  return (
    <div className="modal-backdrop">
      <div className="approval-modal">
        <div className="approval-header"><div className="confirm-icon"><ShieldCheck size={20} /></div><div><h2>工具请求更高权限</h2><p>Reverie 内核暂停执行，等待你的决定。</p></div></div>
        <div className="approval-tool"><Wrench size={15} /><strong>{String(approval.tool ?? "tool")}</strong></div>
        <p className="approval-message">{String(approval.message ?? "此工具超出当前权限级别。")}</p>
        <pre>{JSON.stringify(approval.arguments ?? {}, null, 2)}</pre>
        <div className="approval-actions"><button type="button" className="secondary-button" onClick={() => resolve("deny")}>拒绝</button><button type="button" className="secondary-button" onClick={() => resolve("once")}>仅本次允许</button><button type="button" className="primary-button" onClick={() => resolve("session")}>本会话允许</button></div>
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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() =>
    normalizeSidebarCollapsed(localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY)),
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
  const toastId = useRef(0);
  const sessionRequestSequence = useRef(0);
  const initializeSequence = useRef(0);
  const themeRequestSequence = useRef(0);
  const uiPreferenceRequestSequence = useRef(0);
  const drafts = useRef<Record<string, string>>({});

  useEffect(() => {
    applyTheme(theme, systemDark);
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [systemDark, theme]);

  useEffect(() => {
    applyUiPreferences(uiPreferences);
  }, [uiPreferences]);

  useEffect(() => {
    localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(sidebarCollapsed));
  }, [sidebarCollapsed]);

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
    void window.reverie.setUiPreferences(patch as unknown as CoreResponse).then((preferences) => {
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
        toast("工作区背景已更新", "success");
      }
    } catch (error) {
      toast(error instanceof Error ? error.message : String(error), "error");
    }
  }, [toast]);

  const clearBackground = useCallback(async () => {
    try {
      const preferences = await window.reverie.clearBackground();
      setUiPreferences(normalizeUiPreferences(preferences));
      toast("工作区背景已清除", "success");
    } catch (error) {
      toast(error instanceof Error ? error.message : String(error), "error");
    }
  }, [toast]);

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
      let nextState = response.state as unknown as DesktopState;
      let nextSession: SessionState | null = null;
      const currentId = nextState.sessions.current_session_id || nextState.sessions.items[0]?.id;
      if (currentId) {
        const sessionResponse = await window.reverie.request("getSession", { sessionId: currentId });
        if (requestSequence !== initializeSequence.current) return;
        nextSession = sessionResponse.session as unknown as SessionState;
        nextState = { ...nextState, sessions: sessionResponse.sessions as unknown as DesktopState["sessions"] };
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
        const nextContext = response.context_engine as DesktopState["workspace"]["context_engine"];
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

  useEffect(() => window.reverie.onEvent((message) => {
    const event = asRecord(message.event);
    if (String(event.type ?? "") === "approval.request") setApproval(event);
    setLiveTurn((current) => {
      if (!current) return current;
      const type = String(event.type ?? "");
      if (type === "assistant.delta") return { ...current, assistantText: current.assistantText + String(event.text ?? "") };
      if (type === "reasoning.delta") return { ...current, reasoningText: current.reasoningText + String(event.text ?? "") };
      if (type === "ui.event") return { ...current, events: [...current.events, asRecord(event.event)] };
      if (type === "run.auto_followup") return { ...current, events: [...current.events, event] };
      if (type === "approval.request") return { ...current, events: [...current.events, event] };
      return current;
    });
  }), []);

  useEffect(() => {
    const shortcuts = (event: globalThis.KeyboardEvent) => {
      const modifier = event.ctrlKey || event.metaKey;
      if (modifier && event.key.toLowerCase() === "k") { event.preventDefault(); setCommandOpen(true); }
      if (modifier && event.key.toLowerCase() === "n") { event.preventDefault(); void createSession(); }
      if (modifier && event.key.toLowerCase() === "f") { event.preventDefault(); setSessionSearchOpen(true); }
      if (event.key === "Escape") {
        setModelPickerOpen(false);
        setCommandOpen(false);
        setSessionSearchOpen(false);
        setStandardModelOpen(false);
        setRenameSessionTarget(null);
        setConfirmation(null);
        setMentionItems([]);
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
      const nextSession = response.session as unknown as SessionState;
      setSession(nextSession);
      setState((current) => current ? { ...current, sessions: response.sessions as unknown as DesktopState["sessions"] } : current);
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
      const nextSession = response.session as unknown as SessionState;
      setSession(nextSession);
      setState((current) => current ? { ...current, sessions: response.sessions as unknown as DesktopState["sessions"] } : current);
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

  const sendPrompt = useCallback(async () => {
    const text = prompt.trim();
    if (!text || running || sessionBusy || !state) return;
    setPrompt("");
    setMentionItems([]);
    setMentionOpen(false);
    setRunning(true);
    setLiveTurn({ userText: text, assistantText: "", reasoningText: "", events: [], error: "", startedAt: Date.now() });
    try {
      let activeSession = session;
      if (!activeSession) {
        const created = await window.reverie.request("createSession", {});
        activeSession = created.session as unknown as SessionState;
        setSession(activeSession);
        setState((current) => current ? { ...current, sessions: created.sessions as unknown as DesktopState["sessions"] } : current);
      }
      drafts.current[activeSession.id] = "";
      const response = await window.reverie.request("runPrompt", {
        prompt: text,
        sessionId: activeSession.id,
        mode: state.workspace.mode,
        stream: true,
      });
      const result = response.result as unknown as PromptResult;
      setLiveTurn((current) => current ? {
        ...current,
        assistantText: result.output_text || current.assistantText,
        reasoningText: result.thinking_text || current.reasoningText,
        error: result.error,
      } : current);
      setState((current) => current ? {
        ...current,
        sessions: response.sessions as unknown as DesktopState["sessions"],
        recovery: response.recovery as unknown as RecoveryState,
      } : current);
      const refreshed = await window.reverie.request("getSession", { sessionId: result.session_id || activeSession.id });
      setSession(refreshed.session as unknown as SessionState);
      setState((current) => current ? { ...current, sessions: refreshed.sessions as unknown as DesktopState["sessions"] } : current);
      setLiveTurn(null);
      setAttachments([]);
      if (!result.success) toast(result.error || "请求失败", "error");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setLiveTurn((current) => current ? { ...current, error: message } : current);
      if (!message.includes("cancel")) toast(message, "error");
    } finally {
      setRunning(false);
    }
  }, [prompt, running, session, sessionBusy, state, toast]);

  const cancelPrompt = useCallback(async () => {
    const retryText = liveTurn?.userText ?? "";
    try {
      await window.reverie.cancel();
      if (session) {
        const refreshed = await window.reverie.request("getSession", { sessionId: session.id });
        setSession(refreshed.session as unknown as SessionState);
        setState((current) => current ? { ...current, sessions: refreshed.sessions as unknown as DesktopState["sessions"] } : current);
      }
      setPrompt((current) => current || retryText);
      setLiveTurn(null);
      setApproval(null);
      toast("已停止当前任务，提示已保留", "info");
    } catch (error) {
      toast(error instanceof Error ? error.message : String(error), "error");
    } finally {
      setRunning(false);
    }
  }, [liveTurn?.userText, session, toast]);

  const renameSession = useCallback(async (name: string) => {
    if (!renameSessionTarget || running || sessionBusy) return;
    try {
      const response = await window.reverie.request("renameSession", { sessionId: renameSessionTarget.id, name });
      const activeSession = (response.session as unknown as SessionState | null) ?? null;
      if (activeSession) setSession(activeSession);
      setState((current) => current ? { ...current, sessions: response.sessions as unknown as DesktopState["sessions"] } : current);
      setRenameSessionTarget(null);
      toast("会话标题已更新", "success");
    } catch (error) {
      toast(error instanceof Error ? error.message : String(error), "error");
    }
  }, [renameSessionTarget, running, sessionBusy, toast]);

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
    toast(archived ? "会话已移出归档" : "会话已归档", "success");
  }, [state, toast, uiPreferences.archivedSessions, updateUiPreferences]);

  const forkActiveSession = useCallback(async () => {
    if (!session || running || sessionBusy) return;
    drafts.current[session.id] = prompt;
    const requestSequence = ++sessionRequestSequence.current;
    setSessionBusy(true);
    try {
      const response = await window.reverie.request("forkSession", { sessionId: session.id, messageCount: session.messages.length });
      if (requestSequence !== sessionRequestSequence.current) return;
      const forked = response.session as unknown as SessionState;
      setSession(forked);
      setState((current) => current ? { ...current, sessions: response.sessions as unknown as DesktopState["sessions"] } : current);
      setPrompt("");
      setLiveTurn(null);
      setView("chat");
      toast("已创建独立会话分支", "success");
    } catch (error) {
      if (requestSequence === sessionRequestSequence.current) toast(error instanceof Error ? error.message : String(error), "error");
    } finally {
      if (requestSequence === sessionRequestSequence.current) setSessionBusy(false);
    }
  }, [prompt, running, session, sessionBusy, toast]);

  const rewindActiveSession = useCallback(() => {
    if (!session || running || sessionBusy) return;
    const messageCount = previousTurnBoundary(session.messages);
    if (messageCount === null) return;
    setConfirmation({
      title: "回退上一轮对话？",
      message: "上一轮用户消息、回答及工具活动会从当前会话移除；完整记录仍由内核归档，可通过恢复功能找回。",
      label: "确认回退",
      danger: true,
      action: () => { void (async () => {
        setSessionBusy(true);
        try {
          const response = await window.reverie.request("rewindSession", { sessionId: session.id, messageCount, confirmed: true });
          setSession(response.session as unknown as SessionState);
          setState((current) => current ? { ...current, sessions: response.sessions as unknown as DesktopState["sessions"] } : current);
          setLiveTurn(null);
          toast("已回退上一轮对话", "success");
        } catch (error) {
          toast(error instanceof Error ? error.message : String(error), "error");
        } finally {
          setSessionBusy(false);
        }
      })(); },
    });
  }, [running, session, sessionBusy, toast]);

  const deleteSession = useCallback((target: { id: string; name: string }) => {
    if (running || sessionBusy) return;
    setConfirmation({
      title: "删除这个会话？",
      message: `“${target.name}”的历史记录将被永久删除；项目文件不会受到影响。`,
      label: "删除会话",
      danger: true,
      action: () => { void (async () => {
        setSessionBusy(true);
        try {
          const response = await window.reverie.request("deleteSession", { sessionId: target.id, confirmed: true });
          delete drafts.current[target.id];
          const nextSession = (response.session as unknown as SessionState | null) ?? null;
          setSession(nextSession);
          setState((current) => current ? { ...current, sessions: response.sessions as unknown as DesktopState["sessions"] } : current);
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
          toast("会话已删除", "success");
        } catch (error) {
          toast(error instanceof Error ? error.message : String(error), "error");
        } finally {
          setSessionBusy(false);
        }
      })(); },
    });
  }, [running, sessionBusy, state, toast, uiPreferences.archivedSessions, updateUiPreferences]);

  const deleteArchivedSessions = useCallback((targets: SessionInfo[]) => {
    if (running || sessionBusy || !state || targets.length === 0) return;
    const projectRoot = state.workspace.project_root;
    const targetIds = [...new Set(targets.map((target) => target.id).filter(Boolean))];
    if (targetIds.length === 0) return;
    setConfirmation({
      title: "清空全部归档会话？",
      message: `归档文件夹中的 ${targetIds.length} 条对话记录将被永久删除；项目文件不会受到影响。`,
      label: "清空归档",
      danger: true,
      action: () => { void (async () => {
        setSessionBusy(true);
        try {
          const response = await window.reverie.request("deleteSessions", { sessionIds: targetIds, confirmed: true });
          const deletedIds = Array.isArray(response.deleted_session_ids)
            ? response.deleted_session_ids.map((value) => String(value))
            : targetIds;
          deletedIds.forEach((sessionId) => { delete drafts.current[sessionId]; });
          const nextSession = (response.session as unknown as SessionState | null) ?? null;
          setSession(nextSession);
          setState((current) => current ? { ...current, sessions: response.sessions as unknown as DesktopState["sessions"] } : current);
          setPrompt(nextSession ? drafts.current[nextSession.id] ?? "" : "");
          setLiveTurn(null);
          updateUiPreferences({
            archivedSessions: {
              ...uiPreferences.archivedSessions,
              [projectRoot]: [],
            },
          });
          toast(`已删除 ${deletedIds.length} 条归档会话`, "success");
        } catch (error) {
          toast(error instanceof Error ? error.message : String(error), "error");
        } finally {
          setSessionBusy(false);
        }
      })(); },
    });
  }, [running, sessionBusy, state, toast, uiPreferences.archivedSessions, updateUiPreferences]);

  const resolveApproval = useCallback(async (decision: "once" | "session" | "deny") => {
    if (!approval) return;
    try {
      await window.reverie.request("resolveApproval", { approvalId: approval.approval_id, decision });
      setApproval(null);
      toast(decision === "deny" ? "已拒绝工具执行" : "权限已授予", decision === "deny" ? "info" : "success");
    } catch (error) {
      setApproval(null);
      toast(error instanceof Error ? error.message : String(error), "error");
    }
  }, [approval, toast]);

  const selectModel = useCallback(async (source: ModelSource, model: ModelRecord) => {
    try {
      const reasoning = model.reasoning.options.some((option) => option.id === model.reasoning.value)
        ? model.reasoning.value
        : model.reasoning.options[0]?.id;
      const response = await window.reverie.request("selectModel", { source: source.id, modelId: model.id, ...(reasoning ? { reasoning } : {}) });
      setState((current) => current ? { ...current, models: response.models as unknown as DesktopState["models"], workspace: response.workspace as unknown as DesktopState["workspace"] } : current);
      setModelPickerOpen(false);
      toast(`已切换到 ${model.display_name}`, "success");
    } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); }
  }, [toast]);

  const selectReasoning = useCallback(async (reasoning: string) => {
    if (!state) return;
    const source = state.models.sources.find((item) => item.active);
    if (!source) return;
    try {
      const response = await window.reverie.request("selectModel", { source: source.id, modelId: source.selected_model_id, reasoning });
      setState((current) => current ? { ...current, models: response.models as unknown as DesktopState["models"], workspace: response.workspace as unknown as DesktopState["workspace"] } : current);
      toast("思考设置已更新", "success");
    } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); }
  }, [state, toast]);

  const updateSetting = useCallback(async (key: string, value: unknown) => {
    try {
      const response = await window.reverie.request("setSetting", { key, value });
      if (response.success === false) throw new Error(String(response.message ?? "设置未保存"));
      const settings = response.settings as unknown as DesktopState["settings"];
      setState((current) => current ? { ...current, settings, workspace: key === "mode" ? { ...current.workspace, mode: String(value) } : current.workspace } : current);
      toast("设置已保存", "success");
    } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); }
  }, [toast]);

  const saveProvider = useCallback(async (source: ModelSource, patch: Record<string, unknown>) => {
    try {
      const response = await window.reverie.request("setProviderConfig", { source: source.id, patch });
      setState((current) => current ? { ...current, models: response.models as unknown as DesktopState["models"], workspace: response.workspace as unknown as DesktopState["workspace"] } : current);
      toast(`${source.display_name} 配置已保存`, "success");
    } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); }
  }, [toast]);

  const addStandard = useCallback(async (model: Record<string, unknown>) => {
    try {
      const response = await window.reverie.request("addStandardModel", { model });
      setState((current) => current ? { ...current, models: response.models as unknown as DesktopState["models"], workspace: response.workspace as unknown as DesktopState["workspace"] } : current);
      setStandardModelOpen(false);
      toast("标准模型已添加", "success");
    } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); }
  }, [toast]);

  const deleteStandard = useCallback((index: number) => {
    setConfirmation({ title: "删除标准模型？", message: "这会从 Reverie 内核配置中移除该模型，但不会删除任何远端数据。", label: "删除模型", danger: true, action: () => { void (async () => { try { const response = await window.reverie.request("deleteStandardModel", { index }); setState((current) => current ? { ...current, models: response.models as unknown as DesktopState["models"], workspace: response.workspace as unknown as DesktopState["workspace"] } : current); toast("模型已删除", "success"); } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); } })(); } });
  }, [toast]);

  const updatePlugin = useCallback(async (action: "setPluginEnabled" | "setPluginTrust", plugin: PluginRecord, value: boolean) => {
    try {
      const response = await window.reverie.request(action, { pluginId: plugin.id, [action === "setPluginEnabled" ? "enabled" : "trusted"]: value });
      const plugins = response.plugins as unknown as DesktopState["plugins"];
      setState((current) => current ? { ...current, plugins, settings: (response.settings as unknown as DesktopState["settings"]) ?? current.settings } : current);
      toast(`${plugin.name} 已更新`, "success");
    } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); }
  }, [toast]);

  const refreshPlugins = useCallback(async () => {
    try {
      const response = await window.reverie.request("refreshPlugins", {});
      setState((current) => current ? { ...current, plugins: response.plugins as unknown as DesktopState["plugins"] } : current);
      toast("插件目录已刷新", "success");
    } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); }
  }, [toast]);

  const indexWorkspace = useCallback(async () => {
    toast("工作区索引已开始", "info");
    try {
      const response = await window.reverie.request("indexWorkspace", {});
      setState((current) => current ? { ...current, workspace: response.workspace as unknown as DesktopState["workspace"] } : current);
      toast("工作区索引完成", "success");
    } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); }
  }, [toast]);

  const rollback = useCallback((checkpointId: string) => {
    setConfirmation({ title: "恢复到这个检查点？", message: "Reverie 将恢复会话消息，并回退该检查点之后被操作历史跟踪的文件。建议先提交当前改动。", label: "确认恢复", danger: true, action: () => { void (async () => { try { const response = await window.reverie.request("rollbackCheckpoint", { checkpointId, confirmed: true }); setState((current) => current ? { ...current, recovery: response.recovery as unknown as RecoveryState } : current); if (session) await openSession(session.id); toast("检查点恢复完成", "success"); } catch (error) { toast(error instanceof Error ? error.message : String(error), "error"); } })(); } });
  }, [openSession, session, toast]);

  const requestMentions = useCallback(async () => {
    if (mentionOpen) {
      setMentionOpen(false);
      return;
    }
    setMentionOpen(true);
    setMentionLoading(true);
    setMentionItems([]);
    try {
      const response = await window.reverie.request("workspaceMentions", { query: prompt.trim(), limit: 24 });
      setMentionItems((response.items as Array<Record<string, unknown>>) ?? []);
      const nextContext = response.context_engine as DesktopState["workspace"]["context_engine"];
      setState((current) => current ? {
        ...current,
        workspace: { ...current.workspace, index_ready: Boolean(nextContext?.ready), context_engine: nextContext },
      } : current);
    } catch (error) {
      setMentionOpen(false);
      toast(error instanceof Error ? error.message : String(error), "error");
    } finally {
      setMentionLoading(false);
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
      toast(`已附加 ${attachment.name}`, "success");
    } catch (error) {
      toast(error instanceof Error ? error.message : String(error), "error");
    }
  }, [toast]);

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
      title: `从 Reverie 删除“${target.name}”？`,
      message: "该项目的全部会话、完整转录、记忆、检查点、Context Engine 缓存和已导入附件将永久删除。源码与普通项目文件不会被删除。",
      label: "删除项目与记录",
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
          toast(`项目记录已删除（${result.deletedSessions} 个会话）`, "success");
        } catch (error) {
          toast(error instanceof Error ? error.message : String(error), "error");
        } finally {
          setSessionBusy(false);
        }
      })(); },
    });
  }, [initialize, running, sessionBusy, toast]);

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
    const navigation: Record<string, ViewId> = { "/model": "settings", "/settings": "settings", "/setting": "settings", "/tools": "tools", "/plugins": "plugins", "/checkpoints": "recovery", "/operations": "recovery", "/rollback": "recovery" };
    const target = navigation[command.command];
    if (target) { setView(target); return; }
    setView("chat");
    setPrompt(command.examples?.[0] || command.command);
    toast(`${command.command} 已插入；可按命令提示改写，或用自然语言要求 Reverie 执行。`, "info");
  }, [toast]);

  const activeSessionId = session?.id ?? state?.sessions.current_session_id ?? "";
  const page = useMemo(() => {
    if (!state) return null;
    if (view === "tools") return <ToolsView mode={state.workspace.mode} />;
    if (view === "plugins") return <PluginsView plugins={state.plugins.records} updatePlugin={updatePlugin} refresh={refreshPlugins} />;
    if (view === "recovery") return <RecoveryView recovery={state.recovery} rollback={rollback} />;
    if (view === "settings") return <SettingsView state={state} updateSetting={updateSetting} selectModel={selectModel} saveProvider={saveProvider} addStandard={() => setStandardModelOpen(true)} deleteStandard={deleteStandard} paths={desktopPaths} selectCoreData={() => void selectCoreData()} theme={theme} setTheme={changeTheme} preferences={uiPreferences} updatePreferences={updateUiPreferences} selectBackground={() => void selectBackground()} clearBackground={() => void clearBackground()} />;
    return <ChatView session={session} liveTurn={liveTurn} running={running} prompt={prompt} setPrompt={setPrompt} send={() => void sendPrompt()} cancel={() => void cancelPrompt()} mentionItems={mentionItems} mentionOpen={mentionOpen} mentionLoading={mentionLoading} requestMentions={() => void requestMentions()} chooseMention={(value) => { setPrompt((current) => `${current}${current && !current.endsWith(" ") ? " " : ""}${value} `); setMentionItems([]); setMentionOpen(false); }} attachments={attachments} selectAttachment={() => void selectAttachment()} removeAttachment={removeAttachment} modelName={state.models.active_model?.display_name ?? "Reverie"} sessionBusy={sessionBusy} renameSession={() => { if (session) setRenameSessionTarget({ id: session.id, name: session.name }); }} forkSession={() => void forkActiveSession()} rewindSession={rewindActiveSession} deleteSession={() => { if (session) deleteSession(session); }} preferences={uiPreferences} updatePreferences={updateUiPreferences} />;
  }, [state, view, updatePlugin, refreshPlugins, rollback, updateSetting, selectModel, saveProvider, deleteStandard, desktopPaths, selectCoreData, theme, changeTheme, uiPreferences, updateUiPreferences, selectBackground, clearBackground, session, liveTurn, running, prompt, mentionItems, mentionOpen, mentionLoading, attachments, selectAttachment, removeAttachment, sendPrompt, cancelPrompt, requestMentions, sessionBusy, forkActiveSession, rewindActiveSession, deleteSession]);

  if (bootError) return <ErrorScreen error={bootError} retry={() => void initialize()} />;
  if (!state) return <LoadingScreen />;

  return (
    <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""} ${inspectorOpen ? "with-inspector" : ""}`}>
      <Sidebar state={state} view={view} setView={setView} activeSessionId={activeSessionId} openSession={(id) => void openSession(id)} newSession={() => void createSession()} sessionBusy={sessionBusy} selectWorkspace={() => void selectWorkspace()} switchWorkspace={(projectRoot) => void switchWorkspace(projectRoot)} openSearch={() => setSessionSearchOpen(true)} preferences={uiPreferences} renameSession={(target) => setRenameSessionTarget({ id: target.id, name: target.name })} toggleArchive={toggleSessionArchive} deleteSession={deleteSession} deleteArchivedSessions={deleteArchivedSessions} deleteProject={deleteProject} />
      <main className="main-area">
        <Topbar state={state} sidebarCollapsed={sidebarCollapsed} toggleSidebar={() => setSidebarCollapsed((value) => !value)} openModelPicker={() => setModelPickerOpen(true)} selectReasoning={(value) => void selectReasoning(value)} setMode={(mode) => void updateSetting("mode", mode)} inspectorOpen={inspectorOpen} toggleInspector={() => setInspectorOpen((value) => !value)} openCommands={() => setCommandOpen(true)} theme={theme} setTheme={changeTheme} />
        <div className="content-area">{page}</div>
      </main>
      {inspectorOpen && <Inspector state={state} liveTurn={liveTurn} indexWorkspace={() => void indexWorkspace()} />}
      {modelPickerOpen && <ModelPicker state={state} onSelect={(source, model) => void selectModel(source, model)} close={() => setModelPickerOpen(false)} />}
      {commandOpen && <CommandPalette commands={state.commands.items} close={() => setCommandOpen(false)} choose={chooseCommand} />}
      {sessionSearchOpen && <SessionSearch close={() => setSessionSearchOpen(false)} openSession={(id) => void openSession(id)} />}
      {renameSessionTarget && <RenameSessionModal session={renameSessionTarget} close={() => setRenameSessionTarget(null)} save={(name) => void renameSession(name)} />}
      {standardModelOpen && <StandardModelModal close={() => setStandardModelOpen(false)} save={(model) => void addStandard(model)} />}
      {approval && <ApprovalModal approval={approval} resolve={(decision) => void resolveApproval(decision)} />}
      {confirmation && <ConfirmModal title={confirmation.title} message={confirmation.message} confirmLabel={confirmation.label} danger={confirmation.danger} close={() => setConfirmation(null)} confirm={() => { const action = confirmation.action; setConfirmation(null); action(); }} />}
      <Toasts items={toasts} />
    </div>
  );
}
