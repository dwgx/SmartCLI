"""shot.py -- core of the pyte -> PNG screenshot smoke-test harness.

Feed any command's (or renderable's) raw terminal output through **pyte** -- a
faithful VT emulator -- then render the resulting cell grid to a real PNG with
**PIL**. This is the standard *no-tmux* way to snapshot-test TUI rendering:
tmux itself just re-parses program output through its own VT layer, so pyte
models the cell-level render faithfully. We always LABEL output as
pyte-simulation, never as a real-tmux capture (see :data:`RENDER_LABEL`).

Public API
----------
* :func:`render_bytes_to_screen(data, cols, rows) -> pyte.Screen`
    Feed raw bytes through a fresh ``pyte.ByteStream`` and return the Screen.
* :func:`screen_to_png(screen, path, ...) -> (width_px, height_px)`
    Render every cell (fg/bg/bold/reverse + cursor) to a PNG.
* :func:`capture_cmd(argv, cols, rows, ...) -> bytes`
    Spawn a command under a real PTY (smartcli_core WinptyBackend), pump its
    output for a bounded window, and return the raw byte stream.

The color model mirrors pyte exactly: a cell color is either the string
``"default"``, a named 16-color (``"red"``, ``"brown"`` == yellow, ``"brightred"``
...), or a 6-hex-digit string (truecolor, and 256-indexed colors pyte already
resolved to hex). :func:`color_to_rgb` maps all three to an ``(r, g, b)`` triple.
"""

from __future__ import annotations

import os
import re
import sys
import time
import unicodedata
from typing import List, Optional, Sequence, Tuple, Union

import pyte
from PIL import Image, ImageDraw, ImageFont

# Make smartcli_core importable when this file is run from anywhere.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Honest provenance label -- stamp this onto contact sheets / anywhere a viewer
# might mistake a pyte render for a real-tmux capture.
RENDER_LABEL = "pyte-simulation (VT emulation -> PIL); NOT a real-tmux capture"

DEFAULT_FONT = r"C:\Windows\Fonts\consola.ttf"
DEFAULT_BOLD_FONT = r"C:\Windows\Fonts\consolab.ttf"

# Fallback fonts for glyphs the primary monospace font lacks (CJK, emoji).
# consola.ttf has no CJK/emoji coverage, so wide glyphs would render as tofu
# boxes. These are tried in order for any char the primary font can't draw.
# Missing files are skipped silently.
FALLBACK_FONTS = [
    r"C:\Windows\Fonts\msyh.ttc",       # Microsoft YaHei -- CJK
    r"C:\Windows\Fonts\seguiemj.ttf",   # Segoe UI Emoji -- emoji
    r"C:\Windows\Fonts\malgun.ttf",     # Malgun Gothic -- Korean
]

# Default RGB for pyte's "default" fg/bg (a dark terminal theme).
DEFAULT_FG = (0xC8, 0xC8, 0xC8)
DEFAULT_BG = (0x0C, 0x0C, 0x0C)
CURSOR_RGB = (0xE0, 0xE0, 0xE0)


# --------------------------------------------------------------------------
# Named-color table -- matches pyte.graphics names 1:1.
# --------------------------------------------------------------------------
# pyte emits these names for SGR 30-37 / 40-47 (base) and 90-97 / 100-107
# (bright / aixterm). Values chosen to match the first 16 entries of pyte's
# own 256-color palette (graphics.FG_BG_256[:16]) so named and indexed agree.
NAMED_COLORS: dict[str, Tuple[int, int, int]] = {
    "black": (0x00, 0x00, 0x00),
    "red": (0xCD, 0x00, 0x00),
    "green": (0x00, 0xCD, 0x00),
    "brown": (0xCD, 0xCD, 0x00),   # pyte's name for SGR 33 (yellow)
    "blue": (0x00, 0x00, 0xEE),
    "magenta": (0xCD, 0x00, 0xCD),
    "cyan": (0x00, 0xCD, 0xCD),
    "white": (0xE5, 0xE5, 0xE5),
    "brightblack": (0x7F, 0x7F, 0x7F),
    "brightred": (0xFF, 0x00, 0x00),
    "brightgreen": (0x00, 0xFF, 0x00),
    "brightbrown": (0xFF, 0xFF, 0x00),
    "brightyellow": (0xFF, 0xFF, 0x00),
    "brightblue": (0x5C, 0x5C, 0xFF),
    "brightmagenta": (0xFF, 0x00, 0xFF),
    # pyte 0.8.x has a known typo "bfightmagenta"; alias it so we never crash.
    "bfightmagenta": (0xFF, 0x00, 0xFF),
    "brightcyan": (0x00, 0xFF, 0xFF),
    "brightwhite": (0xFF, 0xFF, 0xFF),
}


def color_to_rgb(
    color: str,
    *,
    is_bg: bool,
    default_fg: Tuple[int, int, int] = DEFAULT_FG,
    default_bg: Tuple[int, int, int] = DEFAULT_BG,
) -> Tuple[int, int, int]:
    """Map a pyte cell color to an ``(r, g, b)`` triple.

    ``color`` is one of: ``"default"``, a named 16-color, or 6 hex digits
    (truecolor / resolved 256). ``is_bg`` selects which "default" to use.
    Unrecognised values fall back to the appropriate default rather than raising.
    """
    if not color or color == "default":
        return default_bg if is_bg else default_fg
    lc = color.lower()
    if lc in NAMED_COLORS:
        return NAMED_COLORS[lc]
    # 6-hex-digit truecolor / resolved-256 string.
    if len(color) == 6:
        try:
            return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))
        except ValueError:
            pass
    return default_bg if is_bg else default_fg


# --------------------------------------------------------------------------
# Character width (wcwidth-style, stdlib-only).
# --------------------------------------------------------------------------
def char_width(ch: str) -> int:
    """Return display cell width of a single character: 0, 1, or 2.

    Zero-width for combining marks and control chars; 2 for East-Asian Wide /
    Fullwidth (and emoji, which unicodedata reports as ``W``); 1 otherwise.
    This mirrors how pyte itself advances the cursor, so a wide glyph occupies
    its own cell plus one empty continuation cell in the buffer.
    """
    if not ch:
        return 0
    o = ord(ch)
    if o == 0:
        return 0
    # C0/C1 control characters.
    if o < 32 or 0x7F <= o < 0xA0:
        return 0
    if unicodedata.combining(ch):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


# --------------------------------------------------------------------------
# pyte feed
# --------------------------------------------------------------------------
def render_bytes_to_screen(data: bytes, cols: int, rows: int) -> pyte.Screen:
    """Feed ``data`` through a fresh ``pyte.ByteStream`` and return the Screen.

    A ``ByteStream`` decodes UTF-8 incrementally, so multibyte characters and
    partial escapes inside ``data`` are handled correctly. The returned Screen
    reflects the final cell grid after the whole stream is consumed.

    Bare ``\\n`` (LF) is normalized to ``\\r\\n`` (CRLF): a terminal treats LF as
    "cursor down, same column" (LNM off by default), so renderables that join
    rows with a plain ``\\n`` (e.g. ``Canvas.to_ansi``) would stack every row at
    the previous row's end column and overwrite. Any existing ``\\r\\n`` is left
    intact (we only add the CR the terminal needs, never double it).
    """
    screen = pyte.Screen(cols, rows)
    stream = pyte.ByteStream(screen)
    if data:
        data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        stream.feed(data)
    return screen


# --------------------------------------------------------------------------
# PNG render
# --------------------------------------------------------------------------
class _FontSet:
    """Primary monospace font + bold + fallbacks, with per-glyph selection.

    consola.ttf lacks CJK/emoji glyphs, so :meth:`pick` returns the first font
    (primary, then bold if applicable, then each fallback) whose cmap actually
    covers the character -- otherwise the glyph renders as a tofu box even
    though pyte decoded it fine. Coverage results are memoized per char.
    """

    def __init__(self, font_path: str, cell_h: int) -> None:
        size = max(6, int(cell_h * 0.82))
        self.size = size
        try:
            self.regular = ImageFont.truetype(font_path, size)
        except Exception:
            self.regular = ImageFont.load_default()
        bold_path = DEFAULT_BOLD_FONT if font_path == DEFAULT_FONT else font_path
        try:
            self.bold = ImageFont.truetype(bold_path, size)
        except Exception:
            self.bold = self.regular
        self.fallbacks: List[ImageFont.FreeTypeFont] = []
        for fp in FALLBACK_FONTS:
            if os.path.exists(fp):
                try:
                    self.fallbacks.append(ImageFont.truetype(fp, size))
                except Exception:
                    pass
        self._cache: dict = {}
        # A font renders every missing codepoint as the SAME .notdef ("tofu")
        # glyph, so bbox alone can't detect coverage. We render a private-use
        # codepoint (U+E000, essentially never in a cmap) once per font as the
        # tofu reference; any glyph whose mask bytes differ is really covered.
        self._notdef: dict = {}
        for f in [self.regular, self.bold, *self.fallbacks]:
            self._notdef[id(f)] = self._mask_bytes(f, "")

    @staticmethod
    def _mask_bytes(font: ImageFont.FreeTypeFont, ch: str) -> Optional[bytes]:
        try:
            return bytes(font.getmask(ch))
        except Exception:
            return None

    def _covers(self, font: ImageFont.FreeTypeFont, ch: str) -> bool:
        try:
            m = font.getmask(ch)
        except Exception:
            return False
        if m.getbbox() is None:
            return False  # whitespace / empty glyph
        nd = self._notdef.get(id(font))
        return nd is None or bytes(m) != nd

    def pick(self, ch: str, bold: bool) -> ImageFont.FreeTypeFont:
        key = (ch, bold)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        primary = self.bold if bold else self.regular
        chosen = primary
        # ASCII always uses the primary monospace face; only probe non-ASCII.
        if ord(ch[0]) >= 0x80 and not self._covers(primary, ch):
            for fb in self.fallbacks:
                if self._covers(fb, ch):
                    chosen = fb
                    break
        self._cache[key] = chosen
        return chosen


def screen_to_png(
    screen: pyte.Screen,
    path: str,
    *,
    font_path: str = DEFAULT_FONT,
    cell_w: int = 9,
    cell_h: int = 19,
    default_fg: Tuple[int, int, int] = DEFAULT_FG,
    default_bg: Tuple[int, int, int] = DEFAULT_BG,
    draw_cursor: bool = True,
) -> Tuple[int, int]:
    """Render a pyte Screen to a PNG, cell by cell. Returns ``(width_px, height_px)``.

    Every cell is drawn with its own fg/bg. ``reverse`` swaps fg and bg (and is
    applied on top of the screen-wide DECSCNM baseline). ``bold`` selects the
    bold font face and brightens the default fg slightly. Wide glyphs (CJK /
    emoji) occupy two cells: the glyph is drawn once and the following empty
    continuation cell is skipped. If the cursor is visible it is drawn as a
    reverse-video block on its cell.
    """
    cols = screen.columns
    rows = screen.lines
    width_px = cols * cell_w
    height_px = rows * cell_h

    base_reverse = bool(screen.default_char.reverse)
    img = Image.new("RGB", (max(1, width_px), max(1, height_px)),
                    default_bg if not base_reverse else default_fg)
    draw = ImageDraw.Draw(img)
    fonts = _FontSet(font_path, cell_h)

    cur_x, cur_y = screen.cursor.x, screen.cursor.y
    cursor_visible = draw_cursor and not bool(screen.cursor.hidden)

    for row in range(rows):
        line = screen.buffer[row]  # StaticDefaultDict: missing cols -> default char
        col = 0
        while col < cols:
            ch = line[col]
            data = ch.data or " "
            w = char_width(data) if data.strip() else 1
            w = max(1, min(2, w))

            fg = color_to_rgb(ch.fg, is_bg=False, default_fg=default_fg, default_bg=default_bg)
            bg = color_to_rgb(ch.bg, is_bg=True, default_fg=default_fg, default_bg=default_bg)

            reverse = bool(ch.reverse) ^ base_reverse
            is_cursor = cursor_visible and row == cur_y and col == cur_x
            if reverse ^ is_cursor:  # reverse OR cursor (but cursor+reverse cancels)
                fg, bg = bg, fg
            if is_cursor and not reverse:
                # Plain cursor cell: make sure fg reads against the block.
                fg = bg if bg != default_bg else default_fg
                bg = CURSOR_RGB

            x0 = col * cell_w
            y0 = row * cell_h
            span = w * cell_w
            # Paint the background span first.
            if bg != default_bg or reverse or is_cursor:
                draw.rectangle([x0, y0, x0 + span - 1, y0 + cell_h - 1], fill=bg)

            if data and data != " ":
                if ch.bold and fg == default_fg:
                    fg = tuple(min(255, c + 40) for c in fg)  # type: ignore[assignment]
                font = fonts.pick(data, bool(ch.bold))
                try:
                    draw.text((x0 + 1, y0 + 1), data, font=font, fill=fg,
                              embedded_color=(font in fonts.fallbacks))
                except Exception:
                    # Unrenderable glyph -> leave the background block only.
                    pass
            col += w

    img.save(path, "PNG")
    return (img.width, img.height)


# --------------------------------------------------------------------------
# Command capture (real PTY, bounded)
# --------------------------------------------------------------------------
def capture_cmd(
    argv: Union[str, Sequence[str]],
    cols: int = 80,
    rows: int = 24,
    *,
    seconds: float = 3.0,
    frames: Optional[int] = None,
    alt_screen: bool = False,
    env: Optional[dict] = None,
    poll_s: float = 0.02,
    settle_s: float = 0.4,
) -> bytes:
    """Spawn ``argv`` under a real PTY and return the raw output byte stream.

    Uses :class:`smartcli_core.PtySession` (WinptyBackend on Windows), pumps the
    child's output for a bounded window, and returns everything read so an
    animation yields a representative frame's worth of bytes.

    Bounds (hard-capped, never unbounded):
      * ``seconds``    -- wall-clock ceiling on the pump loop.
      * ``frames``     -- optional early stop after this many non-empty reads.
      * ``settle_s``   -- after the child exits, keep draining briefly so the
                          final flush (prompt, last frame) is captured.

    ``alt_screen`` is advisory metadata for the caller (the child decides its
    own screen mode); it is not injected into the stream here. ``env`` augments
    the child environment. Raising ``COLORTERM``/``TERM`` for truecolor is the
    caller's job via matrix.py.
    """
    from smartcli_core import PtySession

    session_env = None
    if env:
        session_env = dict(os.environ)
        session_env.update(env)

    buf = bytearray()
    sess = PtySession(cols=cols, rows=rows)
    # WinptyBackend.spawn does not take env; set it on the process env instead.
    saved_env = None
    if session_env is not None:
        saved_env = dict(os.environ)
        os.environ.update(session_env)
    try:
        sess.backend.spawn(argv, cols, rows)
        sess._started = True
        t0 = time.perf_counter()
        nonempty_reads = 0
        # Stop conditions, in priority order:
        #   * hard wall-clock cap (``seconds``) -- always honored, never unbounded;
        #   * EOF sentinel from the reader thread (``_eof``) -- the RELIABLE
        #     end-of-output signal on both backends. ConPTY's ``is_alive()`` lags
        #     the actual child exit, so we do NOT gate on it; the reader thread
        #     blocks until true EOF and only then flags ``_eof``, by which point
        #     all child bytes (including the final flush) are already drained.
        #   * optional ``frames`` cap for animations that never exit.
        while True:
            now = time.perf_counter()
            if now - t0 >= seconds:
                break
            data = sess.backend.read_nonblocking()
            if data:
                buf.extend(data)
                nonempty_reads += 1
                if frames is not None and nonempty_reads >= frames:
                    time.sleep(poll_s)
                    buf.extend(sess.backend.read_nonblocking())
                    break
            if getattr(sess.backend, "_eof", False):
                # Reader hit EOF; drain any straggler bytes and stop.
                buf.extend(sess.backend.read_nonblocking())
                break
            time.sleep(poll_s)
    finally:
        sess.close()
        if saved_env is not None:
            os.environ.clear()
            os.environ.update(saved_env)
    return strip_conpty_handshake(bytes(buf))


# ConPTY (pywinpty) injects a fixed init handshake ahead of the child's own
# output: a window op, a Device-Attributes request, focus-reporting enable, and
# win32-input-mode enable. None of these come from the child, and the focus
# enable (?1004h) has no matching disable, so it trips no_leaked_modes as a
# false positive. Strip this exact preamble (only when it appears at the very
# start) so the returned stream reflects the child faithfully.
_CONPTY_HANDSHAKE = re.compile(
    rb"^(?:\x1b\[\d*t|\x1b\[c|\x1b\[\?1004h|\x1b\[\?9001h|\x1b\[\?25[hl])+"
)


def strip_conpty_handshake(data: bytes) -> bytes:
    """Remove the leading ConPTY init handshake from a captured stream (Windows)."""
    m = _CONPTY_HANDSHAKE.match(data)
    return data[m.end():] if m else data


def render_frame_to_bytes(effect_frame: str) -> bytes:
    """Convenience: turn a rendered fx frame string into feedable bytes.

    fx effects return a frame as a str of rows joined by ``\\n``; a terminal
    would receive CRLF. We normalise to CRLF and prefix a cursor-home so the
    grid lands at the top-left, matching what the fx play loop emits per frame.
    """
    home = "\x1b[H"
    normalized = effect_frame.replace("\r\n", "\n").replace("\n", "\r\n")
    return (home + normalized).encode("utf-8", "replace")
