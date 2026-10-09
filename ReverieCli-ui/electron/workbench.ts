import { execFile, spawn } from "node:child_process";
import { promisify } from "node:util";
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { StringDecoder } from "node:string_decoder";
import { readFile, readdir, realpath, rename, stat, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { within } from "./attachments";

const run = promisify(execFile);
export type DiffScope = "working" | "staged" | "commit" | "branch" | "round";
export interface GitFile { path: string; oldPath?: string; status: string; binary: boolean; additions: number; deletions: number; directory?: boolean }
export interface GitSnapshot { root: string; version: string; indexVersion: string; head: string; branch: string; files: GitFile[]; scope: DiffScope; base: string; conflicts: string[] }
export interface FilePatch { path: string; version: string; text: string; totalLines: number; offset: number; next: number | null; binary: boolean; hunks: string[]; oldLine?:number;newLine?:number;hunkIndex?:number }
export interface Preview { path: string; relativePath: string; version: string; kind: "text" | "markdown" | "image" | "pdf" | "html" | "unsupported"; text?: string; url?: string; size: number; modifiedAt: string; totalLines: number; offset: number; next: number | null }
export interface DirectoryEntry { name: string; path: string; directory: boolean; outside?: boolean }
export interface DirectoryListing { directory: string; entries: DirectoryEntry[]; truncated: boolean }
export interface EditorFile { relativePath: string; version: string; text: string; size: number; newline: "lf" | "crlf"; bom: boolean }
export interface PushPlan { version: string; head: string; branch: string; remote: string; target: string; url: string; commits: string[]; upstream: string }

export async function gitOutput(root: string, args: string[]): Promise<string> {
  try { return (await run("git", args, { cwd: root, windowsHide: true, maxBuffer: 8 * 1024 * 1024, timeout: 120_000 })).stdout; }
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
const untrackedCache = new Map<string, { stamp: string; hash: string; binary: boolean; additions: number; directory: boolean }>();
async function untrackedInfo(root: string, file: string, fresh = false) {
  const target = await safeFile(root, file);
  const info = await stat(target);
  const stamp = `${info.size}:${info.mtimeMs}:${info.ctimeMs}:${info.ino}`;
  const cached = untrackedCache.get(target);
  if (!fresh && cached?.stamp === stamp) return cached;
  const hash = createHash("sha256");
  let binary = false; let additions = 1;
  if (info.isFile()) {
    for await (const chunk of createReadStream(target)) {
      const bytes = chunk as Buffer;
      hash.update(bytes); binary ||= bytes.includes(0);
      for (const byte of bytes) if (byte === 10) additions++;
    }
  }
  const value = { stamp, hash: info.isFile() ? hash.digest("hex") : "directory", binary, additions: binary || !info.isFile() ? 0 : additions, directory: !info.isFile() };
  if (untrackedCache.size >= 2048) untrackedCache.clear();
  untrackedCache.set(target, value);
  return value;
}
async function versions(root: string, fresh = false): Promise<{version: string; indexVersion: string; head: string}> {
  const [working, staged, untracked, commit] = await Promise.all([
    gitOutput(root, ["diff", "--name-only", "-z", "--no-ext-diff"]), gitOutput(root, ["diff", "--cached", "--raw", "--no-abbrev", "-z", "--no-ext-diff"]),
    gitOutput(root, ["ls-files", "--others", "--exclude-standard", "-z"]), head(root),
  ]);
  const files: string[] = [];
  for (const file of [...new Set([...working.split("\0"),...untracked.split("\0")].filter(Boolean))]) {
    try{files.push(`${file}\0${(await untrackedInfo(root,file,fresh)).hash}`);}catch(error){if((error as NodeJS.ErrnoException).code!=="ENOENT")throw error;files.push(`${file}\0deleted`);}
  }
  const indexVersion = digest(`${commit}\0${staged}`);
  return { head: commit, indexVersion, version: digest(`${indexVersion}\0${working}\0${files.join("\0")}`) };
}
const PAGE_BYTES=2*1024*1024;
const LINE_BYTES=256*1024;

/** Read one directory at a time, so opening the explorer never scans the project. */
export async function listDirectory(projectRoot: string, directory = "."): Promise<DirectoryListing> {
  const root = await realpath(projectRoot);
  const target = directory === "." ? root : await safeFile(root, directory);
  const entries = (await readdir(target, { withFileTypes: true })).filter(entry => entry.name !== ".git");
  entries.sort((a, b) => Number(b.isDirectory()) - Number(a.isDirectory()) || a.name.localeCompare(b.name, undefined, { numeric: true }));
  const result = await Promise.all(entries.slice(0, 2000).map(async entry => {
    const file = path.join(target, entry.name);
    let directory = entry.isDirectory(); let outside = false;
    if (entry.isSymbolicLink()) {
      try { const resolved = await realpath(file); outside = !within(root, resolved); if (!outside) directory = (await stat(resolved)).isDirectory(); }
      catch { outside = true; }
    }
    return { name: entry.name, path: path.relative(root, file).replaceAll("\\", "/"), directory, ...(outside ? { outside: true } : {}) };
  }));
  return { directory: path.relative(root, target).replaceAll("\\", "/") || ".", entries: result, truncated: entries.length > 2000 };
}

export async function readEditorFile(projectRoot: string, file: string): Promise<EditorFile> {
  const root = await realpath(projectRoot); const target = await safeFile(root, file);
  if (path.relative(root, await realpath(target)).split(path.sep).includes(".git")) throw new Error("Git metadata cannot be edited here.");
  const info = await stat(target);
  if (!info.isFile() || info.size > PAGE_BYTES) throw new Error("Editing requires a UTF-8 text file up to 2 MiB. Use the preview or open it externally.");
  const bytes = await readFile(target); const text = bytes.toString("utf8");
  if (bytes.length > PAGE_BYTES || bytes.includes(0) || !Buffer.from(text, "utf8").equals(bytes)) throw new Error("This file is not UTF-8 text. Use the preview or open it externally.");
  if (/\r(?!\n)/.test(text) || /\r\n/.test(text) && /(^|[^\r])\n/.test(text)) throw new Error("Mixed line endings require an external editor.");
  const bom = text.startsWith("\uFEFF");
  return { relativePath: path.relative(root, target).replaceAll("\\", "/"), version: digest(bytes), text: text.replace(/^\uFEFF/, "").replaceAll("\r\n", "\n"), size: bytes.length, newline: text.includes("\r\n") ? "crlf" : "lf", bom };
}

const editorWrites = new Map<string, Promise<unknown>>();
export async function saveEditorFile(projectRoot: string, file: string, text: string, version: string): Promise<EditorFile> {
  const root = await realpath(projectRoot); const target = await realpath(await safeFile(root, file));
  const previous = editorWrites.get(target) || Promise.resolve();
  const saving = previous.catch(() => undefined).then(async () => {
    const current = await readEditorFile(root, file);
    if (current.version !== version) throw new Error("File changed on disk. Reload it before saving; your draft has been kept.");
    if (typeof text !== "string" || text.includes("\0") || /\r(?!\n)/.test(text)) throw new Error("Invalid text content.");
    text = text.replaceAll("\r\n", "\n");
    const bytes = Buffer.from(`${current.bom ? "\uFEFF" : ""}${current.newline === "crlf" ? text.replace(/\r?\n/g, "\r\n") : text}`, "utf8");
    if (bytes.length > PAGE_BYTES) throw new Error("The edited file exceeds the 2 MiB limit.");
    const temporary = `${target}.reverie-edit-${process.pid}-${Date.now()}`;
    try {
      await writeFile(temporary, bytes, { flag: "wx", mode: (await stat(target)).mode });
      if ((await readEditorFile(root, file)).version !== version) throw new Error("File changed on disk. Reload it before saving; your draft has been kept.");
      await rename(temporary, target);
    } finally { await unlink(temporary).catch(error => { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }); }
    return readEditorFile(root, file);
  });
  editorWrites.set(target, saving);
  try { return await saving; } finally { if (editorWrites.get(target) === saving) editorWrites.delete(target); }
}
async function textPage(stream:AsyncIterable<Buffer|string>,offset:number,patch=false){
  const decoder=new StringDecoder("utf8");const hash=createHash("sha256");let pending="",totalLines=0,bytes=0,pageBytes=0,binary=false,oldLine=0,newLine=0,hunkIndex=-1;const lines:string[]=[],hunks:string[]=[];let seed={oldLine:0,newLine:0,hunkIndex:-1};let full=false;
  const line=(value:string)=>{const length=Buffer.byteLength(value);if(length>LINE_BYTES)throw new Error("A line exceeds the preview limit (256 KiB). Open this file externally.");if(totalLines===offset)seed={oldLine,newLine,hunkIndex};if(totalLines>=offset && !full){if(lines.length>=2000 || pageBytes+length>PAGE_BYTES)full=true;else{lines.push(value);pageBytes+=length;}}
    if(patch){const header=/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(value);if(header){oldLine=Number(header[1]);newLine=Number(header[2]);hunkIndex++;if(hunks.length>=10000)throw new Error("The diff has too many hunks. Narrow the review scope.");hunks.push(value);}else if(!/^(diff |index |--- |\+\+\+ |new file|deleted file|rename |similarity |Binary |GIT binary|\\)/.test(value)){if(!value.startsWith("+"))oldLine++;if(!value.startsWith("-"))newLine++;}binary ||= /Binary files|GIT binary patch|Binary file \(untracked\)/.test(value);}
    totalLines++;};
  for await(const chunk of stream){const data=Buffer.isBuffer(chunk)?chunk:Buffer.from(chunk);hash.update(data);bytes+=data.length;if(!patch && data.includes(0))binary=true;if(binary && !patch){pending="";continue;}pending+=decoder.write(data);let start=0,next:number;while((next=pending.indexOf("\n",start))>=0){line(pending.slice(start,next));start=next+1;}pending=pending.slice(start);if(Buffer.byteLength(pending)>LINE_BYTES)throw new Error("A line exceeds the preview limit (256 KiB). Open this file externally.");}
  if(!binary || patch)line(pending+decoder.end());const end=offset+lines.length;
  return {text:lines.join("\n"),totalLines,offset,next:end<totalLines?end:null,binary,hunks,...seed,version:hash.digest("hex"),size:bytes};
}
async function gitTextPage(root:string,args:string[],offset:number){
  const child=spawn("git",args,{cwd:root,windowsHide:true});let error="";child.stderr.on("data",chunk=>{if(error.length<32768)error+=chunk.toString().slice(0,32768-error.length);});
  const finished=new Promise<void>((resolve,reject)=>{child.once("error",reject);child.once("close",code=>code===0?resolve():reject(new Error(error || "Git diff failed.")));});
  const timer=setTimeout(()=>child.kill(),120000);try{const [page]=await Promise.all([textPage(child.stdout,offset,true),finished]);return page;}catch(e){child.kill();throw e;}finally{clearTimeout(timer);}
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
  const counts = new Map<string, { binary: boolean; additions: number; deletions: number }>();
  const fields = (await gitOutput(root, [...args, "--numstat", "-z", "--find-renames", "--no-ext-diff", "--"])).split("\0");
  for (let index = 0; index < fields.length && fields[index]; index++) {
    const match = /^(\d+|-)\t(\d+|-)\t([\s\S]*)$/.exec(fields[index]);
    if (!match) continue;
    let file = match[3];
    if (!file) { index++; file = fields[++index]; }
    counts.set(file, { binary: match[1] === "-", additions: Number(match[1]) || 0, deletions: Number(match[2]) || 0 });
  }
  if (scope === "working") for (const file of (await gitOutput(root, ["ls-files", "--others", "--exclude-standard", "-z"])).split("\0").filter(Boolean)) files.push({path: file, status: "?", binary: false, additions: 0, deletions: 0});
  for (const file of files) {
    if (file.status === "?") { const info = await untrackedInfo(root, file.path); Object.assign(file, { binary: info.binary, additions: info.additions, directory: info.directory }); }
    else Object.assign(file, counts.get(file.path));
  }
  return { ...v, version:["working","staged"].includes(scope)?v.version:digest(`${v.version}\0${scope}\0${args.join("\0")}`), root, scope, base, branch: branch.trim() || `detached ${v.head.slice(0,8)}`, files, conflicts: conflicts.split("\0").filter(Boolean) };
}
export async function gitPatch(projectRoot: string, payload: {scope: DiffScope; base?: string; before?: string; after?: string; file: string; oldPath?: string; offset?: number; ignoreWhitespace?: boolean}): Promise<FilePatch> {
  const root = await repository(projectRoot); const args = await diffArgs(root,payload.scope,payload.base,payload.before,payload.after);
  const v = await versions(root);
  const offset=Math.max(0,Math.floor(payload.offset || 0));let page:Awaited<ReturnType<typeof textPage>>;
  if (payload.scope === "working" && (await gitOutput(root,["ls-files","--others","--exclude-standard","-z"])).split("\0").includes(payload.file)) {
    const target = await safeFile(root,payload.file);
    if (!(await stat(target)).isFile()) throw new Error("This entry is a nested repository or directory. Open it as a project to review its files.");
    const info=await untrackedInfo(root,payload.file);if(info.binary)page=await textPage((async function*(){yield Buffer.from("Binary file (untracked)");})(),offset,true);
    else {const decoder=new StringDecoder("utf8");const diff=async function*(){yield Buffer.from(`diff --git a/${payload.file} b/${payload.file}\nnew file mode 100644\n--- /dev/null\n+++ b/${payload.file}\n@@ -0,0 +1,${info.additions} @@\n+`);for await(const chunk of createReadStream(target))yield Buffer.from(decoder.write(chunk as Buffer).replaceAll("\n","\n+"));yield Buffer.from(decoder.end());};page=await textPage(diff(),offset,true);}
  } else page=await gitTextPage(root,[...args,"--no-ext-diff","--no-textconv","--find-renames",...(payload.ignoreWhitespace ? ["--ignore-all-space"] : []),"--",payload.file,...(payload.oldPath ? [payload.oldPath] : [])],offset);
  return {...page,path:payload.file,version:["working","staged"].includes(payload.scope)?v.version:digest(`${v.version}\0${payload.scope}\0${args.join("\0")}`)};
}
async function guarded(root: string, expected: string): Promise<void> { if (!expected || (await versions(root, true)).version !== expected) throw new Error("Files or index changed. Refresh and review before retrying."); }
async function apply(root: string, args: string[], patch: string): Promise<string> {
  return new Promise((resolve,reject) => { const child = spawn("git",["apply",...args,"-"],{cwd:root,windowsHide:true}); let output="";child.stdout.on("data",d=>{output+=d.toString()});child.stderr.on("data",d=>{output+=d.toString()});child.once("error",reject);child.once("exit",code=>code === 0 ? resolve(output) : reject(new Error(output || "Git patch failed.")));child.stdin.end(patch); });
}
export async function gitMutate(projectRoot: string, payload: {operation: "stage" | "unstage" | "revert" | "delete"; file: string; oldPath?: string; version: string; hunk?: number; confirmed?: boolean}): Promise<GitSnapshot> {
  const root = await repository(projectRoot); await safeFile(root,payload.file,true); if(payload.oldPath) await safeFile(root,payload.oldPath,true); await guarded(root,payload.version);
  const selectedInfo = await stat(path.resolve(root, payload.file)).catch(error => { if ((error as NodeJS.ErrnoException).code === "ENOENT") return null; throw error; });
  if (selectedInfo && !selectedInfo.isFile()) throw new Error("Directory operations are unavailable here. Select an individual file.");
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
  const extension=path.extname(target).toLowerCase();let kind:Preview["kind"]= /\.(png|jpg|jpeg|webp|gif|bmp)$/.test(extension) ? "image" : extension === ".pdf" ? "pdf" : [".html",".htm"].includes(extension) ? "html" : [".md",".markdown"].includes(extension) ? "markdown" : "text";
  const value:Preview={path:target,relativePath:path.relative(root,target).replaceAll("\\","/"),version:"",kind,size:info.size,modifiedAt:info.mtime.toISOString(),totalLines:0,offset:Math.max(0,Math.floor(offset)),next:null};
  if(["image","pdf"].includes(kind)) {if(info.size>20*1024*1024)throw new Error("This media file exceeds the preview limit (20 MiB). Open it externally.");const bytes=await readFile(target);value.version=digest(bytes);const mime=kind === "pdf" ? "application/pdf" : extension === ".jpg" || extension === ".jpeg" ? "image/jpeg" : `image/${extension.slice(1)}`;value.url=`data:${mime};base64,${bytes.toString("base64")}`;}
  else {const page=await textPage(createReadStream(target),value.offset);if(page.binary)kind="unsupported";Object.assign(value,{version:page.version,kind,totalLines:page.totalLines,text:kind==="unsupported"?undefined:page.text,next:page.next});}
  return value;
}
