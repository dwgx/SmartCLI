#!/usr/bin/env python
"""One-shot: swap fx-*.gif <img> tags for <video> in the localized site pages,
preserving each page's translated alt/figcaption. Idempotent. Not shipped."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = [ROOT / "docs" / "site" / f"index.{lang}.html"
         for lang in ("zh-Hans", "zh-Hant", "ja", "ko")]
FX = ["fx-solarsystem", "fx-donut", "fx-tunnel", "fx-fire", "fx-rain"]


def video_tag(stem, alt, hero):
    poster = f' poster="assets/{stem}.gif"' if hero else ""
    return (
        f'<video autoplay muted loop playsinline preload="metadata"{poster} '
        f'aria-label="{alt}">'
        f'<source src="assets/{stem}.webm" type="video/webm">'
        f'<source src="assets/{stem}.mp4" type="video/mp4">'
        f'<img src="assets/{stem}.gif" alt="{alt}"></video>'
    )


def main():
    for page in PAGES:
        html = page.read_text(encoding="utf-8")
        orig = html
        # CSS rules -> cover <video> too
        html = html.replace(
            ".gif-hero img{width:100%;height:auto;display:block}",
            ".gif-hero img,.gif-hero video{width:100%;height:auto;display:block}")
        html = html.replace(
            ".gifs img{width:100%;aspect-ratio:3/2;object-fit:cover;display:block}",
            ".gifs img,.gifs video{width:100%;aspect-ratio:3/2;"
            "object-fit:cover;display:block}")
        # swap each fx img -> video, capturing its (translated) alt
        for stem in FX:
            hero = stem == "fx-solarsystem"
            pat = re.compile(
                r'<img src="assets/' + re.escape(stem) +
                r'\.gif" alt="([^"]*)"(?: loading="lazy")?>')
            m = pat.search(html)
            if not m:
                print(f"  [skip] {page.name}: {stem} not found (already swapped?)")
                continue
            html = pat.sub(lambda mm: video_tag(stem, mm.group(1), hero), html, count=1)
        if html != orig:
            page.write_text(html, encoding="utf-8")
            print(f"  [ok]  {page.name}")
        else:
            print(f"  [--]  {page.name}: no change")
    return 0


if __name__ == "__main__":
    sys.exit(main())
