/**
 * A small cache of already-fetched session transcripts.
 *
 * Switching sessions is a round trip to the core plus a transcript read, and the
 * chat view can only show a spinner while it waits. Sessions the user has
 * already opened in this window have not changed unless something in this window
 * changed them, so keeping the last few transcripts lets a switch back render
 * instantly and reconcile with the core afterwards.
 */

import type { SessionState } from "./types";

/** How many transcripts to keep. Enough for the sessions a user cycles between. */
export const SESSION_CACHE_LIMIT = 12;

export class SessionCache {
  private readonly entries = new Map<string, SessionState>();

  constructor(private readonly limit: number = SESSION_CACHE_LIMIT) {}

  /** The cached transcript for a session, or undefined when not cached. */
  get(sessionId: string): SessionState | undefined {
    const key = String(sessionId || "");
    const cached = this.entries.get(key);
    if (cached === undefined) return undefined;
    // Refresh recency: a session being read is a session in use.
    this.entries.delete(key);
    this.entries.set(key, cached);
    return cached;
  }

  /** Remember a transcript, evicting the least recently used one when full. */
  set(session: SessionState | null | undefined): void {
    const key = String(session?.id || "");
    if (!key) return;
    this.entries.delete(key);
    this.entries.set(key, session as SessionState);
    while (this.entries.size > this.limit) {
      const oldest = this.entries.keys().next();
      if (oldest.done) break;
      this.entries.delete(oldest.value);
    }
  }

  /** Forget one session, e.g. after it is deleted or archived. */
  delete(sessionId: string): void {
    this.entries.delete(String(sessionId || ""));
  }

  /** Forget everything, e.g. when the workspace changes. */
  clear(): void {
    this.entries.clear();
  }

  get size(): number {
    return this.entries.size;
  }
}
