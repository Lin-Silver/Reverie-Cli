/**
 * Pass/fail gate for the packaged offline-view isolation probe.
 *
 * Deliberately free of Electron imports: the gate is pure data so the same function
 * judges a report written by the packaged application and one replayed from disk.
 */

export const PROBE_REPORT_VERSION = 1;

/** Round-trip budgets. A host that answers a ping inside `hostPingMs` while a view spins is responsive. */
export const PROBE_BUDGETS = { hostPingMs: 1_500, teardownMs: 3_000 } as const;

export const PROBE_METRICS = ["hostPingDuringLoopMs", "hostPingDuringFloodMs", "hostPingAfterTeardownMs", "viewTeardownMs"] as const;

export const PROBE_CHECKS = [
  // Node and preload reach
  "node-api-absent",
  "preload-bridge-absent",
  "node-integration-disabled",
  "context-isolation-enabled",
  // Host document and origin
  "parent-dom-blocked",
  "top-window-access-blocked",
  "opaque-origin-enforced",
  "storage-apis-blocked",
  // Resource protocol
  "traversal-request-blocked",
  "foreign-token-blocked",
  "script-mime-unmappable",
  "unbound-directory-blocked",
  // Network
  "network-fetch-blocked",
  "websocket-blocked",
  "remote-subresource-blocked",
  // Navigation, popups, downloads
  "frame-navigation-blocked",
  "window-open-blocked",
  "form-submission-blocked",
  "download-blocked",
  // Permissions
  "permission-requests-denied",
  "host-clipboard-allowed",
  // Restricted bridge
  "forged-bridge-source-rejected",
  "missing-capability-rejected",
  "stale-instance-rejected",
  "unsupported-method-rejected",
  "oversize-message-rejected",
  "flood-rate-limited",
  // Containment under abuse
  "view-out-of-process",
  "host-responsive-during-loop",
  "chat-input-usable-during-loop",
  "host-responsive-after-flood",
  "view-destroyed-after-loop",
  "view-process-exited",
  "host-responsive-after-teardown",
] as const;

export type ProbeCheckId = (typeof PROBE_CHECKS)[number];
export type ProbeMetric = (typeof PROBE_METRICS)[number];
export type ProbeCheckResult = { id: string; passed: boolean; detail?: string };
export type ProbeReport = {
  version: number;
  packaged: boolean;
  platform: string;
  electron: string;
  container: string;
  startedAt: string;
  metrics: Partial<Record<ProbeMetric, number>>;
  checks: ProbeCheckResult[];
};
export type ProbeEvaluation = { passed: boolean; failures: string[]; missing: string[] };

const METRIC_BUDGET: Readonly<Record<ProbeMetric, keyof typeof PROBE_BUDGETS>> = {
  hostPingDuringLoopMs: "hostPingMs",
  hostPingDuringFloodMs: "hostPingMs",
  hostPingAfterTeardownMs: "hostPingMs",
  viewTeardownMs: "teardownMs",
};

export function probeMetricBudget(metric: ProbeMetric): number {
  return PROBE_BUDGETS[METRIC_BUDGET[metric]];
}

/** A report is only evidence when every declared check is present and passing and every budget holds. */
export function evaluateProbeReport(candidate: unknown, options: { requirePackaged?: boolean } = {}): ProbeEvaluation {
  if (typeof candidate !== "object" || candidate === null || Array.isArray(candidate)) return { passed: false, failures: ["report-shape"], missing: [] };
  const report = candidate as Partial<ProbeReport>;
  if (report.version !== PROBE_REPORT_VERSION) return { passed: false, failures: ["report-version"], missing: [] };
  if (!Array.isArray(report.checks) || typeof report.metrics !== "object" || report.metrics === null) return { passed: false, failures: ["report-shape"], missing: [] };

  const failures: string[] = [];
  const missing: string[] = [];
  if (options.requirePackaged && report.packaged !== true) failures.push("packaged-build");

  const observed = new Map<string, ProbeCheckResult>();
  for (const check of report.checks) if (check && typeof check === "object" && typeof check.id === "string") observed.set(check.id, check);
  for (const id of PROBE_CHECKS) {
    const check = observed.get(id);
    if (!check) missing.push(id);
    else if (check.passed !== true) failures.push(id);
  }

  const metrics = report.metrics as Partial<Record<ProbeMetric, unknown>>;
  for (const metric of PROBE_METRICS) {
    const value = metrics[metric];
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > probeMetricBudget(metric)) failures.push(`metric:${metric}`);
  }

  return { passed: failures.length === 0 && missing.length === 0, failures, missing };
}

/** One-screen operator summary; the JSON report stays the machine-readable evidence. */
export function renderProbeSummary(report: Partial<ProbeReport>, evaluation: ProbeEvaluation): string {
  const lines = [
    `isolation probe ${evaluation.passed ? "PASS" : "FAIL"}`,
    `container=${report.container ?? "unknown"} packaged=${report.packaged === true} platform=${report.platform ?? "unknown"} electron=${report.electron ?? "unknown"}`,
    `checks=${PROBE_CHECKS.length - evaluation.failures.filter(id => !id.startsWith("metric:")).length - evaluation.missing.length}/${PROBE_CHECKS.length} passed`,
  ];
  for (const metric of PROBE_METRICS) lines.push(`  ${metric}=${report.metrics?.[metric] ?? "n/a"}ms (budget ${probeMetricBudget(metric)}ms)`);
  if (evaluation.failures.length > 0) lines.push(`  failed: ${evaluation.failures.join(", ")}`);
  if (evaluation.missing.length > 0) lines.push(`  missing: ${evaluation.missing.join(", ")}`);
  return lines.join("\n");
}
