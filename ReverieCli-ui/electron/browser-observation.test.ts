import { JSDOM } from "jsdom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FOCUS_ELEMENT_FUNCTION, OBSERVE_FUNCTION, RESOLVE_ELEMENT_FUNCTION, VERIFY_FOCUSED_ELEMENT_FUNCTION, VERIFY_KEY_FUNCTION, VERIFY_OBSERVATION_FUNCTION } from "./browser-observation";

const doms: JSDOM[] = [];
function fixture(html = '<button>Save</button><input aria-label="Name"><input type="password" value="private">') {
  const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true }); doms.push(dom);
  const win = dom.window;
  Object.defineProperty(win.HTMLElement.prototype, "innerText", { get() { return this.textContent ?? ""; }, configurable: true });
  const rectangles = new Map<Element, { x: number; y: number; width: number; height: number }>();
  const rect = (node: Element, x = 10, y = 20, width = 120, height = 40) => {
    rectangles.set(node, { x, y, width, height });
    Object.defineProperties(node, { clientWidth: { value: width, configurable: true }, clientHeight: { value: height, configurable: true }, clientLeft: { value: 0, configurable: true }, clientTop: { value: 0, configurable: true } });
    (node as HTMLElement).style.visibility = "visible"; (node as HTMLElement).style.opacity = "1";
    node.getBoundingClientRect = () => ({ x, y, width, height, left: x, top: y, right: x + width, bottom: y + height, toJSON() { return {}; } });
  };
  rect(win.document.documentElement, 0, 0, 1024, 768); rect(win.document.body, 0, 0, 1024, 768);
  for (const [i, node] of Array.from(win.document.body.querySelectorAll("*")).entries()) rect(node, 10, 20 + i * 60);
  win.document.elementFromPoint = (x: number, y: number) => Array.from(rectangles).reverse().find(([node, r]) => node.isConnected && x >= r.x && x < r.x + r.width && y >= r.y && y < r.y + r.height)?.[0] ?? null;
  const invalidated = vi.fn(); (win as unknown as Record<string, unknown>).notify = invalidated;
  const run = (script: string, args: unknown[] = [], receiver?: Element) => win.eval(`(${script})`).apply(receiver ?? win, args);
  const observe = (id = "observe-1") => run(OBSERVE_FUNCTION, [id, "notify"]) as { elements: { element_id: string; role: string; name: string; text: string; editable: boolean }[] };
  return { dom, win, rect, rectangles, run, observe, invalidated };
}
afterEach(() => { for (const dom of doms.splice(0)) dom.window.close(); });

describe("fixed isolated browser observation functions", () => {
  it("returns visible actionable nodes and never publishes password values", () => {
    const { observe, run } = fixture(); const result = observe("o".repeat(256));
    expect(result.elements.map(e => e.role)).toEqual(["button", "textbox", "textbox"]);
    expect(result.elements[2].text).toBe(""); expect(result.elements[0].element_id).toBe("e0");
    expect(run(VERIFY_OBSERVATION_FUNCTION, ["o".repeat(256)])).toBe(true);
    expect(run(RESOLVE_ELEMENT_FUNCTION, ["different", "e0"])).toBeNull();
  });

  it("refuses hidden, clipped and occluded targets instead of relying on stale rectangles", () => {
    const { win, rect, observe, run } = fixture('<div aria-hidden="true"><button>Hidden</button></div><button>Visible</button>');
    const buttons = win.document.querySelectorAll("button"); rect(buttons[1], 10, 200);
    const result = observe(); expect(result.elements.map(e => e.name)).toEqual(["Visible"]);
    rect(buttons[1], 600, 200); expect(run(RESOLVE_ELEMENT_FUNCTION, ["observe-1", result.elements[0].element_id])).toBeNull();
    rect(buttons[1], 1100, 200); expect(observe("next").elements).toHaveLength(0);
  });

  it("invalidates DOM changes and observes mutations inside open shadow roots", async () => {
    const { win, rect, observe, run, invalidated } = fixture('<div id="host"></div>');
    const host = win.document.getElementById("host")!; rect(host, 10, 20, 160, 60);
    const shadow = host.attachShadow({ mode: "open" }); shadow.innerHTML = "<button>Shadow save</button>";
    const button = shadow.querySelector("button")!; rect(button, 20, 30, 120, 40);
    (shadow as ShadowRoot & { elementFromPoint(x: number, y: number): Element }).elementFromPoint = () => button;
    win.document.elementFromPoint = () => host;
    const result = observe(); expect(result.elements[0].name).toBe("Shadow save");
    expect(run(RESOLVE_ELEMENT_FUNCTION, ["observe-1", "e0"])).toBe(button);
    button.textContent = "Replaced"; await Promise.resolve();
    expect(run(VERIFY_OBSERVATION_FUNCTION, ["observe-1"])).toBe(false);
    expect(invalidated).toHaveBeenCalledOnce();
  });

  it("keeps a resolved node anchored across its own focus event and rejects changed input", () => {
    const { win, observe, run } = fixture('<input aria-label="Name" value="old">');
    observe(); const node = run(RESOLVE_ELEMENT_FUNCTION, ["observe-1", "e0"]) as Element;
    expect(run(FOCUS_ELEMENT_FUNCTION, [true], node)).toBe(true);
    expect(run(VERIFY_OBSERVATION_FUNCTION, ["observe-1"])).toBe(false);
    expect(run(VERIFY_FOCUSED_ELEMENT_FUNCTION, ["e0"], node)).toBe(true);
    (win.document.querySelector("input") as HTMLInputElement).value = "changed";
    expect(run(VERIFY_FOCUSED_ELEMENT_FUNCTION, ["e0"], node)).toBe(false);
  });

  it("rejects disabled, file upload and iframe actions explicitly", () => {
    const { win, observe, run } = fixture('<button disabled>Disabled</button><input type="file" aria-label="Upload"><iframe title="External frame"></iframe>');
    const result = observe();
    for (const element of result.elements) expect(run(RESOLVE_ELEMENT_FUNCTION, ["observe-1", element.element_id])).toBeNull();
    const file = win.document.querySelector("input")!; file.focus(); observe("file-focused");
    expect(run(VERIFY_KEY_FUNCTION, ["file-focused"])).toBe(false);
    const frame = win.document.querySelector("iframe")!; frame.focus(); observe("frame-focused");
    expect(run(VERIFY_KEY_FUNCTION, ["frame-focused"])).toBe(false);
  });
});
