import { useLayoutEffect, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { Command, FileText, Pin, RefreshCw, Sparkles, X } from "lucide-react";
import type { CompletionOption } from "./composer-completion";
import { useI18n } from "./i18n";

export function ComposerSuggestions({ anchor, id, title, hint, options, selected, loading, error, choose, select, close }: {
  anchor: RefObject<HTMLDivElement | null>;
  id: string;
  title: string;
  hint: string;
  options: CompletionOption[];
  selected: number;
  loading: boolean;
  error?: string;
  choose: (option: CompletionOption) => void;
  select: (index: number) => void;
  close: () => void;
}) {
  const { t } = useI18n();
  const panel = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: 0, width: 0, bottom: 0, maxHeight: 360 });
  useLayoutEffect(() => { const element = panel.current; element?.showPopover?.(); return () => element?.hidePopover?.(); }, []);
  useLayoutEffect(() => {
    const update = () => {
      if (!anchor.current) return;
      const rect = anchor.current.getBoundingClientRect();
      const width = Math.min(rect.width, 640, window.innerWidth - 24);
      const top = Math.min(rect.top, window.innerHeight - 16);
      setPosition({ left: Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)), width, bottom: window.innerHeight - top + 8, maxHeight: Math.max(72, Math.min(392, top - 24)) });
    };
    update();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    if (anchor.current) observer?.observe(anchor.current);
    // On draft restoration the following sibling's ref and textarea autosize
    // settle after this layout effect. Observe the final anchor on that frame.
    const frame = requestAnimationFrame(() => { if (anchor.current) observer?.observe(anchor.current); update(); });
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => { cancelAnimationFrame(frame); observer?.disconnect(); window.removeEventListener("resize", update); window.removeEventListener("scroll", update, true); };
  }, [anchor]);
  useLayoutEffect(() => {
    panel.current?.querySelector<HTMLElement>(`[data-index="${selected}"]`)?.scrollIntoView?.({ block: "nearest" });
  }, [selected]);
  useLayoutEffect(() => {
    const dismiss = (event: PointerEvent) => {
      if (event.target instanceof Node && !panel.current?.contains(event.target) && !anchor.current?.contains(event.target)) close();
    };
    const focusOutside = (event: FocusEvent) => {
      if (event.target instanceof Node && !panel.current?.contains(event.target) && !anchor.current?.contains(event.target)) close();
    };
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("focusin", focusOutside);
    return () => { document.removeEventListener("pointerdown", dismiss); document.removeEventListener("focusin", focusOutside); };
  }, [anchor, close]);
  return createPortal(<div ref={panel} popover={typeof HTMLElement.prototype.showPopover === "function" ? "manual" : undefined} className="composer-suggestions" style={position} onMouseDown={event => event.preventDefault()}>
    <header><div><strong>{title}</strong><span>{hint}</span></div><button type="button" className="icon-button" aria-label={t("关闭候选菜单")} onClick={close}><X size={16} /></button></header>
    <div className="composer-suggestion-list" id={id} role="listbox" aria-label={title} aria-busy={loading}>
      {error ? <div className="completion-empty persistent-error" role="alert">{error}</div> : loading ? <div className="completion-empty" role="status"><RefreshCw size={16} className="spin" />{t("正在查找…")}</div> : options.length === 0 ? <div className="completion-empty" role="status">{t("没有匹配结果，请换个关键词")}</div> : options.map((option, index) => {
        const Icon = option.kind === "file" ? FileText : option.kind === "command" ? Command : option.kind === "skill" ? Pin : Sparkles;
        return <button type="button" role="option" id={`${id}-${index}`} aria-selected={selected === index} aria-disabled={option.disabled || undefined} tabIndex={-1} key={option.id} data-index={index} className={`completion-option ${selected === index ? "selected" : ""}`} onPointerMove={() => select(index)} onClick={() => { if (!option.disabled) choose(option); }} title={`${option.label}\n${option.description}`}>
          <span className={`completion-icon ${option.kind}`}><Icon size={17} /></span>
          <span className="completion-copy"><strong>{option.label}</strong><span>{option.description}</span></span>
          {option.badge && <small>{option.badge}</small>}
        </button>;
      })}
    </div>
    <footer><span><kbd>↑</kbd><kbd>↓</kbd> {t("浏览")}</span><span><kbd>Tab</kbd><kbd>Enter</kbd> {t("选择")}</span><span><kbd>Esc</kbd> {t("关闭")}</span></footer>
  </div>, document.body);
}
