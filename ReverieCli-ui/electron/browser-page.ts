import type { WebContents } from "electron";
import type { BrowserAction, PageObservation } from "../src/generated/core-types";
import { saveBrowserImage } from "./browser-artifacts";
import { FOCUS_ELEMENT_FUNCTION, OBSERVE_FUNCTION, RESOLVE_ELEMENT_FUNCTION, SCROLL_FUNCTION, VERIFY_FOCUSED_ELEMENT_FUNCTION, VERIFY_KEY_FUNCTION, VERIFY_OBSERVATION_FUNCTION } from "./browser-observation";
import { observedPage, pngDimensions, type ObservedPage } from "./browser-policy";

const world = "reverie-browser-observer";
const binding = "__reverieInvalidate";
const keys = {
  enter: ["Enter",13], tab: ["Tab",9], escape: ["Escape",27], backspace: ["Backspace",8], delete: ["Delete",46],
  space: [" ",32], arrow_up: ["ArrowUp",38], arrow_down: ["ArrowDown",40], arrow_left: ["ArrowLeft",37], arrow_right: ["ArrowRight",39],
  home: ["Home",36], end: ["End",35], page_up: ["PageUp",33], page_down: ["PageDown",34],
} as const;

/** The guest page never receives the adapter token or a caller-supplied expression. */
export class BrowserPage {
  private snapshot?: { id: string; context: number; page?: ObservedPage };

  constructor(private contents: WebContents, private invalidate: () => void) {
    contents.debugger.on("message", (_event, method, params) => {
      const snapshot = this.snapshot;
      if (method === "Runtime.bindingCalled" && snapshot && params.name === binding && params.executionContextId === snapshot.context
        && params.payload === JSON.stringify({ observation_id: snapshot.id })) this.invalidate();
    });
  }

  async init() {
    await this.contents.debugger.sendCommand("Runtime.addBinding", { name: binding, executionContextName: world });
  }

  private async call(fn: string, args: unknown[], target: { executionContextId: number } | { objectId: string }, byValue = true) {
    const reply = await this.contents.debugger.sendCommand("Runtime.callFunctionOn", {
      ...target, functionDeclaration: fn, arguments: args.map(value => ({ value })), returnByValue: byValue,
    });
    if (reply.exceptionDetails) throw new Error("Browser document changed.");
    return reply.result;
  }

  async observe(id: string, root: string, check: () => void): Promise<Omit<PageObservation, "tab">> {
    const debug = this.contents.debugger;
    const tree = await debug.sendCommand("Page.getFrameTree");
    const frameId = tree.frameTree.frame.id as string;
    const { executionContextId } = await debug.sendCommand("Page.createIsolatedWorld", { frameId, worldName: world });
    const snapshot = this.snapshot = { id, context: executionContextId };
    const target = { executionContextId };
    const page = observedPage((await this.call(OBSERVE_FUNCTION, [id,binding], target)).value, frameId);
    check();
    const captured = await debug.sendCommand("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    const png = Buffer.from(captured.data, "base64"), size = pngDimensions(png);
    if (snapshot !== this.snapshot || !(await this.call(VERIFY_OBSERVATION_FUNCTION, [id], target)).value) throw new Error("Browser observation expired.");
    check();
    await saveBrowserImage(root, id, png);
    check();
    this.snapshot = { ...snapshot, page };
    return { viewport: page.viewport, elements: page.elements.map(item => item.element), screenshot: { image_id: id, returned_width: size.width,
      returned_height: size.height, capture: { x: 0, y: 0, width: page.viewport.width, height: page.viewport.height } } };
  }

  async act(action: Exclude<BrowserAction, {action:"open"|"list"|"observe"}>, begin: () => void) {
    const snapshot = this.snapshot;
    if (!snapshot?.page || action.target.observation_id !== snapshot.id) throw new Error("Browser observation expired.");
    const target = { executionContextId: snapshot.context }, debug = this.contents.debugger;
    const verify = action.action === "key" ? VERIFY_KEY_FUNCTION : VERIFY_OBSERVATION_FUNCTION;
    if (!(await this.call(verify, [snapshot.id], target)).value) throw new Error("Browser observation expired.");
    const element = "element_id" in action && action.element_id ? snapshot.page.elements.find(item => item.element.element_id === action.element_id) : undefined;
    let objectId: string | undefined;
    try {
      if ("element_id" in action && action.element_id) {
        if (!element) throw new Error("Unknown browser element.");
        objectId = (await this.call(RESOLVE_ELEMENT_FUNCTION, [snapshot.id, action.element_id], target, false)).objectId;
        if (!objectId) throw new Error("Browser element changed.");
      }
      begin();
      switch (action.action) {
        case "navigate": await this.contents.loadURL(action.url); break;
        case "close": break; // The owner disposes the verified guest.
        case "click": {
          const point = element!.point;
          await debug.sendCommand("Input.dispatchMouseEvent", {type:"mousePressed", ...point, button:"left", clickCount:1});
          await debug.sendCommand("Input.dispatchMouseEvent", {type:"mouseReleased", ...point, button:"left", clickCount:1});
          break;
        }
        case "type": {
          if (!element?.element.editable || !objectId) throw new Error("Browser element is not editable.");
          if (!(await this.call(FOCUS_ELEMENT_FUNCTION, [action.replace], {objectId})).value ||
              !(await this.call(VERIFY_FOCUSED_ELEMENT_FUNCTION, [action.element_id], {objectId})).value) throw new Error("Browser focus changed.");
          await debug.sendCommand("Input.insertText", {text:action.text});
          break;
        }
        case "key": {
          const [key,code] = keys[action.key];
          const params = {key,windowsVirtualKeyCode:code,modifiers:action.shift?8:0};
          await debug.sendCommand("Input.dispatchKeyEvent", {type:"keyDown",...params, ...(action.key === "space" || action.key === "enter" ? {text:action.key === "space" ? " " : "\r"} : {})});
          await debug.sendCommand("Input.dispatchKeyEvent", {type:"keyUp",...params});
          break;
        }
        case "scroll": {
          const result = await this.call(SCROLL_FUNCTION, [snapshot.id,action.element_id,action.delta_x,action.delta_y], objectId ? {objectId} : target);
          if (!result.value) throw new Error("Browser scroll target changed.");
          break;
        }
      }
    } finally {
      this.snapshot = undefined;
      if (objectId) await debug.sendCommand("Runtime.releaseObject", {objectId}).catch(() => {});
    }
  }
}
