"""Terminal core: ANSI primitives, VT enable, sizing, and the flicker-free play loop.

Everything terminal-facing lives here so effects stay pure (frame string in, frame
string out). Truecolor via ``\\x1b[38;2;R;G;Bm``; tuned for Windows Terminal but works
on any VT-capable terminal. Degrades to a single plain frame when stdout is not a TTY.
"""
from __future__ import annotations

import os
import sys
import time
import shutil

# --------------------------------------------------------------------------
# ANSI primitives
# --------------------------------------------------------------------------
RESET = "\x1b[0m"
HOME = "\x1b[H"
CLEAR = "\x1b[2J"
CLEAR_SCROLL = "\x1b[3J"
HIDE = "\x1b[?25l"
SHOW = "\x1b[?25h"
ALT_ENTER = "\x1b[?1049h"   # switch to alternate screen buffer
ALT_LEAVE = "\x1b[?1049l"   # restore primary screen buffer
NOWRAP = "\x1b[?7l"         # disable line wrap at EOL
WRAP = "\x1b[?7h"           # re-enable line wrap


def ensure_utf8_stdout() -> None:
    """Force stdout to UTF-8 so non-ASCII glyphs (e.g. the U+2580 half-block used
    by image2ascii) never hit a locale codec that can't encode them.

    On Windows a redirected/piped stdout defaults to the ANSI code page (e.g.
    cp936/gbk), which raises UnicodeEncodeError on box/block glyphs. Reconfigure
    to UTF-8 with errors='replace' (Python 3.7+); best-effort and harmless if the
    stream is already UTF-8 or cannot be reconfigured.
    """
    try:
        enc = (getattr(sys.stdout, "encoding", "") or "").lower()
        if enc.replace("-", "") not in ("utf8", "utf8mb4"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def enable_vt() -> None:
    """Windows: enable virtual-terminal processing so escapes render. No-op elsewhere."""
    ensure_utf8_stdout()
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_uint32()
            if k.GetConsoleMode(h, ctypes.byref(mode)):
                # ENABLE_PROCESSED_OUTPUT(1)|WRAP_AT_EOL(2)|VIRTUAL_TERMINAL_PROCESSING(4)
                k.SetConsoleMode(h, mode.value | 0x0001 | 0x0002 | 0x0004)
            else:
                k.SetConsoleMode(h, 7)
        except Exception:
            os.system("")  # fallback: spawning a shell flips the flag on Win10+


def rgb(r, g, b, bg: bool = False) -> str:
    """Truecolor SGR. Foreground by default, background when ``bg=True``."""
    return "\x1b[%d;2;%d;%d;%dm" % (48 if bg else 38, int(r), int(g), int(b))


def is_tty(stream=None) -> bool:
    """True when *stream* (default stdout) is an interactive terminal and NO_COLOR is unset."""
    stream = stream or sys.stdout
    try:
        tty = stream.isatty()
    except Exception:
        tty = False
    return bool(tty)


def term_size(default=(80, 40)):
    """(columns, lines). Falls back to *default* when there is no TTY to query."""
    s = shutil.get_terminal_size(default)
    cols = s.columns if s.columns > 0 else default[0]
    lines = s.lines if s.lines > 0 else default[1]
    return cols, lines


def resolve_size(width=None, height=None, pad_h: int = 1):
    """Fill in width/height from the terminal, leaving *pad_h* rows of headroom."""
    tw, th = term_size()
    w = width if width else tw
    h = height if height else max(1, th - pad_h)
    return w, h


# --------------------------------------------------------------------------
# Render drivers
# --------------------------------------------------------------------------
def _bounded(seconds, frames):
    """Normalize stop conditions. Returns (max_seconds, max_frames) with None = unbounded."""
    return seconds, frames


def play(effect, *, fps=30.0, seconds=None, frames=None, ctx_factory=None,
         force_tty=None):
    """Drive an animated *effect* with a flicker-free home+overwrite loop.

    ``effect`` is anything exposing ``render(ctx) -> str`` plus ``setup()``/``teardown()``
    (see :class:`fx.base.Effect`). ``ctx_factory(t, frame_index)`` builds the per-frame
    :class:`fx.base.FrameCtx`; the CLI supplies one bound to width/height/theme/params.

    Bounds: stops when ``t >= seconds`` OR ``frame_index >= frames`` (whichever first);
    if both are None the loop runs until Ctrl-C.

    Anti-flicker: enters the alt screen, clears ONCE, then each frame emits HOME and a
    full buffer so every cell is overwritten in place.

    Safety: the enter sequence is INSIDE the try, so any failure still hits the
    finally block, which ALWAYS restores color, wrap, cursor, and primary screen.

    No-TTY degrade: when stdout is not a terminal (and ``force_tty`` is not True), renders
    a single frame to the normal screen and returns without touching the alt buffer.
    """
    tty = force_tty if force_tty is not None else is_tty()
    if not tty:
        # Non-interactive: one plain frame, no alt-screen, no loop.
        render_once(effect, ctx_factory=ctx_factory)
        return

    enable_vt()
    frame_dt = 1.0 / max(1.0, fps)
    w = sys.stdout.write
    if ctx_factory is None:
        raise ValueError("play() requires ctx_factory")
    effect.setup()
    try:
        # Inside the try: a failure here still reaches finally-restore, so the
        # terminal never stays stuck in alt-screen / cursor-hidden state.
        w(ALT_ENTER)
        w(HIDE)
        w(NOWRAP)
        w(CLEAR)
        sys.stdout.flush()
        t0 = time.perf_counter()
        frame_index = 0
        while True:
            start = time.perf_counter()
            t = start - t0
            ctx = ctx_factory(t, frame_index)
            w(HOME)
            w(effect.render(ctx))
            sys.stdout.flush()
            frame_index += 1
            if seconds is not None and t >= seconds:
                break
            if frames is not None and frame_index >= frames:
                break
            dt = time.perf_counter() - start
            if dt < frame_dt:
                time.sleep(frame_dt - dt)
    except KeyboardInterrupt:
        pass
    finally:
        w(RESET)
        w(WRAP)
        w(SHOW)
        w(ALT_LEAVE)
        sys.stdout.flush()
        try:
            effect.teardown()
        except Exception:
            pass


def render_once(effect, *, ctx_factory=None, t=0.7, frame_index=0):
    """Render a single frame to the NORMAL screen (no alt buffer, no loop).

    Used for ``--once``, static banners, and the no-TTY fallback. ``ctx_factory`` builds
    the FrameCtx; if omitted, ``effect.default_ctx()`` is used.
    """
    enable_vt()
    effect.setup()
    try:
        ctx = ctx_factory(t, frame_index) if ctx_factory else effect.default_ctx()
        frame = effect.render(ctx)
        sys.stdout.write(frame)
        if not frame.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.write(RESET)
        sys.stdout.flush()
    finally:
        try:
            effect.teardown()
        except Exception:
            pass
