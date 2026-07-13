#!/usr/bin/env python
"""make_fx_video.py — capture a REAL run of a cmd-art fx effect as 60fps video.

Same genuine real-engine capture as make_fx_gif.py (instantiate the actual fx
Effect, call its pure render(ctx) frame by frame, rasterise via the project's own
pyte->PIL pipeline) — but instead of a GIF (capped near 50fps, browsers clamp
short delays), it pipes raw RGB frames to the bundled ffmpeg and encodes a
smooth 60fps H.264 MP4 (yuv420p, Safari/iOS-safe) + VP9 WebM. Both loop
seamlessly because the capture window is an EXACT integer number of the effect's
periods (see CURATED). Pure Python + a bundled static ffmpeg binary; ZERO process
spawning of the target (safe at any scale — repo CLAUDE.md spawn red-line).

Usage:
    python tools/make_fx_video.py --all
    python tools/make_fx_video.py donut --seconds 4 --fps 60 --theme ocean
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "skills" / "cmd-art"))
sys.path.insert(0, str(_ROOT / "tools" / "screenshot"))

from PIL import Image  # noqa: E402
import imageio_ffmpeg  # noqa: E402
import shot  # noqa: E402
from fx import registry  # noqa: E402
from fx.base import FrameCtx  # noqa: E402
from fx.theme import get_theme  # noqa: E402

# Warm-editorial terminal background/fg matching docs/site (not pure black).
BG = (24, 23, 21)     # #181715
FG = (250, 249, 245)  # #faf9f5

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def _render_frames(name, frames, w, h, theme, fps, cell_w, cell_h, params, out):
    """Yield (rgb_bytes, px_w, px_h) for each rendered frame."""
    registry.load_all()
    cls = next((c for c in registry.all_effects() if c.name == name), None)
    if cls is None:
        raise SystemExit(f"unknown effect: {name}")
    eff = cls()
    eff.setup()
    p = dict(cls.param_defaults())
    if params:
        p.update(params)
    tmp = out.with_suffix(".frame.png")
    px_w = px_h = None
    try:
        for i in range(frames):
            t = i / fps
            ctx = FrameCtx(t=t, frame_index=i, width=w, height=h,
                           theme=get_theme(theme or cls.preferred_theme),
                           params=p)
            frame = eff.render(ctx)
            data = shot.render_frame_to_bytes(frame)
            screen = shot.render_bytes_to_screen(data, w, h)
            shot.screen_to_png(screen, str(tmp), cell_w=cell_w, cell_h=cell_h,
                               default_fg=FG, default_bg=BG, draw_cursor=False)
            im = Image.open(tmp).convert("RGB")
            if px_w is None:
                # yuv420p needs even dimensions; pad the canvas if odd.
                px_w = im.width + (im.width & 1)
                px_h = im.height + (im.height & 1)
            if (im.width, im.height) != (px_w, px_h):
                padded = Image.new("RGB", (px_w, px_h), BG)
                padded.paste(im, (0, 0))
                im = padded
            yield im.tobytes(), px_w, px_h
    finally:
        try:
            eff.teardown()
        except Exception:
            pass
        if tmp.exists():
            tmp.unlink()


def _encode(cmd):
    proc = subprocess.run(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE)
    return proc


def render_video(name, out_stem, seconds=4.0, w=72, h=24, fps=60,
                 theme=None, cell_w=8, cell_h=16, params=None):
    frames = max(1, round(seconds * fps))
    # Materialise frames once (the render is deterministic; we feed the same
    # raw stream to both encoders).
    gen = _render_frames(name, frames, w, h, theme, fps, cell_w, cell_h,
                         params, out_stem.with_suffix(".mp4"))
    raw = bytearray()
    px_w = px_h = None
    for buf, pw, ph in gen:
        raw += buf
        px_w, px_h = pw, ph
    if px_w is None:
        raise SystemExit("no frames rendered")

    size = f"{px_w}x{px_h}"
    base_in = [FFMPEG, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", size, "-r", str(fps), "-i", "pipe:0"]

    mp4 = out_stem.with_suffix(".mp4")
    webm = out_stem.with_suffix(".webm")
    mp4.parent.mkdir(parents=True, exist_ok=True)

    # H.264 MP4 — yuv420p + faststart so it streams and plays everywhere.
    mp4_cmd = base_in + ["-an", "-c:v", "libx264", "-preset", "veryslow",
                         "-crf", "20", "-pix_fmt", "yuv420p",
                         "-movflags", "+faststart", str(mp4)]
    # VP9 WebM — better compression, alpha-free, great in Chrome/FF.
    webm_cmd = base_in + ["-an", "-c:v", "libvpx-vp9", "-b:v", "0",
                          "-crf", "30", "-pix_fmt", "yuv420p",
                          "-row-mt", "1", str(webm)]

    for label, cmd, dst in (("mp4", mp4_cmd, mp4), ("webm", webm_cmd, webm)):
        proc = subprocess.run(cmd, input=bytes(raw),
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr.decode("utf-8", "replace")[-800:])
            raise SystemExit(f"ffmpeg {label} failed for {name}")
        print(f"wrote {dst}  ({frames} frames @ {fps}fps, {size}px, "
              f"{dst.stat().st_size // 1024} KB)")


# Curated set mirrors make_fx_gif CURATED: SAME cell size (72x24) and SAME
# seamless-loop windows (integer periods) so each video loops with no seam.
_BASE = dict(w=72, h=24, fps=60)

CURATED = [
    ("donut",  dict(_BASE, theme="ocean", params={"speed": 2.618}, seconds=4.0)),
    ("tunnel", dict(_BASE, theme="synthwave",
                    params={"speed": 1.0, "twist": 1.0}, seconds=4.0)),
    ("fire",   dict(_BASE, theme="fire", params={"cool": 1}, seconds=4.0)),
    ("rain",   dict(_BASE, theme="matrix-green", seconds=4.0)),
    # solarsystem: LOOP_SECONDS = 12.0 (integer orbits/pulse per loop).
    ("solarsystem", dict(_BASE, theme=None, seconds=12.0)),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("effect", nargs="?")
    ap.add_argument("--out", help="output path stem (no extension)")
    ap.add_argument("--seconds", type=float, default=4.0)
    ap.add_argument("--w", type=int, default=72)
    ap.add_argument("--h", type=int, default=24)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--theme")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    if args.all:
        for name, opts in CURATED:
            stem = _ROOT / "docs" / "site" / "assets" / f"fx-{name}"
            render_video(name, stem, **opts)
        return 0

    if not args.effect:
        ap.error("give an effect name, or --all")
    stem = Path(args.out) if args.out else \
        _ROOT / "docs" / "site" / "assets" / f"fx-{args.effect}"
    render_video(args.effect, stem, seconds=args.seconds, w=args.w, h=args.h,
                 fps=args.fps, theme=args.theme)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
