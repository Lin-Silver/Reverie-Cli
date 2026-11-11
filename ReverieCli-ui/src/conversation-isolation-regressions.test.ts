import { expect, it } from "vitest";
import { SessionCache } from "./session-cache";
import type { SessionState } from "./types";

function conversation(workspaceId: string, content: string): SessionState {
  return {
    id: "same-local-id",
    name: content,
    created_at: "2026-11-07T00:00:00Z",
    updated_at: "2026-11-07T00:00:00Z",
    messages: [{ role: "user", content }],
    metadata: { workspace_id: workspaceId },
  };
}

it("keeps transcripts with the same local id from different workspaces independently", () => {
  const cache = new SessionCache();
  const first = conversation("workspace-a", "Investigate A");
  const second = conversation("workspace-b", "Investigate B");
  cache.set(first);
  cache.set(second);

  expect(cache.size).toBe(2);
});

it('uses explicit assistant ownership and preserves ordinary IDs beginning with aio',()=>{
  const cache=new SessionCache();
  const ordinary={...conversation('workspace-a','ordinary'),id:'aio-old'};
  const assistant={...conversation('workspace-b','assistant'),id:'aio-old',metadata:{assistant_id:'aio'}};
  cache.set(ordinary,'C:/a');cache.set(assistant,'C:/b');
  expect(cache.get('aio-old','C:/a')).toBe(ordinary);
  expect(cache.get('aio-old','C:/other','aio')).toBe(assistant);
  expect(cache.get('aio-old','C:/b')).toBeUndefined();
  cache.delete('aio-old','C:/other','aio');
  expect(cache.get('aio-old','C:/a')).toBe(ordinary);
  expect(cache.get('aio-old','C:/b','aio')).toBeUndefined();
});
