"""Check the built reader with Chromium; no model inference or external network."""

import functools
import json
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "outputs" / "responsiveness-check"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def assert_no_overflow(page):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
        page.viewport_size,
        page.evaluate(
            """[...document.querySelectorAll('body *')].filter(el => {
              const r = el.getBoundingClientRect();
              return r.width && (r.right > innerWidth + 1 || r.left < -1);
            }).slice(0, 10).map(el => [el.tagName, el.id, el.className])"""
        ),
    )


def check_reader(browser, base):
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.route(
        "**/*",
        lambda route: (
            route.continue_() if route.request.url.startswith(base) else route.abort()
        ),
    )
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{base}/")
    panel = page.locator("#panel-responsiveness")
    expect(page.locator("#panel-transcript")).to_be_visible()
    page.locator('.masthead-links a[href="#responsiveness"]').click()
    expect(panel).to_be_visible()
    page.go_back()
    expect(page.locator("#panel-transcript")).to_be_visible()
    page.go_forward()
    expect(panel).to_be_visible()
    page.reload()
    expect(panel).to_be_visible()
    expect(page.locator("#reader-filters")).to_be_hidden()
    expect(page.locator("#reader-results")).to_be_hidden()
    expect(page.locator("#reader-end-note")).to_be_hidden()
    expect(page.locator("#empty-state")).to_be_hidden()
    expect(page.locator("#assessment-aligned-count")).to_have_text("2")
    expect(page.locator("#assessment-question option")).to_have_count(2)
    expect(page.locator(".answer-card")).to_have_count(2)
    expect(page.locator(".subquestions li")).to_have_count(4)

    # Read the exact reviewed text, including unresolved flags and a mixed boundary warning.
    details = page.locator(".answer-card .evidence-source").first
    details.locator("summary").click()
    source = json.loads((ROOT / "data" / "transcript.json").read_text(encoding="utf-8"))
    expected_cues = [cue for cue in source["cues"] if 766 <= cue["id"] <= 799]
    lines = details.locator(".evidence-quote p")
    expect(lines).to_have_count(len(expected_cues))
    for index, cue in enumerate(expected_cues):
        expect(lines.nth(index)).to_contain_text(cue["text"])
    expect(details.locator(".evidence-flags li")).to_have_count(4)
    expect(page.locator(".answer-card .assessment-caution").first).to_contain_text(
        "800"
    )
    page.locator(".question-card .evidence-source summary").click()
    expect(page.locator(".question-card .assessment-caution")).to_contain_text(
        "說話者未確認"
    )
    page.locator(".question-card .evidence-header .time-button").click()
    expect(page.locator("#video-link")).to_have_attribute(
        "href", re.compile(r"[?&]t=5828$")
    )
    expect(panel).to_be_visible()

    page.locator("#assessment-question").select_option("1")
    expect(page.locator(".answer-card").first).to_contain_text("沈伯洋")
    expect(page.locator(".answer-card").nth(1)).to_contain_text("蔣萬安")
    page.locator(".answer-card .evidence-link").first.click()
    expect(page.locator("#panel-transcript")).to_be_visible()
    expect(page.locator("#cue-853")).to_have_class(re.compile(r"is-target"))
    expect(page.locator("#reader-filters")).to_be_visible()
    expect(page.locator("#reader-results")).to_be_visible()
    expect(page.locator("#panel-transcript")).to_be_focused()
    page.locator("#tab-corrections").click()
    assert page.url.endswith("#cue-853")
    page.locator("#tab-responsiveness").click()
    page.locator("#tab-corrections").click()
    assert page.url.endswith("#record")
    page.locator('.masthead-links a[href="#record"]').click()
    expect(page.locator("#panel-transcript")).to_be_visible()
    page.locator("#tab-pending").click()
    page.locator(".skip-link").focus()
    page.locator(".skip-link").click()
    expect(page.locator("#panel-transcript")).to_be_visible()

    # Existing filters still work and are preserved across tab changes.
    page.locator("#search").fill("都更")
    count = int(page.locator("#count-transcript").inner_text().replace(",", ""))
    assert 0 < count < len(source["cues"])
    page.locator("#tab-responsiveness").click()
    expect(page.locator("#reader-filters")).to_be_hidden()
    page.locator("#tab-transcript").click()
    expect(page.locator("#search")).to_have_value("都更")
    expect(page.locator("#count-transcript")).to_have_text(str(count))
    page.locator("#reset-filters").click()

    # Roving tab focus, wraparound, Home and End work with all four tabs.
    page.locator("#tab-transcript").focus()
    page.keyboard.press("End")
    expect(page.locator("#tab-responsiveness")).to_be_focused()
    expect(panel).to_be_visible()
    page.keyboard.press("ArrowRight")
    expect(page.locator("#tab-transcript")).to_be_focused()
    page.keyboard.press("ArrowLeft")
    expect(page.locator("#tab-responsiveness")).to_be_focused()
    page.keyboard.press("Home")
    expect(page.locator("#tab-transcript")).to_be_focused()
    for tab in ["corrections", "pending", "responsiveness"]:
        page.keyboard.press("ArrowRight")
        expect(page.locator(f"#tab-{tab}")).to_be_focused()
    expect(page.locator('[role="tab"][aria-selected="true"]')).to_have_count(1)

    expect(page.locator("#example-rates tr").first).to_have_text("示例 A60%20%15%")
    expect(page.locator("#example-rates tr").nth(1)).to_have_text("示例 B20%25%40%")
    expect(page.locator("#example-distribution tr")).to_have_count(5)
    expect(page.locator("#quality-total")).to_have_text("— / 100")
    for key, score in zip(
        ["directness", "completeness", "specificity", "consistency"],
        [5, 4, 3, 2],
        strict=True,
    ):
        page.locator(f"#score-{key}").select_option(str(score))
    expect(page.locator("#quality-total")).to_have_text("78 / 100")
    page.locator("#score-consistency").select_option("")
    expect(page.locator("#quality-total")).to_have_text("— / 100")
    for control in page.locator("#quality-controls select").all():
        control.select_option("0")
    expect(page.locator("#quality-total")).to_have_text("0 / 100")
    page.locator("#reset-quality").click()
    expect(page.locator("#quality-total")).to_have_text("— / 100")

    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    for width in [320, 375, 768, 900, 1280, 1440]:
        page.set_viewport_size({"width": width, "height": 1000})
        for tab in ["transcript", "responsiveness"]:
            page.locator(f"#tab-{tab}").click()
            assert_no_overflow(page)
        if width in {375, 1440}:
            page.locator("#responsiveness").scroll_into_view_if_needed()
            page.screenshot(path=str(SCREENSHOTS / f"assessment-{width}.png"))
    assert not errors, errors
    context.close()


def check_offline_and_empty(browser):
    context = browser.new_context(offline=True)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{(ROOT / 'data' / 'index.html').as_uri()}#responsiveness")
    expect(page.locator("#panel-responsiveness")).to_be_visible()
    expect(page.locator("#assessment-aligned-count")).to_have_text("2")
    for control in page.locator("#quality-controls select").all():
        control.select_option("5")
    expect(page.locator("#quality-total")).to_have_text("100 / 100")
    page.reload()
    expect(page.locator("#quality-total")).to_have_text("— / 100")

    empty = {
        "metadata": {"duration": None, "model": None, "stage": None},
        "display_language": "zh-Hant-TW",
        "roles": {},
        "cues": [],
        "review": {"corrections": [], "flags": [], "method": "", "source_sha256": ""},
    }
    html = (ROOT / "data" / "index.html").read_text(encoding="utf-8")
    html = re.sub(
        r'(<script type="application/json" id="debate-data">).*?(</script>)',
        lambda match: match[1] + json.dumps(empty) + match[2],
        html,
        flags=re.DOTALL,
    )
    page.set_content(html)
    page.locator("#tab-responsiveness").click()
    expect(page.locator("#assessment-aligned-count")).to_have_text("0")
    expect(page.locator("#assessment-question")).to_be_hidden()
    expect(page.locator("#assessment-question-label")).to_be_hidden()
    expect(page.locator("#assessment-alignment-status")).to_contain_text("尚無已對齊")
    expect(page.locator("#empty-state")).to_be_hidden()
    expect(page.locator("#quality-total")).to_have_text("— / 100")
    assert not errors, errors
    context.close()


def main():
    handler = functools.partial(QuietHandler, directory=ROOT / "data")
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    check_reader(browser, f"http://127.0.0.1:{server.server_port}")
                    check_offline_and_empty(browser)
                finally:
                    browser.close()
        finally:
            server.shutdown()
            thread.join()
    print(f"Browser checks passed. Screenshots: {SCREENSHOTS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
