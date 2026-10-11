import { describe, expect, it, vi } from "vitest";
import { WorkerPool } from "./worker-pool";

describe("warm kernels", () => {
  it("spawns only on demand, keeps one idle kernel, and expires it without stopping active work", async () => {
    vi.useFakeTimers();
    try {
      const dispose = vi.fn(async () => {});
      const pool = new WorkerPool<object>(4, dispose, 30_000);
      expect(dispose).not.toHaveBeenCalled();
      const first = await pool.acquire("a", () => ({ id: "first" }));
      const second = await pool.acquire("b", () => ({ id: "second" }));
      const active = await pool.acquire("c", () => ({ id: "active" }));
      await pool.release("a", first.worker, true);
      await pool.release("b", second.worker, true);
      expect(dispose).toHaveBeenCalledWith(first.worker);
      await vi.advanceTimersByTimeAsync(30_000);
      expect(dispose).toHaveBeenCalledWith(second.worker);
      expect(dispose).not.toHaveBeenCalledWith(active.worker);
      expect((await pool.acquire("b", () => ({}))).reused).toBe(false);
      await pool.close();
      expect(vi.getTimerCount()).toBe(0);
    } finally { vi.useRealTimers(); }
  });

  it("cancels expiry when an idle kernel is reused", async () => {
    vi.useFakeTimers();
    try {
      const dispose = vi.fn(async () => {});
      const pool = new WorkerPool<object>(2, dispose);
      const first = await pool.acquire("a", () => ({}));
      await pool.release("a", first.worker, true);
      expect((await pool.acquire("a", () => ({}))).reused).toBe(true);
      await vi.advanceTimersByTimeAsync(60_000);
      expect(dispose).not.toHaveBeenCalled();
      await pool.close();
      expect(dispose).toHaveBeenCalledTimes(1);
    } finally { vi.useRealTimers(); }
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
    const closing = pool.close();
    const rejected = expect(pending).rejects.toThrow("closing");
    await Promise.resolve();
    finish();
    await closing;
    await rejected;
    expect(create).not.toHaveBeenCalled();
  });
});
