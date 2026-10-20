import { expect, it } from "vitest";
import { ViewInstances } from "./view-interactions";

it("binds host leases and rejects stale frames, session switches and reused identities", () => {
  const registry = new ViewInstances();
  const ref = { projectRoot: "workspace", sessionId: "one", viewId: "v1", revision: 1 };
  const id = registry.register(ref);
  const payload = { ...ref, interactionId: id };
  expect(registry.require(payload)).toEqual(ref);
  for (const change of [{ sessionId: "two" }, { revision: 2 }, { viewId: "v2" }, { interactionId: "forged" }]) {
    expect(() => registry.require({ ...payload, ...change })).toThrow("expired");
  }
  registry.revoke(id);
  expect(() => registry.require(payload)).toThrow("expired");
  const second = registry.register(ref);
  registry.clear();
  expect(() => registry.require({ ...payload, interactionId: second })).toThrow("expired");
});
