import { contextBridge,ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('aio',{
  message:(listener:(value:{id:string;text:string})=>void)=>ipcRenderer.on('aio:message',(_event,value)=>listener(value)),
  reply:(text:string)=>ipcRenderer.invoke('aio:reply',text),
  copy:()=>ipcRenderer.invoke('aio:copy'),
  close:()=>ipcRenderer.invoke('aio:close'),
  open:()=>ipcRenderer.invoke('aio:open'),
  readable:()=>ipcRenderer.send('aio:readable'),
});
