import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm, unlink, writeFile, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { archiveManaged, archivePlan, copyPlan, createManaged, listManaged, restoreManaged } from "./isolated-workspaces";

const roots:string[]=[];
const git=(root:string,...args:string[])=>execFileSync("git",args,{cwd:root,encoding:"utf8",windowsHide:true}).trim();
async function fixture(){const root=await mkdtemp(path.join(tmpdir(),"reverie-worktrees-"));roots.push(root);git(root,"init","-b","main");git(root,"config","user.name","Acceptance");git(root,"config","user.email","acceptance@local.invalid");await writeFile(path.join(root,"file.txt"),"original\n");await writeFile(path.join(root,"deleted.txt"),"delete me\n");await writeFile(path.join(root,".gitignore"),"ignored.bin\n");git(root,"add",".");git(root,"commit","-m","Base");return root;}
afterEach(async()=>{for(const root of roots.splice(0)){const actual=path.resolve(root);if(!actual.startsWith(path.resolve(tmpdir())+path.sep))throw new Error("Unsafe test cleanup");await rm(actual,{recursive:true,force:true,maxRetries:10,retryDelay:100});}});
describe("recoverable managed worktrees",()=>{
  it("copies only reviewed modifications and deletion while preserving the source index",async()=>{
    const root=await fixture();await writeFile(path.join(root,"file.txt"),"changed\n");await unlink(path.join(root,"deleted.txt"));await writeFile(path.join(root,"new.txt"),"untracked\n");git(root,"add","file.txt");const originalIndex=git(root,"diff","--cached");const plan=await copyPlan(root);
    const item=await createManaged(root,"selected","HEAD",["file.txt","deleted.txt"],plan.version);
    expect(await readFile(path.join(item.path,"file.txt"),"utf8")).toBe("changed\n");await expect(readFile(path.join(item.path,"deleted.txt"))).rejects.toThrow();await expect(readFile(path.join(item.path,"new.txt"))).rejects.toThrow();expect(git(root,"diff","--cached")).toBe(originalIndex);expect(git(item.path,"rev-parse","--abbrev-ref","HEAD")).toBe("HEAD");
  });
  it("retains unpushed ancestry, dirty bytes, untracked and ignored files through archive and restore",async()=>{
    const root=await fixture();const item=await createManaged(root,"archive","HEAD");await writeFile(path.join(item.path,"file.txt"),"unpushed commit\n");git(item.path,"add",".");git(item.path,"commit","-m","Unpushed local commit");const unpushed=git(item.path,"rev-parse","HEAD");await writeFile(path.join(item.path,"file.txt"),"working after commit\n");await writeFile(path.join(item.path,"new.txt"),"untracked data\n");await writeFile(path.join(item.path,"ignored.bin"),"ignored bytes\n");const primaryHead=git(root,"rev-parse","HEAD");const primaryIndex=git(root,"write-tree");const plan=await archivePlan(root,item.id);
    const archived=await archiveManaged(root,item.id,plan.version,plan.ignored,[]);expect(archived.state).toBe("archived");await expect(readFile(path.join(item.path,"file.txt"))).rejects.toThrow();expect(git(root,"merge-base","--is-ancestor",unpushed,archived.snapshotRef!)).toBe("");
    const restored=await restoreManaged(root,item.id);expect(restored.state).toBe("active");expect(await readFile(path.join(item.path,"file.txt"),"utf8")).toBe("working after commit\n");expect(await readFile(path.join(item.path,"new.txt"),"utf8")).toBe("untracked data\n");expect(await readFile(path.join(item.path,"ignored.bin"),"utf8")).toBe("ignored bytes\n");expect(git(root,"rev-parse","HEAD")).toBe(primaryHead);expect(git(root,"write-tree")).toBe(primaryIndex);expect(await listManaged(item.path)).toHaveLength(1);
  });
  it("refuses stale archive/copy plans, missing ignored choices and embedded repositories",async()=>{
    const root=await fixture();await writeFile(path.join(root,"file.txt"),"copy before\n");const copy=await copyPlan(root);await writeFile(path.join(root,"file.txt"),"copy after\n");await expect(createManaged(root,"stale","HEAD",copy.files,copy.version)).rejects.toThrow("changed");const item=await createManaged(root,"safe","HEAD");await writeFile(path.join(item.path,"ignored.bin"),"keep");const plan=await archivePlan(root,item.id);await expect(archiveManaged(root,item.id,plan.version,[],[])).rejects.toThrow("every ignored");await writeFile(path.join(item.path,"file.txt"),"external change\n");await expect(archiveManaged(root,item.id,plan.version,plan.ignored,[])).rejects.toThrow("changed");await mkdir(path.join(item.path,"nested"));git(path.join(item.path,"nested"),"init");await expect(archivePlan(root,item.id)).rejects.toThrow("Embedded");expect(await readFile(path.join(item.path,"ignored.bin"),"utf8")).toBe("keep");await expect(createManaged(root,"../escape","HEAD")).rejects.toThrow("name");
  });
});
