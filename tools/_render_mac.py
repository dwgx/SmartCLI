#!/usr/bin/env python3
"""_render_mac.py — render captured .ansi frames to 30fps video ON the Mac.

Runs on macOS (over SSH): reads ~/smartcli-reel/frames/<target>/*.ansi, renders
each through shot.py's pyte->PNG pipeline using the system Menlo font, stacks a
caption bar, and pipes to the system ffmpeg to produce H.264 MP4 + VP9 WebM in
~/smartcli-reel/out/. Small outputs come back over SFTP. Uses the Mac's own
ffmpeg (no imageio_ffmpeg) and Menlo (no Windows fonts).
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys

HOME = os.path.expanduser("~")
ROOT = os.path.join(HOME, "smartcli-reel")
sys.path.insert(0, os.path.join(ROOT, "screenshot"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
import shot  # noqa: E402

MENLO = "/System/Library/Fonts/Menlo.ttc"
CELL_W, CELL_H = 7, 14
CAP_H = 30
FPS = 30
BG = (13, 12, 10)
CORAL = (204, 120, 92)
DIM = (168, 164, 152)

REELS = {  # target -> (cols, rows)
    "lazygit": (100, 30), "ncdu": (100, 30), "nano": (100, 26), "htop": (100, 30),
}


def build(target: str, cols: int, rows: int) -> int:
    src = os.path.join(ROOT, "frames", target)
    frames = sorted(glob.glob(os.path.join(src, "[0-9][0-9][0-9][0-9].ansi")))
    if not frames:
        print(f"[{target}] no frames"); return 1
    labels = []
    lp = os.path.join(src, "labels.txt")
    if os.path.exists(lp):
        labels = [l.rstrip("\n") for l in open(lp, encoding="utf-8")]
    try:
        font = ImageFont.truetype(MENLO, 13)
    except Exception:
        font = ImageFont.load_default()

    outdir = os.path.join(ROOT, "out")
    os.makedirs(outdir, exist_ok=True)
    body = os.path.join(outdir, f".{target}.body.png")
    px_w = px_h = None
    raw = bytearray()
    for i, fp in enumerate(frames):
        data = open(fp, "rb").read()
        screen = shot.render_bytes_to_screen(data, cols, rows)
        w, h = shot.screen_to_png(screen, body, cell_w=CELL_W, cell_h=CELL_H,
                                  default_fg=(232, 230, 246), default_bg=BG,
                                  draw_cursor=False, font_path=MENLO)
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
            px_w = canvas.width + (canvas.width & 1)
            px_h = canvas.height + (canvas.height & 1)
        if (canvas.width, canvas.height) != (px_w, px_h):
            pad = Image.new("RGB", (px_w, px_h), BG)
            pad.paste(canvas, (0, 0))
            canvas = pad
        raw += canvas.tobytes()
    if os.path.exists(body):
        os.remove(body)

    size = f"{px_w}x{px_h}"
    base = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", size, "-r", str(FPS), "-i", "pipe:0"]
    mp4 = os.path.join(outdir, f"drive-{target}-macos.mp4")
    webm = os.path.join(outdir, f"drive-{target}-macos.webm")
    for label, extra, dst in (
        ("mp4", ["-an", "-c:v", "libx264", "-preset", "veryslow", "-crf", "21",
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart", mp4], mp4),
        ("webm", ["-an", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "32",
                  "-pix_fmt", "yuv420p", "-row-mt", "1", webm], webm),
    ):
        p = subprocess.run(base + extra, input=bytes(raw),
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if p.returncode != 0:
            sys.stderr.write(p.stderr.decode("utf-8", "replace")[-500:])
            print(f"[{target}] ffmpeg {label} FAILED"); return 1
        kb = os.path.getsize(dst) // 1024
        print(f"[{target}] wrote {os.path.basename(dst)} ({len(frames)} frames, {size}, {kb} KB)")
    return 0


def main() -> int:
    tgt = sys.argv[1] if len(sys.argv) > 1 else "all"
    targets = REELS.keys() if tgt == "all" else [tgt]
    for t in targets:
        if t in REELS:
            build(t, *REELS[t])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
