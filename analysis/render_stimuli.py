"""
Render the 4 stimulus screenshots from index.html (one per condition).

Loads index.html locally in headless Chromium, calls applyCondition(n) and
showScreen(2) to land on the HLXE listing screen, screenshots #screen-2,
and saves to slides/.

Run:
    python3 render_stimuli.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
INDEX = ROOT / "index.html"
OUT = ROOT / "slides"
OUT.mkdir(exist_ok=True)

CELLS = [
    (1, "neutral", "no"),
    (2, "neutral", "yes"),
    (3, "hyped", "no"),
    (4, "hyped", "yes"),
]


def main():
    if not INDEX.exists():
        sys.exit(f"index.html not found at {INDEX}")
    url = INDEX.as_uri()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 480, "height": 1600},
                                      device_scale_factor=2)
        page = context.new_page()

        for n, head, social in CELLS:
            page.goto(url, wait_until="domcontentloaded")
            page.evaluate(
                """(c) => {
                    state.condition = c;
                    applyCondition(c);
                    showScreen(2);
                }""",
                n,
            )
            # let any layout settle
            page.wait_for_timeout(150)
            target = page.locator("#screen-2")
            out_path = OUT / f"cell_{n}_{head}_{social}.png"
            target.screenshot(path=str(out_path))
            print(f"wrote {out_path}")

        browser.close()


if __name__ == "__main__":
    main()
