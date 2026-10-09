/** Keep bounded, idle kernels warm between turns, without sharing active runs. */
export class WorkerPool<T> {
  private idle: Array<{ key: string; worker: T }> = [];
  private active = new Set<T>();
  private closed = false;
  private reserving = 0;
  private preparing = new Map<string, Promise<void>>();

  constructor(private maximum: number, private dispose: (worker: T) => Promise<void>) {}

  async acquire(key: string, create: () => T): Promise<{ worker: T; reused: boolean }> {
    const preparing = this.preparing.get(key);
    if (preparing) await preparing;
    if (this.closed) throw new Error("Kernel pool is closing.");
    const index = this.idle.findIndex(item => item.key === key);
    if (index >= 0) {
      const [{ worker }] = this.idle.splice(index, 1);
      this.active.add(worker);
      return { worker, reused: true };
    }
    if (this.active.size + this.idle.length + this.reserving >= this.maximum) {
      const oldest = this.idle.shift();
      if (!oldest) throw new Error("No idle kernel is available.");
      this.reserving += 1;
      try { await this.dispose(oldest.worker); }
      finally { this.reserving -= 1; }
      if (this.closed) throw new Error("Kernel pool is closing.");
    }
    const worker = create();
    this.active.add(worker);
    return { worker, reused: false };
  }

  /** Prepare at most one idle kernel per workspace, without sending a model request. */
  prepare(key: string, create: () => T, initialize: (worker: T) => Promise<unknown>): Promise<void> {
    const pending = this.preparing.get(key);
    if (pending) return pending;
    if (this.closed || this.idle.some(item => item.key === key) || this.active.size + this.idle.length + this.reserving >= this.maximum) return Promise.resolve();
    const worker = create(); this.active.add(worker);
    const ready = Promise.resolve().then(() => initialize(worker)).then(
      () => this.release(key, worker, true),
      () => this.release(key, worker, false),
    ).finally(() => this.preparing.delete(key));
    this.preparing.set(key, ready);
    return ready;
  }

  async release(key: string, worker: T, reusable: boolean): Promise<void> {
    if (!this.active.delete(worker) && this.closed) return;
    if (reusable && !this.closed) this.idle.push({ key, worker });
    else await this.dispose(worker);
  }

  async close(): Promise<void> {
    this.closed = true;
    const workers = [...this.active, ...this.idle.map(item => item.worker)];
    this.active.clear();
    this.idle = [];
    await Promise.all(workers.map(this.dispose));
  }
}
