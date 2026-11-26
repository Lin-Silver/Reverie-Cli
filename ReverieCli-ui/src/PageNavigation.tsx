import {useEffect, useRef, useState} from 'react';
import {ArchiveRestore, ArrowDown, ArrowUp, Bot, Clock3, Database, Globe, Cable, MessageSquare, MoreHorizontal, Pin, Plug, Settings, Sparkles, Wrench} from 'lucide-react';
import {FloatingMenu} from './FloatingMenu';
import {useI18n} from './i18n';
import type {UiPreferences} from './preferences';
import type {ViewId} from './types';
import './page-navigation.css';

const pages = {
  chat: {label:'对话',icon:MessageSquare}, tools: {label:'工具',icon:Wrench}, subagents: {label:'SubAgents',icon:Bot},
  rats: {label:'RATS',icon:Database}, tasks: {label:'RTP 任务',icon:Clock3}, skills: {label:'技能',icon:Sparkles},
  plugins: {label:'插件',icon:Plug}, context: {label:'上下文引擎',icon:Database}, recovery: {label:'恢复',icon:ArchiveRestore},
  markets: {label:'扩展市场',icon:Globe}, connectors: {label:'Connectors 与 MCP',icon:Cable}, settings: {label:'设置',icon:Settings},
};

export function PageNavigation({view, setView, preferences, updatePreferences}: {
  view: ViewId; setView: (view:ViewId)=>void; preferences:UiPreferences; updatePreferences:(patch:Partial<UiPreferences>)=>void;
}) {
  const {t}=useI18n();
  const [open,setOpen]=useState<'hover'|'manual'|null>(null);
  const trigger=useRef<HTMLButtonElement>(null);
  const hovered=useRef(false);
  const clicked=useRef(false);
  const leaveTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const order=preferences.navigationOrder;
  const pinned=preferences.navigationPinned;
  const clearTimer=()=>{if(leaveTimer.current)clearTimeout(leaveTimer.current);leaveTimer.current=null;};
  const close=()=>{clearTimer();hovered.current=false;clicked.current=false;setOpen(null);};
  useEffect(()=>()=>{if(leaveTimer.current)clearTimeout(leaveTimer.current);},[]);
  const enter=()=>{clearTimer();hovered.current=true;setOpen(current=>current||'hover');};
  const leave=()=>{
    hovered.current=false;
    clearTimer();
    leaveTimer.current=setTimeout(()=>{if(!hovered.current&&!clicked.current)setOpen(null);},180);
  };
  const togglePin=(id:ViewId)=>updatePreferences({navigationPinned:pinned.includes(id)?pinned.filter(page=>page!==id):[...pinned,id]});
  const move=(id:ViewId,direction:number)=>{
    const index=order.indexOf(id), next=index+direction;
    if(next<0||next>=order.length)return;
    const changed=[...order];[changed[index],changed[next]]=[changed[next],changed[index]];
    updatePreferences({navigationOrder:changed});
  };
  const choose=(id:ViewId)=>{setView(id);close();};
  return <nav className="main-nav page-navigation" aria-label={t("主导航")}>
    {order.filter(id=>pinned.includes(id)).map(id=>{
      const Icon=pages[id].icon;
      return <button type="button" key={id} className={view===id?'active':''} aria-current={view===id?'page':undefined} onClick={()=>choose(id)}><Icon size={16}/>{t(pages[id].label)}</button>;
    })}
    <div className="page-navigation-more">
      <button type="button" ref={trigger} aria-label={t("更多页面")} aria-haspopup="dialog" aria-expanded={Boolean(open)} onPointerEnter={event=>{if(event.pointerType==='mouse')enter();}} onPointerLeave={leave} onClick={()=>{clearTimer();clicked.current=!clicked.current;if(clicked.current)setOpen('manual');else close();}} onKeyDown={event=>{if(event.key==='ArrowDown'){event.preventDefault();clicked.current=true;setOpen('manual');}}}><MoreHorizontal size={16}/>{t("更多页面")}</button>
      {open&&<FloatingMenu className="page-navigation-menu" label={t("所有页面")} autoFocus={open==='manual'} close={close}>
        <div onPointerEnter={enter} onPointerLeave={leave} onFocusCapture={()=>{clearTimer();clicked.current=true;setOpen('manual');}}>
          <p className="page-navigation-hint">{t("固定常用页面，并用箭头调整顺序。")}</p>
          {order.map((id,index)=>{
            const Icon=pages[id].icon,label=t(pages[id].label);
            return <div className="page-navigation-row" key={id}>
              <button type="button" className={view===id?'active':''} aria-current={view===id?'page':undefined} onClick={()=>choose(id)}><Icon size={15}/><span>{label}</span></button>
              <button type="button" aria-label={`${t(pinned.includes(id)?'解除固定':'固定到侧栏')} ${label}`} aria-pressed={pinned.includes(id)} onClick={()=>togglePin(id)}><Pin size={14}/></button>
              <button type="button" aria-label={`${t("上移")} ${label}`} disabled={index===0} onClick={()=>move(id,-1)}><ArrowUp size={13}/></button>
              <button type="button" aria-label={`${t("下移")} ${label}`} disabled={index===order.length-1} onClick={()=>move(id,1)}><ArrowDown size={13}/></button>
            </div>;
          })}
        </div>
      </FloatingMenu>}
    </div>
  </nav>;
}
