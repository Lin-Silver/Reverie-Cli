// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { VirtualSessionList } from './VirtualSessionList';
import type { SessionInfo } from './types';

afterEach(cleanup);
it('keeps a thousand conversations reachable while mounting a bounded set of rows', () => {
  const items = Array.from({length:1000}, (_,index) => ({id:String(index),name:`Conversation ${index}`} as SessionInfo));
  const view = render(<VirtualSessionList items={items} activeId="0" renderItem={item => <button>{item.name}</button>} />);
  expect(screen.getAllByRole('button').length).toBeLessThanOrEqual(20);
  const box = view.container.querySelector('.virtual-session-list')!;
  fireEvent.scroll(box, {target:{scrollTop:990 * 72}});
  expect(screen.getByRole('button', {name:'Conversation 999'})).toBeTruthy();
  view.rerender(<VirtualSessionList items={items.filter(item => item.id==='800')} activeId="800" renderItem={item => <button>{item.name}</button>} />);
  expect(screen.getByRole('button', {name:'Conversation 800'})).toBeTruthy();
  expect(screen.getAllByRole('button')).toHaveLength(1);
});
