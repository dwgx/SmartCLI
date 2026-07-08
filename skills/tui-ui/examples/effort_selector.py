"""effort_selector.py — a violet-ripple multi-stage effort selector.

A worked replica of a `/effort`-style picker, built to demonstrate that a rich
animated selector decomposes into the engine's four primitives rather than a
bespoke script. The layout constants, stage colors, and the violet-ripple
animation were measured from the real program and are the values used here.

The ultracode effect (``violet-ripple``) is an EXPANDING CONCENTRIC RIPPLE from
the selected marker column: a cosine wave over aspect-corrected distance, an
8-level violet palette, white text composited on top. It washes the WHOLE panel,
brightest near the ultracode marker, and the wave-front travels outward over
time. It is NOT a static radial glow (that was the earlier, wrong attempt).

Modes:
  python effort_selector.py                               # interactive (←/→/Enter/Esc)
  python effort_selector.py --once --stage ultracode --frame 1   # deterministic frame
"""
from __future__ import annotations

import argparse
import math
import os
import sys

_SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # skills/tui-ui
if _SKILL not in sys.path:
    sys.path.insert(0, _SKILL)

from ui.core import BOLD, Canvas, get_theme  # noqa: E402

THEME = get_theme("dashboard")

# ── measured constants (from the real program) ─────────────────────────────
# base stage marker columns and inter-label spacers
EW = [1, 10, 20, 30, 40]
VW = [5, 5, 5, 6]
BASE_WIDTH = 42
MIN_WIDTH = 14

# base 5 stages: (value, label, color-kind)
BASE_LEVELS = [
    ("low", "low", "warning"),
    ("medium", "medium", "success"),
    ("high", "high", "permission"),
    ("xhigh", "xhigh", "autoAccept-shimmer"),
    ("max", "max", "rainbow-animated"),
]

# GROUND TRUTH (navigation-fixed capture): the SELECTED stage word turns this
# color + bold; all other words are gray #999999; "ultracode" word is always dim
# violet #8c50f0. No background block except when ultracode itself is selected.
SELECTED_COLOR = {
    "low":   (0xFF, 0xC1, 0x07),   # gold  (verified)
    "medium": (0x4E, 0xBA, 0x65),  # green (source=success; verify if needed)
    "high":  (0xB1, 0xB9, 0xF9),   # periwinkle (verified)
    "xhigh": (0xAF, 0x87, 0xFF),   # bright violet (verified)
    "max":   (0xEB, 0x5F, 0x57),   # red (verified — NOT a rainbow)
}

# violet-ripple palette — measured from the real /effort ultracode selector.
# The bg is a
# cosine wave from dark #3e1676 (trough) to bright #8c50f0 (peak).
XDR = [
    (0x3e, 0x16, 0x76),  # 0 trough (darkest)
    (0x49, 0x1e, 0x87),
    (0x54, 0x27, 0x99),
    (0x5f, 0x2f, 0xaa),
    (0x6b, 0x37, 0xbc),
    (0x76, 0x3f, 0xcd),
    (0x81, 0x48, 0xdf),
    (0x8c, 0x50, 0xf0),  # 7 peak (brightest)
]
_XDR_SET = set(XDR)           # fast membership test for "is this cell washed?"
MIO = XDR[-1]                 # brightest violet (bg of selected ultracode label)
WHITE = (255, 255, 255)       # text color on ripple cells
ZRN = MIO                     # unselected ultracode label color
ZTA = (0xD0, 0xB4, 0xFF)      # #d0b4ff — xhigh shimmer bright char
DIM = (0x8A, 0x8A, 0x99)

# ripple wave params
DIO = 20            # wavelength
CW = 0.03           # travel increment per timer tick
QRN = 5             # stages row index (ripple distance origin row) — matches R_STAGES
# the source timer ticks fast; travel = ticks*0.03 creeps outward slowly. Driving
# by real seconds: ~1.5 cells/sec => the wave hugs ultracode for the first ~8s
# and takes ~35s to reach 'low' (col dist 53) — the product's slow focused feel.
CW_TRAVEL_PER_SEC = 1.5
# The wave bands drift outward over time; ~one wavelength (DIO=20 → ~13-14 real
# cols) per ~1.5s reads as a calm ripple. Shifting travel by this per second
# moves the cosine phase while coverage stays full.
WAVE_SHIFT_PER_SEC = 22.0
# Measured live: entering ultracode, the wash's left edge swept 49→8 (≈41 cols)
# in 1.32s ⇒ ~31 cols/sec expansion of the wavefront from the ultracode origin.
WAVE_EXPAND_PER_SEC = 31.0
# On selecting high/xhigh/max, the white highlight sweeps right→left toward the
# selection over ~4 frames across ~6 stages ⇒ ~10 stages/sec fills the lit region.
SWEEP_STAGES_PER_SEC = 12.0
# Fraction/sec that the violet block's left edge sweeps from ultracode out to the
# selected stage's column on select (0→1 over ~0.7s ⇒ visible grow-in animation).
SWEEP_FRAC_PER_SEC = 1.4

# row offsets within the drawn block (Effort at top; then stacked)
R_BORDER = 0        # top ▔ rule (real #b1b9f9), above the block
R_EFFORT = 1
R_BLANK1 = 2
R_FASTER = 3
R_TRACK = 4         # s_p
R_STAGES = 5        # qrn (ripple distance origin row)
R_SUB = 6           # xhigh + workflows (ultracode) / max warning share this slot
R_BLANK2 = 7
R_HINT = 8          # ←/→ to adjust · Enter · Esc  (fixed)
BLOCK_H = 9
# max's warning line (shown when max is selected), on the R_SUB slot per the real program.
MAX_WARNING = ("May use excessive tokens resulting in long response times or "
               "overthinking. Use sparingly for the hardest tasks.")
BORDER_FG = (0xB1, 0xB9, 0xF9)   # periwinkle top rule
TRACK_ON_WASH = (0xD0, 0xB4, 0xFF)  # rail color when on the violet wash (#d0b4ff)
# the ripple's row coordinate for a block row = (block_row - R_STAGES) maps to
# source rows where stages row == qrn(2); we keep distance origin at R_STAGES.


def _cumulative_starts(labels, spacers):
    """Qta: labelStarts[i] = sum over s<i of (len(label[s]) + spacers[s])."""
    starts = []
    for i in range(len(labels)):
        acc = 0
        for s in range(i):
            acc += len(labels[s]) + spacers[s]
        starts.append(acc)
    return starts


def build_layout():
    """Build the full geometry (base 5 stages) with the ultracode stage appended."""
    levels = list(BASE_LEVELS)                       # 5 base
    base_starts = _cumulative_starts([l[1] for l in levels], VW)
    # base width with all 5 stages shown: 42
    base_width = BASE_WIDTH

    # ultracode branch
    a = base_width + 3
    levels = levels + [("ultracode", "ultracode", "violet-ripple")]
    triangle_positions = list(EW) + [a + math.floor(8.5)]        # [...,54]
    spacers = list(VW) + [(a + 4) - base_width]                  # +[7]
    width = a + 17
    label_starts = _cumulative_starts([l[1] for l in levels], spacers)
    track_chars = "─" * (base_width + 1) + "┆" + "─" * 18        # ┆ divider fixed at base_width+1
    accent_start = base_width + 2
    sublabel = {"text": "xhigh + workflows", "start": a}
    return {
        "levels": levels,
        "width": width,
        "trianglePositions": triangle_positions,
        "labelStarts": label_starts,
        "spacers": spacers,
        "trackChars": track_chars,
        "accentStart": accent_start,
        "sublabel": sublabel,
    }


# ── violet-ripple: NOT reimplemented here — this is the ENGINE's field.Ripple.
# The whole point of the rendering-model refactor: effort composes a primitive,
# it does not carry its own copy of the ripple math. See ui/field.py.
from ui import field  # noqa: E402


def make_ripple(origin_col: int, travel: float, phase: float = 0.0):
    """The ultracode effect = the engine's Ripple field: concentric cosine bands
    emanating from the ultracode marker, the wavefront `travel` growing over time
    so the ripple EXPANDS OUTWARD and
    washes the whole panel (every row is sampled). No localization, no static
    glow — it radiates from the center to all sides, animated.

    `phase` is the engine's band-drift offset (field.Ripple's `phase` arg): the
    wavefront cutoff keeps using `travel` while the cosine bands drift by `phase`,
    so the disk grows and shimmers independently. This is the ONLY ripple math in
    play — it lives in ui/field.py, not here."""
    return field.Ripple(
        origin=(origin_col, QRN),
        wavelength=DIO,
        travel=travel,
        palette=XDR,
        text_over=True,
        phase=phase,
    )


def _stage_color(kind, selected, t):
    """Per-stage color for the non-ripple stages."""
    if kind == "warning":
        return KIND_COLORS["warning"]
    if kind == "success":
        return KIND_COLORS["success"]
    if kind == "permission":
        return KIND_COLORS["permission"]
    if kind == "autoAccept-shimmer":
        return ZTA if selected else (0x9A, 0x8C, 0xD0)
    if kind == "rainbow-animated":
        return None  # painted per-glyph below
    return THEME.fg


# GROUND TRUTH rainbow ring for the "max" label (era per-char hue cycling).
# 7 HSV-ring colors measured from the real selector; each frame shifts +1.
_RAINBOW = [(0xEB, 0x5F, 0x57),  # red
            (0xF5, 0x8B, 0x57),  # orange
            (0xFA, 0xC3, 0x5F),  # yellow
            (0x91, 0xC8, 0x82),  # green
            (0x82, 0xAA, 0xDC),  # blue
            (0x9B, 0x82, 0xC8),  # indigo
            (0xC8, 0x82, 0xB4)]  # pink
GRAY = (0x99, 0x99, 0x99)        # real unselected/dim gray (#999999)


def _paint_rainbow(cv, x, row, text, t, bg=None):
    """era: per-char hue cycling for 'max'. Each char = ring[(i + frame) % 7],
    the whole word's hues rotate +1 per ~animation tick."""
    off = int(t * 6)   # ~6 hue steps/sec
    b = bg  # None => transparent (terminal bg), no #0E1016 fill
    for i, ch in enumerate(text):
        cv.set(x + i, row, ch, fg=_RAINBOW[(i + off) % len(_RAINBOW)], bg=b, attrs=BOLD)


# xhigh "autoAccept-shimmer" (ground truth): all chars bright violet #af87ff, a
# single #d0b4ff highlight sweeps L→R one char at a time, then pauses ~4 frames.
SHIMMER_BASE = (0xAF, 0x87, 0xFF)
SHIMMER_HEAD = (0xD0, 0xB4, 0xFF)
SHIMMER_RATE = 8.0   # highlight steps per second


def _paint_shimmer(cv, x, row, text, t, bg=None):
    """xhigh shimmer: bright-violet word with a lighter highlight sweeping L→R,
    then a short pause (period = len+4), matching the measured original."""
    b = bg  # None => transparent (terminal bg), no #0E1016 fill
    n = len(text)
    head = int(t * SHIMMER_RATE) % (n + 4)   # 0..n-1 = sweep, n..n+3 = pause
    for i, ch in enumerate(text):
        fg = SHIMMER_HEAD if i == head else SHIMMER_BASE
        cv.set(x + i, row, ch, fg=fg, bg=b, attrs=BOLD)


def _wash_bg(cv, origin_col, origin_row, travel, phase=0.0):
    """The ultracode glow expands RADIALLY (四处扩展) from the ultracode marker:
    a growing disk. This composes the ENGINE's ``field.Ripple`` primitive — there
    is ZERO inline ripple math here. We build one Ripple (origin at the marker,
    wavelength=DIO, palette=XDR, wavefront cutoff=travel, band drift=phase) and
    SAMPLE it per cell, writing the sampled palette band to ``cell.bg``.

    Distance is the ASPECT-corrected 2-D dist inside field.Ripple, so the wavefront
    spreads in ALL directions (left/right AND up/down), not just horizontally. Cells
    with d>travel are left untouched by the sample (EMPTY) → the disk visibly grows
    out from the center over time. ``phase`` drifts the cosine bands so it also
    ripples as it spreads. travel large ⇒ fills the whole panel."""
    rip = make_ripple(origin_col, travel, phase)
    for row in range(BLOCK_H):
        for col in range(cv.w):
            s = rip.sample(col, row, 0.0)     # engine returns the band bg; alpha 0 = untouched
            if s.alpha <= 0.0 or s.bg is None:
                continue                      # not reached by the expanding front
            cell = cv.cell(col, row)
            if cell is not None:
                cell.bg = s.bg


def render_frame(stage: str, t: float = 0.0, full_width: int = 0) -> Canvas:
    """UNIFIED model (measured from the real selector): a violet ripple RECTANGLE
    is anchored at the ultracode marker and extends LEFT to a boundary set by the
    selected stage — nearer ultracode ⇒ narrower block; ultracode ⇒ fills the bar.
    Text rides white on the wash; outside it, stage labels follow the intrinsic
    colors (gray left of selection, max=rainbow, ultracode=violet). A top ▔
    border sits above the block."""
    lay = build_layout()
    levels = lay["levels"]
    names = [l[0] for l in levels]
    sel = names.index(stage) if stage in names else 0
    tw = len(lay["trackChars"])
    tri = lay["trianglePositions"][sel]
    track = lay["trackChars"]

    # Canvas fills the terminal width (full_width) so the top border & ripple can
    # span edge-to-edge; falls back to just fitting the content. bg=None so blank
    # cells emit NO background color (transparent → terminal's own bg), not #0E1016.
    W = max(full_width, lay["width"] + 4, len(MAX_WARNING) + 2)
    cv = Canvas(W, BLOCK_H, bg=None)
    # Center the slider GROUP (Faster/Smarter, track, stages, sublabel) within the
    # full width. Effort/hint/border keep their own left positions; only the slider
    # group is indented by GI so it sits centered like real Claude.
    group_w = len(lay["trackChars"])
    GI = max(0, (W - group_w) // 2)
    origin = lay["trianglePositions"][-1] + GI   # ripple anchored at ultracode (shifted)

    # GROUND TRUTH (correction 4): ONLY the ultracode state has the full-block
    # violet ripple (expanding, all rows). high/xhigh/max/low/medium have NO
    # background block at all — just gray text, a violet accent rail right of the
    # ┆ divider, max=rainbow, ultracode=violet fg. So the wash runs for ultracode
    # only, expanding from the marker over time.
    is_uc = (stage == "ultracode")
    if is_uc:
        # RADIAL expansion (四处扩展): a disk grows from the ultracode marker in
        # ALL directions. travel (the wavefront radius) grows from ~0 over time;
        # phase drifts the cosine bands so it ripples as it spreads.
        travel = 4.0 + t * WAVE_EXPAND_PER_SEC
        phase = t * WAVE_SHIFT_PER_SEC
        _wash_bg(cv, origin, QRN, travel, phase)

    def on_wash(col):
        c = cv.cell(col, 0)
        return False  # placeholder; per-cell check below uses the row

    def txt(row, x, s, *, fg=None, bold=False):
        """Draw text; where the wash painted a violet bg, force white; else fg."""
        for i, ch in enumerate(s):
            col = x + i
            cell = cv.cell(col, row)
            washed = cell is not None and cell.bg in _XDR_SET
            f = WHITE if washed else (fg or THEME.fg)
            b = cell.bg if (cell is not None and cell.bg is not None) else None
            cv.set(col, row, ch, fg=f, bg=b, attrs=BOLD if (bold or washed) else 0)

    # (top border) — full-width ▔ in periwinkle, above the block (real: #b1b9f9)
    for c in range(W):
        cv.set(c, R_BORDER, "▔", fg=BORDER_FG, bg=None)

    # (Effort) title — left of the block, plain
    txt(R_EFFORT, 3, "Effort", bold=True)   # the real program indents ~3 cols

    # (Faster ... Smarter) — centered as part of the slider group
    faster, smarter = "Faster", "Smarter"
    gap = max(1, tw - len(faster) - len(smarter))
    txt(R_FASTER, GI, faster + " " * gap + smarter)

    # (track) — plain rail (gray) + marker. On the ultracode wash it reads light
    # on the wave; otherwise the whole rail is subtle gray. Marker ▲ plain (no bg)
    # unless it's sitting on the violet block.
    for i, ch in enumerate(track):
        if i == tri:
            continue
        col = i + GI
        cell = cv.cell(col, R_TRACK)
        if cell is not None and cell.bg in _XDR_SET:
            cv.set(col, R_TRACK, ch, fg=TRACK_ON_WASH, bg=cell.bg)
        else:
            cv.set(col, R_TRACK, ch, fg=GRAY, bg=None)
    mcol = tri + GI
    mcell = cv.cell(mcol, R_TRACK)
    if mcell is not None and mcell.bg in _XDR_SET:
        cv.set(mcol, R_TRACK, "▲", fg=WHITE, bg=mcell.bg, attrs=BOLD)
    else:
        cv.set(mcol, R_TRACK, "▲", fg=WHITE, bg=None)

    # (stages) GROUND TRUTH (nav-fixed, FINAL): the SELECTED word turns its color
    # + bold; all other words gray #999999; "ultracode" word always dim violet.
    # NO rainbow, NO accent rail, NO block — except when ultracode is selected, the
    # violet ripple wash covers everything and forces white text.
    for i, (val, label, kind) in enumerate(levels):
        x = lay["labelStarts"][i] + GI
        first = cv.cell(x, R_STAGES)
        washed = first is not None and first.bg in _XDR_SET
        selected = (i == sel)
        if washed:                                        # ultracode block covers it
            txt(R_STAGES, x, label)
        elif selected and kind == "rainbow-animated":     # max: animated rainbow
            _paint_rainbow(cv, x, R_STAGES, label, t)
        elif selected and kind == "autoAccept-shimmer":   # xhigh: L→R white sweep
            _paint_shimmer(cv, x, R_STAGES, label, t)
        elif selected and val in SELECTED_COLOR:          # the selected word: colored+bold
            cv.put_text(x, R_STAGES, label, fg=SELECTED_COLOR[val], bg=None, attrs=BOLD)
        elif val == "ultracode":                          # always dim violet fg
            cv.put_text(x, R_STAGES, label, fg=MIO, bg=None,
                        attrs=BOLD if selected else 0)
        else:                                             # everything else: gray
            cv.put_text(x, R_STAGES, label, fg=GRAY, bg=None)

    # (R_SUB slot) — ultracode shows "xhigh + workflows" (inside the block);
    # max shows its warning line here (dim gray). Only one at a time.
    if stage == "max":
        cv.put_text(GI, R_SUB, MAX_WARNING[:W - GI], fg=GRAY, bg=None)
    else:
        sub = lay["sublabel"]
        sc = cv.cell(sub["start"] + GI, R_SUB)
        if sc is not None and sc.bg in _XDR_SET:
            txt(R_SUB, sub["start"] + GI, sub["text"])

    # (hint) — fixed bottom row; white on wash where covered, else dim
    hint = "←/→ to adjust · Enter to confirm · Esc to cancel"
    txt(R_HINT, 3, hint)   # bottom-left, indented ~3 cols
    return cv


# ── terminal control + CLI ───────────────────────────────────────────────
HIDE, SHOW = "\x1b[?25l", "\x1b[?25h"
ALT_ENTER, ALT_LEAVE = "\x1b[?1049h", "\x1b[?1049l"
HOME = "\x1b[H"


def _enable_vt():
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.GetStdHandle(-11)
            m = ctypes.c_uint32()
            if k.GetConsoleMode(h, ctypes.byref(m)):
                k.SetConsoleMode(h, m.value | 0x0004)
        except Exception:
            os.system("")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _term_size():
    try:
        sz = os.get_terminal_size()
        return sz.columns, sz.lines
    except Exception:
        return 120, 30


def _compose_centered(stage, t):
    """Real Claude layout: the selector is BOTTOM-DOCKED — the hint is the last
    terminal row, the block stacks upward, the top ▔ border sits above Effort.
    Full-width, transparent blanks. Each row absolutely positioned so nothing
    scrolls or stacks between frames."""
    cols, lines = _term_size()
    cv = render_frame(stage, t, full_width=cols)   # full-width: border spans terminal
    top = max(0, lines - BLOCK_H)                  # BOTTOM-DOCK: last block row = last line
    body = cv.to_ansi().split("\n")
    out = ["\x1b[2J"]                              # clear once
    for i, row in enumerate(body):
        out.append(f"\x1b[{top + i + 1};1H" + row)  # absolute row, col 1
    # park cursor at home; NO trailing newline (a newline on the last row scrolls)
    return "".join(out) + "\x1b[0m\x1b[H"


def render_once(stage, frame):
    _enable_vt()
    t = (frame % 3) / 3.0
    sys.stdout.write(_compose_centered(stage, t))   # absolute-positioned, no trailing newline
    sys.stdout.flush()


def _read_key():
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            return "enter"
        if ch in ("\x1b", "q", "Q"):
            return "esc"
        if ch in ("\x00", "\xe0"):
            return {"K": "left", "M": "right"}.get(msvcrt.getwch())
        return {"h": "left", "a": "left", "l": "right", "d": "right"}.get(ch)
    import termios, tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch in ("\r", "\n"):
            return "enter"
        if ch in ("q", "Q"):
            return "esc"
        if ch == "\x1b":
            seq = sys.stdin.read(2)
            return {"[D": "left", "[C": "right"}.get(seq, "esc")
        return {"h": "left", "a": "left", "l": "right", "d": "right"}.get(ch)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def interactive(start="low"):
    _enable_vt()
    names = [l[0] for l in build_layout()["levels"]]
    # NOTE: do NOT bail to a single static frame when isatty() is False — under a
    # PTY (incl. our own SmartCLI driver) isatty is often False yet the animation
    # loop must still run. Only key input needs a real tty; the render loop runs
    # regardless so the ripple animates. (This was why it looked frozen.)
    import threading, time
    idx = names.index(start) if start in names else 0
    result = {"v": None}
    stop = threading.Event()

    def loop():
        nonlocal idx
        while not stop.is_set():
            k = _read_key()
            if k == "left":
                idx = max(0, idx - 1)
            elif k == "right":
                idx = min(len(names) - 1, idx + 1)
            elif k == "enter":
                result["v"] = names[idx]; stop.set()
            elif k == "esc":
                stop.set()

    w = sys.stdout.write
    try:
        w(ALT_ENTER); w(HIDE); w("\x1b[2J"); sys.stdout.flush()
        threading.Thread(target=loop, daemon=True).start()
        uc_t0 = time.perf_counter()   # clock for the ultracode expansion
        prev_idx = idx
        while not stop.is_set():
            # Restart the expansion clock each time the selection ENTERS
            # ultracode, so the ripple spreads from the marker afresh every time.
            if idx != prev_idx:
                uc_t0 = time.perf_counter()
                prev_idx = idx
            t = time.perf_counter() - uc_t0   # seconds since landing on this stage
            w(HOME)
            w(_compose_centered(names[idx], t))   # absolute-positioned; no scroll/stack
            sys.stdout.flush()
            time.sleep(1 / 30.0)
    finally:
        w("\x1b[0m"); w(SHOW); w(ALT_LEAVE); sys.stdout.flush()
    print(f"Set effort level to {result['v']}" if result["v"] else "cancelled")


def main(argv=None):
    ap = argparse.ArgumentParser(description="violet-ripple /effort-style selector replica")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--stage", default="low")
    ap.add_argument("--frame", type=int, default=0)
    args = ap.parse_args(argv)
    if args.once:
        render_once(args.stage, args.frame)
    else:
        interactive(args.stage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

