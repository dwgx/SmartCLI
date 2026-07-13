#!/usr/bin/env python
"""make_demo_svg.py — generate the SmartCLI hero demo as a self-contained,
animated SVG. Pure Python (stdlib only), ZERO process spawning: it does not
drive any real program — it replays a scripted sequence of screen frames
captured from real drive-tui runs in this project, then emits an SVG that
animates through them like a terminal recording.

Why SVG (not GIF): it renders crisply at any size, is tiny, and — crucially —
GitHub's Markdown renderer displays animated SVG inline, so the repo front page
can move without any JS. The same file also drops into the showcase site.

Design: a synthwave-tinted terminal window (the project's own default theme
palette rgb(20,0,40)->(200,30,160)->(60,220,240)), a title-bar with traffic
lights, a typed command line, and a body that swaps between frames on a loop.
Animation is pure SMIL/CSS <style> keyframes embedded in the SVG — no scripts,
so it animates even where JS is blocked (GitHub).

Usage:
    python tools/make_demo_svg.py            # -> docs/site/assets/demo.svg
    python tools/make_demo_svg.py --out X    # custom output path
"""
from __future__ import annotations

import argparse
import html
from pathlib import Path

# --- Anthropic warm-editorial palette (matches docs/site) --------------------
# A dark terminal window that sits on a cream page: warm near-black surface,
# coral / teal / amber accents, cream-tinted foreground. Not synthwave.
BG0 = "#181715"      # window background (warm near-black)
BG1 = "#1f1e1b"      # body panel
TITLEBAR = "#252320"
NEON_MAGENTA = "#cc785c"   # coral (primary accent) — name kept for call sites
NEON_PINK = "#e06c60"      # soft red (traffic light)
NEON_CYAN = "#5db8a6"      # teal (secondary accent)
NEON_VIOLET = "#cc785c"    # coral (box borders) — unified with primary
DIM = "#8e8b82"       # warm muted gray for inactive text
FG = "#faf9f5"        # cream foreground
GREEN = "#5db872"     # success ticks
AMBER = "#e8a55a"

# --- geometry ----------------------------------------------------------------
CW = 8.4              # monospace cell width (px)
CH = 19               # cell height (px)
PAD_X = 22
PAD_TOP = 48          # room for the title bar + caption
COLS = 74
ROWS = 12             # sized to the tallest scene so the window is not sparse
WIDTH = int(PAD_X * 2 + COLS * CW)
HEIGHT = int(PAD_TOP + PAD_X + ROWS * CH)

# --- the story, as real frames -----------------------------------------------
# Each "scene" is (caption, [lines]). Lines are (text, color, bold?). This is the
# real drive-tui grok sequence from this project: perceive the fullscreen TUI,
# navigate with arrow keys to switch effort high->low, confirm. Colors mirror
# what a synthwave terminal shows; content is verbatim from captured snapshots.

C = NEON_CYAN
M = NEON_MAGENTA
P = NEON_PINK
V = NEON_VIOLET


def L(text, color=FG, bold=False):
    return (text, color, bold)


# --- box-art helpers: guarantee every row is the same width (no stray bars) --
_BOX_INDENT = "  "


def _box_top(w: int) -> str:
    return _BOX_INDENT + "╭" + "─" * w + "╮"


def _box_bot(w: int) -> str:
    return _BOX_INDENT + "╰" + "─" * w + "╯"


def _box_row(left: str, w: int, right: str = "") -> str:
    """A │ ... │ row of interior width w, left text and optional right-aligned
    text, padded so the closing bar always lands at the same column."""
    inner = left + " " * max(0, w - len(left) - len(right)) + right
    inner = inner[:w]
    return _BOX_INDENT + "│" + inner + "│"


SCENES = [
    # 0 — the human's intent, typed at a prompt
    ("A human tells the AI what to do", [
        L("$ ai> drive grok, say hi, switch to the lowest tier", C, True),
        L(""),
        L("  the AI is about to open a fullscreen TUI it cannot", DIM),
        L("  see through a normal pipe — no menus, no arrows,", DIM),
        L("  no cursor. a plain subprocess just hangs or prints", DIM),
        L("  nothing.", DIM),
        L(""),
        L("  drive-tui gives the AI eyes and hands:", FG),
        L("  perceive → decide → act → wait → confirm.", M, True),
    ]),
    # 1 — perceive: the real snapshot of grok's fullscreen UI. Box lines are
    # built with _box() so every row is the SAME character width (no stray bars).
    ("perceive  →  a semantic snapshot of the live screen", [
        L("[screen 30x100] cursor=r25c6  title=\"grok\"  [stable]", DIM),
        L(_box_top(40), V),
        L(_box_row("  Grok Build Beta  0.2.99", 40), V),
        L(_box_row("  Grok 4.5 is here!", 40), FG),
        L(_box_row("  New worktree", 40, "ctrl+w"), FG),
        L(_box_row("  Resume session", 40, "ctrl+s"), FG),
        L(_box_bot(40), V),
        L("  ❯ _", C),
        L("  Grok 4.5 (high) · always-approve", M),
    ]),
    # 2 — act: type + send, get a real reply
    ("act  →  type 你好 and read the reply", [
        L("  ❯ 你好                                  9:36 AM", C, True),
        L(""),
        L("  ◆ Thought for 0.1s", DIM),
        L("  你好！我是 Grok，可以帮你处理 SmartCLI 项目里的", FG),
        L("  开发任务，比如写代码、查 bug、跑测试。", FG),
        L("  今天想做什么？", FG),
        L("  Worked for 2.0s.", DIM),
        L(""),
        L("  Grok 4.5 (high) · always-approve", M),
    ]),
    # 3 — navigate: arrow keys move the highlight (the CSI/SS3 win)
    ("act  →  arrow keys navigate the /model picker", [
        L("  /model  ──  choose model, then effort", DIM),
        L(""),
        L("    High Effort (active)   extensive reasoning", DIM),
        L("    Medium Effort          balanced", DIM),
        L("  ❯ Low Effort              quick, fast", C, True),
        L("", FG),
        L("  keys: Down Down → highlight moved to Low  ✓", GREEN),
        L(""),
        L("  Grok 4.5 (high) · always-approve", M),
    ]),
    # 4 — confirm: the status bar proves the switch
    ("confirm  →  the tier actually changed", [
        L("  ❯ 你好                                  9:38 AM", C, True),
        L("  ◆ Thought for 0.0s", DIM),
        L("  你好！有什么需要帮忙的吗？", FG),
        L("  Worked for 1.5s.", DIM),
        L(""),
        L("  Grok 4.5 (low) · always-approve            ✓", GREEN, True),
        L(""),
        L("  perceive → decide → act → wait → confirm", M, True),
        L("  driven like a human. never a blind sleep.", DIM),
    ]),
]

SCENE_SECONDS = 3.0  # dwell per scene


# --- SVG assembly ------------------------------------------------------------

def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def build_window_chrome() -> str:
    """Terminal window: rounded panel, neon border glow, title bar, lights."""
    return f"""
  <defs>
    <linearGradient id="border" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{AMBER}"/>
      <stop offset="50%" stop-color="{NEON_MAGENTA}"/>
      <stop offset="100%" stop-color="{NEON_MAGENTA}"/>
    </linearGradient>
    <linearGradient id="scan" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.04"/>
      <stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="2.2" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" rx="12" fill="{BG0}"/>
  <rect x="1.5" y="1.5" width="{WIDTH-3}" height="{HEIGHT-3}" rx="11"
        fill="none" stroke="url(#border)" stroke-width="2" opacity="0.9"/>
  <rect x="0" y="0" width="{WIDTH}" height="34" rx="12" fill="{TITLEBAR}"/>
  <rect x="0" y="22" width="{WIDTH}" height="12" fill="{TITLEBAR}"/>
  <circle cx="20" cy="17" r="5.5" fill="{NEON_PINK}"/>
  <circle cx="40" cy="17" r="5.5" fill="{AMBER}"/>
  <circle cx="60" cy="17" r="5.5" fill="{GREEN}"/>
  <text x="{WIDTH/2}" y="21" text-anchor="middle" font-family="monospace"
        font-size="12" fill="{DIM}">SmartCLI · drive-tui — grok</text>
"""


def build_scene(idx: int, n_scenes: int, caption: str, lines) -> str:
    """One scene as a <g> that fades in during its slot on a looping timeline."""
    total = n_scenes * SCENE_SECONDS
    begin = idx * SCENE_SECONDS
    # keyframe percentages for this scene's fade in/hold/out inside the loop
    p_in = begin / total * 100
    p_show = (begin + 0.35) / total * 100
    p_hold = (begin + SCENE_SECONDS - 0.35) / total * 100
    p_out = (begin + SCENE_SECONDS) / total * 100

    rows = []
    # caption line: bright cyan, a ▸ accent, and a thin underline rule. No blur
    # filter (it muddied small text); the fill is already vivid enough.
    cap_y = PAD_TOP + 8
    rows.append(
        f'<text x="{PAD_X}" y="{cap_y}" font-family="monospace" '
        f'font-size="14.5" font-weight="700" fill="{NEON_CYAN}">'
        f'▸ {_esc(caption)}</text>'
    )
    rows.append(
        f'<rect x="{PAD_X}" y="{cap_y+8}" width="{COLS*CW-10}" height="1.4" '
        f'fill="{NEON_MAGENTA}" opacity="0.45"/>'
    )
    y = cap_y + int(CH * 1.7)
    for (text, color, bold) in lines:
        weight = "700" if bold else "400"
        rows.append(
            f'<text x="{PAD_X}" y="{y}" font-family="monospace" '
            f'font-size="13.5" font-weight="{weight}" fill="{color}" '
            f'xml:space="preserve">{_esc(text)}</text>'
        )
        y += CH
    body = "\n      ".join(rows)

    # SMIL opacity animation (works on GitHub + all browsers, and renders
    # deterministically — unlike CSS keyframes, which some static renderers
    # freeze at t=0). keyTimes map to: hidden -> fade in -> hold -> fade out.
    kt = f"0;{p_in/100:.4f};{p_show/100:.4f};{p_hold/100:.4f};{p_out/100:.4f};1"
    vals = "0;0;1;1;0;0"
    initial = "1" if idx == 0 else "0"  # scene 0 visible at t=0 (static fallback)
    anim = (
        f'<animate attributeName="opacity" values="{vals}" keyTimes="{kt}" '
        f'dur="{total:.1f}s" repeatCount="indefinite" calcMode="linear"/>'
    )
    return (
        f'  <g opacity="{initial}">\n      {anim}\n      {body}\n  </g>', ""
    )


def build_svg() -> str:
    n = len(SCENES)
    total = n * SCENE_SECONDS
    scene_svgs = [build_scene(i, n, cap, lines)[0]
                  for i, (cap, lines) in enumerate(SCENES)]
    # a soft scanline sweep across the window, looping (SMIL, GitHub-safe)
    sweep = (
        f'  <rect x="0" y="0" width="{WIDTH}" height="46" fill="url(#scan)" '
        f'opacity="0.6"><animate attributeName="y" values="34;{HEIGHT};34" '
        f'dur="{total:.1f}s" repeatCount="indefinite"/></rect>'
    )
    body = "\n".join(scene_svgs)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}"
     width="{WIDTH}" height="{HEIGHT}" role="img"
     aria-label="SmartCLI drive-tui demo: an AI perceiving and driving the grok TUI">
{build_window_chrome()}
{sweep}
{body}
</svg>
"""


def build_static_contact_sheet() -> str:
    """Debug view: every scene at full opacity, stacked vertically, so the real
    colors/typography of each scene can be reviewed in one screenshot."""
    n = len(SCENES)
    parts = []
    for i, (cap, lines) in enumerate(SCENES):
        oy = i * HEIGHT
        # reuse build_scene body but force opacity 1 and offset vertically
        g = build_scene(i, n, cap, lines)[0]
        # strip the <animate> and force opacity=1
        import re as _re
        g = _re.sub(r'<animate[^>]*/>', '', g)
        g = g.replace('opacity="0"', 'opacity="1"', 1)
        parts.append(f'<g transform="translate(0,{oy})">{build_window_chrome()}{g}</g>')
    body = "\n".join(parts)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {WIDTH} {HEIGHT*n}" width="{WIDTH}" height="{HEIGHT*n}">'
            f'\n{body}\n</svg>\n')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/site/assets/demo.svg")
    ap.add_argument("--static", action="store_true",
                    help="emit a stacked all-scenes contact sheet for review")
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    svg = build_static_contact_sheet() if args.static else build_svg()
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out} ({len(svg)} bytes, {len(SCENES)} scenes, "
          f"{WIDTH}x{HEIGHT}px, loop {len(SCENES)*SCENE_SECONDS:.0f}s"
          f"{', STATIC sheet' if args.static else ''})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



