"""Render the report HTML to an A4 PDF with headless Chromium (Playwright)."""
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

exe = "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=exe)
    pg = b.new_page()
    pg.goto(Path(sys.argv[1]).resolve().as_uri())
    pg.pdf(path=sys.argv[2], format="A4", print_background=True)
    b.close()
