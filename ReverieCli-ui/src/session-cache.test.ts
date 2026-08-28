import { describe, expect, it } from "vitest";

import { SESSION_CACHE_LIMIT, SessionCache } from "./session-cache";
import type { SessionState } from "./types";

function session(id: string, name = id): SessionState {
  return {
    id,
    name,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    messages: [{ role: "user", content: name }],
  } as unknown as SessionState;
}

describe("session cache", () => {
  it("returns a stored transcript by id and nothing for an unknown one", () => {
    const cache = new SessionCache();
    const stored = session("a");
    cache.set(stored);

    expect(cache.get("a")).toBe(stored);
    expect(cache.get("b")).toBeUndefined();
  });

  it("ignores sessions without an id instead of caching an empty key", () => {
    const cache = new SessionCache();
    cache.set(null);
    cache.set(undefined);
    cache.set({ ...session(""), id: "" });

    expect(cache.size).toBe(0);
    expect(cache.get("")).toBeUndefined();
  });

  it("keeps the newest write for a session", () => {
    const cache = new SessionCache();
    cache.set(session("a", "first"));
    const second = session("a", "second");
    cache.set(second);

    expect(cache.size).toBe(1);
    expect(cache.get("a")).toBe(second);
  });

  it("evicts the least recently used entry once full", () => {
    const cache = new SessionCache(3);
    cache.set(session("a"));
    cache.set(session("b"));
    cache.set(session("c"));
    cache.set(session("d"));

    expect(cache.size).toBe(3);
    expect(cache.get("a")).toBeUndefined();
    expect(cache.get("d")).toBeDefined();
  });

  it("treats a read as use, so the session being cycled back to survives", () => {
    const cache = new SessionCache(2);
    cache.set(session("a"));
    cache.set(session("b"));
    // `a` is now the oldest write, but the user just looked at it again.
    expect(cache.get("a")).toBeDefined();
    cache.set(session("c"));

    expect(cache.get("a")).toBeDefined();
    expect(cache.get("b")).toBeUndefined();
  });

  it("forgets a deleted session and can be emptied wholesale", () => {
    const cache = new SessionCache();
    cache.set(session("a"));
    cache.set(session("b"));
    cache.delete("a");

    expect(cache.get("a")).toBeUndefined();
    expect(cache.size).toBe(1);

    cache.clear();
    expect(cache.size).toBe(0);
    expect(cache.get("b")).toBeUndefined();
  });

  it("holds enough transcripts for a realistic switching pattern by default", () => {
    const cache = new SessionCache();
    for (let index = 0; index < SESSION_CACHE_LIMIT; index += 1) cache.set(session(`s${index}`));

    expect(cache.size).toBe(SESSION_CACHE_LIMIT);
    expect(cache.get("s0")).toBeDefined();
  });
});
