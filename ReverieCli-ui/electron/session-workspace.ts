import * as pty from "node-pty";
import { createHash, randomUUID } from "node:crypto";
import { appendFile, mkdir, readFile, realpath, rename, stat, writeFile, readdir } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";
import { within } from "./attachments";
import { gitOutput } from "./workbench";

export interface TerminalRecord { id:string;projectRoot:string;sessionId:string;cwd:string;shell:string;pid:number;state:"running"|"exited"|"interrupted";exitCode?:number;createdAt:string;endedAt?:string;actionId?:string;command?:string;logPath:string }
export interface ProjectAction { id:string;name:string;command:string;cwd:string;envRefs:string[];kind:"test"|"build"|"dev"|"initialize"|"custom" }
export interface Goal { title:string;conditions:string;steps:Array<{id:string;text:string;state:"pending"|"implemented"|"verified"|"blocked";source:string}>;validationCommands:string;revisions:Array<{at:string;source:string;summary:string}> }
export interface RunRecord { id:string;projectRoot:string;sessionId:string;createdAt:string;endedAt?:string;state:string;pid?:number;branch:string;model:string;input:unknown;result?:unknown;beforeRef?:string;afterRef?:string;events?:Record<string,unknown>[];unknownEffects?:string;processPresent?:boolean }
export interface LocalNotification { id:string;projectRoot:string;sessionId:string;runId:string;kind:string;title:string;body:string;createdAt:string;read:boolean;osState:string }
const runFile=promisify(execFile);
const key=(value:string)=>createHash("sha256").update(value).digest("hex");
const store=(root:string)=>path.join(root,".reverie","desktop");
export async function atomicJson(file:string,value:unknown):Promise<void>{await mkdir(path.dirname(file),{recursive:true});const temporary=`${file}.${randomUUID()}.tmp`;await writeFile(temporary,JSON.stringify(value,null,2),"utf8");await rename(temporary,file);}
export async function readJson<T>(file:string,fallback:T):Promise<T>{try{return JSON.parse(await readFile(file,"utf8")) as T;}catch(error){if((error as NodeJS.ErrnoException).code==="ENOENT")return fallback;throw error;}}
export function redact(value:unknown):unknown {
  if(Array.isArray(value))return value.map(redact);
  if(value && typeof value==="object")return Object.fromEntries(Object.entries(value).map(([name,data])=>[name,/(api.?key|password|secret|authorization|access.?token|refresh.?token)/i.test(name)?"[redacted]":redact(data)]));
  if(typeof value!=="string")return value;
  let text=value.replace(/(Bearer\s+)[\w.\-/+=]+/gi,"$1[redacted]").replace(/(https?:\/\/)[^\s/@]+:[^\s/@]+@/gi,"$1[redacted]@").replace(/((?:api[_-]?key|password|access[_-]?token|secret)\s*[=:]\s*)[^\s,;]+/gi,"$1[redacted]");
  for(const [name,secret] of Object.entries(process.env))if(/(api.?key|password|secret|token)/i.test(name) && secret && secret.length>=8)text=text.split(secret).join("[redacted]");return text;
}
export class TerminalManager {
  private entries=new Map<string,{record:TerminalRecord;process:pty.IPty;writes:Promise<unknown>;sequence:number;bytes:number}>();
  private history=new Map<string,TerminalRecord>();
  constructor(private emit:(event:Record<string,unknown>)=>void){}
  list(root?:string,session?:string):TerminalRecord[]{return [...this.history.values(),...[...this.entries.values()].map(item=>({...item.record}))].filter(item=>(!root || item.projectRoot.toLowerCase()===root.toLowerCase()) && (!session || item.sessionId===session)).sort((a,b)=>a.createdAt.localeCompare(b.createdAt));}
  async load(root:string,session:string):Promise<TerminalRecord[]>{const directory=path.join(store(root),"terminals");let files:string[];try{files=await readdir(directory);}catch(error){if((error as NodeJS.ErrnoException).code==="ENOENT")return this.list(root,session);throw error;}for(const file of files.filter(value=>/^[\w-]+\.log\.json$/.test(value))){const record=await readJson<TerminalRecord|null>(path.join(directory,file),null);if(!record || this.entries.has(record.id))continue;if(record.projectRoot.toLowerCase()!==root.toLowerCase())continue;if(record.state==="running")record.state="interrupted";this.history.set(record.id,record);}return this.list(root,session);}
  active(root?:string):TerminalRecord[]{return this.list(root).filter(item=>item.state==="running");}
  async create(projectRoot:string,sessionId:string,cwd=".",action?:ProjectAction):Promise<TerminalRecord>{
    if(!sessionId)throw new Error("Create or select a conversation before opening a terminal.");
    if(this.active().length>=16)throw new Error("The desktop allows at most 16 active user terminals.");
    const root=await realpath(projectRoot);const directory=await realpath(path.resolve(root,action?.cwd || cwd));if(!within(root,directory) || !(await stat(directory)).isDirectory())throw new Error("Terminal directory is outside this workspace.");
    const shell=process.platform==="win32" ? process.env.COMSPEC?.replace(/cmd\.exe$/i,"WindowsPowerShell\\v1.0\\powershell.exe") || "powershell.exe" : process.env.SHELL || "/bin/sh";
    const env:{[key:string]:string}={};for(const [name,value] of Object.entries(process.env))if(value!==undefined)env[name]=value;
    if(action)for(const name of action.envRefs){if(!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name) || process.env[name]===undefined)throw new Error(`Environment reference is unavailable: ${name}`);env[name]=process.env[name]!;}
    const args=process.platform==="win32" ? ["-NoLogo","-NoProfile",...(action?["-Command",action.command]:[])] : action?["-lc",action.command]:[];
    const id=randomUUID();const logPath=path.join(store(root),"terminals",`${id}.log`);await mkdir(path.dirname(logPath),{recursive:true});await writeFile(logPath,"");
    const processInstance=pty.spawn(shell,args,{name:"xterm-256color",cols:100,rows:24,cwd:directory,env});
    const record:TerminalRecord={id,projectRoot:root,sessionId,cwd:directory,shell,pid:processInstance.pid,state:"running",createdAt:new Date().toISOString(),logPath,actionId:action?.id,command:action?.command};
    const entry={record,process:processInstance,writes:Promise.resolve() as Promise<unknown>,sequence:0,bytes:0};this.entries.set(id,entry);
    processInstance.onData(data=>{entry.sequence++;entry.bytes+=Buffer.byteLength(data,"utf8");entry.writes=entry.writes.then(()=>appendFile(logPath,data,"utf8")).catch(error=>{this.emit({type:"terminal.error",terminalId:id,error:String(error)});});this.emit({type:"terminal.data",terminalId:id,project_root:root,session_id:sessionId,data,sequence:entry.sequence});});
    processInstance.onExit(event=>{record.state="exited";record.exitCode=event.exitCode;record.endedAt=new Date().toISOString();entry.writes=entry.writes.then(()=>atomicJson(`${logPath}.json`,record));this.emit({type:"terminal.exit",terminalId:id,project_root:root,session_id:sessionId,record:{...record}});});
    await atomicJson(`${logPath}.json`,record);return {...record};
  }
  private entry(id:string,root:string,sessionId:string){const item=this.entries.get(id);if(!item || item.record.projectRoot.toLowerCase()!==path.resolve(root).toLowerCase() || item.record.sessionId!==sessionId)throw new Error("Terminal belongs to a different conversation.");return item;}
  write(id:string,root:string,sessionId:string,data:string){const item=this.entry(id,root,sessionId);if(item.record.state!=="running")throw new Error("Terminal already exited.");item.process.write(data);}
  resize(id:string,root:string,sessionId:string,cols:number,rows:number){const item=this.entry(id,root,sessionId);if(item.record.state==="running")item.process.resize(Math.max(2,Math.min(500,Math.floor(cols))),Math.max(2,Math.min(300,Math.floor(rows))));}
  async read(id:string,root:string,sessionId:string){if(!this.entries.has(id)){const record=this.history.get(id);if(!record || record.projectRoot.toLowerCase()!==path.resolve(root).toLowerCase() || record.sessionId!==sessionId)throw new Error("Terminal belongs to a different conversation.");const logPath=path.join(store(root),"terminals",`${id}.log`);return {record:{...record},text:await readFile(logPath,"utf8")};}const item=this.entry(id,root,sessionId);const sequence=item.sequence;const bytes=item.bytes;await item.writes;return {record:{...item.record},sequence,text:(await readFile(item.record.logPath)).subarray(0,bytes).toString("utf8")};}
  async close(id:string,root:string,sessionId:string){const item=this.entry(id,root,sessionId);if(item.record.state!=="running")return;if(process.platform==="win32")await runFile("taskkill",["/pid",String(item.record.pid),"/t","/f"],{windowsHide:true}).catch(()=>item.process.kill());else item.process.kill();await item.writes;}
  async closeAll(){for(const item of this.list())if(item.state==="running")await this.close(item.id,item.projectRoot,item.sessionId);}
}
export async function actions(root:string):Promise<ProjectAction[]>{return readJson(path.join(root,".reverie","project-actions.json"),[]);}
export async function saveActions(root:string,value:ProjectAction[]):Promise<void>{if(!Array.isArray(value))throw new Error("Invalid project actions.");for(const action of value){if(!action.id || !action.name.trim() || !action.command.trim() || path.isAbsolute(action.cwd) || !within(root,path.resolve(root,action.cwd || ".")))throw new Error("Action needs a name, command and relative workspace directory.");if(!Array.isArray(action.envRefs) || action.envRefs.some(name=>!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)))throw new Error("Store environment variable names, not secret values.");}await atomicJson(path.join(root,".reverie","project-actions.json"),value);}
export async function loadGoal(root:string,session:string):Promise<Goal|null>{return readJson(path.join(store(root),"goals",`${key(session)}.json`),null);}
export async function saveGoal(root:string,session:string,value:Goal|null):Promise<void>{if(!session)throw new Error("Select a conversation before saving a goal.");await atomicJson(path.join(store(root),"goals",`${key(session)}.json`),value);}
export class RunJournal {
  private active=new Map<string,{record:RunRecord;writes:Promise<unknown>}>();
  private file(record:RunRecord){return path.join(store(record.projectRoot),"runs",`${record.id}.json`);}
  async start(root:string,sessionId:string,input:unknown,model:string):Promise<RunRecord>{let branch="";try{branch=(await gitOutput(root,["branch","--show-current"])).trim();}catch{/* non-Git workspace */}const record:RunRecord={id:randomUUID(),projectRoot:root,sessionId,createdAt:new Date().toISOString(),state:"queued",branch,model,input:redact(input)};await atomicJson(this.file(record),record);this.active.set(record.id,{record,writes:Promise.resolve()});return record;}
  async update(id:string,patch:Partial<RunRecord>){const item=this.active.get(id);if(!item)return;Object.assign(item.record,patch);item.writes=item.writes.then(()=>atomicJson(this.file(item.record),redact(item.record)));await item.writes;}
  event(id:string,event:Record<string,unknown>){const item=this.active.get(id);if(!item)return;const line=JSON.stringify({at:new Date().toISOString(),...redact(event) as Record<string,unknown>})+"\n";item.writes=item.writes.then(()=>appendFile(`${this.file(item.record)}.jsonl`,line,"utf8")).catch(error=>{item.record.unknownEffects=`Some event evidence could not be saved: ${String(error)}. Check files and processes before continuing.`;});}
  async finish(id:string,result:unknown,state:string){await this.update(id,{result:redact(result),state,endedAt:new Date().toISOString(),...(["interrupted","cancelled","failed"].includes(state)?{unknownEffects:"Check incomplete tools and live processes against the current workspace before continuing. No actions were replayed."}:{})});this.active.delete(id);}
  async list(root:string):Promise<RunRecord[]>{const directory=path.join(store(root),"runs");let files:string[];try{files=await readdir(directory);}catch(error){if((error as NodeJS.ErrnoException).code==="ENOENT")return [];throw error;}const result:RunRecord[]=[];for(const file of files.filter(name=>/^[\w-]+\.json$/.test(name))){const record=await readJson<RunRecord|null>(path.join(directory,file),null);if(!record)continue;if(!this.active.has(record.id) && ["running","queued","paused","waiting_pause"].includes(record.state)){record.state="interrupted";record.unknownEffects="The prior desktop did not record completion. Verify completed tools, files and processes; continuation never replays prior actions automatically.";}if(record.pid){try{process.kill(record.pid,0);record.processPresent=true;}catch{record.processPresent=false;}}result.push(record);}return result.sort((a,b)=>b.createdAt.localeCompare(a.createdAt));}
  async detail(root:string,id:string):Promise<RunRecord>{if(!/^[\w-]+$/.test(id))throw new Error("Invalid run ID.");const record=(await this.list(root)).find(item=>item.id===id);if(!record)throw new Error("Run record is unavailable.");let text="";try{text=await readFile(path.join(store(root),"runs",`${id}.json.jsonl`),"utf8");}catch(error){if((error as NodeJS.ErrnoException).code!=="ENOENT")throw error;}record.events=text.split("\n").filter(Boolean).flatMap(line=>{try{return [JSON.parse(line)]}catch{return []}});return record;}
  async export(root:string,id:string):Promise<string>{const record=await this.detail(root,id);const target=path.join(store(root),"exports",`${id}.md`);await mkdir(path.dirname(target),{recursive:true});await writeFile(target,`# Reverie run ${id}\n\nState: ${record.state}\nProject: ${record.projectRoot}\nSession: ${record.sessionId}\nModel: ${record.model}\nBranch: ${record.branch}\n\nImplementation, UI and verification must be assessed separately from the tool evidence below.\n\n\`\`\`json\n${JSON.stringify(redact(record),null,2)}\n\`\`\`\n`,"utf8");return target;}
}
