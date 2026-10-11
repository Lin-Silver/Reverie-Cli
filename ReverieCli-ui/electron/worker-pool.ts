/** Reuse one recent kernel briefly, without retaining a kernel for every chat. */
export class WorkerPool<T> {
  private idle: Array<{ key: string; worker: T; timer: ReturnType<typeof setTimeout> }> = [];
  private active = new Set<T>();
  private closed = false;
  private reserving = 0;
  private disposing = new Set<Promise<void>>();

  constructor(private maximum: number, private dispose: (worker: T) => Promise<void>, private idleTimeoutMs = 30_000) {}

  private destroy(worker: T): Promise<void> {
    const pending = Promise.resolve().then(() => this.dispose(worker)).finally(() => this.disposing.delete(pending));
    this.disposing.add(pending);
    return pending;
  }

  async acquire(key: string, create: () => T): Promise<{ worker: T; reused: boolean }> {
    if (this.closed) throw new Error("Kernel pool is closing.");
    const index = this.idle.findIndex(item => item.key === key);
    if (index >= 0) {
      const [{ worker, timer }] = this.idle.splice(index, 1);
      clearTimeout(timer);
      this.active.add(worker);
      return { worker, reused: true };
    }
    if (this.active.size + this.idle.length + this.reserving >= this.maximum) {
      const oldest = this.idle.shift();
      if (!oldest) throw new Error("No idle kernel is available.");
      this.reserving += 1;
      clearTimeout(oldest.timer);
      try { await this.destroy(oldest.worker); }
      finally { this.reserving -= 1; }
      if (this.closed) throw new Error("Kernel pool is closing.");
    }
    const worker = create();
    this.active.add(worker);
    return { worker, reused: false };
  }

  async release(key: string, worker: T, reusable: boolean): Promise<void> {
    if (!this.active.delete(worker)) return;
    if (!reusable || this.closed) { await this.destroy(worker); return; }
    const old = this.idle.shift();
    const timer = setTimeout(() => {
      const index = this.idle.findIndex(item => item.worker === worker);
      if (index < 0) return;
      this.idle.splice(index, 1);
      void this.destroy(worker).catch(error => console.error("Idle kernel cleanup failed:", error));
    }, this.idleTimeoutMs);
    timer.unref?.();
    this.idle.push({ key, worker, timer });
    if (old) { clearTimeout(old.timer); await this.destroy(old.worker); }
  }

  async close(): Promise<void> {
    this.closed = true;
    const workers = [...this.active, ...this.idle.map(item => item.worker)];
    this.idle.forEach(item => clearTimeout(item.timer));
    this.active.clear();
    this.idle = [];
    await Promise.all([...workers.map(worker => this.destroy(worker)), ...this.disposing]);
  }
}
