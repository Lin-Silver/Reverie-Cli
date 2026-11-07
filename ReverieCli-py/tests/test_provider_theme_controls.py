"""Check the provider controls with the browser's actual CSS cascade."""

from pathlib import Path
import os

import pytest


UI_ROOT = Path(__file__).resolve().parents[2] / "ReverieCli-ui"
CSS = "\n".join((UI_ROOT / "src" / name).read_text(encoding="utf-8") for name in (
    "styles.css", "desktop.css", "liquid-glass.css", "classic-light.css",
))


@pytest.fixture(scope="module")
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        channel = None
        if os.name == "nt":
            edge = Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe"
            if edge.is_file():
                channel = "msedge"
        if channel is None and not Path(runtime.chromium.executable_path).is_file():
            pytest.skip("A Chromium browser is required for computed-theme checks.")
        instance = runtime.chromium.launch(headless=True, channel=channel)
        yield instance
        instance.close()


def _page(browser, theme: str, variant: str, content: str):
    page = browser.new_page(viewport={"width": 1100, "height": 800}, reduced_motion="reduce")
    page.set_content(f'<html data-theme="{theme}" data-ui="{variant}" data-accent="rose"><head></head><body><div class="app-shell">{content}</div></body></html>')
    page.add_style_tag(content=CSS)
    return page


def _contrast(button):
    return button.evaluate("""element => {
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 1;
      const context = canvas.getContext('2d', {willReadFrequently: true});
      const rgba = color => {
        context.clearRect(0, 0, 1, 1);
        context.fillStyle = color;
        context.fillRect(0, 0, 1, 1);
        return Array.from(context.getImageData(0, 0, 1, 1).data);
      };
      const ancestors = [];
      for(let node = element; node; node = node.parentElement) ancestors.unshift(node);
      let background = [255, 255, 255];
      for(const node of ancestors) {
        const color = rgba(getComputedStyle(node).backgroundColor);
        const alpha = color[3] / 255;
        background = background.map((channel, index) => color[index] * alpha + channel * (1-alpha));
      }
      const foreground = rgba(getComputedStyle(element).color).slice(0, 3);
      const luminance = color => color.map(channel => {
        const value = channel / 255;
        return value <= .04045 ? value / 12.92 : ((value+.055)/1.055) ** 2.4;
      }).reduce((total, value, index) => total + value * [.2126, .7152, .0722][index], 0);
      const light = luminance(foreground), dark = luminance(background);
      return {ratio: (Math.max(light,dark)+.05)/(Math.min(light,dark)+.05),
              color: getComputedStyle(element).color, background: getComputedStyle(element).backgroundColor};
    }""")


@pytest.mark.parametrize("variant", ["classic", "liquid-glass"])
def test_add_provider_text_remains_readable_when_hovered(browser, variant):
    page = _page(browser, "light", variant, '<div class="form-modal"><div class="form-modal-footer"><button class="primary-button">添加 Provider</button></div></div>')
    try:
        button = page.get_by_role("button", name="添加 Provider", exact=True)
        button.hover()
        page.wait_for_timeout(200)
        actual = _contrast(button)
        assert actual["ratio"] >= 4.5, actual
    finally:
        page.close()


def test_liquid_glass_back_to_model_list_is_a_readable_control(browser):
    page = _page(browser, "dark", "liquid-glass", '<div class="model-picker"><div class="model-picker-sources"></div><div class="model-picker-models"><div class="model-picker-header"><div>选择思考程度</div><button class="ghost-button">返回模型列表</button></div></div></div>')
    try:
        button = page.get_by_role("button", name="返回模型列表", exact=True)
        actual = _contrast(button)
        assert actual["ratio"] >= 4.5, actual
        assert button.bounding_box()["height"] >= 28
    finally:
        page.close()
