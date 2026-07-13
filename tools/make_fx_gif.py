#!/usr/bin/env python
"""make_fx_gif.py — capture a REAL run of a cmd-art fx effect as an animated GIF.

This is genuine real-engine capture, not a mock and NOT a screen recording: it
instantiates the actual fx Effect, calls its pure `render(ctx)` frame by frame
(exactly what `python -m fx play` does), turns each frame into a pyte screen via
the project's own screenshot pipeline, rasterises it to a PIL image, and writes
the sequence as a looping GIF. Pure Python, ZERO process spawning — safe to run
at any scale (see repo CLAUDE.md spawn red-line).

Usage:
    python tools/make_fx_gif.py rain --frames 60 --out docs/site/assets/fx-rain.gif
    python tools/make_fx_gif.py plasma --w 80 --h 24 --theme synthwave
    python tools/make_fx_gif.py --all           # one GIF per effect in a set
"""
from __future__ import annotations

import argparse
import io
import math
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "skills" / "cmd-art"))
sys.path.insert(0, str(_ROOT / "tools" / "screenshot"))

from PIL import Image  # noqa: E402
import shot  # noqa: E402
from fx import registry  # noqa: E402
from fx.base import FrameCtx  # noqa: E402
from fx.theme import get_theme  # noqa: E402

# Warm-editorial terminal background/fg to match docs/site (not pure black).
BG = (24, 23, 21)     # #181715
FG = (250, 249, 245)  # #faf9f5


def render_gif(name: str, out: Path, frames: int = 60, w: int = 76, h: int = 22,
               theme: str | None = None, fps: int = 20, cell_w: int = 8,
               cell_h: int = 16, params: dict | None = None) -> None:
    registry.load_all()
    cls = next((c for c in registry.all_effects() if c.name == name), None)
    if cls is None:
        raise SystemExit(f"unknown effect: {name}")
    eff = cls()
    eff.setup()
    imgs: list[Image.Image] = []
    p = dict(cls.param_defaults())
    if params:
        p.update(params)
    try:
        for i in range(frames):
            t = i / fps
            ctx = FrameCtx(t=t, frame_index=i, width=w, height=h,
                           theme=get_theme(theme or cls.preferred_theme),
                           params=p)
            frame = eff.render(ctx)
            data = shot.render_frame_to_bytes(frame)
            screen = shot.render_bytes_to_screen(data, w, h)
            # rasterise this frame to an in-memory PNG, then load as an Image
            buf = io.BytesIO()
            # screen_to_png writes to a path; capture via a temp in-memory round-trip
            tmp = out.with_suffix(".frame.png")
            shot.screen_to_png(screen, str(tmp), cell_w=cell_w, cell_h=cell_h,
                               default_fg=FG, default_bg=BG, draw_cursor=False)
            imgs.append(Image.open(tmp).convert("RGB").copy())
    finally:
        try:
            eff.teardown()
        except Exception:
            pass
        # clean the scratch frame
        tmp = out.with_suffix(".frame.png")
        if tmp.exists():
            tmp.unlink()

    if not imgs:
        raise SystemExit("no frames rendered")
    out.parent.mkdir(parents=True, exist_ok=True)
    # Quantize every frame to ONE shared adaptive palette (64 colors is plenty
    # for these ASCII gradients) so the GIF stays small and the palette does not
    # flicker between frames.
    pal_src = imgs[0].quantize(colors=40, method=Image.MEDIANCUT)
    q = [im.quantize(colors=40, palette=pal_src, dither=Image.NONE) for im in imgs]
    dur = int(1000 / fps)
    # optimize=False: keep EVERY frame. optimize drops "duplicate" frames, which
    # corrupts exact-timing seamless loops (the loop window must contain exactly
    # `frames` steps of duration `dur`). The 64-colour palette keeps size sane.
    q[0].save(out, save_all=True, append_images=q[1:], loop=0,
              duration=dur, disposal=2, optimize=False)
    print(f"wrote {out}  ({len(q)} frames, {w}x{h} cells, "
          f"{imgs[0].size[0]}x{imgs[0].size[1]}px, {out.stat().st_size//1024} KB)")


# Curated set: ALL rendered at the SAME cell size (72x24) so every GIF shares
# one aspect ratio and the gallery grid tiles perfectly. Where an effect is
# periodic (rotation / orbits), 'loop' is chosen so the capture window is an
# EXACT integer number of cycles -> the GIF loops with no visible seam:
#   * donut : A=1.2·s, B=0.6·s. With s so B·loop = 2π·1 and A·loop = 2π·2.
#   * sphere: A=0.9·s, B=1.3·s. loop chosen so both are integer turns.
#   * solarsystem: seamless by construction (integer turns/loop, see the effect).
#   * fire/rain are stochastic (no periodicity) — chaotic, so no hard seam shows;
#     we just capture a natural window.
_BASE = dict(w=72, h=24, fps=24)


def _frames(loop, fps):
    return max(1, round(loop * fps))


CURATED = [
    # donut: speed 2.618 -> B rate 1.5708 -> loop = EXACTLY 4.0s (A: 2 turns,
    # B: 1 turn). 4.0·24 = 96 whole frames -> frame-exact seamless, half the
    # weight of the 8s version.
    ("donut",  dict(_BASE, theme="ocean", params={"speed": 2.618},
                    frames=_frames(4.0, 24))),
    # tunnel: texture wraps every TEX; speed=1,twist=1 -> loop EXACTLY 4.0s.
    # 4.0·24 = 96 whole frames -> frame-exact seamless. Fills the whole frame.
    ("tunnel", dict(_BASE, theme="synthwave", params={"speed": 1.0, "twist": 1.0},
                    frames=_frames(4.0, 24))),
    # fire / rain are stochastic (random heat / drops) — no periodicity, but they
    # are chaotic so no hard seam is visible on loop; capture a natural window.
    ("fire",   dict(_BASE, theme="fire", params={"cool": 1}, frames=72)),
    ("rain",   dict(_BASE, theme="matrix-green", frames=72)),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("effect", nargs="?", help="effect name (e.g. rain, plasma)")
    ap.add_argument("--out", help="output .gif path")
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--w", type=int, default=76)
    ap.add_argument("--h", type=int, default=22)
    ap.add_argument("--fps", type=int, default=20)
    ap.add_argument("--theme")
    ap.add_argument("--all", action="store_true", help="render the curated set")
    args = ap.parse_args()

    if args.all:
        for name, opts in CURATED:
            out = _ROOT / "docs" / "site" / "assets" / f"fx-{name}.gif"
            render_gif(name, out, **opts)
        return 0

    if not args.effect:
        ap.error("give an effect name, or --all")
    out = Path(args.out) if args.out else \
        _ROOT / "docs" / "site" / "assets" / f"fx-{args.effect}.gif"
    render_gif(args.effect, out, frames=args.frames, w=args.w, h=args.h,
               fps=args.fps, theme=args.theme)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
