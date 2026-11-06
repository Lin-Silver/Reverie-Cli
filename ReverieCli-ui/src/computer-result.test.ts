import { describe, expect, it } from 'vitest';
import { parseComputerResult } from './computer-result';

describe('desktop delivery display', () => {
  it('keeps an uncertain error distinct from failure before delivery', () => {
    const result = parseComputerResult('Error: ' + JSON.stringify({version:'2.6',ok:false,command:'click',error:{code:'TIMEOUT',disposition:{delivery:'delivery_uncertain',retry:'unsafe'}}}));
    expect(result?.label).toBe('操作结果不确定');
    expect(result?.retry).toBe('unsafe');
  });
  it('shows an image path without treating successful capture as verified action', () => {
    const result = parseComputerResult(JSON.stringify({version:'2.6',ok:true,command:'screenshot',data:{path:'G:/project/screen.png',image_id:'img-1'}}) + '\nMedia: G:/project/screen.png');
    expect(result?.path).toBe('G:/project/screen.png');
    expect(result?.label).toBe('已获取界面信息');
  });
  it('ignores ordinary non-desktop tool output', () => expect(parseComputerResult('saved')).toBeNull());
});
