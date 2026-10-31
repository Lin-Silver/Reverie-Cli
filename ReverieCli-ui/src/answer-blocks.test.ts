import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { parseAnswerBlock } from "./answer-blocks";

describe("rich answer data fidelity", () => {
  it("preserves numeric display text before JavaScript can round it", () => {
    const source = '{"type":"metrics","items":[{"label":"记录编号","value":9007199254740993},{"label":"精确小数","value":0.1234567890123456789},{"label":"负零","value":-0},{"label":"金额","value":1.2300}]}';
    const block = parseAnswerBlock(source);
    expect(block?.type).toBe("metrics");
    if (block?.type !== "metrics") throw new Error("Expected complete metric content");
    expect(block.items.map(item => String(item.value))).toEqual([
      "9007199254740993", "0.1234567890123456789", "-0", "1.2300",
    ]);
  });

  it("preserves numeric table cells alongside original text, zero, false and null", () => {
    const block = parseAnswerBlock('{"type":"table","columns":["编号","值","备注","完成","空值"],"rows":[[9007199254740993,0.1234567890123456789,"ID  01\\n第二行",false,null],[0,1.2300,"正常",true,null]]}');
    if (block?.type !== "table") throw new Error("Expected complete table content");
    expect(block.rows).toEqual([
      [{ kind: "answer-number", text: "9007199254740993" }, { kind: "answer-number", text: "0.1234567890123456789" }, "ID  01\n第二行", false, null],
      [{ kind: "answer-number", text: "0" }, { kind: "answer-number", text: "1.2300" }, "正常", true, null],
    ]);
  });

  it.each([
    { type: "metrics", items: [{ label: "任务", value: 3 }], note: "仍有两个阻塞项" },
    { type: "metrics", items: [{ label: "任务", value: 3, unit: "小时" }] },
    { type: "table", columns: ["项目"], rows: [["CLI"]], notes: ["尚未验收"] },
    { type: "table", columns: ["状态"], rows: [[{ text: "完成", detail: "仅源码" }]] },
    { type: "cards", items: [{ title: "Plane", description: "项目管理", limitations: "不含托管费用" }] },
    { type: "cards", items: [{ title: "Plane", description: "项目管理", image: { url: "https://example.com/image.png", alt: "截图", caption: "历史版本" } }] },
    { type: "sources", items: [{ label: "来源", url: "https://example.com", quote: "仅限测试" }] },
  ])("retains the whole source when an unsupported field would otherwise disappear: %j", value => {
    expect(parseAnswerBlock(JSON.stringify(value))).toBeNull();
  });

  it.each([
    '{"type":"cards","items":[{"title":123,"description":"说明"}]}',
    '{"type":"table","columns":[123],"rows":[[0]]}',
    '{"type":"metrics","items":[{"label":123,"value":0}]}',
    '{"type":"cards","numbered":1,"items":[{"title":"标题","description":"说明"}]}',
  ])("does not coerce numeric metadata into valid string fields: %s", source => {
    expect(parseAnswerBlock(source)).toBeNull();
  });

  it.each([
    '{"type":"metrics","items":[{"label":"任务","value":1}],"items":[{"label":"任务","value":2}]}',
    '{"type":"metrics","items":[{"label":"任务","value":1,"label":"覆盖"}]}',
    '{"type":"metrics","items":[{"label":"任务","value":1,"la\\u0062el":"覆盖"}]}',
    '{"type":"cards","items":[{"title":"图","description":"说明","image":{"url":"https://example.com/a.png","url":"https://example.com/b.png","alt":"截图"}}]}',
  ])("retains JSON with repeated keys as raw content: %s", source => {
    expect(parseAnswerBlock(source)).toBeNull();
  });
});


describe("compact prompt and renderer schema contract", () => {
  it("provides renderable examples of every component, including an empty table", () => {
    const agent = readFileSync(new URL("../../ReverieCli-py/reverie/agent/agent.py", import.meta.url), "utf8");
    const guidance = agent.match(/_DESKTOP_STATIC_RICH_ANSWER_TURN_GUIDANCE = """([\s\S]*?)"""/)![1];
    const examples = [...guidance.matchAll(/```reverie-ui\r?\n([\s\S]*?)\r?\n```/g)].map(match => parseAnswerBlock(match[1]));
    expect(examples.every(Boolean)).toBe(true);
    expect(new Set(examples.map(block => block?.type))).toEqual(new Set(["metrics", "table", "cards", "sources"]));
    expect(examples.some(block => block?.type === "table" && block.rows.length === 0)).toBe(true);
  });
});
