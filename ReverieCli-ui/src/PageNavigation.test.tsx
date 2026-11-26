// @vitest-environment jsdom
import {useState} from 'react';
import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, expect, it} from 'vitest';
import {PageNavigation} from './PageNavigation';
import {DEFAULT_UI_PREFERENCES, normalizeUiPreferences, type UiPreferences} from './preferences';
import type {ViewId} from './types';

afterEach(cleanup);
function Harness(){
  const [view,setView]=useState<ViewId>('chat');
  const [preferences,setPreferences]=useState(DEFAULT_UI_PREFERENCES);
  return <><PageNavigation view={view} setView={setView} preferences={preferences} updatePreferences={(patch:Partial<UiPreferences>)=>setPreferences(current=>normalizeUiPreferences({...current,...patch}))}/><output>{view}</output></>;
}
it('opens all pages from the keyboard, pins a page and preserves its selected state',()=>{
  render(<Harness/>);
  const trigger=screen.getByRole('button',{name:'更多页面'});
  fireEvent.keyDown(trigger,{key:'ArrowDown'});
  const menu=screen.getByRole('dialog',{name:'所有页面'});
  expect(document.activeElement).toBe(within(menu).getByRole('button',{name:'对话'}));
  fireEvent.click(within(menu).getByRole('button',{name:'固定到侧栏 扩展市场'}));
  const navigation=screen.getByRole('navigation');
  expect(within(navigation).getByRole('button',{name:'扩展市场'})).toBeTruthy();
  fireEvent.click(within(menu).getByRole('button',{name:'扩展市场'}));
  expect(screen.getByRole('status').textContent).toBe('markets');
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(within(navigation).getByRole('button',{name:'扩展市场'}).getAttribute('aria-current')).toBe('page');
});
it('changes the persisted page order and can unpin all pages without losing the menu',()=>{
  render(<Harness/>);
  fireEvent.click(screen.getByRole('button',{name:'更多页面'}));
  const menu=screen.getByRole('dialog');
  fireEvent.click(within(menu).getByRole('button',{name:'固定到侧栏 扩展市场'}));
  fireEvent.click(within(menu).getByRole('button',{name:'上移 扩展市场'}));
  const buttons=within(screen.getByRole('navigation')).getAllByRole('button');
  expect(buttons.findIndex(button=>button.textContent==='扩展市场')).toBeLessThan(buttons.findIndex(button=>button.textContent==='恢复'));
  fireEvent.click(within(menu).getByRole('button',{name:'解除固定 扩展市场'}));
  expect(within(screen.getByRole('navigation')).queryByRole('button',{name:'扩展市场'})).toBeNull();
  fireEvent.keyDown(menu,{key:'Escape'});
  expect(document.activeElement).toBe(screen.getByRole('button',{name:'更多页面'}));
});
it('opens on mouse hover without taking focus until explicitly activated',()=>{
  render(<><input aria-label="composer"/><Harness/></>);
  const composer=screen.getByLabelText('composer');composer.focus();
  const trigger=screen.getByRole('button',{name:'更多页面'});
  fireEvent.pointerEnter(trigger,{pointerType:'mouse'});
  expect(screen.getByRole('dialog',{name:'所有页面'})).toBeTruthy();
  expect(document.activeElement).toBe(composer);
  fireEvent.click(trigger);
  expect(document.activeElement).toBe(within(screen.getByRole('dialog')).getByRole('button',{name:'对话'}));
});
it('keeps the open menu attached when pinning changes the trigger position',()=>{
  render(<Harness/>);
  const trigger=screen.getByRole('button',{name:'更多页面'});
  const navigation=screen.getByRole('navigation');
  Object.defineProperty(trigger,'getBoundingClientRect',{value:()=>new DOMRect(14,100+(within(navigation).queryByRole('button',{name:'扩展市场'})?36:0),240,36)});
  fireEvent.click(trigger);
  const menu=screen.getByRole('dialog',{name:'所有页面'});
  expect(menu.style.top).toBe('144px');
  fireEvent.click(within(menu).getByRole('button',{name:'固定到侧栏 扩展市场'}));
  expect(menu.style.top).toBe('180px');
});
