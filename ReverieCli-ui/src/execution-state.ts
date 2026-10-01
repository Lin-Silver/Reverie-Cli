import { normalizeProjectRoot } from "./drafts";
import type { StructuredDraft } from "./drafts";

export interface QueuedMessage extends StructuredDraft { id: string; projectRoot: string; sessionId: string; createdAt: number }
export function ownerKey(root: string, sessionId: string): string { return `${normalizeProjectRoot(root)}:${sessionId}`; }
export function loadQueue(root: string, id: string): QueuedMessage[] {
  try { return JSON.parse(localStorage.getItem(`reverie.queue.v1:${ownerKey(root, id)}`) ?? "[]") as QueuedMessage[]; }
  catch { return []; }
}
export function saveQueue(root: string, id: string, queue: QueuedMessage[]): string {
  try { localStorage.setItem(`reverie.queue.v1:${ownerKey(root, id)}`, JSON.stringify(queue)); return ""; }
  catch (error) { return error instanceof Error ? error.message : String(error); }
}
