#!/usr/bin/env python3
"""make_lazygit_gif.py — assemble the lazygit drive reel into a GIF.

Input: /tmp/lgframes/NN.ansi (real ANSI frames captured driving lazygit in the
Linux container) + labels.txt (a caption per beat). Renders each frame to a PNG
via the project's own pyte->PNG pipeline (tools/screenshot), stacks a caption
bar on top, and writes an animated GIF. Pure local; no processes driven here.
"""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tools" / "screenshot"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
import shot  # noqa: E402

SRC = r"C:\Users\dwgx1\AppData\Local\Temp\lgframes"
OUT = _ROOT / "docs" / "site" / "assets" / "drive-lazygit.gif"
COLS, ROWS = 100, 30
CELL_W, CELL_H = 7, 14
CAP_H = 30           # caption bar height (px)
BG = (13, 12, 10)    # #0d0c0a warm near-black to match the site
CORAL = (204, 120, 92)
DIM = (142, 139, 130)


def load_labels():
    p = os.path.join(SRC, "labels.txt")
    if os.path.exists(p):
        return [l.strip() for l in open(p, encoding="utf-8") if l.strip()]
    return []


def caption_font(sz=13):
    for name in ("consola.ttf", "cour.ttf", "DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(name, sz)
        except Exception:
            continue
    return ImageFont.load_default()


def main() -> int:
    labels = load_labels()
    frames = sorted(glob.glob(os.path.join(SRC, "[0-9][0-9].ansi")))
    if not frames:
        print("no frames found in", SRC)
        return 1
    font = caption_font()
    imgs = []
    for i, fp in enumerate(frames):
        data = open(fp, "rb").read()
        screen = shot.render_bytes_to_screen(data, COLS, ROWS)
        body = os.path.join(SRC, f"_body_{i}.png")
        w, h = shot.screen_to_png(screen, body, cell_w=CELL_W, cell_h=CELL_H,
                                  default_fg=(232, 230, 246), default_bg=BG,
                                  draw_cursor=False)
        term = Image.open(body).convert("RGB")
        # compose: caption bar + terminal
        canvas = Image.new("RGB", (w, h + CAP_H), BG)
        d = ImageDraw.Draw(canvas)
        label = labels[i] if i < len(labels) else ""
        # color the "perceive/act/confirm" verb coral, rest dim
        d.text((12, 8), label, font=font, fill=DIM)
        # a coral accent for the leading verb
        verb = label.split(" ")[0] if label else ""
        if verb:
            d.text((12, 8), verb, font=font, fill=CORAL)
        canvas.paste(term, (0, CAP_H))
        imgs.append(canvas)
        os.remove(body)

    # hold each beat ~1.6s; a longer hold on the diff/confirm frames
    durs = [1600] * len(imgs)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pal = imgs[0].quantize(colors=128, method=Image.MEDIANCUT)
    q = [im.quantize(colors=128, palette=pal, dither=Image.NONE) for im in imgs]
    q[0].save(OUT, save_all=True, append_images=q[1:], loop=0,
              duration=durs, disposal=2, optimize=False)
    print(f"wrote {OUT}  ({len(imgs)} frames, {imgs[0].size[0]}x{imgs[0].size[1]}px, "
          f"{OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
