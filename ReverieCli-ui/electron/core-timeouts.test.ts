import { describe, expect, it } from "vitest";
import { coreRequestTimeoutMs } from "./core-timeouts";

describe("desktop core request timeouts", () => {
  it("allows slow cold-start initialization to finish", () => {
    expect(coreRequestTimeoutMs("initialize")).toBe(300_000);
  });

  it("keeps prompt and indexing requests streaming without a transport deadline", () => {
    expect(coreRequestTimeoutMs("runPrompt")).toBe(0);
    expect(coreRequestTimeoutMs("indexWorkspace")).toBe(0);
  });

  it("retains bounded deadlines for ordinary requests", () => {
    expect(coreRequestTimeoutMs("getSession")).toBe(15_000);
    expect(coreRequestTimeoutMs("listTools")).toBe(60_000);
  });
});
