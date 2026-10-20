import { describe, expect, it, vi } from "vitest";

import { prepareViewResolution } from "./view-resolve";

// prepareViewResolution is the main-process seam between the kernel's
// authoritative view resolution and the renderer. The kernel's ViewStore
// returns a `view.resolved` envelope that carries BOTH a model-safe reference
// (session/view/revision + title/summary/state) AND an authoritative path block
// (`resolved`: directory/entry/viewsRoot). The path block is what the host needs
// to bind a `reverie-view:` origin -- and it is exactly what must NEVER reach the
// renderer, since a filesystem path in the renderer is a confinement leak. These
// tests pin that contract: the registrar receives the real paths, the renderer
// reference carries only the opaque url + policy, and a malformed envelope is
// refused before anything is bound.

const PYTHON = {
  id: 7,
  type: "view.resolved",
  view: {
    sessionId: "session-a",
    viewId: "v0123456789abcdef",
    revision: 2,
    title: "Sales chart",
    summary: "A bar chart of Q3 sales.",
    mimeType: "text/html",
    policyId: "local-offline-v1",
    schemaVersion: 1,
    createdAt: "2026-10-11T07:55:00+00:00",
    replacesViewId: "v0123456789abcdef",
    state: { revision: 3, state: { tab: "q3" }, updated_at: "2026-10-11T08:00:00+00:00" },
  },
  resolved: {
    directory: "/data/views/session-a/v0123456789abcdef/2",
    entry: "index.html",
    viewsRoot: "/data/views",
  },
};

const okRegistrar = () =>
  vi.fn(async () => ({ url: `reverie-view://${"d".repeat(32)}/index.html`, policyId: "local-offline-v1" }));

describe("prepareViewResolution", () => {
  it("hands the authoritative directory/entry/viewsRoot to the registrar and returns its url + policy", async () => {
    const register = okRegistrar();
    const ref = await prepareViewResolution(PYTHON, register);
    expect(register).toHaveBeenCalledTimes(1);
    expect(register).toHaveBeenCalledWith(
      expect.objectContaining({
        directory: "/data/views/session-a/v0123456789abcdef/2",
        entry: "index.html",
        viewsRoot: "/data/views",
        viewId: "v0123456789abcdef",
        revision: 2,
        sessionId: "session-a",
      }),
    );
    expect(ref.url).toBe(`reverie-view://${"d".repeat(32)}/index.html`);
    expect(ref.policyId).toBe("local-offline-v1");
  });

  it("never lets a filesystem path reach the renderer reference", async () => {
    const register = okRegistrar();
    // A store that wrongly folds path fields into `view` must still be stripped:
    // the renderer reference is built as an allow-list, not a pass-through.
    const poisoned = {
      ...PYTHON,
      view: { ...PYTHON.view, directory: "/leak", entry: "leak.html", viewsRoot: "/leak", realRoot: "/leak" },
    };
    const ref = (await prepareViewResolution(poisoned, register)) as Record<string, unknown>;
    for (const key of ["directory", "entry", "viewsRoot", "path", "entryPath", "realRoot"]) {
      expect(ref, key).not.toHaveProperty(key);
    }
    const serialized = JSON.stringify(ref);
    expect(serialized).not.toContain("/leak");
    expect(serialized).not.toContain("/data/views");
  });

  it("carries the model-safe metadata and persisted state through unchanged", async () => {
    const ref = await prepareViewResolution(PYTHON, okRegistrar());
    expect(ref).toMatchObject({
      sessionId: "session-a",
      viewId: "v0123456789abcdef",
      revision: 2,
      title: "Sales chart",
      summary: "A bar chart of Q3 sales.",
      schemaVersion: 1,
      createdAt: "2026-10-11T07:55:00+00:00",
      replacesViewId: "v0123456789abcdef",
      state: { revision: 3, state: { tab: "q3" }, updated_at: "2026-10-11T08:00:00+00:00" },
    });
  });

  it("prefers the registrar url + policy over any carried in the kernel view", async () => {
    const register = okRegistrar();
    const spoofed = { ...PYTHON, view: { ...PYTHON.view, url: "reverie-view://forged/index.html", policyId: "wide-open" } };
    const ref = await prepareViewResolution(spoofed, register);
    expect(ref.url).toBe(`reverie-view://${"d".repeat(32)}/index.html`);
    expect(ref.policyId).toBe("local-offline-v1");
  });

  it("throws without registering when the resolved path block is missing or malformed", async () => {
    const register = okRegistrar();
    await expect(prepareViewResolution({ type: "view.resolved", view: PYTHON.view }, register)).rejects.toThrow();
    await expect(
      prepareViewResolution({ ...PYTHON, resolved: { entry: "index.html", viewsRoot: "/data/views" } }, register),
    ).rejects.toThrow();
    await expect(prepareViewResolution({ ...PYTHON, view: {} }, register)).rejects.toThrow();
    await expect(prepareViewResolution(null, register)).rejects.toThrow();
    expect(register).not.toHaveBeenCalled();
  });
});
