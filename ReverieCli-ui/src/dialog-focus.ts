import {useEffect, useRef} from 'react';

const DIALOG_FOCUSABLE=["button:not([disabled])","input:not([disabled])","select:not([disabled])","textarea:not([disabled])","[href]","[tabindex]:not([tabindex='-1'])"].join(',');
export function useDialogFocus(dialogRef:{current:HTMLElement|null},close?:()=>void):void {
  const closeRef=useRef(close);closeRef.current=close;
  const restoreFocus=useRef<HTMLElement|null>(typeof document!=='undefined'&&document.activeElement instanceof HTMLElement?document.activeElement:null);
  useEffect(()=>{
    const dialog=dialogRef.current;if(!dialog)return;
    const focusable=()=>Array.from(dialog.querySelectorAll<HTMLElement>(DIALOG_FOCUSABLE)).filter(element=>!element.hidden&&element.getAttribute('aria-hidden')!=='true');
    const initial=dialog.querySelector<HTMLElement>('[autofocus]')??focusable()[0]??dialog;initial.focus();
    const keyDown=(event:globalThis.KeyboardEvent)=>{
      if(event.key==='Escape'&&closeRef.current){event.preventDefault();event.stopPropagation();closeRef.current();return;}
      if(event.key!=='Tab')return;
      const elements=focusable();
      if(!elements.length){event.preventDefault();dialog.focus();return;}
      const first=elements[0],last=elements[elements.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
    };
    dialog.addEventListener('keydown',keyDown);
    return()=>{dialog.removeEventListener('keydown',keyDown);restoreFocus.current?.focus();};
  },[dialogRef]);
}
