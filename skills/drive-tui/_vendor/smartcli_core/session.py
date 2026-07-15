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

import time
from typing import List, Optional, Tuple, Union, Sequence

from .pty_backend import PtyBackend, get_default_backend
from .readiness import wait_any, wait_for_regex, wait_ready, wait_until_stable
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


# SS3 (application-cursor) forms of the cursor/nav keys. When the target program
# has enabled DECCKM (ESC[?1h) — as most full-screen/curses TUIs do — it expects
# these SS3 sequences (ESC O x), NOT the CSI forms (ESC [ x). Sending CSI to a
# DECCKM app moves nothing (verified on real Linux ncurses). send_keys picks the
# right form from the live screen mode.
KEY_MAP_SS3: dict[str, bytes] = {
    "Up": b"\x1bOA",
    "Down": b"\x1bOB",
    "Right": b"\x1bOC",
    "Left": b"\x1bOD",
    "Home": b"\x1bOH",
    "End": b"\x1bOF",
}


def _resolve_key(token: str, app_cursor: bool = False) -> bytes:
    """Map a single key token to bytes.

    Recognises :data:`KEY_MAP` names, ``C-x`` control combos (Ctrl+letter), and
    ``M-x`` meta/alt combos (ESC prefix). Unknown single characters are sent
    literally.

    ``app_cursor`` — when True (the target program has DECCKM / application
    cursor keys enabled), cursor/navigation keys are emitted in their SS3 form
    (``ESC O x``) instead of CSI (``ESC [ x``); a curses app in that mode only
    recognises SS3 arrows. Non-cursor keys are unaffected.
    """
    if app_cursor and token in KEY_MAP_SS3:
        return KEY_MAP_SS3[token]
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
        """Read whatever is available and feed it into the screen. Returns bytes.

        After feeding, answer any device-status/attribute queries the program
        emitted (DSR-CPR ``ESC[6n``, DA ``ESC[c``): pyte builds the correct reply
        from its own cursor/attr state, and we write it back to the PTY. Without
        this, a program that synchronously waits for a cursor-position report can
        stall or fall back to a degraded mode. Best-effort: a write failure here
        must never break perception.
        """
        data = self.backend.read_nonblocking()
        if data:
            self.model.feed(data)
            reply = self.model.drain_replies()
            if reply:
                try:
                    self.backend.write(reply)
                except Exception:
                    pass
        return data

    def send_text(self, text: str) -> None:
        """Type literal text (no trailing newline added)."""
        self.backend.write(text.encode("utf-8"))

    def send_keys(self, keys: List[str]) -> None:
        """Send a sequence of key tokens (see :data:`KEY_MAP` and ``C-x``/``M-x``).

        Cursor/nav keys adapt to the program's cursor-key mode: if the target has
        enabled DECCKM (``model.app_cursor``), arrows are sent as SS3 (``ESC O A``)
        so curses/full-screen apps actually receive them; otherwise CSI is used.
        """
        app_cursor = self.model.app_cursor
        for token in keys:
            self.backend.write(_resolve_key(token, app_cursor=app_cursor))

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

    def wait_any(
        self,
        patterns: Sequence[str],
        timeout_ms: int = 10000,
        poll_ms: int = 30,
        min_wait_ms: int = 0,
        flags: int = 0,
    ) -> Tuple[int, Snapshot]:
        """Wait for ANY of ``patterns`` (pexpect ``expect([...])`` style).

        Returns ``(index, snapshot)`` where ``index`` is the 0-based position of
        the pattern that matched (earliest in the list wins a same-poll tie), or
        ``-1`` on timeout. The snapshot is always the current screen. See
        :func:`readiness.wait_any`.
        """
        index, snap = wait_any(
            read_fn=self.pump,
            get_text_fn=self.model.text,
            get_snapshot_fn=self.snapshot,
            patterns=patterns,
            timeout_ms=timeout_ms,
            poll_ms=poll_ms,
            min_wait_ms=min_wait_ms,
            flags=flags,
        )
        return index, snap  # type: ignore[return-value]

    def wait_change(
        self,
        baseline_hash: Optional[str] = None,
        timeout_ms: int = 10000,
        poll_ms: int = 30,
    ) -> Tuple[bool, Snapshot]:
        """Wait until the screen content changes away from ``baseline_hash``.

        The precise "did my action land?" primitive: after sending input, block
        until the screen's content hash differs from the baseline (by default,
        the hash at the moment of the call). Returns (changed, snapshot) —
        ``changed`` is False on timeout, and the snapshot is always the latest
        screen so the caller can inspect it either way. Complements wait_stable
        (settle) / wait_for (a specific marker): this catches ANY change, which
        is what you want right after acting, and it can't false-positive on a
        screen that was already showing the target text.

        This is a thin session-level poll over the existing pump + content_hash;
        it adds no new core state.
        """
        if baseline_hash is None:
            # Baseline = the screen as it stands NOW, WITHOUT draining pending
            # bytes first — otherwise the very output we're waiting for could be
            # folded into the baseline and never register as a change.
            baseline_hash = self.model.content_hash()
        deadline = time.monotonic() + timeout_ms / 1000.0
        poll_s = max(0.0, poll_ms / 1000.0)
        while True:
            self.pump()
            if self.model.content_hash() != baseline_hash:
                return True, self.snapshot()
            if time.monotonic() >= deadline:
                return False, self.snapshot()
            time.sleep(poll_s)
