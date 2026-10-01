import { copyFile, mkdir, readFile, realpath, stat, writeFile } from "node:fs/promises";
import { createHash, randomUUID } from "node:crypto";
import path from "node:path";

export interface ComposerAttachment {
  name: string;
  relativePath: string;
  size: number;
  id?: string;
  sourcePath?: string;
  kind?: "reference" | "copy";
  status?: "pending" | "ready" | "failed" | "cancelled";
  error?: string;
  version?: string;
  mime?: string;
  width?: number;
  height?: number;
  thumbnail?: string;
  line?: number;
}

export const ATTACHMENT_LIMITS = { count: 20, fileBytes: 50 * 1024 * 1024, totalBytes: 200 * 1024 * 1024 };

export async function validateAttachments(projectRoot:string,items:ComposerAttachment[]):Promise<ComposerAttachment[]> {
  const root=await realpath(projectRoot);let total=0;const result:ComposerAttachment[]=[];
  for(const item of items){if(item.status && item.status!=="ready"){result.push(item);continue;}try{const target=await realpath(path.resolve(root,item.relativePath));if(!within(root,target))throw new Error("Attachment is outside this workspace.");const info=await stat(target);if(!info.isFile())throw new Error("Attachment is not a file.");const version=createHash("sha256").update(await readFile(target)).digest("hex");if(item.kind==="copy" && item.version && item.version!==version)throw new Error("Attachment copy changed; re-import it.");total+=info.size;if(info.size>ATTACHMENT_LIMITS.fileBytes || total>ATTACHMENT_LIMITS.totalBytes || items.length>ATTACHMENT_LIMITS.count)throw new Error("Attachment limits exceeded.");result.push({...item,size:info.size,version,status:"ready",error:undefined});}catch(error){result.push({...item,status:"failed",error:String(error)});}}
  return result;
}

export function within(root: string, file: string): boolean {
  const relative = path.relative(root, file);
  return relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative));
}

export async function importAttachments(projectRoot: string, sources: string[], copy = false): Promise<ComposerAttachment[]> {
  if (sources.length > ATTACHMENT_LIMITS.count) throw new Error("每条消息最多 20 个附件 / Maximum 20 attachments per message.");
  const root = await realpath(projectRoot);
  let total = 0;
  const result: ComposerAttachment[] = [];
  for (const source of sources) {
    const item: ComposerAttachment = { id: randomUUID(), name: path.basename(source) || "attachment", sourcePath: source, relativePath: "", size: 0, status: "failed" };
    try {
      if (!source || !path.isAbsolute(source)) throw new Error("不支持无磁盘路径的拖放；请用 @ 选择文件 / Drop a local file or use @.");
      const resolved = await realpath(source);
      const info = await stat(resolved);
      if (!info.isFile()) throw new Error("不支持文件夹；请用 @ 选择工作区文件 / Folders are not supported.");
      item.size = info.size;
      if (info.size > ATTACHMENT_LIMITS.fileBytes) throw new Error("单文件限制 50 MiB / File exceeds 50 MiB.");
      if (total + info.size > ATTACHMENT_LIMITS.totalBytes) throw new Error("附件总量限制 200 MiB / Total exceeds 200 MiB.");
      let target = resolved;
      item.kind = !copy && within(root, resolved) ? "reference" : "copy";
      if (item.kind === "copy") {
        const directory = path.join(root, ".reverie", "attachments");
        await mkdir(directory, { recursive: true });
        const safeName = item.name.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-");
        target = path.join(directory, `${item.id}-${safeName}`);
        await copyFile(resolved, target);
      }
      item.relativePath = path.relative(root, target).replaceAll("\\", "/");
      item.version = createHash("sha256").update(await readFile(target)).digest("hex");
      item.status = "ready";
      total += item.size;
    } catch (error) {
      item.error = error instanceof Error ? error.message : String(error);
    }
    result.push(item);
  }
  return result;
}

export async function saveClipboardImage(projectRoot: string, png: Buffer): Promise<ComposerAttachment> {
  if (!png.length) throw new Error("剪贴板没有图片 / Clipboard has no image.");
  if (png.length > ATTACHMENT_LIMITS.fileBytes) throw new Error("剪贴板图片超过 50 MiB / Image exceeds 50 MiB.");
  const root = await realpath(projectRoot);
  const id = randomUUID();
  const relativePath = `.reverie/attachments/${id}-clipboard.png`;
  await mkdir(path.join(root, ".reverie", "attachments"), { recursive: true });
  await writeFile(path.join(root, relativePath), png, { flag: "wx" });
  return { id, name: "clipboard.png", relativePath, size: png.length, kind: "copy", status: "ready", mime: "image/png", version: createHash("sha256").update(png).digest("hex") };
}
