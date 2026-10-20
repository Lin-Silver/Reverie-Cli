import { describe, expect, it } from "vitest";
import { PROBE_BUDGETS, PROBE_CHECKS, PROBE_METRICS, evaluateProbeReport } from "./view-isolation-probe";

const metrics = { hostPingDuringLoopMs: 12, hostPingDuringFloodMs: 20, hostPingAfterTeardownMs: 8, viewTeardownMs: 90 };
const report = (overrides: Record<string, unknown> = {}, failing: readonly string[] = []) => ({
  version: 1,
  packaged: true,
  platform: "win32",
  electron: "41.2.1",
  container: "sandboxed-iframe",
  startedAt: "2026-10-10T00:00:00.000Z",
  metrics: { ...metrics },
  checks: PROBE_CHECKS.map(id => ({ id, passed: !failing.includes(id), detail: "observed" })),
  ...overrides,
});

describe("packaged isolation probe report", () => {
  it("declares a complete, unique check list covering the mandated isolation gates", () => {
    expect(new Set(PROBE_CHECKS).size).toBe(PROBE_CHECKS.length);
    expect(PROBE_CHECKS.length).toBeGreaterThanOrEqual(24);
    for (const id of ["node-api-absent", "preload-bridge-absent", "parent-dom-blocked", "traversal-request-blocked", "permission-requests-denied", "download-blocked", "network-fetch-blocked", "frame-navigation-blocked", "forged-bridge-source-rejected", "flood-rate-limited", "view-out-of-process", "host-responsive-during-loop", "view-destroyed-after-loop", "host-responsive-after-teardown"]) expect(PROBE_CHECKS).toContain(id);
    expect(PROBE_METRICS).toEqual(Object.keys(metrics));
  });

  it("fails the gate on a missing check, a failing check, a broken budget or a malformed report", () => {
    expect(evaluateProbeReport(report())).toEqual({ passed: true, failures: [], missing: [] });
    expect(evaluateProbeReport(report({}, ["download-blocked"]))).toEqual({ passed: false, failures: ["download-blocked"], missing: [] });
    const partial = evaluateProbeReport(report({ checks: [{ id: "node-api-absent", passed: true }] }));
    expect(partial.passed).toBe(false);
    expect(partial.missing).toHaveLength(PROBE_CHECKS.length - 1);
    expect(evaluateProbeReport(report({ metrics: { ...metrics, hostPingDuringLoopMs: PROBE_BUDGETS.hostPingMs + 1 } }))).toMatchObject({ passed: false, failures: ["metric:hostPingDuringLoopMs"] });
    expect(evaluateProbeReport(report({ metrics: { ...metrics, viewTeardownMs: PROBE_BUDGETS.teardownMs + 1 } }))).toMatchObject({ passed: false, failures: ["metric:viewTeardownMs"] });
    expect(evaluateProbeReport(report({ metrics: {} })).failures).toEqual(PROBE_METRICS.map(name => `metric:${name}`));
    expect(evaluateProbeReport(report({ packaged: false }))).toMatchObject({ passed: true });
    expect(evaluateProbeReport(report({ packaged: false }), { requirePackaged: true })).toEqual({ passed: false, failures: ["packaged-build"], missing: [] });
    expect(evaluateProbeReport(report({ version: 2 }))).toEqual({ passed: false, failures: ["report-version"], missing: [] });
    for (const malformed of [null, undefined, "report", 7, []]) expect(evaluateProbeReport(malformed)).toEqual({ passed: false, failures: ["report-shape"], missing: [] });
  });
});
