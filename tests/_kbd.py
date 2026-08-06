"""Cross-platform blocking single-character read for the driven test apps.

``tests/_menu_app.py`` and friends are PTY fixtures: the drive probes spawn them
and exercise the recipes against them. Each reads one character at a time and
they ALREADY handle both arrow encodings — the Windows ``\\xe0``/``\\x00`` prefix
and the ANSI ``ESC [ A`` form — so the only thing tying them to Windows was
``import msvcrt``. On macOS and Linux that import raises ``ModuleNotFoundError``
before the app draws anything, the probe sees a traceback instead of a menu, and
``tests/run_all.py`` reports four failures that have nothing to do with the code
under test.

That noise floor is the real cost: it made a POSIX run of the suite permanently
red, so a genuine regression in those probes could not be distinguished from the
platform gap.

The Windows path is byte-for-byte the old behaviour. The POSIX path puts the tty
into raw mode ONCE and restores it at exit, rather than per keystroke: toggling
around each read would drop the second and third bytes of an ``ESC [ A``
sequence, which is exactly what these fixtures need to receive intact.
"""
from __future__ import annotations

import sys

if sys.platform == "win32":  # pragma: no cover - platform-specific
    import msvcrt

    def getwch() -> str:
        """Read one character, blocking. Windows: unchanged from msvcrt."""
        return msvcrt.getwch()

else:
    import atexit
    import termios
    import tty

    _saved: list | None = None

    def _ensure_raw() -> None:
        """Put the tty into raw mode once, and schedule its restoration.

        Raw mode is what makes a single-byte read return immediately instead of
        waiting for a newline. Doing it once (rather than around every read)
        keeps multi-byte escape sequences together.
        """
        global _saved
        if _saved is not None:
            return
        fd = sys.stdin.fileno()
        try:
            _saved = termios.tcgetattr(fd)
        except (termios.error, ValueError, OSError):
            # Not a tty (stdin redirected). Leave it alone; the read below still
            # works line-wise, which is enough for a non-interactive caller.
            _saved = []
            return
        tty.setraw(fd)
        atexit.register(_restore)

    def _restore() -> None:
        if _saved:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _saved)
            except (termios.error, ValueError, OSError):
                pass

    def getwch() -> str:
        """Read one character, blocking. Returns ``""`` at EOF."""
        _ensure_raw()
        return sys.stdin.read(1)
