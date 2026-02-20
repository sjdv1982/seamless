#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

BANNER_MARKER = "<!-- seamless-legacy-banner -->"
BANNER_SNIPPET = """<!-- seamless-legacy-banner -->
<style>
  body { padding-top: 56px; }
  #seamless-legacy-banner {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 9999;
    background: #8b0000;
    color: #ffffff;
    padding: 12px 16px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 15px;
    line-height: 1.35;
    text-align: center;
  }
  #seamless-legacy-banner a {
    color: #ffffff;
    text-decoration: underline;
    font-weight: 600;
  }
</style>
<div id="seamless-legacy-banner">
  Legacy Seamless documentation (0.x). This branch is deprecated.
  Use the new docs at <a href="/">Seamless Documentation</a>.
</div>
"""


def inject_banner(html_path: Path) -> bool:
    text = html_path.read_text(encoding="utf-8")
    if BANNER_MARKER in text:
        return False
    if "</body>" in text:
        text = text.replace("</body>", f"{BANNER_SNIPPET}\n</body>", 1)
    else:
        text = f"{text}\n{BANNER_SNIPPET}\n"
    html_path.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: inject_legacy_banner.py <legacy-dir>")
        return 2
    legacy_dir = Path(sys.argv[1]).resolve()
    if not legacy_dir.is_dir():
        print(f"Not a directory: {legacy_dir}")
        return 2

    changed = 0
    for html_path in legacy_dir.rglob("*.html"):
        if inject_banner(html_path):
            changed += 1
    print(f"Injected legacy banner into {changed} HTML files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
