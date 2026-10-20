import { randomUUID } from "node:crypto";

export interface ViewInstance { projectRoot: string; sessionId: string; viewId: string; revision: number }

/** Host-owned leases. Frame-supplied identity can only match, never replace, a binding. */
export class ViewInstances {
  private entries = new Map<string, ViewInstance>();
  generation = 0;
  private selectedSession = "";

  selectSession(sessionId: string): boolean {
    if (this.selectedSession === sessionId) return false;
    this.clear(); this.selectedSession = sessionId;
    return true;
  }

  register(ref: ViewInstance): string {
    if (!this.selectedSession) this.selectedSession = ref.sessionId;
    for (const [id, entry] of this.entries) if (entry.projectRoot === ref.projectRoot && entry.sessionId === ref.sessionId && entry.viewId === ref.viewId) this.entries.delete(id);
    const id = randomUUID();
    this.entries.set(id, { ...ref });
    return id;
  }

  require(payload: Record<string, unknown>): ViewInstance {
    const ref = this.entries.get(String(payload.interactionId || ""));
    if (!ref || payload.sessionId !== ref.sessionId || payload.viewId !== ref.viewId || payload.revision !== ref.revision) {
      throw new Error("View instance expired or belongs to another session/revision. Reload the view.");
    }
    return ref;
  }

  revoke(id: string): ViewInstance | undefined { const ref = this.entries.get(id); this.entries.delete(id); return ref; }
  clear(): void { this.entries.clear(); this.selectedSession = ""; this.generation += 1; }
}
