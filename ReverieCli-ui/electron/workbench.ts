import { execFile, spawn } from "node:child_process";
import { promisify } from "node:util";
import { createHash } from "node:crypto";
import { readFile, realpath, stat, unlink } from "node:fs/promises";
import path from "node:path";
import { within } from "./attachments";

const run = promisify(execFile);
export type DiffScope = "working" | "staged" | "commit" | "branch" | "round";
export interface GitFile { path: string; oldPath?: string; status: string; binary: boolean; additions: number; deletions: number }
export interface GitSnapshot { root: string; version: string; indexVersion: string; head: string; branch: string; files: GitFile[]; scope: DiffScope; base: string; conflicts: string[] }
export interface FilePatch { path: string; version: string; text: string; totalLines: number; offset: number; next: number | null; binary: boolean; hunks: string[]; oldLine?:number;newLine?:number;hunkIndex?:number }
export interface Preview { path: string; relativePath: string; version: string; kind: "text" | "markdown" | "image" | "pdf" | "html" | "unsupported"; text?: string; url?: string; size: number; modifiedAt: string; totalLines: number; offset: number; next: number | null }
export interface PushPlan { version: string; head: string; branch: string; remote: string; target: string; url: string; commits: string[]; upstream: string }

export async function gitOutput(root: string, args: string[]): Promise<string> {
  try { return (await run("git", args, { cwd: root, windowsHide: true, maxBuffer: 128 * 1024 * 1024, timeout: 120_000 })).stdout; }
  catch (error) { const e = error as Error & { stderr?: string; stdout?: string }; throw new Error([e.message, e.stderr, e.stdout].filter(Boolean).join("\n")); }
}
const digest = (data: string | Buffer) => createHash("sha256").update(data).digest("hex");
async function repository(root: string): Promise<string> { return realpath((await gitOutput(root, ["rev-parse", "--show-toplevel"])).trim()); }
async function head(root: string): Promise<string> { try { return (await gitOutput(root, ["rev-parse", "--verify", "HEAD"])).trim(); } catch { return ""; } }
async function safeFile(root: string, file: string, missing = false): Promise<string> {
  if (!file || file.includes("\0")) throw new Error("A file path is required.");
  const target = path.resolve(root, file);
  if (!within(root, target) || target === root) throw new Error("File is outside this workspace.");
  let resolved: string;
  try { resolved = await realpath(target); }
  catch (error) { if (!missing || (error as NodeJS.ErrnoException).code !== "ENOENT") throw error; resolved = path.join(await realpath(path.dirname(target)), path.basename(target)); }
  if (!within(root, resolved)) throw new Error("Symlink target is outside this workspace.");
  return target;
}
function names(raw: string): GitFile[] {
  const fields = raw.split("\0"); const files: GitFile[] = [];
  for (let index = 0; index < fields.length && fields[index];) {
    const status = fields[index++]; const first = fields[index++];
    if (!first) break;
    const renamed = /^[RC]/.test(status);
    files.push({ path: renamed ? fields[index++] : first, oldPath: renamed ? first : undefined, status, binary: false, additions: 0, deletions: 0 });
  }
  return files;
}
async function versions(root: string): Promise<{version: string; indexVersion: string; head: string}> {
  const [working, staged, untracked, commit] = await Promise.all([
    gitOutput(root, ["diff", "--binary", "--no-ext-diff"]), gitOutput(root, ["diff", "--cached", "--binary", "--no-ext-diff"]),
    gitOutput(root, ["ls-files", "--others", "--exclude-standard", "-z"]), head(root),
  ]);
  const files: string[] = [];
  for (const file of untracked.split("\0").filter(Boolean)) { const target = await safeFile(root, file); const info = await stat(target); files.push(`${file}\0${info.size}\0${digest(await readFile(target))}`); }
  const indexVersion = digest(`${commit}\0${staged}`);
  return { head: commit, indexVersion, version: digest(`${indexVersion}\0${working}\0${files.join("\0")}`) };
}
async function diffArgs(root: string, scope: DiffScope, base = "", before = "", after = ""): Promise<string[]> {
  if (scope === "staged") return ["diff", "--cached"];
  if (scope === "working") return ["diff"];
  if (scope === "commit") { const ref = (await gitOutput(root, ["rev-parse", "--verify", `${base || "HEAD"}^{commit}`])).trim(); return ["show", "--format=", ref]; }
  if (scope === "round") {
    if (!before.startsWith("refs/reverie/runs/") || !after.startsWith("refs/reverie/runs/")) throw new Error("Select a persisted AI run snapshot.");
    const refs = await Promise.all([before, after].map(ref => gitOutput(root, ["rev-parse", "--verify", `${ref}^{commit}`])));
    return ["diff", refs[0].trim(), refs[1].trim()];
  }
  const ref = (await gitOutput(root, ["rev-parse", "--verify", `${base || "HEAD"}^{commit}`])).trim();
  const common = (await gitOutput(root, ["merge-base", "HEAD", ref])).trim(); return ["diff", common, "HEAD"];
}
export async function gitSnapshot(projectRoot: string, scope: DiffScope = "working", base = "", before = "", after = ""): Promise<GitSnapshot> {
  const root = await repository(projectRoot); const args = await diffArgs(root, scope, base, before, after);
  const [v, branch, changed, conflicts] = await Promise.all([versions(root), gitOutput(root, ["branch", "--show-current"]), gitOutput(root, [...args, "--name-status", "-z", "--find-renames", "--no-ext-diff", "--"]), gitOutput(root, ["diff", "--name-only", "--diff-filter=U", "-z"])]);
  const files = names(changed);
  if (scope === "working") for (const file of (await gitOutput(root, ["ls-files", "--others", "--exclude-standard", "-z"])).split("\0").filter(Boolean)) files.push({path: file, status: "?", binary: false, additions: 0, deletions: 0});
  for (const file of files) {
    if (file.status === "?") { const bytes = await readFile(await safeFile(root, file.path)); file.binary = bytes.includes(0); file.additions = file.binary ? 0 : bytes.toString("utf8").split("\n").length; }
    else {
      const count = (await gitOutput(root, [...args, "--numstat", "--no-ext-diff", "--", file.path, ...(file.oldPath ? [file.oldPath] : [])])).trim().split("\t");
      file.binary = count[0] === "-"; file.additions = Number(count[0]) || 0; file.deletions = Number(count[1]) || 0;
    }
  }
  return { ...v, version:["working","staged"].includes(scope)?v.version:digest(`${v.version}\0${scope}\0${args.join("\0")}`), root, scope, base, branch: branch.trim() || `detached ${v.head.slice(0,8)}`, files, conflicts: conflicts.split("\0").filter(Boolean) };
}
export async function gitPatch(projectRoot: string, payload: {scope: DiffScope; base?: string; before?: string; after?: string; file: string; oldPath?: string; offset?: number; ignoreWhitespace?: boolean}): Promise<FilePatch> {
  const root = await repository(projectRoot); const args = await diffArgs(root,payload.scope,payload.base,payload.before,payload.after);
  const v = await versions(root);
  let text: string;
  if (payload.scope === "working" && (await gitOutput(root,["ls-files","--others","--exclude-standard","-z"])).split("\0").includes(payload.file)) {
    const bytes = await readFile(await safeFile(root,payload.file)); text = bytes.includes(0) ? "Binary file (untracked)" : `diff --git a/${payload.file} b/${payload.file}\nnew file mode 100644\n--- /dev/null\n+++ b/${payload.file}\n@@ -0,0 +1,${bytes.toString("utf8").split("\n").length} @@\n${bytes.toString("utf8").split("\n").map(line => `+${line}`).join("\n")}`;
  } else text = await gitOutput(root,[...args,"--no-ext-diff","--find-renames",...(payload.ignoreWhitespace ? ["--ignore-all-space"] : []),"--",payload.file,...(payload.oldPath ? [payload.oldPath] : [])]);
  const lines = text.split("\n"); const offset = Math.max(0,payload.offset || 0); const end = Math.min(lines.length,offset + 2000);
  const hunks = text.match(/@@[^\n]*@@[^\n]*/g) ?? [];
  let oldLine=0,newLine=0,hunkIndex=-1;
  for(const line of lines.slice(0,offset)){const header=/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(line);if(header){oldLine=Number(header[1]);newLine=Number(header[2]);hunkIndex++;}else if(!/^(diff |index |--- |\+\+\+ |new file|deleted file|rename |similarity |Binary |GIT binary|\\)/.test(line)){if(!line.startsWith("+"))oldLine++;if(!line.startsWith("-"))newLine++;}}
  return {path: payload.file, version:["working","staged"].includes(payload.scope)?v.version:digest(`${v.version}\0${payload.scope}\0${args.join("\0")}`), text: lines.slice(offset,end).join("\n"), totalLines: lines.length,offset,next:end < lines.length ? end : null,binary: /Binary files|GIT binary patch|Binary file \(untracked\)/.test(text),hunks,oldLine,newLine,hunkIndex};
}
async function guarded(root: string, expected: string): Promise<void> { if (!expected || (await versions(root)).version !== expected) throw new Error("Files or index changed. Refresh and review before retrying."); }
async function apply(root: string, args: string[], patch: string): Promise<string> {
  return new Promise((resolve,reject) => { const child = spawn("git",["apply",...args,"-"],{cwd:root,windowsHide:true}); let output="";child.stdout.on("data",d=>{output+=d.toString()});child.stderr.on("data",d=>{output+=d.toString()});child.once("error",reject);child.once("exit",code=>code === 0 ? resolve(output) : reject(new Error(output || "Git patch failed.")));child.stdin.end(patch); });
}
export async function gitMutate(projectRoot: string, payload: {operation: "stage" | "unstage" | "revert" | "delete"; file: string; oldPath?: string; version: string; hunk?: number; confirmed?: boolean}): Promise<GitSnapshot> {
  const root = await repository(projectRoot); await safeFile(root,payload.file,true); if(payload.oldPath) await safeFile(root,payload.oldPath,true); await guarded(root,payload.version);
  if (["revert","delete"].includes(payload.operation) && payload.confirmed !== true) throw new Error("Confirm the exact file or hunk before discarding.");
  const files = [payload.file,...(payload.oldPath ? [payload.oldPath] : [])];
  if(payload.hunk !== undefined) {
    const staged = payload.operation === "unstage";
    const raw = await gitOutput(root,["diff",...(staged ? ["--cached"] : []),"--no-ext-diff","--",...files]);
    const start = raw.indexOf("@@"); const header = raw.slice(0,start); const pieces = raw.slice(start).split(/(?=^@@)/m);
    if (start < 0 || !pieces[payload.hunk] || /^(rename |Binary |GIT binary)/m.test(raw)) throw new Error("This change cannot be applied as a text hunk.");
    const patch = header + pieces[payload.hunk]; const args = [...(payload.operation !== "revert" ? ["--cached"] : []),...(payload.operation !== "stage" ? ["--reverse"] : []),"--whitespace=nowarn"];
    await apply(root,[...args,"--check"],patch); await guarded(root,payload.version); await apply(root,args,patch);
  } else if (payload.operation === "stage") await gitOutput(root,["add","--",...files]);
  else if (payload.operation === "unstage") await gitOutput(root,(await head(root)) ? ["restore","--staged","--source=HEAD","--",...files] : ["update-index","--force-remove","--",...files]);
  else if (payload.operation === "delete") {
    const untracked = (await gitOutput(root,["ls-files","--others","--exclude-standard","-z"])).split("\0");
    if (!untracked.includes(payload.file)) throw new Error("Only the selected untracked file can be deleted."); await unlink(await safeFile(root,payload.file));
  } else await gitOutput(root,["restore","--worktree","--",...files]);
  return gitSnapshot(root,payload.operation === "unstage" ? "staged" : "working");
}
export async function gitCommit(projectRoot: string, message: string, version: string): Promise<{head: string; output: string}> {
  const root = await repository(projectRoot); await guarded(root,version);
  if (!message.trim()) throw new Error("Enter a commit message.");
  if (!(await gitOutput(root,["diff","--cached","--name-only"])).trim()) throw new Error("The index is empty.");
  const output = await gitOutput(root,["commit","-m",message]); return {head:await head(root),output};
}
export async function gitPushPlan(projectRoot: string, remote = "", target = ""): Promise<PushPlan> {
  const root = await repository(projectRoot); const branch = (await gitOutput(root,["branch","--show-current"])).trim(); if (!branch) throw new Error("Create or select a branch before pushing a detached HEAD.");
  let upstream=""; try { upstream = (await gitOutput(root,["rev-parse","--abbrev-ref","--symbolic-full-name","@{upstream}"])).trim(); } catch { /* explicit destination is required below */ }
  let configuredRemote=""; try { configuredRemote = (await gitOutput(root,["config",`branch.${branch}.remote`])).trim(); } catch { /* no upstream */ }
  const selectedRemote = remote || configuredRemote; if (!selectedRemote || selectedRemote === "." || selectedRemote.startsWith("-")) throw new Error("Choose an existing remote explicitly.");
  const remotes=(await gitOutput(root,["remote"])).trim().split(/\r?\n/);if(!remotes.includes(selectedRemote)) throw new Error("Selected remote does not exist.");
  const destination = target || (upstream.startsWith(`${selectedRemote}/`) ? upstream.slice(selectedRemote.length+1) : branch);
  await gitOutput(root,["check-ref-format",`refs/heads/${destination}`]);
  const commit = await head(root); const tracking = `refs/remotes/${selectedRemote}/${destination}`; let commits: string[];
  try { await gitOutput(root,["rev-parse","--verify",tracking]); commits=(await gitOutput(root,["log","--format=%h %s",`${tracking}..HEAD`])).trim().split(/\r?\n/).filter(Boolean); }
  catch { commits=(await gitOutput(root,["log","--format=%h %s","HEAD"])).trim().split(/\r?\n/).filter(Boolean); }
  return {version:(await versions(root)).version,head:commit,branch,remote:selectedRemote,target:destination,url:(await gitOutput(root,["remote","get-url","--push",selectedRemote])).trim(),commits,upstream};
}
export async function gitPush(projectRoot: string, plan: PushPlan, confirmed: boolean): Promise<{output: string; remoteHead: string}> {
  if (!confirmed) throw new Error("Confirm the shown commits and push destination.");
  const root=await repository(projectRoot);const current=await gitPushPlan(root,plan.remote,plan.target);
  if(current.head!==plan.head || current.branch!==plan.branch || current.url!==plan.url || current.version!==plan.version) throw new Error("Push plan changed. Review again.");
  const output=await gitOutput(root,["push","--porcelain",...(!plan.upstream ? ["--set-upstream"] : []),plan.remote,`${plan.head}:refs/heads/${plan.target}`]);
  const remoteHead=(await gitOutput(root,["ls-remote","--heads",plan.remote,`refs/heads/${plan.target}`])).trim().split(/\s+/)[0];
  if(remoteHead!==plan.head) throw new Error("Push returned but the remote ref does not match the reviewed commit.");
  if(!plan.upstream && plan.branch){await gitOutput(root,["config",`branch.${plan.branch}.remote`,plan.remote]);await gitOutput(root,["config",`branch.${plan.branch}.merge`,`refs/heads/${plan.target}`]);}
  return {output,remoteHead};
}
export async function readPreview(projectRoot: string, file: string, offset = 0): Promise<Preview> {
  const root=await realpath(projectRoot); const target=await safeFile(root,file);const info=await stat(target);if(!info.isFile()) throw new Error("Select a file to preview.");
  const bytes=await readFile(target);const extension=path.extname(target).toLowerCase();
  const kind:Preview["kind"]= /\.(png|jpg|jpeg|webp|gif|bmp)$/.test(extension) ? "image" : extension === ".pdf" ? "pdf" : [".html",".htm"].includes(extension) ? "html" : [".md",".markdown"].includes(extension) ? "markdown" : bytes.includes(0) ? "unsupported" : "text";
  const value:Preview={path:target,relativePath:path.relative(root,target).replaceAll("\\","/"),version:digest(bytes),kind,size:info.size,modifiedAt:info.mtime.toISOString(),totalLines:0,offset:Math.max(0,offset),next:null};
  if(["image","pdf"].includes(kind)) { const mime=kind === "pdf" ? "application/pdf" : extension === ".jpg" || extension === ".jpeg" ? "image/jpeg" : `image/${extension.slice(1)}`; value.url=`data:${mime};base64,${bytes.toString("base64")}`; }
  else if(kind!=="unsupported") {const lines=bytes.toString("utf8").split("\n");value.totalLines=lines.length;const end=Math.min(lines.length,value.offset+2000);value.text=lines.slice(value.offset,end).join("\n");value.next=end<lines.length ? end : null;}
  return value;
}
