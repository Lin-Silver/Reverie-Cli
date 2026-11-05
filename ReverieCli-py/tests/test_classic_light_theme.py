"""Check classic light surfaces and contrast with the actual CSS in Chromium."""
from pathlib import Path

import pytest


UI_ROOT = Path(__file__).resolve().parents[2] / "ReverieCli-ui"


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            pytest.skip("Chromium is required to verify theme colors")
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


def theme_page(browser, variant, theme, background, accent="violet"):
    page = browser.new_page()
    page.set_content(f'''<html data-ui="{variant}" data-theme="{theme}" data-accent="{accent}"
        class="{'has-workspace-background' if background else ''}"><body>
      <div class="app-shell"><aside class="sidebar">项目与会话</aside>
      <main class="main-area"><div class="settings-page"><nav class="settings-nav">外观</nav>
      <div class="settings-content"><section class="preference-section">
        <div class="preference-heading"><div><h2>界面主题</h2><p>选择整体界面阅读尺度</p></div></div>
        <span class="ui-variant-preview classic"><i></i><span><b></b></span></span>
        <button class="primary-button">导入图片</button>
        <button class="toggle"><span></span></button>
        <button class="toggle on"><span></span></button>
      </section></div></div></main></div></body></html>''')
    for stylesheet in ("styles.css", "desktop.css", "liquid-glass.css"):
        page.add_style_tag(content=(UI_ROOT / "src" / stylesheet).read_text(encoding="utf-8"))
    # Compare the final palette, rather than intermediate button color transitions.
    page.add_style_tag(content="*, *::before, *::after { transition: none !important; animation: none !important; }")
    return page


def colors(page):
    return page.evaluate('''() => {
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 1;
      const context = canvas.getContext('2d');
      const rgba = color => {
        context.clearRect(0, 0, 1, 1); context.fillStyle = color; context.fillRect(0, 0, 1, 1);
        return [...context.getImageData(0, 0, 1, 1).data];
      };
      const selectors = ['.main-area', '.sidebar', '.settings-nav', '.preference-section',
        '.preference-heading p', '.ui-variant-preview.classic', '.primary-button', '.toggle', '.toggle.on', '.toggle.on span'];
      return Object.fromEntries(selectors.map(selector => {
        const style = getComputedStyle(document.querySelector(selector));
        return [selector, { background: rgba(style.backgroundColor), text: rgba(style.color) }];
      }));
    }''')


def contrast(first, second):
    def luminance(color):
        values = [channel / 255 for channel in color[:3]]
        linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in values]
        return sum(value * weight for value, weight in zip(linear, [.2126, .7152, .0722]))
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + .05) / (dark + .05)


@pytest.mark.parametrize("background", [False, True])
@pytest.mark.parametrize("accent", ["violet", "blue", "teal", "rose", "amber"])
def test_classic_light_stays_readable_with_wallpaper(browser, background, accent):
    page = theme_page(browser, "classic", "light", background, accent)
    try:
        stylesheet = UI_ROOT / "src/classic-light.css"
        if stylesheet.is_file():
            page.add_style_tag(content=stylesheet.read_text(encoding="utf-8"))
        result = colors(page)
        assert result[".main-area"]["background"][3] >= 244
        assert result[".sidebar"]["background"][3] == 255
        assert result[".settings-nav"]["background"][3] == 255
        assert min(result[".ui-variant-preview.classic"]["background"][:3]) > 200
        panel = result[".preference-section"]["background"]
        assert contrast(result[".preference-heading p"]["text"], panel) >= 4.5
        button = result[".primary-button"]
        assert contrast(button["text"], button["background"]) >= 4.5
        assert min(result[".toggle"]["background"][:3]) > 200
        assert result[".toggle.on"]["background"] == button["background"]
        assert contrast(result[".toggle.on span"]["background"], result[".toggle.on"]["background"]) >= 3
        assert 'import "./classic-light.css";' in (UI_ROOT / "src/main.tsx").read_text(encoding="utf-8")
    finally:
        page.close()


@pytest.mark.parametrize("background", [False, True])
@pytest.mark.parametrize("variant,theme", [("classic", "dark"), ("liquid-glass", "dark"), ("liquid-glass", "light")])
def test_classic_light_does_not_restyle_other_appearances(browser, background, variant, theme):
    page = theme_page(browser, variant, theme, background)
    try:
        before = colors(page)
        stylesheet = UI_ROOT / "src/classic-light.css"
        if stylesheet.is_file():
            page.add_style_tag(content=stylesheet.read_text(encoding="utf-8"))
        assert colors(page) == before
    finally:
        page.close()
