"""Optional Chromium smoke check: python -m tools.check_academy_preview FILE."""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def check(path: Path, executable: str | None = None) -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=executable)
        for width in (390, 1024):
            page = browser.new_page(viewport={"width": width, "height": 850})
            errors = []
            page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
            page.route("http*://**/*", lambda route: route.abort())
            page.set_content(path.read_text(encoding="utf-8"))
            assert page.locator("#equivalence").inner_text() == "2/4 = 4/8"
            page.locator("#den").focus()
            page.keyboard.press("ArrowRight")
            assert page.locator("#equivalence").inner_text() == "2/5 = 4/10"
            assert page.locator("#double-bar .fill").count() == 4
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator("#start").click()
            tasks = page.evaluate("tasks")
            for i, task in enumerate(tasks):
                answer = page.locator("#answer")
                if i == 0:
                    answer.fill("1/0")
                    page.locator("#check").click()
                    assert "valid number" in page.locator("#feedback").inner_text()
                    page.locator("#hint").click()
                    assert page.locator("#hint-text").inner_text()
                if i == 1:
                    page.locator("#solution").click()
                    assert answer.is_disabled()
                else:
                    if i >= 4:
                        assert page.locator("#hint").is_hidden()
                        assert page.locator("#solution").is_hidden()
                    n, d = task["expected"]
                    answer.fill(f"{n + d if i == 4 else n}/{d}")
                    page.locator("#check").click()
                    if i >= 4:
                        assert page.locator("#feedback").inner_text() == (
                            "Answer recorded. Feedback comes at the end."
                        )
                        assert answer.is_disabled()
                page.locator("#next").click()
            assert page.locator("#score").inner_text() == "2/3 independent exit answers"
            assert "2/4" in page.locator("#summary").inner_text()
            assert page.locator("#review p").count() == 3
            page.locator("#restart").click()
            assert page.locator("#learn").is_visible()
            assert not errors, errors
            page.close()
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--chromium")
    args = parser.parse_args()
    check(args.file, args.chromium)
    print("Passed: 390px and 1024px full lesson smoke checks")
