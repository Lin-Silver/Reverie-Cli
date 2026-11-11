import { type ReactNode, useLayoutEffect, useRef, useState } from 'react';
import type { SessionInfo } from './types';

const ROW_HEIGHT = 72;
const VISIBLE_ROWS = 12;
const OVERSCAN = 4;

export function VirtualSessionList({items, activeId, renderItem}: {items:SessionInfo[]; activeId:string; renderItem:(item:SessionInfo)=>ReactNode}) {
  const box = useRef<HTMLDivElement>(null);
  const [first, setFirst] = useState(0);
  const virtual = items.length > 80;
  const identity = items.map(item => item.id).join('\n');
  useLayoutEffect(() => {
    if (!virtual || !box.current) return;
    const selected = items.findIndex(item => item.id === activeId);
    const target = selected < 0 ? 0 : selected * ROW_HEIGHT;
    if (target < box.current.scrollTop || target >= box.current.scrollTop + box.current.clientHeight) box.current.scrollTop = target;
    setFirst(Math.max(0, Math.floor(box.current.scrollTop / ROW_HEIGHT) - OVERSCAN));
  }, [identity, activeId, virtual]);
  if (!virtual) return <>{items.map(renderItem)}</>;
  const start = Math.min(first, Math.max(0, items.length - 1));
  const end = Math.min(items.length, start + VISIBLE_ROWS + OVERSCAN * 2);
  return <div ref={box} className="virtual-session-list" style={{maxHeight:432, overflowY:'auto'}}
    onScroll={event => setFirst(Math.max(0, Math.floor(event.currentTarget.scrollTop / ROW_HEIGHT) - OVERSCAN))}>
    <div aria-hidden="true" style={{height:start * ROW_HEIGHT}} />
    {items.slice(start, end).map(item => <div key={item.id} style={{height:ROW_HEIGHT}}>{renderItem(item)}</div>)}
    <div aria-hidden="true" style={{height:(items.length - end) * ROW_HEIGHT}} />
  </div>;
}
