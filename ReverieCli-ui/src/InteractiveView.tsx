import { memo, useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, AppWindow, ChevronDown, ChevronUp, RefreshCw } from "lucide-react";

import { useI18n } from "./i18n";
import type { ResolvedViewRef } from "./types";
import { ViewChannel, VIEW_PROTOCOL_VERSION } from "./view-bridge";
import { ViewInteractionController, type CoreRequestFn } from "./view-interaction";
import { McpAppLifecycle } from "./mcp-app-lifecycle";
import { ViewDisplayControls } from "./ConversationDisplay";
import { VIEW_DISPLAY_MODES, readViewPresentation, saveViewPresentation, useViewPresentation, type ViewContent, type ViewDisplayMode } from "./view-presentation-context";
import { viewHostContext } from "./view-host-context";

/** The highest view schema this client knows how to paint. A view minted by a
 *  newer Reverie degrades to its summary text rather than rendering a frame it
 *  cannot be trusted to display. */
const SUPPORTED_VIEW_SCHEMA = 1;

/** A fresh per-instance capability. The frame only ever learns it from the
 *  `ui/initialize` reply, so a message that presents the wrong token (or none)
 *  is rejected by the ViewChannel before it reaches the controller. */
function newCapability(): string {
  return globalThis.crypto.randomUUID();
}

type Resolution =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; view: ResolvedViewRef }
  | { status: "error"; message: string };

/**
 * Interactive-view surface. It resolves a kernel-minted opaque handle through
 * the `getView` core action and paints the resolved bytes inside a scripts-only
 * sandboxed iframe.
 *
 * P2 interactivity: once the frame is painted, {@link ViewChannel} +
 * {@link ViewInteractionController} are mounted against its window. The frame
 * speaks JSON-RPC over `postMessage`; the host issues a per-instance capability
 * ONLY in the `ui/initialize` reply, binds every later message to that frame +
 * capability + live revision, funnels `tools/call` into the gated
 * `callViewTool` core action, maps `reverie/view-state`/`ui/update-model-context`
 * to their core actions, and stages `ui/message` for a trusted host confirmation.
 *
 * Security seam: the HTML never enters the renderer DOM. The frame loads an
 * opaque `reverie-view:` URL (never `srcdoc`/raw HTML), under `allow-scripts`
 * WITHOUT `allow-same-origin` so it holds an opaque origin and cannot reach the
 * host document, cookies, or storage. A handle the kernel never minted fails in
 * `getView` (the ViewStore re-checks it), so a forged event degrades to an error
 * card, never arbitrary HTML. The channel is revoked when the view is torn down
 * or its revision/session changes, so a late reply is never posted into a dead
 * frame and an old frame cannot drive the new one.
 */
export const InteractiveView = memo(function InteractiveView({ segment, onFollowUp }: ViewContent) {
  const presentation = useViewPresentation();
  const anchor = useRef<HTMLDivElement>(null);
  const owner = useRef({});
  const [errorKey] = useState(() => crypto.randomUUID());
  const key = `${presentation.scope}:${segment.sessionId}:${segment.viewId || errorKey}:${segment.revision}`;
  useLayoutEffect(() => {
    if (!anchor.current || !presentation.mountView) return;
    presentation.mountView(key, owner.current, anchor.current, { segment, onFollowUp });
    return () => presentation.unmountView?.(key, owner.current);
  }, [key, segment, onFollowUp, presentation.mountView, presentation.unmountView]);
  return presentation.mountView ? <div className="interactive-view-mount" ref={anchor} /> : <InteractiveViewRuntime segment={segment} onFollowUp={onFollowUp} />;
});

const alwaysHosted = () => true;
export const InteractiveViewRuntime = memo(function InteractiveViewRuntime({ segment, onFollowUp, isHosted = alwaysHosted }: ViewContent & { isHosted?: () => boolean }) {
  const { t, language } = useI18n();
  const translate = useRef(t); translate.current = t;
  const [resolution, setResolution] = useState<Resolution>({ status: "idle" });
  const [proposal, setProposal] = useState("");
  const [toolBusy, setToolBusy] = useState(false);
  const [summaryExpanded, setSummaryExpanded] = useState(false);
  const summaryId = useId();
  const presentation = useViewPresentation();
  const requestKey = `${presentation.scope}:${segment.sessionId}:${segment.viewId}:${segment.revision}`;
  const metricKey = `riu-view:${segment.sessionId}:${segment.viewId}:${segment.revision}`;
  const [expanded, setExpanded] = useState(() => readViewPresentation(requestKey, presentation.persisted?.[requestKey]).expanded !== false);
  const [nonce, setNonce] = useState(0);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const teardownRef = useRef<(() => Promise<void>) | null>(null);
  const frameLoadRef = useRef<(() => void) | null>(null);
  const contextChangedRef = useRef<(() => void) | null>(null);
  const anchor = useRef<HTMLDivElement>(null);
  const [surface] = useState(() => document.createElement("div"));
  const [visible, setVisible] = useState(() => typeof IntersectionObserver === "undefined");
  const [focused, setFocused] = useState(false);
  const [reservedHeight, setReservedHeight] = useState(0);

  const kernelError = segment.status === "error";
  const futureSchema = (segment.schemaVersion ?? SUPPORTED_VIEW_SCHEMA) > SUPPORTED_VIEW_SCHEMA;
  const resolvable = !kernelError && !futureSchema && !!segment.viewId;
  const mode: ViewDisplayMode = presentation.active?.key === requestKey ? presentation.active.mode : "inline";
  const collapsibleSummary = !!segment.summary && (segment.summary.length > 180 || mode === "pip");
  const appearance = useRef<{ mode: ViewDisplayMode; language: string }>({ mode, language }); appearance.current = { mode, language };
  const selectMode = useCallback((value: ViewDisplayMode) => {
    presentation.select(requestKey, segment.title || translate.current("交互式视图"), value);
  }, [presentation.select, requestKey, segment.title]);
  const selectModeRef = useRef(selectMode); selectModeRef.current = selectMode;
  const active = mode !== "inline" || visible || focused || toolBusy;
  useEffect(() => () => {
    for (const phase of ["resolve-start", "resolved", "frame-initialize", "interactive"]) performance.clearMarks?.(`${metricKey}:${phase}`);
  }, [metricKey, active, expanded]);

  useEffect(() => {
    const focus = () => setFocused(surface.contains(document.activeElement));
    const blur = () => queueMicrotask(focus);
    surface.addEventListener("focusin", focus); surface.addEventListener("focusout", blur);
    return () => { surface.removeEventListener("focusin", focus); surface.removeEventListener("focusout", blur); };
  }, [surface]);

  useEffect(() => {
    const saved = readViewPresentation(requestKey, presentation.persisted?.[requestKey]);
    setExpanded(saved.expanded !== false);
    setSummaryExpanded(false);
    if (saved.mode && saved.mode !== "inline") selectModeRef.current(saved.mode);
  }, [requestKey]);
  useEffect(() => {
    if (mode === "inline") return;
    const escape = () => { if (appearance.current.mode !== "inline") selectModeRef.current("inline"); };
    const returnInline = (event: Event) => {
      if ((event as CustomEvent).detail?.key !== requestKey) return;
      setVisible(true); anchor.current?.scrollIntoView?.({ block: "nearest" });
    };
    window.addEventListener("reverie:view-escape", escape);
    window.addEventListener("reverie:view-inline", returnInline);
    return () => { window.removeEventListener("reverie:view-escape", escape); window.removeEventListener("reverie:view-inline", returnInline); };
  }, [mode, requestKey]);

  useLayoutEffect(() => {
    const home = anchor.current;
    if (!home) return;
    home.appendChild(surface);
    return () => { surface.remove(); presentation.forget(requestKey); };
  }, [surface, presentation.forget, requestKey]);

  useLayoutEffect(() => {
    const home = anchor.current;
    const target = mode === "fullscreen" ? presentation.fullscreenSlot : mode === "pip" ? presentation.pipSlot : home;
    if (!target || target === surface.parentElement) return;
    if (mode !== "inline") setReservedHeight(home?.getBoundingClientRect().height || 120);
    // appendChild/insertBefore resets iframe documents, even with the same React key.
    // Electron 41 provides the atomic, state-preserving DOM move operation.
    if (target.moveBefore) target.moveBefore(surface, null);
    else { selectModeRef.current("inline"); return; }
    if (mode === "inline") surface.querySelector<HTMLButtonElement>("[data-view-mode=fullscreen]")?.focus({ preventScroll: true });
    else surface.querySelector<HTMLButtonElement>("[data-view-mode=inline]")?.focus({ preventScroll: true });
  }, [surface, mode, presentation.fullscreenSlot, presentation.pipSlot]);

  useEffect(() => {
    if (!anchor.current || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(entries => {
      const intersecting = entries[0]?.isIntersecting ?? false;
      if (!intersecting && mode === "inline") setReservedHeight(anchor.current?.getBoundingClientRect().height || 120);
      setVisible(intersecting);
    });
    observer.observe(anchor.current);
    return () => observer.disconnect();
  }, [surface, requestKey, mode]);

  useLayoutEffect(() => { contextChangedRef.current?.(); }, [mode, language]);

  useEffect(() => {
    if (!resolvable || !active || !expanded) {
      setResolution({ status: "idle" });
      return;
    }
    let current = true;
    performance.mark?.(`${metricKey}:resolve-start`);
    setProposal("");
    setResolution({ status: "loading" });
    window.reverie
      .request("getView", { sessionId: segment.sessionId, viewId: segment.viewId, revision: segment.revision })
      .then((response) => {
        const view = response.view;
        performance.mark?.(`${metricKey}:resolved`);
        if (!current || !isHosted()) { if (view.interactionId) void window.reverie.request("releaseView", { interactionId: view.interactionId }).catch(() => {}); return; }
        if (view.sessionId !== segment.sessionId || view.viewId !== segment.viewId || view.revision !== segment.revision) {
          if (view.interactionId) void window.reverie.request("releaseView", { interactionId: view.interactionId }).catch(() => {});
          setResolution({ status: "error", message: "视图实例已过期，请重新加载。" }); return;
        }
        if ((view.schemaVersion ?? SUPPORTED_VIEW_SCHEMA) > SUPPORTED_VIEW_SCHEMA) {
          if (view.interactionId) void window.reverie.request("releaseView", { interactionId: view.interactionId }).catch(() => {});
          setResolution({ status: "error", message: "此视图由更新版本的 Reverie 生成，暂以摘要显示。" });
          return;
        }
        setResolution({ status: "ready", view });
      })
      .catch((error) => {
        if (current) setResolution({ status: "error", message: error instanceof Error ? error.message : String(error) });
      });
    return () => {
      current = false;
    };
    // requestKey folds sessionId/viewId/revision; nonce re-runs on an explicit retry.
  }, [requestKey, nonce, resolvable, active, expanded, segment.sessionId, segment.viewId, segment.revision]);

  const retry = useCallback(() => setNonce((value) => value + 1), []);

  // P2 restricted channel. Mounted ONLY against a painted, expanded frame: it
  // mints a per-instance capability, hands it out ONLY in the `ui/initialize`
  // reply, and funnels every later (capability-bearing, same-frame, live-revision)
  // message through the controller into the gated core actions. Torn down on
  // collapse, revision/session change or unmount, it revokes both halves so a
  // late reply never posts into a dead frame and an old frame cannot drive the new.
  useLayoutEffect(() => {
    if (resolution.status !== "ready" || !expanded || !active) return;
    const view = resolution.view;
    const frameWindow = iframeRef.current?.contentWindow;
    if (!frameWindow) return;

    const channel = new ViewChannel({
      source: frameWindow,
      sessionId: segment.sessionId,
      viewId: segment.viewId,
      revision: segment.revision,
      capability: newCapability(),
      standard: !!view.mcpApp,
    });
    const post = (message: Record<string, unknown>) => frameWindow.postMessage(message, "*");
    let lastContext = "";
    let contextFrame = 0;
    const sendContext = () => {
      if (!channel.ready || !iframeRef.current) return;
      const context = viewHostContext(iframeRef.current, appearance.current.language, appearance.current.mode);
      const encoded = JSON.stringify(context);
      if (encoded !== lastContext) { lastContext = encoded; post({ jsonrpc: "2.0", method: "ui/notifications/host-context-changed", params: context }); }
    };
    const queueContext = () => { if (!contextFrame) contextFrame = requestAnimationFrame(() => { contextFrame = 0; sendContext(); }); };
    contextChangedRef.current = queueContext;
    const lifecycle = view.mcpApp ? new McpAppLifecycle(frameWindow, post, view.mcpApp) : null;
    const request: CoreRequestFn = async (action, payload) => {
      if (action === "callViewTool") setToolBusy(true);
      try { return await window.reverie.request(action as never, payload as never); }
      finally { if (action === "callViewTool") setToolBusy(false); }
    };
    const controller = new ViewInteractionController({
      ref: { sessionId: segment.sessionId, viewId: segment.viewId, revision: segment.revision, interactionId: view.interactionId },
      request,
      onFollowUp: (text) => setProposal(current => current || text),
    });
    let closing: Promise<void> | undefined;
    const teardown = () => {
      if (closing) return closing;
      controller.revoke(); channel.revoke();
      closing = lifecycle?.teardown() ?? Promise.resolve();
      if (view.interactionId) void window.reverie.request("releaseView", { interactionId: view.interactionId }).catch(() => {});
      return closing;
    };
    teardownRef.current = teardown;
    let loads = 0;
    const frameLoaded = () => {
      queueContext();
      if (++loads < 2) return;
      void teardown();
      setResolution({ status: "error", message: "视图实例已过期，请重新加载。" });
    };
    frameLoadRef.current = frameLoaded;

    const onMessage = (event: MessageEvent) => {
      if (!isHosted()) return;
      // Cosmetic keyboard relay only; registered source cannot close another
      // view or reach any core action through this message.
      if (event.source === frameWindow && event.data?.type === "reverie:view-escape") { selectModeRef.current("inline"); return; }
      if (lifecycle?.receive(event)) return;
      const verdict = channel.accept(event);
      if (!verdict.accepted) {
        if (event.source === frameWindow && ["string", "number"].includes(typeof event.data?.id) && !["rate-limited", "oversize", "revoked"].includes(verdict.reason)) frameWindow.postMessage({ jsonrpc: "2.0", id: event.data.id, error: { code: verdict.reason === "unsupported-method" ? -32601 : -32600, message: verdict.reason } }, "*");
        return;
      }
      const settle = () => {
        if (verdict.id !== null) channel.settle(verdict.id);
      };
      // The handshake is the ONLY path that mints the capability, and it is
      // synchronous (no teardown race): answer it and never route it onward.
      if (verdict.method === "ui/initialize") {
        performance.mark?.(`${metricKey}:frame-initialize`);
        frameWindow.postMessage({ jsonrpc: "2.0", id: verdict.id, result: { protocolVersion: VIEW_PROTOCOL_VERSION, capability: verdict.capabilityIssued,
          hostInfo: { name: "Reverie", version: "2.5.0" },
          hostCapabilities: { ...(view.mcpApp ? { serverTools: {}, sandbox: { csp: {}, permissions: {} } } : { experimental: { "reverie/generated-tools": {}, "reverie/view-state": {} } }), message: { text: {} }, updateModelContext: { text: {}, structuredContent: {} } },
          hostContext: iframeRef.current ? viewHostContext(iframeRef.current, appearance.current.language, appearance.current.mode) : {},
          reverieViewState: view.state, reverieToolCalls: view.toolCalls || [] } }, "*");
        settle();
        return;
      }
      if (verdict.method === "ui/notifications/initialized") { performance.mark?.(`${metricKey}:interactive`); lifecycle?.ready(); sendContext(); settle(); return; }
      if (verdict.method === "ui/request-display-mode") {
        const requested = (verdict.params as { mode?: unknown } | undefined)?.mode;
        if (!VIEW_DISPLAY_MODES.includes(requested as ViewDisplayMode)) post({ jsonrpc: "2.0", id: verdict.id, error: { code: -32602, message: "Unknown display mode. Card and carousel are content layouts." } });
        else {
          const actual = surface.parentElement?.moveBefore ? requested as ViewDisplayMode : "inline";
          selectModeRef.current(actual);
          post({ jsonrpc: "2.0", id: verdict.id, result: { mode: actual } });
        }
        settle(); return;
      }
      if (verdict.method === "ui/notifications/request-teardown") {
        void teardown().then(() => { saveViewPresentation(requestKey, { expanded: false }, presentation.persisted?.[requestKey]); setExpanded(false); selectModeRef.current("inline"); });
        settle(); return;
      }
      if (verdict.method === "ui/notifications/size-changed") {
        const height = (verdict.params as { height?: unknown } | undefined)?.height;
        if (typeof height === "number" && Number.isFinite(height) && iframeRef.current) {
          const clamped = Math.max(120, Math.min(800, height));
          surface.style.setProperty("--view-inline-height", `${clamped}px`);
        }
        settle(); return;
      }
      void controller.handle(verdict).then((reply) => {
        // `drop` (revoked / no core request) posts nothing; the controller also
        // drops a result that resolves after revoke, so this never wakes a dead frame.
        if (reply.kind !== "drop" && !controller.revoked && isHosted() && reply.id !== null) {
          const body = reply.kind === "response"
            ? { jsonrpc: "2.0", id: reply.id, result: reply.result }
            : { jsonrpc: "2.0", id: reply.id, error: reply.error };
          frameWindow.postMessage(body, "*");
        }
        settle();
      });
    };

    window.addEventListener("message", onMessage);
    const mutations = new MutationObserver(queueContext);
    mutations.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "style", "lang"] });
    const resize = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(queueContext);
    if (iframeRef.current) resize?.observe(iframeRef.current);
    const motion = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    motion?.addEventListener("change", queueContext);
    const expiration = window.setInterval(() => {
      if (channel.expire().length) {
        controller.revoke(); channel.revoke();
        void teardown();
        setResolution({ status: "error", message: "视图请求超时。请核对操作结果后重新加载。" });
      }
    }, 1000);
    return () => {
      if (teardownRef.current === teardown) teardownRef.current = null;
      if (frameLoadRef.current === frameLoaded) frameLoadRef.current = null;
      if (lifecycle) void teardown().finally(() => window.removeEventListener("message", onMessage));
      else { void teardown(); window.removeEventListener("message", onMessage); }
      window.clearInterval(expiration);
      mutations.disconnect(); resize?.disconnect(); motion?.removeEventListener("change", queueContext);
      cancelAnimationFrame(contextFrame);
      if (contextChangedRef.current === queueContext) contextChangedRef.current = null;
    };
    // resolution.status gates the painted frame; the ref/view identity rebinds the channel.
  }, [resolution, expanded, active, segment.sessionId, segment.viewId, segment.revision, surface]);

  const title = segment.title || (resolution.status === "ready" ? resolution.view.title : "") || t("交互式视图");
  const canRetry = resolvable && resolution.status === "error";

  return <div ref={anchor} className="interactive-view-anchor" data-view-key={requestKey} style={mode !== "inline" || !active ? { minHeight: reservedHeight } : undefined}>
    {mode !== "inline" && <button type="button" className="interactive-view-return" onClick={() => selectMode("inline")}>{t("视图已移至其他位置，返回对话内")}</button>}
    {createPortal(
    <section className="interactive-view" data-display-mode={mode} aria-label={title} onKeyDown={event => {
      if (event.key === "Escape" && mode !== "inline") { event.preventDefault(); event.stopPropagation(); selectMode("inline"); }
    }}>
      <header className="interactive-view-head">
        <span className="interactive-view-title">
          <AppWindow size={14} aria-hidden="true" />
          <strong>{title}</strong>
          {segment.revision > 1 && <span className="interactive-view-rev">v{segment.revision}</span>}
        </span>
        <span className="interactive-view-actions">
          {resolvable && expanded && <ViewDisplayControls mode={mode} change={selectMode} />}
          {canRetry && (
            <button type="button" className="ghost-button" onClick={retry} aria-label={t("重试加载视图")}>
              <RefreshCw size={13} aria-hidden="true" /> {t("重试")}
            </button>
          )}
          {resolvable && (
            <button type="button" className="ghost-button" onClick={async () => { if (expanded) await teardownRef.current?.(); saveViewPresentation(requestKey, { expanded: !expanded }, presentation.persisted?.[requestKey]); setExpanded(value => !value); if (expanded) selectMode("inline"); }} aria-expanded={expanded}>
              {expanded ? <ChevronUp size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}
              {expanded ? t("收起") : t("展开")}
            </button>
          )}
        </span>
      </header>

      {proposal && <div className="interactive-view-note">
        <p>{t("组件建议的追问，发送前请确认：")}</p><p>{proposal}</p>
        <button type="button" className="ghost-button" disabled={toolBusy} onClick={() => {
          if (onFollowUp) onFollowUp(proposal);
          else if (!window.dispatchEvent(new CustomEvent("reverie:view-followup", { cancelable: true, detail: { text: proposal, sessionId: segment.sessionId } }))) return;
          setProposal("");
        }}>{t("发送追问")}</button>
        <button type="button" className="ghost-button" onClick={() => setProposal("")}>{t("忽略建议")}</button>
      </div>}
      {toolBusy && <p role="status">{t("视图工具处理中，可用 Stop 取消。")}</p>}
      {resolution.status === "ready" && resolution.view.toolCalls?.some(call => call.status === "unknown") && <p role="alert">{t("上次操作结果未知，已阻止自动重试。请先核对实际结果。")}</p>}
      {segment.summary && <div className="interactive-view-summary">
        <p id={summaryId} className={collapsibleSummary && !summaryExpanded ? "interactive-view-summary-clamped" : undefined}>{segment.summary}</p>
        {collapsibleSummary && <button type="button" className="interactive-view-summary-toggle" aria-expanded={summaryExpanded} aria-controls={summaryId} onClick={() => setSummaryExpanded(value => !value)}>{summaryExpanded ? t("收起摘要") : t("展开摘要")}</button>}
      </div>}

      {kernelError ? (
        <div className="interactive-view-error" role="alert">
          <AlertCircle size={14} aria-hidden="true" />
          <span>{segment.error || t("视图生成失败。")}</span>
        </div>
      ) : futureSchema ? (
        <p className="interactive-view-note">{t("此视图由更新版本的 Reverie 生成，暂以摘要显示。")}</p>
      ) : resolution.status === "loading" ? (
        <div className="interactive-view-loading interactive-view-placeholder" role="status">
          <RefreshCw className="spin" size={14} aria-hidden="true" /> {t("正在加载视图…")}
        </div>
      ) : resolution.status === "error" ? (
        <div className="interactive-view-error" role="alert">
          <AlertCircle size={14} aria-hidden="true" />
          <span>{t(resolution.message)}</span>
        </div>
      ) : resolution.status === "idle" && expanded && resolvable ? <p className="interactive-view-note interactive-view-placeholder">{t("滚动到此处时加载视图。")}</p>
      : resolution.status === "ready" && expanded && active ? (
        <iframe
          ref={iframeRef}
          onLoad={() => frameLoadRef.current?.()}
          className="interactive-view-frame"
          style={{ background: "var(--bg)", colorScheme: "normal" }}
          title={title}
          data-view-id={segment.viewId}
          src={resolution.view.url}
          sandbox="allow-scripts"
          referrerPolicy="no-referrer"
          loading="lazy"
        />
      ) : null}
    </section>, surface)}
  </div>;
});
