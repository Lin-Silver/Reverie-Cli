import { randomUUID } from "node:crypto";
import { realpath } from "node:fs/promises";

export interface ExecutionEntry { id:string;projectRoot:string;checkout:string;sessionId:string;state:"queued"|"running"|"stopping";readOnly:boolean;reason:string;createdAt:string;pid?:number }
export class ExecutionCoordinator {
  readonly maximum=4;
  private entries=new Map<string,ExecutionEntry>();
  private waiting=new Map<string,{resolve:()=>void;reject:(error:Error)=>void}>();
  constructor(private changed:(entries:ExecutionEntry[])=>void){}
  list():ExecutionEntry[]{return [...this.entries.values()].map(item=>({...item}));}
  busy(root:string):boolean{return this.list().some(item=>item.checkout===root.toLowerCase() && item.state!=="queued");}
  private publish(){this.changed(this.list());}
  private drain(){
    const active=this.list().filter(item=>item.state!=="queued");
    for(const item of this.entries.values()){
      if(item.state!=="queued")continue;
      const earlier=this.list().find(other=>other.id!==item.id && other.checkout===item.checkout && (!item.readOnly || !other.readOnly) && (other.state!=="queued" || other.createdAt<item.createdAt));
      const reason=earlier?`Waiting for ${earlier.sessionId} (${earlier.id}) in this checkout`:active.length>=this.maximum?`Waiting for a core slot (${this.maximum} maximum)`:"";
      item.reason=reason;if(reason)continue;item.state="running";active.push(item);this.waiting.get(item.id)?.resolve();this.waiting.delete(item.id);
    }
    this.publish();
  }
  async acquire(projectRoot:string,sessionId:string,readOnly=false):Promise<ExecutionEntry>{
    const root=await realpath(projectRoot);const checkout=root.toLowerCase();
    if(this.list().some(item=>item.checkout===checkout && item.sessionId===sessionId))throw new Error("This conversation already has a running or queued task.");
    const entry:ExecutionEntry={id:randomUUID(),projectRoot:root,checkout,sessionId,state:"queued",readOnly,reason:"",createdAt:new Date().toISOString()};this.entries.set(entry.id,entry);
    const granted=new Promise<void>((resolve,reject)=>this.waiting.set(entry.id,{resolve,reject}));this.drain();await granted;return {...entry};
  }
  pid(id:string,pid:number){const item=this.entries.get(id);if(item){item.pid=pid;this.publish();}}
  find(root:string,sessionId:string){return this.list().find(item=>item.checkout===root.toLowerCase() && item.sessionId===sessionId);}
  cancelQueued(root:string,sessionId:string):boolean{const item=this.find(root,sessionId);if(!item || item.state!=="queued")return false;this.waiting.get(item.id)?.reject(new Error("Queued run cancelled before execution. No tools ran."));this.waiting.delete(item.id);this.entries.delete(item.id);this.drain();return true;}
  release(id:string){this.entries.delete(id);this.waiting.delete(id);this.drain();}
}
