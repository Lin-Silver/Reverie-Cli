// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it } from "vitest";
import { viewHostContext } from "./view-host-context";

afterEach(() => {
  document.documentElement.removeAttribute("style");
  delete document.documentElement.dataset.theme;
});

describe("semantic colors received by an embedded view", () => {
  it.each(["dark", "light"])("exports current %s success, warning and info colors", theme => {
    document.documentElement.dataset.theme = theme;
    const values = theme === "dark"
      ? { "--green": "#72d4a4", "--amber": "#e8bd74", "--blue": "#83b7ff" }
      : { "--green": "#176a46", "--amber": "#815318", "--blue": "#285f9d" };
    for (const [key, value] of Object.entries(values)) document.documentElement.style.setProperty(key, value);
    const context = viewHostContext(document.createElement("iframe"), "zh-CN", "inline");
    expect(context.styles.variables).toMatchObject({
      "--color-text-success": values["--green"],
      "--color-text-warning": values["--amber"],
      "--color-text-info": values["--blue"],
    });
  });
});

const styles = readFileSync("src/styles.css", "utf8");
const glass = readFileSync("src/liquid-glass.css", "utf8");
const light = styles.split(':root[data-theme="light"] {')[1].split("}")[0];
const glassLight = glass.split('&[data-theme="light"] {')[1].split("}")[0];
function color(css: string, name: string) {
  const match = css.match(new RegExp(`${name}:\\s*(#[0-9a-f]{6});`, "i"));
  if (!match) throw new Error(`Missing opaque theme color: ${name}`);
  return match[1];
}
function luminance(hex: string) {
  const channels = [1, 3, 5].map(i => Number.parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
  return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
}
it.each(["--green", "--amber", "--blue", "--red"])("keeps %s text readable on the light glass background", variable => {
  const text = luminance(color(light, variable));
  const background = luminance(color(glassLight, "--bg"));
  expect((Math.max(text, background) + .05) / (Math.min(text, background) + .05)).toBeGreaterThanOrEqual(4.5);
});
