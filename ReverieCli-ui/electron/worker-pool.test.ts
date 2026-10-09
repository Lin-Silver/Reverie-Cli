import { describe, expect, it, vi } from "vitest";
import { WorkerPool } from "./worker-pool";

describe("warm kernels", () => {
  it("prepares one kernel in advance and shares preparation with the first request", async () => {
    let finish!: () => void;
    const pool = new WorkerPool<object>(2, vi.fn(async () => {}));
    const worker = {}; const create = vi.fn(() => worker);
    const initialize = vi.fn(() => new Promise<void>(resolve => { finish = resolve; }));
    const prepared = pool.prepare("project", create, initialize);
    expect(pool.prepare("project", create, initialize)).toBe(prepared);
    const acquired = pool.acquire("project", create);
    await Promise.resolve(); expect(initialize).toHaveBeenCalledTimes(1);
    finish(); await prepared;
    expect(await acquired).toEqual({ worker, reused: true });
    expect(create).toHaveBeenCalledTimes(1);
    await pool.close();
  });

  it("discards failed preparation and permits a fresh kernel on request", async () => {
    const dispose = vi.fn(async () => {}); const pool = new WorkerPool<object>(1, dispose);
    await pool.prepare("project", () => ({}), async () => { throw new Error("initialization failed"); });
    expect(dispose).toHaveBeenCalledTimes(1);
    expect((await pool.acquire("project", () => ({}))).reused).toBe(false);
    await pool.close();
  });
  it("reuses idle kernels and keeps simultaneous runs separate", async () => {
    const dispose = vi.fn(async () => {});
    const pool = new WorkerPool<object>(2, dispose);
    const first = await pool.acquire("project", () => ({}));
    const parallel = await pool.acquire("project", () => ({}));
    expect(parallel.worker).not.toBe(first.worker);
    await pool.release("project", first.worker, true);
    expect(await pool.acquire("project", () => { throw new Error("unexpected spawn"); })).toEqual({ worker: first.worker, reused: true });
    await pool.release("project", first.worker, true);
    await pool.release("project", parallel.worker, true);
    await pool.close();
    expect(dispose).toHaveBeenCalledTimes(2);
  });

  it("evicts idle kernels at capacity and discards failed runs", async () => {
    const dispose = vi.fn(async () => {});
    const pool = new WorkerPool<object>(1, dispose);
    const first = await pool.acquire("a", () => ({}));
    await pool.release("a", first.worker, true);
    const second = await pool.acquire("b", () => ({}));
    expect(dispose).toHaveBeenCalledWith(first.worker);
    await pool.release("b", second.worker, false);
    expect(dispose).toHaveBeenCalledTimes(2);
    expect((await pool.acquire("b", () => ({}))).reused).toBe(false);
    await pool.close();
  });

  it("reserves an evicted slot while asynchronous disposal is still running", async () => {
    let finish!: () => void;
    const pool = new WorkerPool<object>(1, () => new Promise<void>(resolve => { finish = resolve; }));
    const first = await pool.acquire("a", () => ({}));
    await pool.release("a", first.worker, true);
    const pending = pool.acquire("b", () => ({}));
    await expect(pool.acquire("c", () => ({}))).rejects.toThrow("No idle kernel");
    finish();
    expect((await pending).reused).toBe(false);
  });

  it("prevents a new kernel from spawning when shutdown interrupts eviction", async () => {
    let finish!: () => void;
    const create = vi.fn(() => ({}));
    const pool = new WorkerPool<object>(1, () => new Promise<void>(resolve => { finish = resolve; }));
    const first = await pool.acquire("a", () => ({}));
    await pool.release("a", first.worker, true);
    const pending = pool.acquire("b", create);
    await pool.close();
    finish();
    await expect(pending).rejects.toThrow("closing");
    expect(create).not.toHaveBeenCalled();
  });
});
