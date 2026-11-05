"""Verify transcript alignment with the renderer's actual CSS in Chromium."""
from pathlib import Path

import pytest


UI_ROOT = Path(__file__).resolve().parents[2] / "ReverieCli-ui"


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            pytest.skip("Chromium is required to verify transcript geometry")
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("variant", ["classic", "liquid-glass"])
@pytest.mark.parametrize("width", [640, 1280])
def test_user_bubbles_stay_right_and_answers_stay_left(browser, theme, variant, width):
    page = browser.new_page(viewport={"width": width, "height": 960})
    try:
        page.set_content(f'''<html data-theme="{theme}" data-ui="{variant}">
          <body><div class="message-column">
            <article class="message user">
              <div class="message-heading"><div class="message-avatar">你</div></div>
              <div class="message-body"><div class="user-text">查看任务列表</div></div>
            </article>
            <article class="message user live-user-message">
              <div class="message-heading"><div class="message-avatar">你</div></div>
              <div class="message-body"><div class="user-text">{'LongMessage' * 200}</div>
                <button class="message-attachment">task.md</button></div>
            </article>
            <article class="message assistant">
              <div class="message-heading"><div class="message-avatar">R</div><strong>Reverie</strong></div>
              <div class="message-body"><div class="markdown"><p>任务列表已读取。</p></div></div>
            </article>
          </div></body></html>''')
        # Match main.tsx import order, including the nested Liquid Glass rules.
        for stylesheet in ("styles.css", "desktop.css", "liquid-glass.css", "classic-light.css"):
            page.add_style_tag(content=(UI_ROOT / "src" / stylesheet).read_text(encoding="utf-8"))
        column = page.locator(".message-column").bounding_box()
        answer = page.locator(".message.assistant .markdown").bounding_box()
        assert abs(answer["x"] - column["x"] - 38) <= .5
        for index in range(2):
            message = page.locator(".message.user").nth(index)
            body = message.locator(".message-body").bounding_box()
            avatar = message.locator(".message-avatar").bounding_box()
            assert abs(avatar["x"] + avatar["width"] - column["x"] - column["width"]) <= .5
            assert abs(body["x"] + body["width"] + 38 - column["x"] - column["width"]) <= .5
            assert body["x"] >= column["x"]
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        page.close()
