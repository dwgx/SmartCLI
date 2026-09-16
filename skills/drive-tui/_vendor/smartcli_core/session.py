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
from collections.abc import Callable, Sequence

from .pty_backend import PtyBackend, ReadBudgetUnsupported, get_default_backend, supports_read_budget
from .readiness import PollHook, wait_any, wait_for_regex, wait_ready, wait_until_stable
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
        backend: PtyBackend | None = None,
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
        # -- io accounting (A04-S1) -----------------------------------------
        # Both watermarks count BYTES DELIVERED TO THIS SESSION within one spawn
        # generation (0 <= fed_offset <= read_offset). They are not batch counts,
        # not screen revisions, and on Windows not the child's raw stdout: the
        # representation field says which byte domain applies.
        self._io_generation = 0
        self._read_offset = 0
        self._fed_offset = 0
        self._last_cut: str = "unknown"     # drained | budget_limited | unknown | error
        self._stream_error: str | None = None
        self._pending_reply_bytes = 0
        self._reply_error: str | None = None
        # S6: the device-reply ledger. ``_reply_owed`` is the payload the
        # transport has NOT accepted, in wire order, and it is the ONLY thing a
        # later turn may re-send. ``_reply_unknown`` counts bytes whose fate the
        # transport could not report: they stay visible as owed but must never
        # go out again (a re-send could duplicate a prefix that did land).
        # ``_pending_reply_bytes`` is their sum -- the ``reply_bytes`` field.
        self._reply_owed = b""
        self._reply_unknown = 0
        self._reply_retry_spent = 0
        # Close protocol (A04-S4): requested -> closing -> confirmed | unconfirmed.
        self._close_requested = False
        self._closing = False
        self._close_confirmed = False
        self._close_unconfirmed = False
        #: A04-S3: when set, this session's OWN waits read through the budgeted
        #: path instead of draining everything each poll. ``None`` (default) keeps
        #: the previous behaviour for every existing caller; the daemon sets a
        #: production value.
        self.io_turn_bytes: int | None = None
        #: S6: byte budget for RESUMING a device reply the transport would not
        #: accept, spent across the turns of one spawn generation. ``None`` or 0
        #: (the default) keeps the pre-S6 behaviour -- one write attempt per
        #: observation, the remainder reported and left unwritten -- so no
        #: existing caller changes meaning. The daemon sets it from
        #: ``SMARTCLI_REPLY_RETRY_BYTES``.
        self.reply_retry_bytes: int | None = None

    def _read_for_wait(self) -> bytes:
        """The read call this session's waits use (budgeted when configured)."""
        if self.io_turn_bytes is None:
            return self.pump()
        return self.pump(max_bytes=self.io_turn_bytes)

    # -- lifecycle ---------------------------------------------------------

    def start(self, cmd: str | Sequence[str]) -> None:
        """Spawn ``cmd`` in the PTY. The pyte screen matches the PTY winsize."""
        self.backend.spawn(cmd, self.cols, self.rows)
        self._started = True
        # A new child is a new byte domain: watermarks restart, so a stale
        # offset from the previous child can never be read as progress here.
        # The backend's own generation is reused when it publishes one, so a
        # receipt can correlate session watermarks with a transport generation.
        backend_gen = getattr(self.backend, "_generation", None)
        self._io_generation = (backend_gen if isinstance(backend_gen, int)
                               else self._io_generation + 1)
        self._read_offset = 0
        self._fed_offset = 0
        self._last_cut = "unknown"
        self._stream_error = None
        self._pending_reply_bytes = 0
        self._reply_error = None
        self._reply_owed = b""
        self._reply_unknown = 0
        self._reply_retry_spent = 0
        self._close_requested = False
        self._closing = False
        self._close_confirmed = False
        self._close_unconfirmed = False

    def close(self) -> dict:
        """Terminate the child, then report what could actually be CONFIRMED.

        A04-S4: "the native close call returned" is not "the child is gone" -- on
        Windows ConPTY may still be producing output while the pseudoconsole
        closes, and Microsoft documents that the native call's return behaviour
        changed around build 26100. So this returns the backend's close state
        instead of a bare None: ``close_unconfirmed`` with the last progress is a
        real answer, and it is the only honest one when the child cannot be
        observed to be gone. Idempotent.
        """
        self._close_requested = True
        self._closing = True
        self.backend.terminate()
        self._started = False
        self._closing = False
        state = self.close_state()
        self._close_confirmed = bool(state.get("closed_confirmed"))
        self._close_unconfirmed = bool(state.get("close_unconfirmed"))
        return state

    def close_state(self) -> dict:
        """The close protocol as observed, with the runtime's own evidence."""
        fn = getattr(self.backend, "close_state", None)
        state = {}
        if fn is not None:
            try:
                state = dict(fn())
            except Exception as exc:
                state = {"close_unconfirmed": True,
                         "last_progress": f"close_state raised {type(exc).__name__}: {exc}"}
        state.setdefault("close_requested", self._close_requested)
        state.setdefault("closing", self._closing)
        state.setdefault("closed_confirmed", self._close_confirmed)
        state.setdefault("close_unconfirmed", self._close_unconfirmed)
        state.setdefault("output_eof", False)
        state.setdefault("last_progress", None)
        state.setdefault("generation", self._io_generation)
        state["basis_origin"] = "runtime"
        return state

    def __enter__(self) -> PtySession:
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

    def pump(self, max_bytes: int | None = None) -> bytes:
        """Read available output and feed it into the screen. Returns bytes.

        After feeding, answer any device-status/attribute queries the program
        emitted (DSR-CPR ``ESC[6n``, DA ``ESC[c``): pyte builds the correct reply
        from its own cursor/attr state, and we write it back to the PTY. Without
        this, a program that synchronously waits for a cursor-position report can
        stall or fall back to a degraded mode. Best-effort: a write failure here
        must never break perception.

        ``max_bytes`` is the A04-S1 budget: when given, at most that many bytes
        are read in this call and the cut is recorded in :meth:`io_state`. The
        default (``None``) is byte-for-byte the previous behaviour, so every
        existing caller is unaffected. A backend that does not declare
        ``READ_BUDGET_CAPABLE`` raises :class:`ReadBudgetUnsupported` BEFORE any
        read -- read-everything-then-slice would break the very bound the budget
        exists to enforce.

        S6: what this call cannot deliver is not dropped. The unwritten suffix
        stays on the reply ledger and :meth:`retry_pending_reply` resumes it on a
        later turn; the read path above is unchanged.
        """
        if max_bytes is None:
            data = self.backend.read_nonblocking()
            self._last_cut = "drained" if not data else "unknown"
        else:
            if not supports_read_budget(self.backend):
                raise ReadBudgetUnsupported(
                    f"{type(self.backend).__name__} does not implement the budgeted-read "
                    "capability (READ_BUDGET_CAPABLE); refusing to read unbounded and slice")
            data = self.backend._read_budgeted(max_bytes)
            self._last_cut = self._cut_after_budgeted_read(data, max_bytes)
        if data:
            self._read_offset += len(data)
            try:
                self.model.feed(data)
            except Exception as exc:  # a parser failure must not look like an empty read
                self._stream_error = f"{type(exc).__name__}: {exc}"
                self._last_cut = "error"
                raise
            self._fed_offset += len(data)
            reply = self.model.drain_replies()
            if reply:
                # S6: a reply is still written once per observation, but it is
                # written from the LEDGER rather than thrown away on failure. Any
                # suffix a previous turn could not deliver therefore goes out
                # ahead of this one -- the child's order -- and only bytes the
                # transport reported as NOT accepted are ever re-sent. The first
                # attempt is deliberately unbudgeted: that is exactly the write
                # this path made before, and budgeting it would change reachable
                # behaviour for every existing caller.
                self._reply_owed += reply
                self._attempt_reply_write(None)
        return data

    def _attempt_reply_write(self, limit: int | None) -> int:
        """Write at most ``limit`` bytes (``None`` = all) of the owed reply, once.

        Returns the number of bytes ATTEMPTED, which is what a retry budget is
        spent on: a transport that accepts nothing must not be retried forever on
        a budget stated in bytes, so the attempt -- not the landing -- is charged.

        The unwritten remainder is re-derived from the transport's own receipt
        (:attr:`IncompleteWrite.written_bytes`) instead of being guessed, and when
        the transport cannot report progress at all the payload moves to the
        un-retryable side of the ledger: `written_bytes is None` means bytes may
        already be on the wire, and re-sending them would duplicate input the
        child has already acted on.
        """
        owed = self._reply_owed
        payload = owed if limit is None else owed[:limit]
        if not payload:
            return 0
        try:
            self.backend.write(payload)
        except Exception as exc:
            written = getattr(exc, "written_bytes", None)
            if written is None:
                # The payload was ATTEMPTED and its landing point is unknown: it
                # leaves the resumable ledger (re-sending it could duplicate a
                # prefix the child already acted on) and stays counted as owed.
                self._reply_unknown += len(payload)
                self._reply_owed = owed[len(payload):]
            else:
                landed = min(max(int(written), 0), len(payload))
                self._reply_owed = owed[landed:]
            self._reply_error = f"{type(exc).__name__}: {exc}"
        else:
            self._reply_owed = owed[len(payload):]
            if not self._reply_owed and not self._reply_unknown:
                self._reply_error = None
        self._pending_reply_bytes = len(self._reply_owed) + self._reply_unknown
        return len(payload)

    def retry_pending_reply(self) -> dict:
        """Resume a device reply the transport would not take, on a LATER turn (S6).

        A child that is synchronously waiting for its device answer stays blocked
        until the answer arrives, so an unwritten reply is not a reporting detail:
        it is a stuck program. This is the call that gives that reply progress,
        and it exists as its own entry point so the retry lands on a *later* turn
        -- the daemon calls it from the same bounded I/O turn that services the
        transport -- instead of looping inside the observation that failed.

        Bounded by :attr:`reply_retry_bytes` per spawn generation and a no-op when
        that budget is unset or spent; a no-op also when nothing is owed, which is
        the case on every turn of a healthy session.
        """
        budget = self.reply_retry_bytes
        if not isinstance(budget, int) or budget <= 0:
            # No budget declared (or a zero one): the pre-S6 behaviour, and the
            # default for every caller that is not the daemon.
            return {"attempted": 0, "owed": self._pending_reply_bytes,
                    "budget_left": 0, "reason": self._reply_error}
        left = budget - self._reply_retry_spent
        owed = self._reply_owed
        if left <= 0 or not owed:
            return {"attempted": 0, "owed": self._pending_reply_bytes,
                    "budget_left": max(left, 0), "reason": self._reply_error}
        attempted = self._attempt_reply_write(min(len(owed), left))
        self._reply_retry_spent += attempted
        return {"attempted": attempted, "owed": self._pending_reply_bytes,
                "budget_left": budget - self._reply_retry_spent,
                "reason": self._reply_error}

    def io_block(self) -> dict:
        """The inner ``io`` dict -- what readiness gates and the daemon expect.

        ``io_state()`` wraps it with the field name for whole-response reads;
        waits want the block itself as their ``io_fn`` result.
        """
        return self.io_state()["io"]

    def _cut_after_budgeted_read(self, data: bytes, max_bytes: int) -> str:
        """Classify a budgeted read without inventing knowledge we do not have.

        A turn that consumed exactly its budget is ``budget_limited`` even when
        the next check would find nothing: only a real, separate emptiness check
        may say ``drained``. Anything the transport cannot answer stays
        ``unknown`` rather than being rounded to "quiet".
        """
        if self._stream_error:
            return "error"
        if len(data) >= max_bytes:
            return "budget_limited"
        status_fn = getattr(self.backend, "read_status", None)
        if status_fn is None:
            return "unknown"
        try:
            status = status_fn()
        except Exception:
            return "unknown"
        if status.get("eof"):
            return "drained"
        readable = status.get("readable_now")
        if readable is True:
            return "budget_limited"
        if readable is False:
            return "drained"
        return "unknown"

    def io_state(self) -> dict:
        """The additive ``io`` block for observations/CLI/MCP (A04-S1).

        Unknown values are ``None``/``null``, never ``0``: a caller must not be
        able to merge "nothing pending" with "I cannot tell". ``read_offset`` and
        ``fed_offset`` live in the delivered-byte domain of one generation; the
        representation says which transport produced those bytes.
        """
        status: dict = {}
        status_fn = getattr(self.backend, "read_status", None)
        if status_fn is not None:
            try:
                status = status_fn() or {}
            except Exception as exc:
                status = {"error": f"{type(exc).__name__}: {exc}"}
        representation = ("posix_pty_stream" if type(self.backend).__name__ == "PosixPtyBackend"
                          else "conpty_reconstructed_utf8")
        known = status.get("queued_payload_bytes")
        held = status.get("reader_held_payload_bytes")
        if known is not None and held is not None:
            known = int(known) + int(held)
        return {
            "io": {
                "generation": self._io_generation,
                "read_offset": self._read_offset,
                "fed_offset": self._fed_offset,
                "pending": {
                    "known_payload_bytes": known,
                    "readable_now": status.get("readable_now"),
                    "parser_incomplete": self._parser_incomplete(),
                    "reply_bytes": self._pending_reply_bytes,
                    "reply_error": self._reply_error,
                    "upstream": "unknown" if representation == "conpty_reconstructed_utf8" else None,
                },
                "local_cut": self._last_cut,
                "representation": representation,
                "stream_error": self._stream_error or status.get("error"),
                "basis_origin": "runtime",
                "close": {
                    "close_requested": self._close_requested,
                    "closing": self._closing,
                    "closed_confirmed": self._close_confirmed,
                    "close_unconfirmed": self._close_unconfirmed,
                },
            }
        }

    def _parser_incomplete(self) -> bool | None:
        """Is the byte-to-text path holding an unfinished sequence?

        Delegates to :meth:`ScreenModel.stream_incomplete`, which covers BOTH the
        streaming SGR filter (a partially received CSI) and pyte's incremental
        UTF-8 decoder (a split multi-byte character). ``None`` means the runtime
        cannot tell -- it must never be reported as a confident ``False``.
        """
        fn = getattr(self.model, "stream_incomplete", None)
        if fn is None:
            return None
        try:
            return fn()
        except Exception:
            return None

    def send_text(self, text: str) -> None:
        """Type literal text (no trailing newline added)."""
        self.backend.write(text.encode("utf-8"))

    def send_keys(self, keys: list[str]) -> None:
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
        marker: str | None = None,
        quiet_ms: int = 200,
        poll_ms: int = 30,
        max_wait_ms: int = 10000,
        min_wait_ms: int = 50,
        grace_ms: int = 40,
        flags: int = 0,
        on_poll: PollHook = None,
    ) -> tuple[str, Snapshot]:
        """Wait for ``marker`` OR screen stability. See :func:`readiness.wait_ready`.

        Returns ``(reason, snapshot)`` with reason in ``MARKER``/``STABLE``/``TIMEOUT``.
        """
        reason, snap = wait_ready(
            read_fn=self._read_for_wait,
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
            on_poll=on_poll,
        )
        return reason, snap  # type: ignore[return-value]

    def wait_stable(
        self,
        quiet_ms: int = 200,
        poll_ms: int = 30,
        max_wait_ms: int = 8000,
        grace_ms: int = 40,
        min_wait_ms: int = 0,
        on_poll: PollHook = None,
    ) -> bool:
        """Wait until the screen settles. See :func:`readiness.wait_until_stable`."""
        return wait_until_stable(
            read_fn=self._read_for_wait,
            get_screen_hash_fn=self.model.content_hash,
            quiet_ms=quiet_ms,
            poll_ms=poll_ms,
            max_wait_ms=max_wait_ms,
            grace_ms=grace_ms,
            min_wait_ms=min_wait_ms,
            blank_hash=self._blank_hash,
            on_poll=on_poll,
        )

    def wait_for(
        self,
        pattern: str,
        timeout_ms: int = 10000,
        poll_ms: int = 30,
        min_wait_ms: int = 0,
        flags: int = 0,
        on_poll: PollHook = None,
    ) -> tuple[bool, Snapshot]:
        """Wait for ``pattern`` on the screen. See :func:`readiness.wait_for_regex`."""
        matched, snap = wait_for_regex(
            read_fn=self._read_for_wait,
            get_text_fn=self.model.text,
            get_snapshot_fn=self.snapshot,
            pattern=pattern,
            timeout_ms=timeout_ms,
            poll_ms=poll_ms,
            min_wait_ms=min_wait_ms,
            flags=flags,
            on_poll=on_poll,
        )
        return matched, snap  # type: ignore[return-value]

    def wait_any(
        self,
        patterns: Sequence[str],
        timeout_ms: int = 10000,
        poll_ms: int = 30,
        min_wait_ms: int = 0,
        flags: int = 0,
        on_poll: PollHook = None,
    ) -> tuple[int, Snapshot]:
        """Wait for ANY of ``patterns`` (pexpect ``expect([...])`` style).

        Returns ``(index, snapshot)`` where ``index`` is the 0-based position of
        the pattern that matched (earliest in the list wins a same-poll tie), or
        ``-1`` on timeout. The snapshot is always the current screen. See
        :func:`readiness.wait_any`.
        """
        index, snap = wait_any(
            read_fn=self._read_for_wait,
            get_text_fn=self.model.text,
            get_snapshot_fn=self.snapshot,
            patterns=patterns,
            timeout_ms=timeout_ms,
            poll_ms=poll_ms,
            min_wait_ms=min_wait_ms,
            flags=flags,
            on_poll=on_poll,
        )
        return index, snap  # type: ignore[return-value]

    def wait_change(
        self,
        baseline_hash: int | None = None,
        timeout_ms: int = 10000,
        poll_ms: int = 30,
        on_poll: PollHook = None,
    ) -> tuple[bool, Snapshot]:
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
        return self._wait_hash_change(
            self.model.content_hash,
            baseline_hash=baseline_hash,
            timeout_ms=timeout_ms,
            poll_ms=poll_ms,
            on_poll=on_poll,
        )

    def wait_visual_change(
        self,
        baseline_hash: int | None = None,
        timeout_ms: int = 10000,
        poll_ms: int = 30,
        on_poll: PollHook = None,
    ) -> tuple[bool, Snapshot]:
        """Wait for text, styling, selection, or cursor state to change.

        Use this after navigation keys in TUIs whose selected row changes only by
        reverse video/background attributes or cursor movement. Text-only
        :meth:`wait_change` remains preferable for output streams because it
        intentionally ignores cosmetic attribute churn.
        """
        return self._wait_hash_change(
            self.model.visual_hash,
            baseline_hash=baseline_hash,
            timeout_ms=timeout_ms,
            poll_ms=poll_ms,
            on_poll=on_poll,
        )

    def _wait_hash_change(
        self,
        hash_fn: Callable[[], int],
        baseline_hash: int | None,
        timeout_ms: int,
        poll_ms: int,
        on_poll: PollHook = None,
    ) -> tuple[bool, Snapshot]:
        if baseline_hash is None:
            # Baseline = the screen as it stands NOW, WITHOUT draining pending
            # bytes first — otherwise the very output we're waiting for could be
            # folded into the baseline and never register as a change.
            baseline_hash = hash_fn()
        deadline = time.monotonic() + timeout_ms / 1000.0
        poll_s = max(0.0, poll_ms / 1000.0)
        while True:
            self._read_for_wait()
            if hash_fn() != baseline_hash:
                return True, self.snapshot()
            if time.monotonic() >= deadline:
                return False, self.snapshot()
            if on_poll is not None:
                on_poll()          # the daemon's poll gap: fast verbs + one I/O turn
            time.sleep(poll_s)
