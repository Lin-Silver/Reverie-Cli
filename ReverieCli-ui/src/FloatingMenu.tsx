import { useLayoutEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** Native top-layer placement keeps menus above scroll containers and side panels. */
export function FloatingMenu({ children, className, close, side = "bottom", label }: {
  children: ReactNode;
  className: string;
  close: () => void;
  side?: "top" | "bottom";
  label?: string;
}) {
  const marker = useRef<HTMLSpanElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const closeRef = useRef(close);
  closeRef.current = close;
  useLayoutEffect(() => {
    const element = menu.current;
    const anchor = marker.current?.previousElementSibling as HTMLElement | null;
    if (!element || !anchor) return;
    window.dispatchEvent(new Event("reverie:menu-open"));
    element.showPopover?.();
    const position = () => {
      const rect = anchor.getBoundingClientRect();
      const margin = 8;
      const below = window.innerHeight - rect.bottom - margin * 2;
      const above = rect.top - margin * 2;
      const up = side === "top" ? above >= Math.min(element.scrollHeight, 180) || above > below : below < Math.min(element.scrollHeight, 180) && above > below;
      element.style.maxHeight = `${Math.max(48, up ? above : below)}px`;
      element.style.left = `${Math.max(margin, Math.min(rect.left, window.innerWidth - element.offsetWidth - margin))}px`;
      element.style.transformOrigin = `${Math.max(0, Math.min(element.offsetWidth, rect.left + rect.width / 2 - parseFloat(element.style.left)))}px ${up ? "bottom" : "top"}`;
      element.style.top = `${up ? Math.max(margin, rect.top - element.offsetHeight - margin) : rect.bottom + margin}px`;
    };
    position();
    const dismiss = () => closeRef.current();
    const outside = (event: PointerEvent) => { if (event.target instanceof Node && !element.contains(event.target) && !anchor.contains(event.target)) dismiss(); };
    const focusOutside = (event: FocusEvent) => { if (event.target instanceof Node && !element.contains(event.target) && !anchor.contains(event.target)) dismiss(); };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); dismiss(); anchor.focus(); }
    };
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(position);
    observer?.observe(element);
    observer?.observe(anchor);
    element.querySelector<HTMLElement>("input,button:not(:disabled)")?.focus();
    document.addEventListener("pointerdown", outside, true);
    document.addEventListener("focusin", focusOutside);
    document.addEventListener("keydown", key, true);
    window.addEventListener("resize", position);
    window.addEventListener("scroll", position, true);
    window.addEventListener("reverie:menu-open", dismiss);
    return () => {
      observer?.disconnect();
      document.removeEventListener("pointerdown", outside, true);
      document.removeEventListener("focusin", focusOutside);
      document.removeEventListener("keydown", key, true);
      window.removeEventListener("resize", position);
      window.removeEventListener("scroll", position, true);
      window.removeEventListener("reverie:menu-open", dismiss);
      element.hidePopover?.();
    };
  }, [side]);
  return <><span ref={marker} hidden />{createPortal(<div ref={menu} role={label ? "dialog" : undefined} aria-label={label} popover={typeof HTMLElement.prototype.showPopover === "function" ? "manual" : undefined} className={`${className} floating-menu`} onPointerDown={event => event.stopPropagation()} onMouseDown={event => event.stopPropagation()} onKeyDown={event => {
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));
    if (!buttons.length) return;
    event.preventDefault(); event.stopPropagation();
    const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
    const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (current + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
    buttons[next]?.focus();
  }}>{children}</div>, document.body)}</>;
}
