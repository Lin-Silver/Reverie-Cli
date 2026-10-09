import { describe, expect, it } from "vitest";
import { composerToken, slashOptions } from "./composer-completion";
import type { CommandRecord, SkillRecord } from "./types";

const command: CommandRecord = { id: "compact", command: "/compact", section: "Session", summary: "Compact context", overview: "", detail: "", aliases: ["/compress"] };
const skill: SkillRecord = { key: "apple-design", name: "apple-design", description: "Typography and fluid interfaces", summary: "", path: "", scope: "Built-in", root: "builtin", plugin_id: "", pinned: false, shadowed: false, allow_implicit_invocation: true };

describe("composer token boundaries", () => {
  it("finds the token at the caret without consuming the rest of a draft", () => {
    expect(composerToken("Compare @read and explain", 13)).toEqual({ kind: "mention", query: "read", start: 8, end: 13 });
    expect(composerToken("Compare @read and explain", 24)).toBeNull();
    expect(composerToken("dev@example.com", 15)).toBeNull();
    expect(composerToken("https://example.com/", 20)).toBeNull();
    expect(composerToken("\n/skill apple", 13)?.kind).toBe("skill");
    expect(composerToken("/skill pin $apple", 17)?.query).toBe("apple");
    expect(composerToken("/compact keep code", 18)).toBeNull();
    expect(composerToken("请读 @中文", 6)?.query).toBe("中文");
  });
  it("offers commands, aliases and directly searchable required skills", () => {
    expect(slashOptions(composerToken("/", 1)!, [command], [skill], false, k => k).map(v => v.id)).toEqual(["skills", "command:compact"]);
    expect(slashOptions(composerToken("/compress", 9)!, [command], [], false, k => k)[0].label).toBe("/compact");
    expect(slashOptions(composerToken("/apple", 6)!, [command], [skill], false, k => k)[0].value).toBe("apple-design");
  });
  it("marks full and already pinned skills, excludes shadowed definitions, and handles empty catalogs", () => {
    const token = composerToken("/skill ", 7)!;
    expect(slashOptions(token, [], [], false, k => k)).toEqual([]);
    expect(slashOptions(token, [], [{ ...skill, shadowed: true }], false, k => k)).toEqual([]);
    expect(slashOptions(token, [], [{ ...skill, pinned: true }], false, k => k)[0].disabled).toBe(true);
    expect(slashOptions(token, [], [skill], true, k => k)[0].badge).toBe("固定数量已满");
  });
});
