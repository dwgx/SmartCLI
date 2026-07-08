"""checks.py -- automated rendering-defect detectors.

Two families of check run against a screenshot target so smoke tests fail
*loudly* rather than silently producing a broken image:

* **Stream checks** scan the raw byte stream for VT-mode balance bugs (the
  exact defects the tmux research flagged in fx/core.py): a ``?1049h`` with no
  ``?1049l`` leaks the alt screen into the user's shell; a ``?25l`` with no
  ``?25h`` leaves the cursor hidden. See :func:`run_stream_checks`.

* **Screen checks** run against a rendered pyte Screen: cursor left hidden,
  content clipped / unexpected blank frame, color present when truecolor was
  expected, mojibake (box-drawing / CJK collapsed to ``?``), and wrap/overflow
  sanity (no row wider than ``cols``). See :func:`run_screen_checks`.

Every individual check returns ``(ok: bool, detail: str)``. The ``run_*``
helpers return a list of ``(name, ok, detail)`` triples.
"""

from __future__ import annotations

import re
from typing import List, Tuple

import pyte

Check = Tuple[bool, str]

# Sentinel glyphs that indicate a decode / width failure ("mojibake").
_REPLACEMENT = "�"
_BOX_DRAWING = set("─│┌┐└┘├┤┬┴┼━┃╭╮╯╰╱╲═║╔╗╚╝")

# ANSI/SGR stripper for measuring the *visible* width of a raw frame string.
_ANSI_SEQ = re.compile(r"\x1b\[[0-9;:?]*[A-Za-z]")


def _visible_width(line: str) -> int:
    """Visible cell width of a frame line: strip ANSI, count wide glyphs as 2.

    Uses wcwidth when available (authoritative East-Asian width incl. emoji);
    falls back to a unicodedata east_asian_width heuristic otherwise.
    """
    s = _ANSI_SEQ.sub("", line)
    try:
        from wcwidth import wcswidth
        w = wcswidth(s)
        if w >= 0:
            return w
    except Exception:
        pass
    import unicodedata
    w = 0
    for ch in s:
        if unicodedata.combining(ch):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def frame_no_overflow(frame: str, cols: int, rows: int) -> Check:
    """Raw-frame geometry guard: no line wider than ``cols``, no more than ``rows`` lines.

    This runs on the effect's frame STRING, before pyte parses it. pyte always
    clamps its rendered grid to ``cols`` (wrapping or truncating overflow), so a
    check on the rendered grid can never see an effect that emits an over-wide
    row -- the very 'overflows at N cols' defect the smoke test must catch. A
    compact banner that emits *fewer* than ``rows`` lines is fine (not overflow);
    only exceeding the bounds is a defect.
    """
    lines = frame.split("\n")
    if len(lines) > rows:
        return False, f"{len(lines)} frame rows > {rows} (overflows bottom)"
    worst_w = 0
    worst_i = -1
    for i, ln in enumerate(lines):
        w = _visible_width(ln)
        if w > worst_w:
            worst_w, worst_i = w, i
    if worst_w > cols:
        return False, f"row {worst_i} visible width {worst_w} > {cols} cols (overflows right)"
    return True, f"frame fits {cols}x{rows} (max row width {worst_w}, {len(lines)} rows)"


# --------------------------------------------------------------------------
# Stream-level checks (byte scan)
# --------------------------------------------------------------------------
def alt_screen_balanced(data: bytes) -> Check:
    """Every ``?1049h`` (enter alt screen) must have a matching ``?1049l``.

    Also accepts the legacy ``?47`` / ``?1047`` alt-screen pairs. An unbalanced
    enter means the program would strand the terminal in the alt buffer on exit.
    """
    enters = 0
    leaves = 0
    for code in (b"1049", b"1047", b"47"):
        enters += len(re.findall(rb"\x1b\[\?" + code + rb"h", data))
        leaves += len(re.findall(rb"\x1b\[\?" + code + rb"l", data))
    if enters == 0:
        return True, "no alt-screen enter (fine)"
    if enters == leaves:
        return True, f"balanced ({enters} enter / {leaves} leave)"
    return False, f"UNBALANCED alt-screen: {enters} enter vs {leaves} leave (leaks alt buffer)"


def cursor_hide_balanced(data: bytes) -> Check:
    """Every ``?25l`` (hide cursor) must have a matching ``?25h`` (show)."""
    hides = len(re.findall(rb"\x1b\[\?25l", data))
    shows = len(re.findall(rb"\x1b\[\?25h", data))
    if hides == 0:
        return True, "cursor never hidden (fine)"
    if shows >= hides:
        return True, f"balanced ({hides} hide / {shows} show)"
    return False, f"cursor hidden {hides}x but shown {shows}x (leaves cursor hidden)"


def no_leaked_modes(data: bytes) -> Check:
    """Mouse / bracketed-paste / focus modes enabled must be disabled by end.

    These would otherwise leak into the user's shell. Checks the common private
    modes fx effects should never leave on: 1000/1002/1003/1006 (mouse),
    2004 (bracketed paste), 1004 (focus).
    """
    leaked = []
    for code in (b"1000", b"1002", b"1003", b"1006", b"2004", b"1004"):
        on = len(re.findall(rb"\x1b\[\?" + code + rb"h", data))
        off = len(re.findall(rb"\x1b\[\?" + code + rb"l", data))
        if on > off:
            leaked.append(code.decode())
    if leaked:
        return False, "modes enabled but not disabled: " + ", ".join(leaked)
    return True, "no leaked input modes"


# --------------------------------------------------------------------------
# Screen-level checks (rendered grid)
# --------------------------------------------------------------------------
def no_cursor_left_hidden(screen: pyte.Screen) -> Check:
    """The final rendered screen should not have the cursor left hidden.

    (Stream balance is the primary guard; this catches the end-state directly.)
    """
    if bool(screen.cursor.hidden):
        return False, "cursor is hidden in the final frame"
    return True, "cursor visible"


def _nonblank_cells(screen: pyte.Screen) -> int:
    """Count cells that would render something: a glyph OR a colored background.

    Background-only effects (plasma, fire, tunnel) fill the screen with SPACE
    characters on colored backgrounds -- those are visible content, not blank,
    so a naive "has non-whitespace glyph" count would wrongly report them blank.
    """
    count = 0
    for row in range(screen.lines):
        line = screen.buffer[row]
        for col in range(screen.columns):
            ch = line[col]
            d = ch.data
            if (d and d.strip()) or (ch.bg and ch.bg != "default"):
                count += 1
    return count


def has_color(screen: pyte.Screen) -> bool:
    """True if any cell carries a non-default fg or bg color."""
    for row in range(screen.lines):
        line = screen.buffer[row]
        for col in range(screen.columns):
            ch = line[col]
            if (ch.fg and ch.fg != "default") or (ch.bg and ch.bg != "default"):
                return True
    return False


def no_unexpected_blank(screen: pyte.Screen, *, expect_content: bool = True) -> Check:
    """A frame that should draw something must not be entirely blank.

    Catches effects that produce an all-blank screen (bad frame, wrong size,
    crashed render) when they were expected to draw. Colored-background cells
    count as content.
    """
    n = _nonblank_cells(screen)
    if not expect_content:
        return True, f"blank-ok ({n} non-blank cells)"
    if n == 0:
        return False, "screen is entirely blank (expected content)"
    return True, f"{n} non-blank cells"


def no_content_clipped_badly(screen: pyte.Screen) -> Check:
    """No row may exceed ``cols`` cells -- overflow means clipping/wrap damage.

    pyte's display is always right-padded to exactly ``cols``; a longer row
    signals a buffer inconsistency. Long input lines are expected to wrap or
    clip within ``cols``, so this asserts the invariant holds.
    """
    cols = screen.columns
    for row, line in enumerate(screen.display):
        if len(line) > cols:
            return False, f"row {row} has {len(line)} cells > cols {cols}"
    return True, f"all rows within {cols} cols"


def wrap_overflow_sanity(screen: pyte.Screen) -> Check:
    """Alias-style sanity check: the buffer grid matches declared geometry."""
    if len(screen.display) != screen.lines:
        return False, f"{len(screen.display)} rows rendered vs {screen.lines} declared"
    return no_content_clipped_badly(screen)


def stream_has_color(data: bytes) -> bool:
    """True if the raw byte stream contains any SGR color escape.

    Matches 38/48 (256 & truecolor) and the 30-37/40-47/90-97/100-107 ANSI
    color ranges. Used to decide whether :func:`color_present` is meaningful:
    a program that emitted no color can't be faulted for rendering none.
    """
    if re.search(rb"\x1b\[[0-9;:]*\b(?:38|48)[;:]", data):
        return True
    for m in re.finditer(rb"\x1b\[([0-9;]*)m", data):
        for part in m.group(1).split(b";"):
            if part.isdigit():
                n = int(part)
                if 30 <= n <= 37 or 40 <= n <= 47 or 90 <= n <= 97 or 100 <= n <= 107:
                    return True
    return False


def color_present(screen: pyte.Screen, *, expected: bool = True) -> Check:
    """When color is expected, some cell must carry a non-default color.

    ``expected`` should reflect whether the source stream actually emitted color
    (see :func:`stream_has_color`). A truecolor target that emitted color but
    renders with only defaults means the color escapes were dropped -- a defect.
    """
    if not expected:
        return True, "no color in source stream (not required)"
    if has_color(screen):
        for row in range(screen.lines):
            line = screen.buffer[row]
            for col in range(screen.columns):
                ch = line[col]
                if (ch.fg and ch.fg != "default") or (ch.bg and ch.bg != "default"):
                    return True, f"color present (e.g. fg={ch.fg} bg={ch.bg})"
    return False, "source emitted color but rendered screen has none (dropped color)"


def no_mojibake(screen: pyte.Screen) -> Check:
    """No replacement char ``U+FFFD`` -- box-drawing / CJK must not collapse.

    A ``?`` or ``U+FFFD`` where a box-drawing or CJK glyph belongs signals a
    decode failure (wrong locale, ACS instead of UTF-8, or a codec drop).
    """
    for row in range(screen.lines):
        line = screen.buffer[row]
        for col in range(screen.columns):
            if line[col].data == _REPLACEMENT:
                return False, f"replacement char U+FFFD at row {row} col {col}"
    return True, "no U+FFFD replacement chars"


# --------------------------------------------------------------------------
# Runners
# --------------------------------------------------------------------------
def run_stream_checks(data: bytes) -> List[Tuple[str, bool, str]]:
    """Run all byte-stream checks. Returns ``[(name, ok, detail), ...]``."""
    out = []
    for name, fn in (
        ("alt_screen_balanced", alt_screen_balanced),
        ("cursor_hide_balanced", cursor_hide_balanced),
        ("no_leaked_modes", no_leaked_modes),
    ):
        ok, detail = fn(data)
        out.append((name, ok, detail))
    return out


def run_screen_checks(
    screen: pyte.Screen,
    *,
    depth: str = "truecolor",
    expected_alt: bool = False,
    expect_content: bool = True,
    source_has_color: bool = True,
) -> List[Tuple[str, bool, str]]:
    """Run all rendered-screen checks. Returns ``[(name, ok, detail), ...]``.

    ``color_present`` is asserted only when ``depth == 'truecolor'`` AND the
    source stream actually emitted color (``source_has_color``); mono has no
    color by design and a colorless program can't be faulted for rendering none.
    ``expect_content`` lets a caller mark a deliberately-blank target as ok.
    """
    out = []
    ok, d = no_cursor_left_hidden(screen)
    out.append(("no_cursor_left_hidden", ok, d))
    ok, d = no_unexpected_blank(screen, expect_content=expect_content)
    out.append(("no_unexpected_blank", ok, d))
    ok, d = no_content_clipped_badly(screen)
    out.append(("no_content_clipped_badly", ok, d))
    ok, d = wrap_overflow_sanity(screen)
    out.append(("wrap_overflow_sanity", ok, d))
    ok, d = no_mojibake(screen)
    out.append(("no_mojibake", ok, d))
    ok, d = color_present(screen, expected=(depth == "truecolor" and source_has_color))
    out.append(("color_present", ok, d))
    return out
