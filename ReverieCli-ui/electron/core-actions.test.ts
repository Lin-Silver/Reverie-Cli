import { describe, expect, it } from "vitest";

import {
  assertCoreAction,
  assertCoreResponse,
  normalizeCorePayload,
} from "./core-actions";

describe("core protocol runtime boundary", () => {
  it("accepts declared actions and object payloads", () => {
    expect(assertCoreAction("initialize")).toBe("initialize");
    expect(normalizeCorePayload({ projectRoot: "C:/workspace" })).toEqual({ projectRoot: "C:/workspace" });
  });

  it("rejects undeclared actions and non-object payloads", () => {
    expect(() => assertCoreAction("typoAction")).toThrow(/Unsupported Reverie core action/);
    expect(() => normalizeCorePayload("not-an-object")).toThrow(/payload must be an object/);
  });

  it("detects response discriminant and required-field drift", () => {
    expect(assertCoreResponse("initialize", { type: "state", state: {} }).type).toBe("state");
    expect(() => assertCoreResponse("initialize", { type: "session", state: {} })).toThrow(/protocol mismatch/);
    expect(() => assertCoreResponse("initialize", { type: "state" })).toThrow(/missing: state/);
  });
});
