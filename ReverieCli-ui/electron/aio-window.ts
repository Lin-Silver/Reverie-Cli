import { BrowserWindow,clipboard,ipcMain,screen } from 'electron';
import path from 'node:path';
import { randomUUID } from 'node:crypto';

export interface AiOMessage {id:string;branch:string;root:string;text:string;queuedAt:number}
export class AiOWindow {
  private window:BrowserWindow|null=null;
  private current:AiOMessage|null=null;
  private queue:AiOMessage[]=[];
  private presented=false;
  constructor(private reply:(message:AiOMessage,text:string,replyId:string)=>Promise<void>,private open:(message:AiOMessage)=>void,private readable:(message:AiOMessage,latency:number)=>Promise<void>){
    const trusted=(event:Electron.IpcMainInvokeEvent|Electron.IpcMainEvent)=>{if(!this.window || event.sender!==this.window.webContents || event.senderFrame!==this.window.webContents.mainFrame || !this.current)throw new Error('Untrusted AiO window request.');return this.current;};
    ipcMain.handle('aio:reply',async(event,text:unknown)=>{const message=trusted(event);if(typeof text!=='string' || !text.trim())throw new Error('Reply text is required.');await this.reply(message,text,randomUUID());this.dismiss(message.id);});
    ipcMain.handle('aio:copy',event=>clipboard.writeText(trusted(event).text));
    ipcMain.handle('aio:close',event=>{trusted(event);this.dismiss();});
    ipcMain.handle('aio:open',event=>this.open(trusted(event)));
    ipcMain.on('aio:readable',event=>{
      if(!this.window || !this.current || event.sender!==this.window.webContents || event.senderFrame!==this.window.webContents.mainFrame || this.presented)return;
      this.presented=true;
      void this.readable(this.current,Date.now()-this.current.queuedAt).catch(error=>console.error('AiO display acknowledgement failed:',error));
    });
  }
  enqueue(message:AiOMessage){if(this.current?.id===message.id || this.queue.some(item=>item.id===message.id))return;this.queue.push(message);void this.next();}
  private async next(){
    if(this.current || !this.queue.length)return;
    this.current=this.queue.shift()!;
    this.presented=false;
    this.current.queuedAt=Date.now();
    const display=screen.getDisplayNearestPoint(screen.getCursorScreenPoint());const area=display.workArea;
    const width=Math.min(440,area.width-24),height=Math.min(520,area.height-24);
    const window=new BrowserWindow({width,height,x:area.x+area.width-width-12,y:area.y+area.height-height-12,show:false,title:'AiO',alwaysOnTop:true,skipTaskbar:true,autoHideMenuBar:true,webPreferences:{preload:path.join(__dirname,'aio-preload.js'),nodeIntegration:false,contextIsolation:true,sandbox:true}});
    this.window=window;
    window.webContents.setWindowOpenHandler(()=>({action:'deny'}));window.webContents.on('will-navigate',event=>event.preventDefault());
    window.on('closed',()=>{if(this.window===window){this.window=null;this.current=null;void this.next();}});
    const html=`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'"><style>html{color-scheme:dark light;font:15px system-ui}body{margin:0;padding:16px;box-sizing:border-box;height:100vh;display:flex;flex-direction:column;gap:12px}header{display:flex;justify-content:space-between;align-items:center}h1{margin:0;font-size:18px}article{flex:1;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.6}textarea{font:inherit;resize:vertical;min-height:64px}nav{display:flex;gap:8px}button{font:inherit;padding:7px 12px;border-radius:7px;cursor:pointer}#error{color:#d55;margin:0}</style><body><header><h1>AiO</h1><button id="close" aria-label="关闭">×</button></header><article id="body" aria-live="polite"></article><nav><button id="copy">复制</button><button id="open">打开对话</button></nav><label for="reply">回复</label><textarea id="reply"></textarea><button id="send">发送</button><p id="error" role="alert"></p><script>const api=window.aio;api.message(message=>{document.getElementById('body').textContent=message.text;requestAnimationFrame(()=>requestAnimationFrame(()=>api.readable()));});for(const name of ['copy','open','close'])document.getElementById(name).onclick=()=>api[name]();document.getElementById('send').onclick=async()=>{const button=document.getElementById('send');button.disabled=true;try{await api.reply(document.getElementById('reply').value);}catch(error){document.getElementById('error').textContent=String(error);button.disabled=false;}};</script></body></html>`;
    try{await window.loadURL('data:text/html;charset=utf-8,'+encodeURIComponent(html));}
    catch(error){if(window.isDestroyed())return;throw error;}
    if(!window.isDestroyed() && this.current){window.webContents.send('aio:message',this.current);window.showInactive();}
  }
  dismiss(messageId?:string){if(!messageId || this.current?.id===messageId)this.window?.close();}
  stop(){
    const undisplayed=this.queue.map(message=>message.id);
    if(this.current && !this.presented)undisplayed.push(this.current.id);
    this.queue=[];this.window?.destroy();this.current=null;this.window=null;
    return undisplayed;
  }
}
