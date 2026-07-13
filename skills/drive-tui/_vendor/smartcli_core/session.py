"""High-level interactive PTY session -- the entry point the skills call.

:class:`PtySession` wires together a pluggable :class:`PtyBackend`, a
:class:`ScreenModel` (pyte), the semantic :func:`build_snapshot`, and the
:mod:`readiness` waits. Typical use::

    sess = PtySession(cols=100, rows=30)
    sess.start("python")
    # Use an unanchored marker: pyte space-pads every line, so r">>> $" never
    # matches (use r">>> " or r">>> *$" with re.M).
    sess.wait_ready(marker=r">>> ")
    sess.send_text("print('hi')")
    sess.send_keys(["Enter"])
    snap = sess.wait_ready(marker=r">>> ")[1]
    print(snap.to_text())
    sess.close()

Key tokens (``send_keys``) are mapped to escape bytes via :data:`KEY_MAP`.
"""

from __future__ import annotations

from typing import List, Optional, Tuple, Union, Sequence

from .pty_backend import PtyBackend, get_default_backend
from .readiness import wait_for_regex, wait_ready, wait_until_stable
from .screen_model import ScreenModel
from .snapshot import Snapshot, build_snapshot

# Named key tokens -> the raw bytes to write to the PTY.
# Control keys use their ASCII control code; navigation keys use the common
# xterm/VT100 escape sequences that virtually every TUI understands.
KEY_MAP: dict[str, bytes] = {
    # Whitespace / editing
    "Enter": b"\r",
    "Return": b"\r",
    "Tab": b"\t",
    "BackTab": b"\x1b[Z",
    "Space": b" ",
    "Backspace": b"\x7f",
    "Delete": b"\x1b[3~",
    "Escape": b"\x1b",
    "Esc": b"\x1b",
    # Arrows
    "Up": b"\x1b[A",
    "Down": b"\x1b[B",
    "Right": b"\x1b[C",
    "Left": b"\x1b[D",
    # Navigation
    "Home": b"\x1b[H",
    "End": b"\x1b[F",
    "PageUp": b"\x1b[5~",
    "PageDown": b"\x1b[6~",
    "Insert": b"\x1b[2~",
    # Function keys
    "F1": b"\x1bOP",
    "F2": b"\x1bOQ",
    "F3": b"\x1bOR",
    "F4": b"\x1bOS",
    "F5": b"\x1b[15~",
    "F6": b"\x1b[17~",
    "F7": b"\x1b[18~",
    "F8": b"\x1b[19~",
    "F9": b"\x1b[20~",
    "F10": b"\x1b[21~",
    "F11": b"\x1b[23~",
    "F12": b"\x1b[24~",
}


def _resolve_key(token: str) -> bytes:
    """Map a single key token to bytes.

    Recognises :data:`KEY_MAP` names, ``C-x`` control combos (Ctrl+letter), and
    ``M-x`` meta/alt combos (ESC prefix). Unknown single characters are sent
    literally.
    """
    if token in KEY_MAP:
        return KEY_MAP[token]

    # Ctrl combos: "C-c", "C-x", "^C"
    if (token.startswith("C-") or token.startswith("^")) and len(token) >= 2:
        letter = token[2:] if token.startswith("C-") else token[1:]
        if len(letter) == 1:
            c = letter.upper()
            if "A" <= c <= "Z":
                return bytes([ord(c) - 64])  # Ctrl-A == 0x01
            if c == "@" or c == " ":
                return b"\x00"
            if c == "[":
                return b"\x1b"
            if c == "\\":
                return b"\x1c"
            if c == "]":
                return b"\x1d"

    # Meta/Alt combos: "M-x" -> ESC + x
    if token.startswith("M-") and len(token) == 3:
        return b"\x1b" + token[2].encode("utf-8")

    # Fallback: send the literal token text.
    return token.encode("utf-8")


class PtySession:
    """A running interactive program behind a PTY, with a semantic screen view."""

    def __init__(
        self,
        cols: int = 80,
        rows: int = 24,
        backend: Optional[PtyBackend] = None,
    ) -> None:
        self.cols = cols
        self.rows = rows
        self.backend: PtyBackend = backend or get_default_backend()
        self.model = ScreenModel(cols, rows)
        # Baseline hash of the freshly-constructed (all-blank) screen. Passed to
        # the readiness waits so they never declare STABLE on a never-painted
        # screen during a startup quiet-gap. Recomputed on resize.
        self._blank_hash = self.model.content_hash()
        self._started = False

    # -- lifecycle ---------------------------------------------------------

    def start(self, cmd: Union[str, Sequence[str]]) -> None:
        """Spawn ``cmd`` in the PTY. The pyte screen matches the PTY winsize."""
        self.backend.spawn(cmd, self.cols, self.rows)
        self._started = True

    def close(self) -> None:
        """Terminate the child and release resources. Idempotent."""
        self.backend.terminate()
        self._started = False

    def __enter__(self) -> "PtySession":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def is_alive(self) -> bool:
        return self.backend.is_alive()

    def resize(self, cols: int, rows: int) -> None:
        """Resize both the PTY and the pyte screen together (keep them in sync)."""
        self.cols = cols
        self.rows = rows
        self.backend.resize(cols, rows)
        self.model.resize(cols, rows)
        # Blank baseline for the new dimensions (only used by the readiness gate
        # before any output has been seen).
        self._blank_hash = ScreenModel(cols, rows).content_hash()

    # -- io ----------------------------------------------------------------

    def pump(self) -> bytes:
        """Read whatever is available and feed it into the screen. Returns bytes."""
        data = self.backend.read_nonblocking()
        if data:
            self.model.feed(data)
        return data

    def send_text(self, text: str) -> None:
        """Type literal text (no trailing newline added)."""
        self.backend.write(text.encode("utf-8"))

    def send_keys(self, keys: List[str]) -> None:
        """Send a sequence of key tokens (see :data:`KEY_MAP` and ``C-x``/``M-x``)."""
        for token in keys:
            self.backend.write(_resolve_key(token))

    def send_line(self, text: str) -> None:
        """Type ``text`` followed by Enter."""
        self.send_text(text)
        self.backend.write(KEY_MAP["Enter"])

    # -- snapshot ----------------------------------------------------------

    def snapshot(self) -> Snapshot:
        """Build a semantic :class:`Snapshot` of the current screen."""
        return build_snapshot(self.model)

    # -- readiness ---------------------------------------------------------

    def wait_ready(
        self,
        marker: Optional[str] = None,
        quiet_ms: int = 200,
        poll_ms: int = 30,
        max_wait_ms: int = 10000,
        min_wait_ms: int = 50,
        grace_ms: int = 40,
        flags: int = 0,
    ) -> Tuple[str, Snapshot]:
        """Wait for ``marker`` OR screen stability. See :func:`readiness.wait_ready`.

        Returns ``(reason, snapshot)`` with reason in ``MARKER``/``STABLE``/``TIMEOUT``.
        """
        reason, snap = wait_ready(
            read_fn=self.pump,
            get_screen_hash_fn=self.model.content_hash,
            get_text_fn=self.model.text,
            get_snapshot_fn=self.snapshot,
            marker=marker,
            quiet_ms=quiet_ms,
            poll_ms=poll_ms,
            max_wait_ms=max_wait_ms,
            min_wait_ms=min_wait_ms,
            grace_ms=grace_ms,
            flags=flags,
            blank_hash=self._blank_hash,
        )
        return reason, snap  # type: ignore[return-value]

    def wait_stable(
        self,
        quiet_ms: int = 200,
        poll_ms: int = 30,
        max_wait_ms: int = 8000,
        grace_ms: int = 40,
        min_wait_ms: int = 0,
    ) -> bool:
        """Wait until the screen settles. See :func:`readiness.wait_until_stable`."""
        return wait_until_stable(
            read_fn=self.pump,
            get_screen_hash_fn=self.model.content_hash,
            quiet_ms=quiet_ms,
            poll_ms=poll_ms,
            max_wait_ms=max_wait_ms,
            grace_ms=grace_ms,
            min_wait_ms=min_wait_ms,
            blank_hash=self._blank_hash,
        )

    def wait_for(
        self,
        pattern: str,
        timeout_ms: int = 10000,
        poll_ms: int = 30,
        min_wait_ms: int = 0,
        flags: int = 0,
    ) -> Tuple[bool, Snapshot]:
        """Wait for ``pattern`` on the screen. See :func:`readiness.wait_for_regex`."""
        matched, snap = wait_for_regex(
            read_fn=self.pump,
            get_text_fn=self.model.text,
            get_snapshot_fn=self.snapshot,
            pattern=pattern,
            timeout_ms=timeout_ms,
            poll_ms=poll_ms,
            min_wait_ms=min_wait_ms,
            flags=flags,
        )
        return matched, snap  # type: ignore[return-value]
