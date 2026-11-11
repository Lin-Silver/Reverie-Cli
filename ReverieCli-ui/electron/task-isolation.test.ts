import { mkdtemp, readFile, writeFile, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { expect,it } from 'vitest';
import { isolateTask,incorporateTask } from './task-isolation';
import { ExecutionCoordinator } from './execution-coordinator';
const exec=promisify(execFile);
async function fixture(){
  const root=await mkdtemp(path.join(tmpdir(),'aio-isolation-'));
  const git=async(...args:string[])=>(await exec('git',['-C',root,...args],{windowsHide:true})).stdout;
  await git('init','-b','main');await writeFile(path.join(root,'a.txt'),'base\n');await writeFile(path.join(root,'b.txt'),'base\n');
  await git('add','.');await git('-c','user.name=Test','-c','user.email=test@local.invalid','commit','-m','base');
  return {root,git};
}
it('incorporates only task changes and retains dirty bytes, untracked files and staging',async()=>{
  const {root,git}=await fixture();await writeFile(path.join(root,'a.txt'),'user staged\n');await git('add','a.txt');
  await writeFile(path.join(root,'a.txt'),'user unstaged\n');await writeFile(path.join(root,'new.txt'),'user file\n');
  const index=await git('diff','--cached','--binary');const id=randomUUID();const task=await isolateTask(root,id);
  expect(await readFile(path.join(task.path,'a.txt'),'utf8')).toBe('user unstaged\n');expect(await readFile(path.join(task.path,'new.txt'),'utf8')).toBe('user file\n');
  await writeFile(path.join(task.path,'b.txt'),'task change\n');await writeFile(path.join(root,'new.txt'),'later user file\n');
  const result=await incorporateTask(root,task,id);expect(result.conflicts).toEqual([]);
  expect(await readFile(path.join(root,'b.txt'),'utf8')).toBe('task change\n');expect(await readFile(path.join(root,'a.txt'),'utf8')).toBe('user unstaged\n');
  expect(await readFile(path.join(root,'new.txt'),'utf8')).toBe('later user file\n');expect(await git('diff','--cached','--binary')).toBe(index);
},30000);
it('retains conflicting task results without incorporating other files',async()=>{
  const {root}=await fixture();const id=randomUUID();const task=await isolateTask(root,id);
  await writeFile(path.join(root,'a.txt'),'user change\n');await writeFile(path.join(task.path,'a.txt'),'task change\n');await writeFile(path.join(task.path,'b.txt'),'another task change\n');
  expect((await incorporateTask(root,task,id)).conflicts).toEqual(['a.txt']);
  expect(await readFile(path.join(root,'a.txt'),'utf8')).toBe('user change\n');expect(await readFile(path.join(root,'b.txt'),'utf8')).toBe('base\n');
  expect(await readFile(path.join(task.path,'a.txt'),'utf8')).toBe('task change\n');
},30000);
it('shares four slots between isolated writers in the same repository',async()=>{
  const {root}=await fixture();const coordinator=new ExecutionCoordinator(()=>{});
  const entries=await Promise.all([0,1,2,3].map(i=>coordinator.acquire(root,String(i),false,true,true)));
  expect(entries.every(entry=>entry.state==='running')).toBe(true);
  const fifth=coordinator.acquire(root,'5',false,true,true);coordinator.release(entries[0].id);const granted=await fifth;
  for(const entry of [...entries.slice(1),granted])coordinator.release(entry.id);
});

it('isolates a workspace below the Git root and preserves byte-only task changes',async()=>{
  const {root,git}=await fixture();await mkdir(path.join(root,'nested'));
  await writeFile(path.join(root,'nested','file.txt'),'first\r\nsecond\r\n');
  await git('add','.');await git('-c','user.name=Test','-c','user.email=test@local.invalid','commit','-m','nested');
  const id=randomUUID();const task=await isolateTask(path.join(root,'nested'),id);
  expect(await readFile(path.join(task.path,'nested','file.txt'),'utf8')).toBe('first\r\nsecond\r\n');
  await writeFile(path.join(task.path,'nested','file.txt'),'first\nsecond\n');
  const result=await incorporateTask(path.join(root,'nested'),task,id);
  expect(result.conflicts).toEqual([]);
  expect(result.files).toContain('nested/file.txt');
  expect(await readFile(path.join(root,'nested','file.txt'),'utf8')).toBe('first\nsecond\n');
},30000);

it('incorporates a linked-checkout task into its selected owner and preserves both indexes',async()=>{
  const {root,git}=await fixture();await mkdir(path.join(root,'nested'));
  await writeFile(path.join(root,'nested','file.txt'),'base\n');
  await git('add','.');await git('-c','user.name=Test','-c','user.email=test@local.invalid','commit','-m','nested');
  const linked=`${root}-linked`;await git('worktree','add','--detach',linked,'HEAD');
  const linkedGit=async(...args:string[])=>(await exec('git',['-C',linked,...args],{windowsHide:true})).stdout;
  await writeFile(path.join(root,'nested','file.txt'),'primary staged\n');await git('add','nested/file.txt');
  await writeFile(path.join(root,'nested','file.txt'),'primary unstaged\n');
  await writeFile(path.join(linked,'nested','file.txt'),'linked staged\n');await linkedGit('add','nested/file.txt');
  await writeFile(path.join(linked,'nested','file.txt'),'linked unstaged\n');
  const primaryIndex=await git('diff','--cached','--binary');const linkedIndex=await linkedGit('diff','--cached','--binary');
  const workspace=path.join(linked,'nested');const id=randomUUID();const task=await isolateTask(workspace,id);
  expect(await readFile(path.join(task.path,'nested','file.txt'),'utf8')).toBe('linked unstaged\n');
  await writeFile(path.join(task.path,'nested','file.txt'),'linked task result\n');
  const result=await incorporateTask(workspace,task,id);
  expect(result.conflicts).toEqual([]);
  expect(await readFile(path.join(linked,'nested','file.txt'),'utf8')).toBe('linked task result\n');
  expect(await readFile(path.join(root,'nested','file.txt'),'utf8')).toBe('primary unstaged\n');
  expect(await git('diff','--cached','--binary')).toBe(primaryIndex);
  expect(await linkedGit('diff','--cached','--binary')).toBe(linkedIndex);
},30000);
