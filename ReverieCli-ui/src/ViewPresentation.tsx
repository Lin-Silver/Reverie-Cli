import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { InteractiveViewRuntime } from "./InteractiveView";
import { ViewPresentationContext, saveViewPresentation, type ActiveView, type ViewContent, type ViewDisplayMode } from "./view-presentation-context";
import type { ViewDisplayPreference } from "../electron/view-display-preferences";
export { VIEW_DISPLAY_MODES, useViewPresentation, type ViewDisplayMode } from "./view-presentation-context";

type Entry = ViewContent & { key: string; mount: HTMLDivElement; owners: Map<object, { anchor: HTMLDivElement; content: ViewContent }>; current: object; generation: number; isHosted: () => boolean };
function move(target: HTMLElement, mount: HTMLElement) {
  if (mount.parentElement === target) return;
  if (mount.isConnected && target.moveBefore) target.moveBefore(mount, null);
  else target.appendChild(mount);
}

/** One runtime per view identity, including live -> history handoffs. Connected
 * mounts let Chromium moveBefore preserve the document, JS heap and focus. */
export function ViewPresentationProvider({ children, scope = "", persisted }: { children: ReactNode; scope?: string; persisted?: Record<string, ViewDisplayPreference> }) {
  const [active, setActive] = useState<ActiveView | null>(null);
  const activeRef = useRef(active); activeRef.current = active;
  const savedRef = useRef(persisted); savedRef.current = persisted;
  const [fullscreenSlot, setFullscreenSlot] = useState<HTMLDivElement | null>(null);
  const [pipSlot, setPipSlot] = useState<HTMLDivElement | null>(null);
  const entries = useRef(new Map<string, Entry>());
  const [hostedViews, setHostedViews] = useState<Entry[]>([]);
  const parking = useRef<HTMLDivElement>(null);
  const mounted = useRef(true);
  useLayoutEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; for (const entry of entries.current.values()) { entry.owners.clear(); entry.mount.remove(); } entries.current.clear(); };
  }, []);
  const mountView = useCallback((key: string, owner: object, anchor: HTMLDivElement, content: ViewContent) => {
    let entry = entries.current.get(key);
    if (!entry) {
      const owners: Entry["owners"] = new Map();
      entry = { key, ...content, mount: document.createElement("div"), owners, current: owner, generation: 0, isHosted: () => owners.size > 0 };
      entries.current.set(key, entry);
    }
    const existed = entry.owners.has(owner);
    entry.owners.set(owner, { anchor, content }); entry.generation++;
    if (!existed || entry.current === owner) { entry.current = owner; Object.assign(entry, content); move(anchor, entry.mount); }
    setHostedViews([...entries.current.values()]);
  }, []);
  const unmountView = useCallback((key: string, owner: object) => {
    const entry = entries.current.get(key);
    if (!entry) return;
    entry.owners.delete(owner);
    if (entry.current === owner) {
      const previous = [...entry.owners.entries()].at(-1);
      if (previous) { entry.current = previous[0]; Object.assign(entry, previous[1].content); move(previous[1].anchor, entry.mount); }
      else if (parking.current) move(parking.current, entry.mount);
    }
    const generation = ++entry.generation;
    // Live -> restored-history replacement occurs in one React commit. Keep
    // the connected mount until that commit ends, but accept no unowned calls.
    queueMicrotask(() => {
      if (!mounted.current || generation !== entry.generation || entry.owners.size) return;
      entries.current.delete(key); setHostedViews([...entries.current.values()]);
      entry.mount.remove();
    });
  }, []);
  const select = useCallback((key: string, title: string, mode: ViewDisplayMode) => {
    const previous = activeRef.current;
    if (previous && previous.key !== key) {
      window.dispatchEvent(new CustomEvent("reverie:view-inline", { detail: { key: previous.key } }));
      saveViewPresentation(previous.key, { mode: "inline" }, savedRef.current?.[previous.key]);
    }
    if (mode === "inline") window.dispatchEvent(new CustomEvent("reverie:view-inline", { detail: { key } }));
    saveViewPresentation(key, { mode }, savedRef.current?.[key]);
    setActive(current => mode === "inline" ? current?.key === key ? null : current : { key, title, mode });
  }, []);
  const forget = useCallback((key: string) => setActive(current => current?.key === key ? null : current), []);
  useEffect(() => window.reverie?.onEvent?.(message => {
    if (message.type === "view.escape" && !document.querySelector('[aria-modal="true"]')) window.dispatchEvent(new Event("reverie:view-escape"));
  }), []);
  const value = useMemo(() => ({ scope, persisted, active, fullscreenSlot, pipSlot, setFullscreenSlot, select, forget, mountView, unmountView }), [scope, persisted, active, fullscreenSlot, pipSlot, select, forget, mountView, unmountView]);
  return <ViewPresentationContext.Provider value={value}>{children}<div className="view-pip-slot" ref={setPipSlot} /><div ref={parking} hidden aria-hidden="true" />
    {hostedViews.map(entry => createPortal(<InteractiveViewRuntime segment={entry.segment} onFollowUp={entry.onFollowUp} isHosted={entry.isHosted} />, entry.mount, entry.key))}
  </ViewPresentationContext.Provider>;
}
