import { afterEach, expect, it, vi } from 'vitest';

type WindowFixture = {
  destroyed:boolean;
  rejectLoad:((error:Error)=>void)|null;
  webContents:{send:ReturnType<typeof vi.fn>;mainFrame:object};
  showInactive:ReturnType<typeof vi.fn>;
};
const fixture=vi.hoisted(()=>({windows:[] as WindowFixture[],handlers:new Map<string,Function>(),deferLoad:false,copy:vi.fn()}));
vi.mock('electron',()=>({
  clipboard:{writeText:fixture.copy},
  ipcMain:{handle:(name:string,handler:Function)=>fixture.handlers.set(name,handler),on:vi.fn()},
  screen:{getCursorScreenPoint:()=>({x:0,y:0}),getDisplayNearestPoint:()=>({workArea:{x:0,y:0,width:1920,height:1040}})},
  BrowserWindow:class {
    destroyed=false;
    rejectLoad:((error:Error)=>void)|null=null;
    private closed:(()=>void)|null=null;
    webContents={send:vi.fn(),mainFrame:{},setWindowOpenHandler:vi.fn(),on:vi.fn()};
    showInactive=vi.fn();
    constructor(){fixture.windows.push(this);}
    on(name:string,callback:()=>void){if(name==='closed')this.closed=callback;}
    isDestroyed(){return this.destroyed;}
    loadURL(){return fixture.deferLoad?new Promise<void>((_resolve,reject)=>{this.rejectLoad=reject;}):Promise.resolve();}
    close(){this.destroy();}
    destroy(){this.destroyed=true;this.closed?.();this.rejectLoad?.(new Error('ERR_ABORTED: window closed during load'));}
  },
}));
import { AiOWindow, type AiOMessage } from './aio-window';

afterEach(()=>{fixture.windows=[];fixture.handlers.clear();fixture.deferLoad=false;fixture.copy.mockClear();vi.restoreAllMocks();});
const message=(id:string):AiOMessage=>({id,branch:'aio-mainline',root:'workspace',text:`完整正文 ${id}\n`,queuedAt:1});

it('stops a loading popup without an asynchronous failure and returns its saved message for recovery',async()=>{
  fixture.deferLoad=true;
  const popup=new AiOWindow(vi.fn(),vi.fn(),vi.fn());
  const starts=vi.spyOn(popup as unknown as {next:()=>Promise<void>},'next');
  popup.enqueue(message('first'));
  const completion=expect(starts.mock.results[0].value).resolves.toBeUndefined();
  expect(popup.stop()).toEqual(['first']);
  await completion;
  expect(fixture.windows[0].destroyed).toBe(true);
  expect(fixture.windows[0].webContents.send).not.toHaveBeenCalled();
  expect(fixture.windows[0].showInactive).not.toHaveBeenCalled();
});

it('keeps the current body and reply ownership while another saved message is queued',async()=>{
  const reply=vi.fn(async()=>{});
  const popup=new AiOWindow(reply,vi.fn(),vi.fn());
  const first=message('first');
  popup.enqueue(first);
  await vi.waitFor(()=>expect(fixture.windows[0].webContents.send).toHaveBeenCalledWith('aio:message',first));
  const second=message('second');
  popup.enqueue(second);
  popup.enqueue(message('second'));
  expect(fixture.windows).toHaveLength(1);
  const event={sender:fixture.windows[0].webContents,senderFrame:fixture.windows[0].webContents.mainFrame};
  fixture.handlers.get('aio:copy')!(event);
  expect(fixture.copy).toHaveBeenCalledWith(first.text);
  await fixture.handlers.get('aio:reply')!(event,'保留正在输入的回复。');
  expect(reply).toHaveBeenCalledWith(first,'保留正在输入的回复。',expect.any(String));
  await vi.waitFor(()=>expect(fixture.windows[1].webContents.send).toHaveBeenCalledWith('aio:message',second));
  expect(fixture.windows).toHaveLength(2);
  popup.stop();
});

it('retains a genuine load failure while the popup window is still open',async()=>{
  fixture.deferLoad=true;
  const popup=new AiOWindow(vi.fn(),vi.fn(),vi.fn());
  const starts=vi.spyOn(popup as unknown as {next:()=>Promise<void>},'next');
  popup.enqueue(message('first'));
  const completion=expect(starts.mock.results[0].value).rejects.toThrow('Renderer load failed');
  fixture.windows[0].rejectLoad!(new Error('Renderer load failed'));
  await completion;
  popup.stop();
});
