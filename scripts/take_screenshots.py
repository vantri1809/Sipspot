#!/usr/bin/env python3
"""Capture homepage (desktop + mobile) and one city page via Chrome."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "screenshots"


def cities():
    path = ROOT / "data" / "cities.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text())


def pick_city():
    rows = cities()
    if not rows:
        return "london"
    rows = sorted(rows, key=lambda c: c.get("osm_count") or 0, reverse=True)
    return rows[0]["slug"]


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. Trying a one-shot pip install...", flush=True)
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "-q"])
        from playwright.sync_api import sync_playwright

    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
    slug = pick_city()
    SHOTS.mkdir(parents=True, exist_ok=True)

    chrome = Path("/usr/bin/google-chrome")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=str(chrome) if chrome.exists() else None,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        def snap(url, path, width, height, label):
            page = browser.new_page(viewport={"width": width, "height": height}, locale="en-GB")
            page.goto(url, wait_until="networkidle", timeout=60000)
            # Wait for the map pane and at least one canvas/tile or leaflet pane
            page.wait_for_selector("#map", timeout=20000)
            page.wait_for_timeout(3500)
            page.screenshot(path=str(path), full_page=False)
            print(f"Wrote {path} ({label}, {width}x{height})")
            page.close()

        snap(base + "/", SHOTS / "homepage-desktop.png", 1440, 900, "homepage desktop")
        snap(base + "/", SHOTS / "homepage-mobile.png", 390, 844, "homepage mobile")
        snap(base + f"/{slug}/", SHOTS / "city-page.png", 1440, 900, f"city page /{slug}/")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
