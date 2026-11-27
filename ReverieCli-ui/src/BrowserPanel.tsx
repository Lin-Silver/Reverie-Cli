import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { PanelTab } from "../electron/desktop-browser";
import { useI18n } from "./i18n";

export function BrowserPanel({root,sessionId}:{root:string;sessionId:string}) {
  const {t} = useI18n();
  const [tabs,setTabs] = useState<PanelTab[]>([]), [selected,setSelected] = useState(""), [error,setError] = useState("");
  const slot = useRef<HTMLDivElement>(null);
  const tab = tabs.find(item => item.id === selected) ?? tabs[0];
  useEffect(() => {
    let live = true, sequence = 0;
    const refresh = async () => {
      const current = ++sequence;
      try {
        const items = await window.reverie.browserPanel(root,sessionId,{operation:"list"});
        if (live && sequence === current) setTabs(items);
      } catch (failure) { if (live) setError(String(failure)); }
    };
    void refresh();
    const off = window.reverie.onEvent(message => { if (message.type === "browser.tabsChanged") void refresh(); });
    return () => { live = false; off(); };
  },[root,sessionId]);
  const tabId = tab?.id;
  useLayoutEffect(() => {
    const element = slot.current;
    if (!element || !tabId) return;
    let live = true;
    const place = () => {
      const rect = element.getBoundingClientRect(), x = Math.ceil(rect.left), y = Math.ceil(rect.top);
      const width = Math.floor(Math.min(innerWidth,rect.right))-x, height = Math.floor(Math.min(innerHeight,rect.bottom))-y;
      if (width<1 || height<1 || x<0 || y<0) { void window.reverie.browserPanel(root,sessionId,{operation:"hide"}).catch(() => {}); return; }
      void window.reverie.browserPanel(root,sessionId,{operation:"show",tab:tabId,bounds:{x,y,width,height}})
        .then(() => { if (live) setError(""); }, failure => { if (live) setError(String(failure)); });
    };
    const observer = new ResizeObserver(place);
    observer.observe(element); window.addEventListener("resize",place); window.addEventListener("scroll",place,true); place();
    return () => {
      live = false; observer.disconnect(); window.removeEventListener("resize",place); window.removeEventListener("scroll",place,true);
      void window.reverie.browserPanel(root,sessionId,{operation:"hide"}).catch(() => {});
    };
  },[root,sessionId,tabId]);
  return <div className="browser-panel">
    {error && <p role="alert">{error}</p>}
    {tab ? <><div className="workbench-toolbar">
      <select aria-label={t("浏览器标签页")} value={tab.id} onChange={event => setSelected(event.target.value)}>
        {tabs.map(item => <option key={item.id} value={item.id}>{item.title || item.url}</option>)}
      </select>
      <button type="button" onClick={() => void window.reverie.browserPanel(root,sessionId,{operation:"close",tab:tab.id}).catch(failure => setError(String(failure)))}>{t("关闭标签页")}</button>
    </div><div className="browser-page-slot" ref={slot}/></> : <p className="workbench-empty">{t("此会话尚无浏览器标签页。")}</p>}
  </div>;
}
