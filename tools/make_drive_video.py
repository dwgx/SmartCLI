#!/usr/bin/env python3
"""make_drive_video.py — assemble a real-TUI drive reel into a 30fps video.

Input: <src>/NNNN.ansi (real ANSI frames captured driving a TUI in the Linux
container at 30fps by tests/_demo_drive.py) + labels.txt (one caption per frame).
Renders each frame to a PNG via the project's own pyte->PNG pipeline
(tools/screenshot), stacks a caption bar on top, and pipes the sequence to the
bundled ffmpeg as an H.264 MP4 (yuv420p, Safari/iOS-safe) + VP9 WebM. Identical
consecutive frames cost almost nothing in these codecs, so a 30fps reel of a
mostly-static TUI stays small. Pure local; no processes driven here.

Usage:
    python tools/make_drive_video.py --src <dir> --out docs/site/assets/drive-htop
    python tools/make_drive_video.py --all      # every reel from the default temp dirs
"""
from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tools" / "screenshot"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
import imageio_ffmpeg  # noqa: E402
import shot  # noqa: E402

CELL_W, CELL_H = 7, 14
CAP_H = 30            # caption bar height (px)
FPS = 30
BG = (13, 12, 10)     # #0d0c0a warm near-black to match the site
CORAL = (204, 120, 92)
DIM = (168, 164, 152)
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def load_labels(src):
    p = os.path.join(src, "labels.txt")
    if os.path.exists(p):
        return [l.rstrip("\n") for l in open(p, encoding="utf-8")]
    return []


def caption_font(sz=13):
    for name in ("consola.ttf", "cour.ttf", "DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(name, sz)
        except Exception:
            continue
    return ImageFont.load_default()


def build(src: str, out_stem: Path, cols: int, rows: int) -> int:
    labels = load_labels(src)
    frames = sorted(glob.glob(os.path.join(src, "[0-9][0-9][0-9][0-9].ansi")))
    if not frames:
        # fall back to the old 2-digit naming so old captures still work
        frames = sorted(glob.glob(os.path.join(src, "[0-9][0-9].ansi")))
    if not frames:
        print("no frames found in", src)
        return 1
    font = caption_font()

    body = out_stem.with_suffix(".body.png")
    px_w = px_h = None
    raw = bytearray()
    for i, fp in enumerate(frames):
        data = open(fp, "rb").read()
        screen = shot.render_bytes_to_screen(data, cols, rows)
        w, h = shot.screen_to_png(screen, str(body), cell_w=CELL_W, cell_h=CELL_H,
                                  default_fg=(232, 230, 246), default_bg=BG,
                                  draw_cursor=False)
        term = Image.open(body).convert("RGB")
        canvas = Image.new("RGB", (w, h + CAP_H), BG)
        d = ImageDraw.Draw(canvas)
        label = labels[i] if i < len(labels) else ""
        d.text((12, 8), label, font=font, fill=DIM)
        verb = label.split(" ")[0] if label else ""
        if verb:
            d.text((12, 8), verb, font=font, fill=CORAL)
        canvas.paste(term, (0, CAP_H))
        if px_w is None:
            # yuv420p needs even dimensions
            px_w = canvas.width + (canvas.width & 1)
            px_h = canvas.height + (canvas.height & 1)
        if (canvas.width, canvas.height) != (px_w, px_h):
            padded = Image.new("RGB", (px_w, px_h), BG)
            padded.paste(canvas, (0, 0))
            canvas = padded
        raw += canvas.tobytes()
    if body.exists():
        body.unlink()

    size = f"{px_w}x{px_h}"
    base_in = [FFMPEG, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", size, "-r", str(FPS), "-i", "pipe:0"]
    mp4 = out_stem.with_suffix(".mp4")
    webm = out_stem.with_suffix(".webm")
    mp4.parent.mkdir(parents=True, exist_ok=True)
    mp4_cmd = base_in + ["-an", "-c:v", "libx264", "-preset", "veryslow",
                         "-crf", "21", "-pix_fmt", "yuv420p",
                         "-movflags", "+faststart", str(mp4)]
    webm_cmd = base_in + ["-an", "-c:v", "libvpx-vp9", "-b:v", "0",
                          "-crf", "32", "-pix_fmt", "yuv420p",
                          "-row-mt", "1", str(webm)]
    nframes = len(frames)
    for label, cmd, dst in (("mp4", mp4_cmd, mp4), ("webm", webm_cmd, webm)):
        proc = subprocess.run(cmd, input=bytes(raw),
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr.decode("utf-8", "replace")[-800:])
            raise SystemExit(f"ffmpeg {label} failed for {out_stem.name}")
        print(f"wrote {dst}  ({nframes} frames @ {FPS}fps, {size}px, "
              f"{dst.stat().st_size // 1024} KB)")
    return 0


# default per-reel temp source dirs + geometry (matches _demo_drive SCRIPTS)
TEMP = Path(os.environ.get("LOCALAPPDATA", "")) / "Temp" / "demoframes"
REELS = {
    "htop":    (TEMP / "htop", 100, 30),
    "ncdu":    (TEMP / "ncdu", 100, 30),
    "nano":    (TEMP / "nano", 100, 26),
    "lazygit": (TEMP / "lazygit", 100, 30),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src")
    ap.add_argument("--out", help="output path stem (no extension)")
    ap.add_argument("--cols", type=int, default=100)
    ap.add_argument("--rows", type=int, default=30)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    if args.all:
        for name, (src, c, r) in REELS.items():
            if not src.exists():
                print(f"  [skip] {name}: {src} not present")
                continue
            out = _ROOT / "docs" / "site" / "assets" / f"drive-{name}"
            build(str(src), out, c, r)
        return 0

    if not args.src or not args.out:
        ap.error("give --src and --out, or --all")
    return build(args.src, Path(args.out), args.cols, args.rows)


if __name__ == "__main__":
    raise SystemExit(main())
