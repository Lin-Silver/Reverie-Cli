import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { gitCommit, gitMutate, gitPatch, gitPush, gitPushPlan, gitSnapshot, readPreview } from "./workbench";

const roots:string[]=[];
const git=(root:string,...args:string[])=>execFileSync("git",args,{cwd:root,encoding:"utf8",windowsHide:true}).trim();
async function fixture(){const root=await mkdtemp(path.join(tmpdir(),"reverie-workbench-"));roots.push(root);git(root,"init","-b","main");git(root,"config","user.name","Acceptance");git(root,"config","user.email","acceptance@local.invalid");await writeFile(path.join(root,"two hunks.txt"),Array.from({length:40},(_,i)=>`line ${i+1}`).join("\n")+"\n");git(root,"add",".");git(root,"commit","-m","Initial fixture");return root;}
afterEach(async()=>{for(const root of roots.splice(0))await rm(root,{recursive:true,force:true,maxRetries:10,retryDelay:100});});
describe("real Git workbench",()=>{
  it("retains exact source line numbers and hunk identity across diff pages",async()=>{const root=await fixture();const file=path.join(root,"large.txt");await writeFile(file,Array.from({length:6000},(_,i)=>`original ${i+1}`).join("\n")+"\n");git(root,"add","large.txt");git(root,"commit","-m","Large fixture");await writeFile(file,Array.from({length:6000},(_,i)=>`changed ${i+1}`).join("\n")+"\n");const page=await gitPatch(root,{scope:"working",file:"large.txt",offset:2000});expect(page.text.split("\n")[0]).toBe("-original 1996");expect(page.oldLine).toBe(1996);expect(page.newLine).toBe(1);expect(page.hunkIndex).toBe(0);expect(page.next).toBe(4000);});
  it("separates working deletion, binary changes, untracked files and staged rename metadata",async()=>{const root=await fixture();await writeFile(path.join(root,"delete.txt"),"tracked\n");await writeFile(path.join(root,"binary.bin"),Buffer.from([0,1,2]));git(root,"add",".");git(root,"commit","-m","Status fixture");git(root,"mv","two hunks.txt","renamed.txt");await rm(path.join(root,"delete.txt"));await writeFile(path.join(root,"binary.bin"),Buffer.from([0,3,4]));await writeFile(path.join(root,"new.txt"),"untracked\n");const working=await gitSnapshot(root);expect(working.files.find(item=>item.path==="delete.txt")?.status).toBe("D");expect(working.files.find(item=>item.path==="binary.bin")?.binary).toBe(true);expect(working.files.find(item=>item.path==="new.txt")?.status).toBe("?");const staged=await gitSnapshot(root,"staged");expect(staged.files.find(item=>item.path==="renamed.txt")?.oldPath).toBe("two hunks.txt");});
  it("reports actual merge conflicts separately without modifying either index stage",async()=>{const root=await fixture();git(root,"checkout","-b","other");await writeFile(path.join(root,"two hunks.txt"),"other\n");git(root,"add",".");git(root,"commit","-m","Other");git(root,"checkout","main");await writeFile(path.join(root,"two hunks.txt"),"main\n");git(root,"add",".");git(root,"commit","-m","Main");expect(()=>git(root,"merge","other")).toThrow();const before=git(root,"ls-files","--unmerged");expect((await gitSnapshot(root)).conflicts).toContain("two hunks.txt");expect(git(root,"ls-files","--unmerged")).toBe(before);});
  it("partially stages, unstages and reverts a selected hunk while preserving the earlier index",async()=>{
    const root=await fixture();const file=path.join(root,"two hunks.txt");let value=await readFile(file,"utf8");value=value.replace("line 2\n","staged old\n");await writeFile(file,value);git(root,"add",".");value=value.replace("line 16\n","working first\n").replace("line 34\n","working second\n");await writeFile(file,value);
    const originalIndex=git(root,"show",":two hunks.txt");const snapshot=await gitSnapshot(root);const patch=await gitPatch(root,{scope:"working",file:"two hunks.txt"});expect(patch.hunks).toHaveLength(2);
    await gitMutate(root,{operation:"stage",file:"two hunks.txt",version:snapshot.version,hunk:0});expect(git(root,"show",":two hunks.txt")).toContain("working first");expect(git(root,"diff","--","two hunks.txt")).toContain("working second");
    const staged=await gitPatch(root,{scope:"staged",file:"two hunks.txt"});expect(staged.hunks).toHaveLength(2);await gitMutate(root,{operation:"unstage",file:"two hunks.txt",version:staged.version,hunk:1});expect(git(root,"show",":two hunks.txt")).toBe(originalIndex);
    const next=await gitPatch(root,{scope:"working",file:"two hunks.txt"});await gitMutate(root,{operation:"revert",file:"two hunks.txt",version:next.version,hunk:0,confirmed:true});expect(await readFile(file,"utf8")).toContain("working second");expect(await readFile(file,"utf8")).not.toContain("working first");expect(git(root,"show",":two hunks.txt")).toBe(originalIndex);
  });
  it("rejects stale snapshots, index locks and unconfirmed untracked deletion",async()=>{
    const root=await fixture();await writeFile(path.join(root,"new file.txt"),"new\n");const snapshot=await gitSnapshot(root);await writeFile(path.join(root,"new file.txt"),"changed\n");await expect(gitMutate(root,{operation:"stage",file:"new file.txt",version:snapshot.version})).rejects.toThrow("changed");
    const current=await gitSnapshot(root);await writeFile(path.join(root,".git/index.lock"),"");await expect(gitMutate(root,{operation:"stage",file:"new file.txt",version:current.version})).rejects.toThrow("index.lock");await rm(path.join(root,".git/index.lock"));
    await expect(gitMutate(root,{operation:"delete",file:"new file.txt",version:current.version})).rejects.toThrow("Confirm");expect(await readFile(path.join(root,"new file.txt"),"utf8")).toBe("changed\n");
  });
  it("commits only the exact reviewed index and verifies an actual bare remote ref",async()=>{
    const root=await fixture();const remote=await mkdtemp(path.join(tmpdir(),"reverie-bare-"));roots.push(remote);git(remote,"init","--bare");git(root,"remote","add","origin",remote);
    const file=path.join(root,"two hunks.txt");const initial=await readFile(file,"utf8");await writeFile(file,initial.replace("line 2\n","commit first\n").replace("line 34\n","keep local\n"));const patch=await gitPatch(root,{scope:"working",file:"two hunks.txt"});await gitMutate(root,{operation:"stage",file:"two hunks.txt",version:patch.version,hunk:0});
    const staged=await gitSnapshot(root,"staged");const commit=await gitCommit(root,"Partial index",staged.version);expect(git(root,"show","HEAD:two hunks.txt")).toContain("commit first");expect(git(root,"show","HEAD:two hunks.txt")).not.toContain("keep local");expect(await readFile(file,"utf8")).toContain("keep local");
    const plan=await gitPushPlan(root,"origin","main");expect(plan.head).toBe(commit.head);const result=await gitPush(root,plan,true);expect(result.remoteHead).toBe(commit.head);expect(git(remote,"rev-parse","refs/heads/main")).toBe(commit.head);
  });
  it("keeps form data and staged content after a real commit hook failure",async()=>{
    const root=await fixture();await writeFile(path.join(root,"new.txt"),"staged\n");git(root,"add",".");await writeFile(path.join(root,".git/hooks/pre-commit"),"#!/bin/sh\necho acceptance-hook-failed >&2\nexit 1\n",{mode:0o755});const before=git(root,"diff","--cached");const snapshot=await gitSnapshot(root,"staged");await expect(gitCommit(root,"This message remains",snapshot.version)).rejects.toThrow("acceptance-hook-failed");expect(git(root,"diff","--cached")).toBe(before);
  });
  it("pages a large preview without escaping through parent or symlink paths",async()=>{
    const root=await fixture();await mkdir(path.join(root,"docs"));await writeFile(path.join(root,"docs/large.md"),Array.from({length:5001},(_,i)=>`line ${i}`).join("\n"));const preview=await readPreview(root,"docs/large.md");expect(preview.totalLines).toBe(5001);expect(preview.next).toBe(2000);expect((await readPreview(root,"docs/large.md",4000)).next).toBeNull();await expect(readPreview(root,"../outside.txt")).rejects.toThrow("outside");
  });
  it("bounds preview payloads and rejects oversized single lines and media clearly",async()=>{
    const root=await fixture();await writeFile(path.join(root,"wide.txt"),("a".repeat(10000)+"\n").repeat(800));
    const preview=await readPreview(root,"wide.txt");expect(Buffer.byteLength(preview.text || "")).toBeLessThanOrEqual(2*1024*1024);expect(preview.next).not.toBeNull();
    await writeFile(path.join(root,"single.txt"),"a".repeat(300000));await expect(readPreview(root,"single.txt")).rejects.toThrow(/line|externally/);
    await writeFile(path.join(root,"huge.png"),Buffer.alloc(21*1024*1024));await expect(readPreview(root,"huge.png")).rejects.toThrow(/20|externally/);
  });
});
