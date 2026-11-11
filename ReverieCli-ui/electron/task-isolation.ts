import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { readFile, writeFile, mkdir, unlink, rename, lstat, realpath } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { workingSnapshot, createManaged, type ManagedWorkspace } from './isolated-workspaces';
import { gitOutput } from './workbench';
import { within } from './attachments';

const exec=promisify(execFile);
export type TaskWorkspace=ManagedWorkspace & {sourceRoot:string};
type Edit={file:string;before:Buffer|null;after:Buffer|null};
const equal=(a:Buffer|null,b:Buffer|null)=>a===null ? b===null : b!==null && a.equals(b);
async function bytes(root:string,file:string):Promise<Buffer|null>{
  const target=path.resolve(root,file);if(!within(root,target))throw new Error(`Task path escaped workspace: ${file}`);
  let parent=path.dirname(target);
  while(parent!==root){try{if(!within(root,await realpath(parent)))throw new Error(`Task path crosses a link: ${file}`);break;}catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error;parent=path.dirname(parent);}}
  try{if(!(await lstat(target)).isFile())throw new Error(`Only ordinary files can be incorporated automatically: ${file}`);return await readFile(target);}catch(error){if((error as NodeJS.ErrnoException).code==='ENOENT')return null;throw error;}
}
export async function isolateTask(root:string,runId:string):Promise<TaskWorkspace>{
  root=await realpath((await gitOutput(root,['rev-parse','--show-toplevel'])).trim());
  const base=await workingSnapshot(root,`refs/reverie/runs/${runId}/before`);
  const task=await createManaged(root,`task-${runId}`,base);
  const baseDirectory=path.join(root,'.reverie','desktop','task-bases',runId);await mkdir(baseDirectory,{recursive:true});
  const files=(await gitOutput(task.path,['ls-files','-z'])).split('\0').filter(Boolean);
  // Git filters/CRLF conversion are not a byte-preserving workspace snapshot.
  for(const file of files){
    const original=await bytes(root,file);if(original===null)throw new Error(`Workspace changed during snapshot: ${file}`);
    const destination=path.resolve(task.path,file);await mkdir(path.dirname(destination),{recursive:true});await writeFile(destination,original);
    const preserved=path.resolve(baseDirectory,file);if(!within(baseDirectory,preserved))throw new Error('Invalid snapshot path.');await mkdir(path.dirname(preserved),{recursive:true});await writeFile(preserved,original);
  }
  for(const file of files)if(!equal(await bytes(root,file),await bytes(baseDirectory,file)))throw new Error(`Workspace changed during snapshot; isolated result retained: ${file}`);
  return {...task,sourceRoot:root};
}
export async function incorporateTask(root:string,task:TaskWorkspace,runId:string):Promise<{conflicts:string[];files:string[];afterRef:string}>{
  root=await realpath(task.sourceRoot);
  const after=await workingSnapshot(task.path,`refs/reverie/runs/${runId}/after`);
  const candidates=[...new Set((await gitOutput(root,['ls-tree','-r','--name-only','-z',task.head])).split('\0').concat((await gitOutput(task.path,['ls-files','-z','--cached','--others','--exclude-standard'])).split('\0')).filter(Boolean))];
  const files:string[]=[];
  const conflicts:string[]=[];const edits:Edit[]=[];
  const directory=path.join(root,'.reverie','desktop','merges',runId);await mkdir(directory,{recursive:true});
  for(const file of candidates){
    const [base,result,current]=await Promise.all([bytes(path.join(root,'.reverie','desktop','task-bases',runId),file),bytes(task.path,file),bytes(root,file)]);
    if(equal(base,result))continue;
    files.push(file);
    if(equal(result,current))continue;
    if(equal(base,current)){edits.push({file,before:current,after:result});continue;}
    if(base===null || result===null || current===null || [base,result,current].some(value=>value.includes(0))){conflicts.push(file);continue;}
    const prefix=path.join(directory,randomUUID());
    await Promise.all([writeFile(`${prefix}.current`,current),writeFile(`${prefix}.base`,base),writeFile(`${prefix}.result`,result)]);
    try{const merged=await exec('git',['merge-file','-p',`${prefix}.current`,`${prefix}.base`,`${prefix}.result`],{windowsHide:true,encoding:'buffer',maxBuffer:128*1024*1024});edits.push({file,before:current,after:merged.stdout});}
    catch(error){if(typeof (error as {code?:unknown}).code==='number')conflicts.push(file);else throw error;}
  }
  // Check every path before touching any bytes. Conflicting results stay recoverable.
  for(const edit of edits)if(!equal(await bytes(root,edit.file),edit.before))conflicts.push(edit.file);
  if(conflicts.length)return {conflicts:[...new Set(conflicts)],files,afterRef:after};
  await workingSnapshot(root,`refs/reverie/runs/${runId}/before-incorporation`);
  for(const edit of edits){
    if(!equal(await bytes(root,edit.file),edit.before))throw new Error(`Workspace changed during incorporation; result retained: ${edit.file}`);
    const target=path.resolve(root,edit.file);
    if(edit.after===null)await unlink(target);
    else{await mkdir(path.dirname(target),{recursive:true});const temporary=path.join(path.dirname(target),`.reverie-${randomUUID()}.tmp`);await writeFile(temporary,edit.after);await rename(temporary,target);}
  }
  return {conflicts:[],files,afterRef:after};
}
