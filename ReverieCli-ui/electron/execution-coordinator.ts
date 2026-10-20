import { randomUUID } from "node:crypto";
import { realpath } from "node:fs/promises";
import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";

const runGit = promisify(execFile);
const pathKey = (value:string) => process.platform === "win32" ? path.resolve(value).toLowerCase() : path.resolve(value);
const overlaps = (a:string,b:string) => a === b || a.startsWith(b+path.sep) || b.startsWith(a+path.sep);

export interface ExecutionEntry { id:string;projectRoot:string;checkout:string;gitCheckout?:boolean;sessionId:string;state:"queued"|"running"|"stopping";readOnly:boolean;reason:string;createdAt:string;pid?:number }
const conflicts=(a:ExecutionEntry,b:ExecutionEntry)=>a.checkout===b.checkout || (!(a.gitCheckout && b.gitCheckout) && overlaps(pathKey(a.projectRoot),pathKey(b.projectRoot)));
export class ExecutionCoordinator {
  readonly maximum=4;
  private entries=new Map<string,ExecutionEntry>();
  private waiting=new Map<string,{resolve:()=>void;reject:(error:Error)=>void}>();
  private roots=new Map<string,string>();
  private owners=new Map<string,string>();
  private gitRoots=new Set<string>();
  constructor(private changed:(entries:ExecutionEntry[])=>void){}
  list():ExecutionEntry[]{return [...this.entries.values()].map(item=>({...item}));}
  busy(root:string):boolean{const key=pathKey(root);const candidate={projectRoot:root,checkout:this.roots.get(key) || key,gitCheckout:this.gitRoots.has(key)} as ExecutionEntry;return this.list().some(item=>item.state!=="queued" && conflicts(item,candidate));}
  private publish(){this.changed(this.list());}
  private drain(){
    const active=this.list().filter(item=>item.state!=="queued");
    for(const item of this.entries.values()){
      if(item.state!=="queued")continue;
      const ordered=this.list();
      const earlier=ordered.find((other,index)=>other.id!==item.id && conflicts(other,item) && (!item.readOnly || !other.readOnly) && (other.state!=="queued" || index<ordered.findIndex(value=>value.id===item.id)));
      const reason=earlier?`Waiting for ${earlier.sessionId} (${earlier.id}) in this checkout`:active.length>=this.maximum?`Waiting for a core slot (${this.maximum} maximum)`:"";
      item.reason=reason;if(reason)continue;item.state="running";active.push(item);this.waiting.get(item.id)?.resolve();this.waiting.delete(item.id);
    }
    this.publish();
  }
  async acquire(projectRoot:string,sessionId:string,readOnly=false,queue=true):Promise<ExecutionEntry>{
    const root=await realpath(projectRoot);let checkout=pathKey(root);let gitCheckout=false;
    try{const result=await runGit("git",["-C",root,"rev-parse","--show-toplevel"],{windowsHide:true,timeout:10000,maxBuffer:1024*1024});checkout=pathKey(await realpath(result.stdout.trim()));gitCheckout=true;}catch{/* Non-Git projects coordinate overlapping directories. */}
    this.roots.set(pathKey(projectRoot),checkout);this.roots.set(pathKey(root),checkout);
    this.owners.set(pathKey(projectRoot),pathKey(root));
    for(const key of [pathKey(projectRoot),pathKey(root)]){if(gitCheckout)this.gitRoots.add(key);else this.gitRoots.delete(key);}
    if(this.list().some(item=>pathKey(item.projectRoot)===pathKey(root) && item.sessionId===sessionId))throw new Error("This conversation already has a running or queued task.");
    const entry:ExecutionEntry={id:randomUUID(),projectRoot:root,checkout,gitCheckout,sessionId,state:"queued",readOnly,reason:"",createdAt:new Date().toISOString()};this.entries.set(entry.id,entry);
    const granted=new Promise<void>((resolve,reject)=>this.waiting.set(entry.id,{resolve,reject}));this.drain();if(!queue && entry.state==="queued"){this.waiting.delete(entry.id);this.entries.delete(entry.id);this.drain();throw new Error("View tool busy: another run owns this checkout.");}await granted;return {...entry};
  }
  pid(id:string,pid:number){const item=this.entries.get(id);if(item){item.pid=pid;this.publish();}}
  find(root:string,sessionId:string){const key=this.owners.get(pathKey(root)) || pathKey(root);return this.list().find(item=>pathKey(item.projectRoot)===key && item.sessionId===sessionId);}
  cancelQueued(root:string,sessionId:string):boolean{const item=this.find(root,sessionId);if(!item || item.state!=="queued")return false;this.waiting.get(item.id)?.reject(new Error("Queued run cancelled before execution. No tools ran."));this.waiting.delete(item.id);this.entries.delete(item.id);this.drain();return true;}
  release(id:string){this.entries.delete(id);this.waiting.delete(id);this.drain();}
}
