import { describe, expect, it } from "vitest";
import { isThinkTool, thinkToolText } from "./thinking-tool";

describe("thinking tool identity", () => {
  it("recognizes every spelling the model may use", () => {
    for (const name of ["deep_think", "think", "think_tool", "deep_thinking"]) {
      expect(isThinkTool(name)).toBe(true);
      expect(isThinkTool(`  ${name.toUpperCase()}  `)).toBe(true);
    }
  });

  it("does not claim ordinary tools", () => {
    for (const name of ["command_exec", "codebase-retrieval", "thinking_output", "", null, undefined]) {
      expect(isThinkTool(name)).toBe(false);
    }
  });
});

describe("thinking tool body", () => {
  it("builds one block from topic, thought, and next step", () => {
    const text = thinkToolText({
      topic: "  Retrieval channel  ",
      thought: "Scores are computed twice.",
      next_step: "Read the ranker.",
    });

    expect(text).toBe("**Retrieval channel**\n\nScores are computed twice.\n\nNext: Read the ranker.");
  });

  it("reads the arguments the bridge sends as a JSON string", () => {
    expect(thinkToolText(JSON.stringify({ thought: "Just this." }))).toBe("Just this.");
  });

  it("shows a half-streamed call verbatim rather than nothing", () => {
    expect(thinkToolText('{"thought": "still arriving')).toBe('{"thought": "still arriving');
  });

  it("returns nothing when there is nothing to show", () => {
    expect(thinkToolText("")).toBe("");
    expect(thinkToolText("   ")).toBe("");
    expect(thinkToolText({})).toBe("");
    expect(thinkToolText(null)).toBe("");
    expect(thinkToolText([1, 2])).toBe("");
  });

  it("joins a thought the model sent as a list of steps", () => {
    expect(thinkToolText({ thought: ["First.", "  ", "Second."] })).toBe("First.\nSecond.");
  });
});
