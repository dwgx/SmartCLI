# R3 - Terminal Color & Typography Techniques

> **Archived first-pass research** — superseded by [`../knowledge/sources/`](../knowledge/sources/); folded into [`../knowledge/color-type/`](../knowledge/color-type/README.md). See [`README.md`](README.md). Kept for provenance.


Research date: 2026-07-07

Sources summary: ANSI/SGR conventions from ECMA-48/xterm-style control sequences and terminal truecolor references (https://invisible-island.net/xterm/ctlseqs/ctlseqs.html, https://github.com/termstandard/colors); xterm 256-color palette from xterm docs and community palette tables (https://invisible-island.net/xterm/ctlseqs/ctlseqs.html, https://jonasjacek.github.io/colors/); lolcat sine rainbow from public lolcat implementations (https://github.com/tehmaze/lolcat, https://github.com/busyloop/lolcat); FIGfont from the official FIGfont spec (http://www.jave.de/figlet/figfont.html) and pyfiglet docs/source (https://github.com/pwaller/pyfiglet); Unicode character inventories from Unicode charts (https://www.unicode.org/charts/PDF/U2500.pdf, https://www.unicode.org/charts/PDF/U2580.pdf, https://www.unicode.org/charts/PDF/U2800.pdf); terminal half-block rendering from Chafa-style terminal graphics docs/source (https://hpjansson.org/chafa/, https://github.com/hpjansson/chafa); palette anchors from Matplotlib/viridis-family public colormap data (https://matplotlib.org/stable/users/explain/colors/colormaps.html, https://github.com/BIDS/colormap).

## 1. Truecolor 24-Bit ANSI

ANSI terminal color is emitted with Control Sequence Introducer (CSI) Select Graphic Rendition (SGR) escape sequences. `ESC` is byte `0x1b`, commonly written as `\x1b` in Python. CSI is `ESC[`, so SGR is `\x1b[...m` (xterm control sequence reference: https://invisible-island.net/xterm/ctlseqs/ctlseqs.html).

24-bit foreground color:

```text
ESC[38;2;R;G;Bm
\x1b[38;2;R;G;Bm
```

24-bit background color:

```text
ESC[48;2;R;G;Bm
\x1b[48;2;R;G;Bm
```

`R`, `G`, `B` are decimal integers in `[0, 255]`. A foreground/background cell can combine both:

```python
def sgr_truecolor(fg=None, bg=None):
    parts = []
    if fg is not None:
        r, g, b = fg
        parts.extend(["38", "2", str(r), str(g), str(b)])
    if bg is not None:
        r, g, b = bg
        parts.extend(["48", "2", str(r), str(g), str(b)])
    return "\x1b[" + ";".join(parts) + "m" if parts else ""
```

Common reset forms:

```text
ESC[0m      reset all SGR attributes
ESC[39m     reset foreground to default
ESC[49m     reset background to default
ESC[22m     reset bold/faint
ESC[23m     reset italic
ESC[24m     reset underline
```

Use `\x1b[0m` at the end of a rendered frame/string unless the caller owns terminal state. Prefer narrower resets (`39`, `49`) inside streaming renderers when preserving bold/italic/underline matters.

Truecolor detection is not standardized, but the de facto convention is `COLORTERM=truecolor` or `COLORTERM=24bit` (terminal truecolor discussion: https://github.com/termstandard/colors). Also consider `$TERM` values ending in `-direct` as direct-color capable in terminfo-aware environments. Minimal stdlib heuristic:

```python
import os

def supports_truecolor(env=os.environ):
    colorterm = env.get("COLORTERM", "").lower()
    term = env.get("TERM", "").lower()
    return colorterm in {"truecolor", "24bit"} or term.endswith("-direct")
```

Performance rule for ASCII/ANSI art renderers: only emit an escape when the current cell's style differs from the previous adjacent cell. Escape sequences are much longer than printable cells; repeated `\x1b[38;2;...m` per character can dominate output size and terminal parse time.

```python
RESET = "\x1b[0m"

def render_cells(cells):
    # cells: iterable of (text, fg_rgb_or_none, bg_rgb_or_none)
    out = []
    cur_fg = cur_bg = object()
    for ch, fg, bg in cells:
        if fg != cur_fg or bg != cur_bg:
            out.append(sgr_truecolor(fg, bg))
            cur_fg, cur_bg = fg, bg
        out.append(ch)
    out.append(RESET)
    return "".join(out)
```

## 2. 256-Color Degradation

xterm-compatible 256-color mode uses SGR `38;5;N` for foreground and `48;5;N` for background, where `N` is `[0, 255]` (xterm control sequence reference: https://invisible-island.net/xterm/ctlseqs/ctlseqs.html).

```text
ESC[38;5;Nm   256-color foreground
ESC[48;5;Nm   256-color background
```

Palette layout:

```text
0..15       system colors, terminal/theme dependent
16..231     6x6x6 RGB color cube
232..255    24-step grayscale ramp
```

The standard xterm cube channel levels are:

```python
XTERM_LEVELS = (0, 95, 135, 175, 215, 255)
```

Cube index formula:

```text
N = 16 + 36*r + 6*g + b
```

where `r`, `g`, `b` are cube component indexes in `[0, 5]`, not raw byte values (xterm 256 palette table: https://jonasjacek.github.io/colors/).

Grayscale index and value:

```text
N = 232..255
gray = 8 + 10 * (N - 232)
```

The grayscale ramp therefore covers approximate gray values `8, 18, ..., 238`. It intentionally excludes exact black and white, which are covered by system/cube entries.

Inverse mapping from arbitrary RGB to cube index:

```python
def nearest_xterm_level_index(c):
    levels = (0, 95, 135, 175, 215, 255)
    return min(range(6), key=lambda i: abs(c - levels[i]))
```

Fast approximation commonly used for the nonzero levels:

```python
def approx_xterm_level_index(c):
    if c < 48:
        return 0
    if c < 115:
        return 1
    return max(0, min(5, int((c - 35) / 40)))
```

This approximation encodes midpoints between the xterm levels: `0/95` midpoint `47.5`, `95/135` midpoint `115`, then 40-unit spacing.

Decision rule for gray ramp vs cube:

- If `r == g == b`, evaluate both grayscale and cube candidates and choose the lower squared RGB error.
- For low-saturation colors, evaluate both and choose lower squared RGB error. A cheap saturation proxy is `max(r,g,b) - min(r,g,b) <= threshold`, with `threshold` around `8..24`.
- For general colors, cube usually wins, but evaluating both is still cheap and exact.

Complete reference algorithm:

```python
XTERM_LEVELS = (0, 95, 135, 175, 215, 255)

def clamp8(x):
    return max(0, min(255, int(round(x))))

def sqdist(a, b):
    return sum((x - y) * (x - y) for x, y in zip(a, b))

def cube_candidate(r, g, b):
    ri = min(range(6), key=lambda i: abs(r - XTERM_LEVELS[i]))
    gi = min(range(6), key=lambda i: abs(g - XTERM_LEVELS[i]))
    bi = min(range(6), key=lambda i: abs(b - XTERM_LEVELS[i]))
    n = 16 + 36 * ri + 6 * gi + bi
    rgb = (XTERM_LEVELS[ri], XTERM_LEVELS[gi], XTERM_LEVELS[bi])
    return n, rgb

def gray_candidate(r, g, b):
    gray = round((r + g + b) / 3)
    # Ramp values are 8 + 10*k for k in 0..23.
    k = max(0, min(23, int(round((gray - 8) / 10))))
    n = 232 + k
    v = 8 + 10 * k
    return n, (v, v, v)

def rgb_to_256(r, g, b):
    r, g, b = clamp8(r), clamp8(g), clamp8(b)

    cube_n, cube_rgb = cube_candidate(r, g, b)
    gray_n, gray_rgb = gray_candidate(r, g, b)

    # Exact error comparison gives the correct choice for gray and low-saturation
    # colors and costs only a few integer operations.
    if sqdist((r, g, b), gray_rgb) < sqdist((r, g, b), cube_rgb):
        return gray_n
    return cube_n

def sgr_256(fg=None, bg=None):
    parts = []
    if fg is not None:
        parts.extend(["38", "5", str(fg)])
    if bg is not None:
        parts.extend(["48", "5", str(bg)])
    return "\x1b[" + ";".join(parts) + "m" if parts else ""
```

Do not rely on entries `0..15` for exact RGB unless you are targeting a fixed palette. Terminals commonly theme or remap system colors.

## 3. Multi-Stop Gradient Interpolation

Linear RGB interpolation between two byte colors:

```text
lerp(a, b, t) = a + (b - a) * t
```

For RGB:

```python
def lerp(a, b, t):
    return a + (b - a) * t

def lerp_rgb(c0, c1, t):
    t = max(0.0, min(1.0, float(t)))
    return tuple(int(round(lerp(a, b, t))) for a, b in zip(c0, c1))
```

N-stop gradient with even stop spacing:

```text
scaled = t * (n - 1)
i = floor(scaled)
local = scaled - i
color = lerp(stops[i], stops[i+1], local)
```

Edge case: if `t >= 1`, return the final stop. If `n == 1`, always return the only stop.

```python
import math

def gradient(stops, t):
    if not stops:
        raise ValueError("at least one color stop is required")
    if len(stops) == 1:
        return stops[0]
    t = max(0.0, min(1.0, float(t)))
    if t >= 1.0:
        return stops[-1]
    scaled = t * (len(stops) - 1)
    i = int(math.floor(scaled))
    local = scaled - i
    return lerp_rgb(stops[i], stops[i + 1], local)
```

Gamma-correct interpolation note: straight RGB lerp blends in gamma-encoded sRGB and often looks too dark. For more perceptual blends, convert sRGB byte channels to linear light, interpolate, then convert back. sRGB transfer function reference: IEC 61966-2-1 / W3C color specs (https://www.w3.org/TR/css-color-4/#color-conversion-code).

```python
def srgb_to_linear_byte(c):
    x = c / 255.0
    if x <= 0.04045:
        return x / 12.92
    return ((x + 0.055) / 1.055) ** 2.4

def linear_to_srgb_byte(x):
    x = max(0.0, min(1.0, x))
    if x <= 0.0031308:
        y = 12.92 * x
    else:
        y = 1.055 * (x ** (1 / 2.4)) - 0.055
    return int(round(y * 255))

def lerp_rgb_gamma_correct(c0, c1, t):
    t = max(0.0, min(1.0, float(t)))
    out = []
    for a, b in zip(c0, c1):
        la = srgb_to_linear_byte(a)
        lb = srgb_to_linear_byte(b)
        out.append(linear_to_srgb_byte(la + (lb - la) * t))
    return tuple(out)
```

Text block mapping formulas, for zero-based column `x`, row `y`, width `w`, height `h`:

```text
horizontal: t = x / max(1, w - 1)
vertical:   t = y / max(1, h - 1)
diagonal:   t = (x + y) / max(1, (w - 1) + (h - 1))
anti-diag:  t = ((w - 1 - x) + y) / max(1, (w - 1) + (h - 1))
radial:     t = sqrt((x - cx)^2 + (y - cy)^2) / max_radius
```

Radial center and max radius:

```python
def radial_t(x, y, w, h, cx=None, cy=None):
    if cx is None:
        cx = (w - 1) / 2
    if cy is None:
        cy = (h - 1) / 2
    d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
    corners = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    max_d = max(((px - cx) ** 2 + (py - cy) ** 2) ** 0.5 for px, py in corners)
    return 0.0 if max_d == 0 else d / max_d
```

For terminal cells, radial/diagonal geometry may need aspect compensation because many monospace cells are taller than they are wide:

```text
dx = (x - cx) * cell_width_scale
dy = (y - cy) * cell_height_scale
```

Use `cell_height_scale ~= 2.0` if treating a terminal cell as approximately twice as tall as it is wide.

## 4. HSV Cycling and Lolcat Rainbow

The classic lolcat rainbow effect is a sine-wave RGB palette with channels phase-shifted by 120 degrees. Public implementations expose frequency/spread controls; the common sine form is:

```text
r = sin(freq * i + 0)        * 127 + 128
g = sin(freq * i + 2*pi/3)   * 127 + 128
b = sin(freq * i + 4*pi/3)   * 127 + 128
```

The Ruby lolcat CLI has historically used defaults such as `--freq 0.1` and `--spread 3.0` for rainbow progression (source: https://github.com/busyloop/lolcat). Python ports use the same three-sine phase structure (source: https://github.com/tehmaze/lolcat).

`i` is the position along the rainbow. A practical text formula:

```text
i = x / spread + line_offset
line_offset += line_increment per printed line
```

Reference implementation:

```python
import math

def lolcat_rgb(x, y=0, freq=0.1, spread=3.0, line_increment=1.0):
    i = (x / spread) + (y * line_increment)
    r = math.sin(freq * i + 0.0) * 127 + 128
    g = math.sin(freq * i + 2 * math.pi / 3) * 127 + 128
    b = math.sin(freq * i + 4 * math.pi / 3) * 127 + 128
    return (int(round(r)), int(round(g)), int(round(b)))
```

HSV cycling in Python stdlib uses `colorsys.hsv_to_rgb(h, s, v)`, where all components are floats in `[0.0, 1.0]` (Python docs: https://docs.python.org/3/library/colorsys.html).

```python
import colorsys

def hsv_to_rgb8(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))
```

Hue-rotation animation:

```text
h = (base_hue + time_seconds * speed_hz) mod 1
```

Per-cell animated hue:

```python
def animated_hue_rgb(x, y, t, speed=0.2, spatial_x=0.015, spatial_y=0.035):
    h = (x * spatial_x + y * spatial_y + t * speed) % 1.0
    return hsv_to_rgb8(h, 1.0, 1.0)
```

Use HSV when hue continuity is more important than palette-specific luminance. Use curated palettes or gamma-correct RGB gradients when maintaining readable brightness matters.

## 5. Curated Palettes With Exact RGB Anchor Stops

Viridis is a perceptually uniform Matplotlib colormap family designed to remain readable under grayscale conversion and common color-vision deficiencies (Matplotlib colormap docs: https://matplotlib.org/stable/users/explain/colors/colormaps.html; original viridis data: https://github.com/BIDS/colormap).

Viridis anchor stops, dark base to bright accent:

```python
VIRIDIS = [
    (68, 1, 84),      # #440154
    (65, 68, 135),    # #414487
    (42, 120, 142),   # #2A788E
    (34, 168, 132),   # #22A884
    (122, 209, 81),   # #7AD151
    (253, 231, 37),   # #FDE725
]
```

Usage: strong default for scientific, heatmap, terminal charts, and text gradients where monotonic luminance helps legibility. Order from deep purple base through blue/green to yellow highlight.

Magma anchor stops:

```python
MAGMA = [
    (0, 0, 4),        # #000004
    (59, 15, 112),    # #3B0F70
    (140, 41, 129),   # #8C2981
    (222, 73, 104),   # #DE4968
    (254, 159, 109),  # #FE9F6D
    (252, 253, 191),  # #FCFDBF
]
```

Usage: dark UI terminal backgrounds, heat/fire intensity maps, and high-contrast art. Order from near-black to warm white.

Inferno anchor stops:

```python
INFERNO = [
    (0, 0, 4),        # #000004
    (66, 10, 104),    # #420A68
    (147, 38, 103),   # #932667
    (221, 81, 58),    # #DD513A
    (252, 165, 10),   # #FCA50A
    (246, 215, 70),   # #F6D746
    (252, 255, 164),  # #FCFFA4
]
```

Usage: like magma but with stronger orange/yellow high end; effective for sparks, warning levels, and terminal plots.

Synthwave/outrun community-style anchors:

```python
SYNTHWAVE = [
    (22, 0, 51),      # #160033 deep purple
    (48, 25, 103),    # #301967 violet
    (125, 45, 217),   # #7D2DD9 electric purple
    (255, 42, 109),   # #FF2A6D neon magenta
    (5, 217, 232),    # #05D9E8 cyan
    (255, 246, 0),    # #FFF600 yellow accent
]
```

Usage: dark base to neon accents for banners, logo text, grids, and animated rainbows. Keep bright cyan/yellow sparse for readability.

Fire / demoscene-style palette:

```python
FIRE = [
    (0, 0, 0),        # black
    (96, 0, 0),       # dark red
    (192, 0, 0),      # red
    (255, 96, 0),     # orange
    (255, 192, 0),    # yellow-orange
    (255, 255, 128),  # pale yellow
    (255, 255, 255),  # white hot
]
```

Usage: scalar intensity maps, flame simulations, warning text, and radial bursts. Order encodes heat from unlit black to white hot.

Pastel high-lightness anchors:

```python
PASTEL = [
    (255, 179, 186),  # soft rose
    (255, 223, 186),  # peach
    (255, 255, 186),  # pale yellow
    (186, 255, 201),  # mint
    (186, 225, 255),  # sky
    (218, 198, 255),  # lavender
]
```

Usage: light backgrounds, subtle terminal dashboards, or low-fatigue decorative gradients. On dark terminals, pastels are readable but low-drama; on light terminals, avoid using them as foreground unless contrast is checked.

## 6. Half-Block Image Rendering

The common terminal image trick used by tools in the Chafa/catimg/timg family is to represent two vertical image pixels in one terminal cell using the Unicode upper half block `▀` (`U+2580`). Foreground color is the top pixel; background color is the bottom pixel. Chafa documents terminal-symbol graphics and color-pair cell rendering concepts (https://hpjansson.org/chafa/).

Per-cell assembly:

```text
ESC[38;2;top_r;top_g;top_bm ESC[48;2;bot_r;bot_g;bot_bm ▀
```

Python:

```python
UPPER_HALF_BLOCK = "\u2580"

def half_block_cell(top_rgb, bottom_rgb):
    tr, tg, tb = top_rgb
    br, bg, bb = bottom_rgb
    return (
        f"\x1b[38;2;{tr};{tg};{tb}m"
        f"\x1b[48;2;{br};{bg};{bb}m"
        f"{UPPER_HALF_BLOCK}"
    )
```

Output image size:

```text
target_pixel_width  = terminal_columns
target_pixel_height = terminal_rows * 2
```

because one cell covers one pixel horizontally and two pixels vertically. For target terminal output of `cols x rows`, resize source image to `cols x (rows * 2)` sampled pixels, then render image rows in pairs: `(0,1)`, `(2,3)`, ...

Aspect correction: terminal cells are not square. A typical monospace cell is approximately 2 times taller than it is wide. Half-block rendering already doubles vertical pixel density, partially compensating. Generic fit math:

```python
def fit_image_to_halfblock(src_w, src_h, max_cols, max_rows, cell_aspect=2.0):
    # cell_aspect = cell_height / cell_width, commonly about 2.0.
    # Half-block gives 2 vertical samples per row, so effective sample aspect:
    # sample_height / sample_width = cell_aspect / 2.
    sample_aspect = cell_aspect / 2.0
    max_px_w = max_cols
    max_px_h = max_rows * 2

    # Preserve displayed aspect:
    # displayed_width  = px_w
    # displayed_height = px_h * sample_aspect
    scale = min(max_px_w / src_w, (max_px_h * sample_aspect) / src_h)
    px_w = max(1, int(src_w * scale))
    px_h = max(2, int(src_h * scale / sample_aspect))
    if px_h % 2:
        px_h += 1
    return min(px_w, max_px_w), min(px_h, max_px_h)
```

If using Pillow is forbidden, pure stdlib image input is limited. Options:

- Use a simple text/source format such as PPM `P3`/`P6`, which is trivial to parse with `open(..., "rb")`.
- Accept pre-decoded RGB arrays from caller code.
- Use ANSI art generation from procedural data instead of arbitrary image files.

Other subdivision characters:

- Lower half block `▄` (`U+2584`): foreground = bottom pixel, background = top pixel.
- Full block `█` (`U+2588`): one color per cell.
- Quadrants `U+2596..U+259F`: 2x2 subcell patterns, useful for binary masks or limited-color dither (Unicode block chart: https://www.unicode.org/charts/PDF/U2580.pdf).
- Braille `U+2800..U+28FF`: 2x4 dot matrix per character using a bitmask, high spatial resolution for monochrome/limited-color plots (Unicode braille chart: https://www.unicode.org/charts/PDF/U2800.pdf).

Braille bit layout for dots:

```text
dot positions:   bits:
1 4              0 3
2 5              1 4
3 6              2 5
7 8              6 7
codepoint = 0x2800 + bitmask
```

## 7. FIGlet Font Principles

FIGlet/FIGfont `.flf` files are text fonts for large ASCII art. The header begins with `flf2a` followed immediately by the hardblank character. Official FIGfont spec: http://www.jave.de/figlet/figfont.html.

Header fields:

```text
flf2a$ 6 5 20 15 3 0 143 229
^^^^^ ^ ^ ^  ^^ ^^ ^ ^ ^   ^
sig   | | |  |  |  | | |   codetag_count
      | | |  |  |  | | full_layout
      | | |  |  |  | print_direction
      | | |  |  |  comment_lines
      | | |  |  old_layout
      | | |  max_length
      | | baseline
      | height
      hardblank
```

Core required fields:

```text
signature + hardblank: "flf2a" plus one hardblank char
height:                 number of lines per glyph
baseline:               line index baseline, historically used by FIGlet
max_length:             maximum glyph line length
old_layout:             legacy layout/smushing integer
comment_lines:          number of comment lines after header
```

Later FIGfont versions may include `print_direction`, `full_layout`, and `codetag_count`.

Glyph storage:

- After header and comment lines, glyphs are stored in ASCII order, commonly beginning at code 32 (space).
- Each glyph has exactly `height` lines.
- Each glyph line ends with one or more endmark characters, normally `@`.
- The endmark is stripped when loading. The final glyph line often has two endmarks.
- The hardblank character visually behaves like a space inside a glyph but is protected during smushing, then output as a normal space or preserved according to renderer behavior.

Minimal glyph parser sketch:

```python
def strip_figlet_endmark(line):
    line = line.rstrip("\n")
    if not line:
        return line
    endmark = line[-1]
    while line.endswith(endmark):
        line = line[:-1]
    return line
```

Kerning vs smushing:

- Full width: concatenate glyphs with no overlap.
- Kerning: remove only empty columns between adjacent glyphs.
- Smushing: overlap glyphs and combine touching characters according to rules.

The six classic horizontal smushing rules from FIGfont:

1. Equal character smushing: two identical characters smush into one.
2. Underscore smushing: `_` smushes with `|`, `/`, `\`, `[`, `]`, `{`, `}`, `(`, `)`, `<`, `>`, becoming the non-underscore character.
3. Hierarchy smushing: `|`, `/\`, `[]`, `{}`, `()`, `<>` groups smush according to hierarchy, with later/higher group winning.
4. Opposite pair smushing: bracket pairs `[]`, `{}`, `()`, `<>` facing each other smush into `|`.
5. Big X smushing: `/\` becomes `|`, `\/` becomes `Y`, and `><` becomes `X`.
6. Hardblank smushing: two hardblanks smush into one hardblank.

Stdlib fallback renderers usually implement full width or simple kerning only; full FIGlet-compatible smushing is subtle. If third-party packages are allowed, `pyfiglet` exposes:

```python
from pyfiglet import Figlet

text = Figlet(font="slant").renderText("Hello")
```

Source/docs: https://github.com/pwaller/pyfiglet.

Minimal hand-rolled 5-row block font:

```python
FONT5 = {
    "A": [
        " ### ",
        "#   #",
        "#####",
        "#   #",
        "#   #",
    ],
    "B": [
        "#### ",
        "#   #",
        "#### ",
        "#   #",
        "#### ",
    ],
    " ": [
        "   ",
        "   ",
        "   ",
        "   ",
        "   ",
    ],
}

def render_font5(text, spacing=1):
    rows = [""] * 5
    gap = " " * spacing
    for ch in text.upper():
        glyph = FONT5.get(ch, FONT5[" "])
        for i in range(5):
            rows[i] += glyph[i] + gap
    return "\n".join(row.rstrip() for row in rows)
```

To make this useful, add `A-Z`, `0-9`, and punctuation as `dict[str, list[str]]`. Keep every glyph exactly 5 rows; allow variable width per glyph, but compute layout row-wise.

## 8. Unicode Box Drawing and Tables

Unicode box drawing lives primarily in `U+2500..U+257F`; block elements are `U+2580..U+259F` (Unicode charts: https://www.unicode.org/charts/PDF/U2500.pdf, https://www.unicode.org/charts/PDF/U2580.pdf).

Common box drawing inventory:

```text
Light:   ─ │ ┌ ┐ └ ┘ ├ ┤ ┬ ┴ ┼
Heavy:   ━ ┃ ┏ ┓ ┗ ┛ ┣ ┫ ┳ ┻ ╋
Double:  ═ ║ ╔ ╗ ╚ ╝ ╠ ╣ ╦ ╩ ╬
Rounded: ╭ ╮ ╰ ╯
Mixed:   ╒ ╕ ╘ ╛ ╞ ╡ ╤ ╧ ╪ ╓ ╖ ╙ ╜ ╟ ╢ ╥ ╨ ╫
```

Rounded corners:

```text
U+256D ╭ BOX DRAWINGS LIGHT ARC DOWN AND RIGHT
U+256E ╮ BOX DRAWINGS LIGHT ARC DOWN AND LEFT
U+256F ╯ BOX DRAWINGS LIGHT ARC UP AND LEFT
U+2570 ╰ BOX DRAWINGS LIGHT ARC UP AND RIGHT
```

Block elements inventory highlights:

```text
U+2580 ▀ upper half block
U+2581 ▁ lower one eighth block
U+2582 ▂ lower one quarter block
U+2583 ▃ lower three eighths block
U+2584 ▄ lower half block
U+2585 ▅ lower five eighths block
U+2586 ▆ lower three quarters block
U+2587 ▇ lower seven eighths block
U+2588 █ full block
U+2589 ▉ left seven eighths block
U+258A ▊ left three quarters block
U+258B ▋ left five eighths block
U+258C ▌ left half block
U+258D ▍ left three eighths block
U+258E ▎ left one quarter block
U+258F ▏ left one eighth block
U+2590 ▐ right half block
U+2591 ░ light shade
U+2592 ▒ medium shade
U+2593 ▓ dark shade
U+2594 ▔ upper one eighth block
U+2595 ▕ right one eighth block
U+2596 ▖ quadrant lower left
U+2597 ▗ quadrant lower right
U+2598 ▘ quadrant upper left
U+2599 ▙ quadrants upper left, lower left, lower right
U+259A ▚ quadrants upper left and lower right
U+259B ▛ quadrants upper left, upper right, lower left
U+259C ▜ quadrants upper left, upper right, lower right
U+259D ▝ quadrant upper right
U+259E ▞ quadrants upper right and lower left
U+259F ▟ quadrants upper right, lower left, lower right
```

Ready-to-use border presets:

```python
BORDERS = {
    "light": {
        "h": "─", "v": "│",
        "tl": "┌", "tr": "┐", "bl": "└", "br": "┘",
        "lt": "├", "rt": "┤", "tt": "┬", "bt": "┴", "x": "┼",
    },
    "heavy": {
        "h": "━", "v": "┃",
        "tl": "┏", "tr": "┓", "bl": "┗", "br": "┛",
        "lt": "┣", "rt": "┫", "tt": "┳", "bt": "┻", "x": "╋",
    },
    "double": {
        "h": "═", "v": "║",
        "tl": "╔", "tr": "╗", "bl": "╚", "br": "╝",
        "lt": "╠", "rt": "╣", "tt": "╦", "bt": "╩", "x": "╬",
    },
    "rounded": {
        "h": "─", "v": "│",
        "tl": "╭", "tr": "╮", "bl": "╰", "br": "╯",
        "lt": "├", "rt": "┤", "tt": "┬", "bt": "┴", "x": "┼",
    },
    "ascii": {
        "h": "-", "v": "|",
        "tl": "+", "tr": "+", "bl": "+", "br": "+",
        "lt": "+", "rt": "+", "tt": "+", "bt": "+", "x": "+",
    },
}
```

Table layout rules:

1. Convert every cell to `str`.
2. Split multiline cells on `\n`; compute display width per visual line.
3. Column width is `max(display_width(cell_line))` over header/body cells in that column.
4. Add left/right padding, usually one space each.
5. Top border uses `tl + h*width + tt + ... + tr`.
6. Header separator uses `lt/rt/x` joints.
7. Body rows use `v + padded cell + v`.
8. Bottom border uses `bl + h*width + bt + ... + br`.

Basic ASCII-width implementation, suitable when inputs are plain ASCII:

```python
def make_border(widths, style, left, mid, right):
    parts = [left]
    for i, w in enumerate(widths):
        parts.append(style["h"] * (w + 2))
        parts.append(right if i == len(widths) - 1 else mid)
    return "".join(parts)

def render_table(rows, headers=None, border="light"):
    style = BORDERS[border]
    data = []
    if headers is not None:
        data.append([str(x) for x in headers])
    data.extend([[str(x) for x in row] for row in rows])
    cols = max((len(row) for row in data), default=0)
    normalized = [row + [""] * (cols - len(row)) for row in data]
    widths = [max(len(row[c]) for row in normalized) for c in range(cols)]

    def row_line(row):
        cells = []
        for c, text in enumerate(row):
            cells.append(" " + text.ljust(widths[c]) + " ")
        return style["v"] + style["v"].join(cells) + style["v"]

    out = [make_border(widths, style, style["tl"], style["tt"], style["tr"])]
    if headers is not None:
        out.append(row_line(normalized[0]))
        out.append(make_border(widths, style, style["lt"], style["x"], style["rt"]))
        body = normalized[1:]
    else:
        body = normalized
    out.extend(row_line(row) for row in body)
    out.append(make_border(widths, style, style["bl"], style["bt"], style["br"]))
    return "\n".join(out)
```

Unicode width caveat: Python stdlib has no complete `wcwidth`. For pure stdlib, `len()` is acceptable only for ASCII or controlled box-art strings. For East Asian wide characters, emoji, combining marks, and ANSI-escaped text, implement a conservative width function with `unicodedata.east_asian_width`, strip ANSI escapes before measuring, and treat combining marks as width 0.

```python
import re
import unicodedata

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

def display_width(s):
    s = ANSI_RE.sub("", s)
    width = 0
    for ch in s:
        if unicodedata.combining(ch):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in {"F", "W"} else 1
    return width
```
