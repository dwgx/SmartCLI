"""Image -> terminal art via half-blocks (chafa technique) or an ASCII ramp.

Half-block mode: one cell shows TWO vertical pixels -- ``\u2580`` (upper half
block) with foreground = top pixel, background = bottom pixel. Because a cell
is ~2x taller than wide, the two stacked pixels come out square.

Degradation ladder (no hard PIL dependency):
1. PIL/Pillow available          -> any image format, smooth resize.
2. No PIL, file is .ppm/.pgm     -> pure-stdlib P2/P3/P5/P6 parser.
3. No PIL, other format          -> honest error frame telling you the options.
4. No path at all                -> procedural theme-colored demo sphere, so the
                                    technique is demonstrable with zero deps.
"""
from __future__ import annotations

import math
from pathlib import Path

from ..core import RESET, rgb
from ..base import DEFAULT_RAMP, FrameCtx, Param, StaticEffect
from ..registry import register
from ..util import clamp

HALF = "\u2580"  # upper half block


# --------------------------------------------------------------------------
# Pixel sources
# --------------------------------------------------------------------------
def _load_pil(path: str):
    from PIL import Image  # ImportError handled by caller
    img = Image.open(path).convert("RGB")
    return img.size, img  # ((w, h), handle)


def _resize_pil(img, pw: int, ph: int):
    from PIL import Image
    resample = getattr(Image, "LANCZOS", getattr(Image, "BICUBIC", 3))
    small = img.resize((max(1, pw), max(1, ph)), resample)
    px = small.load()
    return [[px[x, y] for x in range(small.width)] for y in range(small.height)]


def _parse_pnm(path: str):
    """Minimal P2/P3 (ascii) + P5/P6 (binary) PNM reader -> 2D RGB list."""
    data = Path(path).read_bytes()

    tokens = []
    i, n = 0, len(data)
    while i < n and len(tokens) < 4:
        c = data[i:i + 1]
        if c == b"#":
            while i < n and data[i:i + 1] not in (b"\n", b"\r"):
                i += 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not data[j:j + 1].isspace():
                j += 1
            tokens.append(data[i:j])
            i = j
    magic = tokens[0].decode()
    if magic not in ("P2", "P3", "P5", "P6"):
        raise ValueError(f"unsupported PNM magic {magic!r}")
    w, h, maxv = int(tokens[1]), int(tokens[2]), int(tokens[3])
    gray = magic in ("P2", "P5")
    ch = 1 if gray else 3

    if magic in ("P5", "P6"):
        raw = data[i + 1:]  # single whitespace after maxval
        vals = list(raw[: w * h * ch])
    else:
        vals = [int(v) for v in data[i:].split()][: w * h * ch]
    if maxv != 255 and maxv > 0:
        vals = [v * 255 // maxv for v in vals]

    rows = []
    k = 0
    for _ in range(h):
        row = []
        for _ in range(w):
            if gray:
                g = vals[k]; k += 1
                row.append((g, g, g))
            else:
                row.append((vals[k], vals[k + 1], vals[k + 2])); k += 3
        rows.append(row)
    return rows


def _resize_nearest(pixels, pw: int, ph: int):
    ih, iw = len(pixels), len(pixels[0])
    return [[pixels[min(ih - 1, y * ih // ph)][min(iw - 1, x * iw // pw)]
             for x in range(pw)] for y in range(ph)]


def _demo_pixels(theme, size=96):
    """Procedural fallback: Lambert-shaded sphere over a soft gradient."""
    out = []
    for y in range(size):
        row = []
        ny = y / (size - 1) * 2 - 1
        for x in range(size):
            nx = x / (size - 1) * 2 - 1
            r = math.hypot(nx, ny)
            if r < 0.72:
                z = math.sqrt(max(0.0, 0.72 * 0.72 - nx * nx - ny * ny)) / 0.72
                lum = clamp(0.15 + 0.85 * (nx * -0.35 + ny * -0.5 + z * 0.79),
                            0.0, 1.0)
                row.append(theme.color_at(lum))
            else:
                row.append(theme.color_at(clamp(0.06 + 0.10 * (1 - ny), 0.0, 1.0)))
        out.append(row)
    return out


# --------------------------------------------------------------------------
# Renderers
# --------------------------------------------------------------------------
def render_half_blocks(pixels) -> str:
    """2D RGB rows -> half-block art (2 pixel rows per text line)."""
    lines = []
    for y in range(0, len(pixels) - 1, 2):
        top, bot = pixels[y], pixels[y + 1]
        buf, last = [], None
        for x in range(len(top)):
            key = (top[x], bot[x])
            if key != last:
                buf.append(rgb(*top[x]) + rgb(*bot[x], bg=True))
                last = key
            buf.append(HALF)
        lines.append("".join(buf) + RESET)
    return "\n".join(lines)


def render_ascii_ramp(pixels, colored=True) -> str:
    lines = []
    hi = len(DEFAULT_RAMP) - 1
    for row in pixels:
        buf, last = [], None
        for (r, g, b) in row:
            lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
            ch = DEFAULT_RAMP[int(lum * hi)]
            if colored:
                c = (r, g, b)
                if c != last:
                    buf.append(rgb(*c))
                    last = c
            buf.append(ch)
        buf.append(RESET)
        lines.append("".join(buf))
    return "\n".join(lines)


def _fit(iw: int, ih: int, w: int, h: int, mode: str) -> tuple[int, int]:
    """Target pixel grid: half mode packs 2 square px per row; ascii halves y."""
    if mode == "half":
        scale = min(w / iw, (2 * h) / ih)
        return max(1, int(iw * scale)), max(2, int(ih * scale))
    scale = min(w / iw, h / (ih * 0.5))
    return max(1, int(iw * scale)), max(1, int(ih * scale * 0.5))


@register
class Image2Ascii(StaticEffect):
    name = "image2ascii"
    aliases = ("img",)
    description = "Image -> half-block truecolor art (PIL optional, PNM/demo fallback)."
    tags = ("image", "static")
    params = (
        Param("path", "str", "", "image file (empty = built-in demo sphere)"),
        Param("mode", "str", "half", "half-block or ascii ramp", choices=("half", "ascii")),
    )

    def render(self, ctx: FrameCtx) -> str:
        p = ctx.params
        path, mode = p["path"], p["mode"]
        w, h = ctx.width, ctx.height

        pixels = None
        note = ""
        if path:
            if not Path(path).exists():
                return f"image2ascii: file not found: {path}"
            try:
                (iw, ih), img = _load_pil(path)
                pw, ph = _fit(iw, ih, w, h, mode)
                pixels = _resize_pil(img, pw, ph)
            except ImportError:
                if path.lower().endswith((".ppm", ".pgm", ".pnm")):
                    try:
                        src = _parse_pnm(path)
                    except Exception as exc:
                        return f"image2ascii: PNM parse failed: {exc}"
                    pw, ph = _fit(len(src[0]), len(src), w, h, mode)
                    pixels = _resize_nearest(src, pw, ph)
                    note = "(no PIL: stdlib PNM path)"
                else:
                    return ("image2ascii: PIL/Pillow is not installed and only "
                            ".ppm/.pgm can be read without it.\n"
                            "Options: pip install pillow | convert the image to "
                            "PPM | run without path for the built-in demo.")
            except Exception as exc:
                return f"image2ascii: failed to read {path}: {exc}"
        else:
            side = min(w, 2 * (h - 1))
            src = _demo_pixels(ctx.theme, size=max(16, side))
            if mode == "half":
                pw = ph = max(2, side)
            else:
                pw, ph = max(2, side), max(1, side // 2)
            pixels = _resize_nearest(src, pw, ph)
            note = "(demo sphere; pass --set path=... for a real image)"

        art = render_half_blocks(pixels) if mode == "half" \
            else render_ascii_ramp(pixels)
        if note:
            # The note is plain text (no SGR) so it is safe to clip to width;
            # only append it when a spare row is left, so it never pushes the
            # frame past ctx.height or spills past the right edge.
            note = note[:ctx.width]
            if art.count("\n") + 1 < ctx.height:
                art += "\n" + note
        return art
