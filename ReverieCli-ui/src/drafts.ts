/**
 * Crash-safe, per-conversation composer drafts.
 *
 * Every conversation keeps its own unsent composer text so that a sudden quit,
 * a crash, or a machine restart never loses what was typed. localStorage is the
 * store on purpose: its writes are synchronous and land before the frame that
 * triggered them can be interrupted, so the last keystroke survives even a hard
 * kill -- an IPC round trip to the main process could be cut off in flight.
 *
 * Session ids are only a per-project timestamp (`YYYYMMDD_HHMMSS_ffffff`), so
 * two projects can mint the same id. Keys therefore fold in the project root,
 * which keeps every conversation's draft independent instead of collapsing to
 * one shared slot.
 */

/** Prefix for every draft entry, so a project sweep can find them by scan. */
const DRAFT_KEY_PREFIX = "reverie.draft.v1:";
const STRUCTURED_PREFIX = "reverie.draft.v2:";
import type { ComposerAttachment } from "../electron/attachments";

export interface StructuredDraft { text: string; attachments: ComposerAttachment[] }
export function normalizeProjectRoot(root: string): string {
  const normalized = root.replaceAll("\\", "/").replace(/\/+$/, "");
  return /^[A-Za-z]:/.test(normalized) ? normalized.toLowerCase() : normalized;
}
function structuredKey(root: string, id: string): string {
  return `${STRUCTURED_PREFIX}${encodeSegment(normalizeProjectRoot(root))}:${encodeSegment(id)}`;
}
export function saveStructuredDraft(root: string, id: string, draft: StructuredDraft): string {
  try {
    if (draft.text || draft.attachments.length) localStorage.setItem(structuredKey(root, id), JSON.stringify(draft));
    else localStorage.removeItem(structuredKey(root, id));
    return "";
  } catch (error) { return error instanceof Error ? error.message : String(error); }
}
export function loadStructuredDraft(root: string, id: string): StructuredDraft {
  try {
    const stored = localStorage.getItem(structuredKey(root, id));
    if (stored) {
      const draft = JSON.parse(stored) as StructuredDraft;
      if (typeof draft.text === "string" && Array.isArray(draft.attachments)) return { text: draft.text, attachments: draft.attachments.map(item => item.status === "pending" ? { ...item, status: "cancelled", error: "导入被中断 / Import interrupted" } : item) };
    }
    return { text: localStorage.getItem(draftStorageKey(root, id)) ?? "", attachments: [] };
  } catch { return { text: "", attachments: [] }; }
}

/**
 * Placeholder session id for text typed before a conversation exists yet. The
 * first send mints the real session, so this slot is transient by nature.
 */
export const NEW_SESSION_DRAFT_ID = "__new__";

/** Encode one path/id segment so a delimiter inside it cannot forge a key. */
function encodeSegment(value: string): string {
  return encodeURIComponent(String(value ?? ""));
}

/** The localStorage key for one conversation's draft. */
export function draftStorageKey(projectRoot: string, sessionId: string): string {
  return `${DRAFT_KEY_PREFIX}${encodeSegment(projectRoot)}:${encodeSegment(sessionId)}`;
}

/** The key prefix shared by every draft belonging to one project. */
function projectKeyPrefix(projectRoot: string): string {
  return `${DRAFT_KEY_PREFIX}${encodeSegment(projectRoot)}:`;
}

/**
 * Persist (or clear) one conversation's draft. Empty text removes the entry so
 * abandoned drafts never accumulate. Storage failures (quota, private mode) are
 * swallowed: a lost draft must never break the composer.
 */
export function saveDraft(projectRoot: string, sessionId: string, text: string): void {
  if (!sessionId) return;
  const key = draftStorageKey(projectRoot, sessionId);
  try {
    if (text) localStorage.setItem(key, text);
    else localStorage.removeItem(key);
  } catch {
    // Non-fatal: persistence is best-effort.
  }
}

/** Remove one conversation's draft, e.g. after it is deleted. */
export function clearDraft(projectRoot: string, sessionId: string): void {
  if (!sessionId) return;
  try {
    localStorage.removeItem(draftStorageKey(projectRoot, sessionId));
    localStorage.removeItem(structuredKey(projectRoot, sessionId));
  } catch {
    // Non-fatal.
  }
}

/**
 * Load every stored draft for a project as a `{ sessionId: text }` map, ready to
 * seed the in-memory cache when a workspace opens. Malformed keys are skipped.
 */
export function loadProjectDrafts(projectRoot: string): Record<string, string> {
  const prefix = projectKeyPrefix(projectRoot);
  const drafts: Record<string, string> = {};
  try {
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (!key || !key.startsWith(prefix)) continue;
      const encodedId = key.slice(prefix.length);
      if (!encodedId) continue;
      let sessionId = "";
      try {
        sessionId = decodeURIComponent(encodedId);
      } catch {
        continue;
      }
      const text = localStorage.getItem(key);
      if (sessionId && text) drafts[sessionId] = text;
    }
  } catch {
    // Non-fatal: fall back to no restored drafts.
  }
  return drafts;
}

/** Remove every stored draft for a project, e.g. when the project is deleted. */
export function clearProjectDrafts(projectRoot: string): void {
  const prefix = projectKeyPrefix(projectRoot);
  const structured = `${STRUCTURED_PREFIX}${encodeSegment(normalizeProjectRoot(projectRoot))}:`;
  try {
    const doomed: string[] = [];
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (key && (key.startsWith(prefix) || key.startsWith(structured))) doomed.push(key);
    }
    doomed.forEach((key) => localStorage.removeItem(key));
  } catch {
    // Non-fatal.
  }
}
