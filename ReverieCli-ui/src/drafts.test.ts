// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import {
  NEW_SESSION_DRAFT_ID,
  clearDraft,
  clearProjectDrafts,
  draftStorageKey,
  loadProjectDrafts,
  saveDraft,
} from "./drafts";

const PROJECT_A = "G:\\work\\alpha";
const PROJECT_B = "G:\\work\\beta";

afterEach(() => {
  localStorage.clear();
});

describe("per-conversation composer drafts", () => {
  it("keeps each conversation's draft in its own slot", () => {
    saveDraft(PROJECT_A, "20260101_000000_000001", "draft one");
    saveDraft(PROJECT_A, "20260101_000000_000002", "draft two");

    const drafts = loadProjectDrafts(PROJECT_A);
    expect(drafts).toEqual({
      "20260101_000000_000001": "draft one",
      "20260101_000000_000002": "draft two",
    });
  });

  it("never lets two projects with the same session id collide", () => {
    // Session ids are only a per-project timestamp, so the same id can appear in
    // two projects -- each must keep its own text.
    const sharedId = "20260101_120000_000000";
    saveDraft(PROJECT_A, sharedId, "alpha text");
    saveDraft(PROJECT_B, sharedId, "beta text");

    expect(loadProjectDrafts(PROJECT_A)).toEqual({ [sharedId]: "alpha text" });
    expect(loadProjectDrafts(PROJECT_B)).toEqual({ [sharedId]: "beta text" });
  });

  it("persists synchronously so a restore reads the last keystroke", () => {
    // Simulate a crash: the value is in localStorage the instant saveDraft
    // returns, with no async flush that a hard kill could drop.
    saveDraft(PROJECT_A, "s1", "half-typed prom");
    expect(localStorage.getItem(draftStorageKey(PROJECT_A, "s1"))).toBe("half-typed prom");
    saveDraft(PROJECT_A, "s1", "half-typed prompt");
    expect(loadProjectDrafts(PROJECT_A)).toEqual({ s1: "half-typed prompt" });
  });

  it("clears a slot when its text goes empty so blanks are not restored", () => {
    saveDraft(PROJECT_A, "s1", "something");
    saveDraft(PROJECT_A, "s1", "");
    expect(loadProjectDrafts(PROJECT_A)).toEqual({});
    expect(localStorage.getItem(draftStorageKey(PROJECT_A, "s1"))).toBeNull();
  });

  it("drops one conversation's draft without touching the others", () => {
    saveDraft(PROJECT_A, "s1", "keep me");
    saveDraft(PROJECT_A, "s2", "delete me");
    clearDraft(PROJECT_A, "s2");
    expect(loadProjectDrafts(PROJECT_A)).toEqual({ s1: "keep me" });
  });

  it("sweeps every draft for a deleted project only", () => {
    saveDraft(PROJECT_A, "s1", "alpha");
    saveDraft(PROJECT_B, "s1", "beta");
    clearProjectDrafts(PROJECT_A);
    expect(loadProjectDrafts(PROJECT_A)).toEqual({});
    expect(loadProjectDrafts(PROJECT_B)).toEqual({ s1: "beta" });
  });

  it("parks pre-session text under the placeholder id", () => {
    saveDraft(PROJECT_A, NEW_SESSION_DRAFT_ID, "typed before a session existed");
    expect(loadProjectDrafts(PROJECT_A)).toEqual({
      [NEW_SESSION_DRAFT_ID]: "typed before a session existed",
    });
  });

  it("isolates keys even when a project path contains the delimiter", () => {
    // A colon in the path must not let one project read another's slot.
    const trickyRoot = "https://host:8080/repo";
    saveDraft(trickyRoot, "s1", "safe");
    saveDraft(PROJECT_A, "s1", "other");
    expect(loadProjectDrafts(trickyRoot)).toEqual({ s1: "safe" });
    expect(loadProjectDrafts(PROJECT_A)).toEqual({ s1: "other" });
  });
});
