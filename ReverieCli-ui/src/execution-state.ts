import { normalizeProjectRoot } from "./drafts";
import type { StructuredDraft } from "./drafts";

export interface QueuedMessage extends StructuredDraft { id: string; projectRoot: string; sessionId: string;assistantId?:'aio'; createdAt: number; configuration?: Record<string, unknown>; configurationRevision?: number }
export function ownerKey(root: string, sessionId: string,assistantId?:'aio'): string { return `${assistantId==='aio'?'assistant:aio':normalizeProjectRoot(root)}:${sessionId}`; }
export function loadQueue(root: string, id: string,assistantId?:'aio'): QueuedMessage[] {
  try { return JSON.parse(localStorage.getItem(`reverie.queue.v1:${ownerKey(root, id,assistantId)}`) ?? "[]") as QueuedMessage[]; }
  catch { return []; }
}
export function saveQueue(root: string, id: string, queue: QueuedMessage[],assistantId?:'aio'): string {
  try { localStorage.setItem(`reverie.queue.v1:${ownerKey(root, id,assistantId)}`, JSON.stringify(queue)); return ""; }
  catch (error) { return error instanceof Error ? error.message : String(error); }
}
