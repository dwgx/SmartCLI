"""Thin wrapper over ``pyte`` that turns a byte stream into an inspectable grid.

:class:`ScreenModel` owns a single long-lived ``pyte.ByteStream`` + ``pyte.Screen``
pair. Feed raw PTY bytes with :meth:`feed`; the stream is stateful and stream-safe
so partial ANSI escapes and split multibyte UTF-8 across reads are handled
correctly. Never recreate the stream per read.

Exposes plain text (``pyte.screen.display``), the cursor, a stability hash, and a
per-cell attribute reader that copes with the sparse dict-of-dicts buffer.
"""

from __future__ import annotations

import zlib
from typing import List, NamedTuple, Tuple

import pyte


def safe_screen_display(screen: "pyte.Screen") -> List[str]:
    """Crash-safe mirror of ``pyte.Screen.display``.

    pyte's own ``display`` renderer calls ``wcwidth(char[0])`` unconditionally,
    which raises ``IndexError`` when a cell's ``data`` is the empty string — a
    state reachable from malformed byte runs (a wide char followed by CR and an
    invalid UTF-8 tail). This mirrors pyte's renderer exactly (including the
    wide-char stub skip) but renders an empty cell as a single blank instead of
    crashing. Byte-identical to ``pyte.Screen.display`` on well-formed screens
    (verified). Shared by :class:`ScreenModel` and the screenshot tooling.
    """
    from wcwidth import wcwidth  # pyte's own width dependency

    def render_row(line) -> str:
        out: List[str] = []
        is_wide = False
        for x in range(screen.columns):
            if is_wide:
                is_wide = False
                continue
            char = line[x].data
            if not char:  # the guard pyte lacks: empty cell -> single blank
                out.append(" ")
                is_wide = False
                continue
            is_wide = wcwidth(char[0]) == 2
            out.append(char)
        return "".join(out)

    return [render_row(screen.buffer[y]) for y in range(screen.lines)]


class CellAttrs(NamedTuple):
    """Reduced view of a single :class:`pyte.screens.Char`."""

    data: str
    fg: str
    bg: str
    bold: bool
    reverse: bool


class ScreenModel:
    """Feed PTY bytes into a ``pyte`` screen and read structured state back out."""

    def __init__(self, cols: int = 80, rows: int = 24) -> None:
        self._cols = cols
        self._rows = rows
        self.screen = pyte.Screen(cols, rows)
        # ByteStream decodes UTF-8 incrementally, so multibyte chars split across
        # feed() boundaries are reassembled correctly.
        self.stream = pyte.ByteStream(self.screen)
        # Count of feed() batches pyte failed to parse (malformed control seqs).
        # Observable so a SYSTEMIC failure (e.g. a regression that makes every
        # feed raise) is not silently indistinguishable from the occasional
        # garbled byte run it is meant to tolerate.
        self.feed_errors = 0

    # -- feeding -----------------------------------------------------------

    def feed(self, data: bytes) -> None:
        """Feed raw bytes from the PTY into the screen. Safe with partial data.

        Hardened against malformed control sequences: some byte sequences make
        ``pyte`` itself raise (e.g. a CSI insert/delete op with an empty leading
        numeric parameter — ``ESC[;@`` — dispatches to ``insert_characters`` with
        the wrong arity → ``TypeError``). pyte already resets its own parser FSM
        before re-raising (streams.py ``_send_to_parser``), so the stream stays
        usable; we swallow the exception here so one hostile/garbled byte run from
        a real program cannot break perception. Bytes up to the offending control
        char are already drawn; the rest of that batch is dropped, and the next
        ``feed`` continues normally. Verified: valid sequences are unaffected.
        """
        if data:
            try:
                self.stream.feed(data)
            except Exception:
                # pyte has already re-initialised its parser (streams.py
                # _send_to_parser), so the stream stays usable; keep going. Bump
                # an observable counter rather than swallowing silently, so a
                # systemic failure is diagnosable instead of a frozen screen.
                self.feed_errors += 1

    def resize(self, cols: int, rows: int) -> None:
        """Resize the underlying screen. Keep this in sync with the PTY winsize."""
        self._cols = cols
        self._rows = rows
        # pyte.Screen.resize takes (lines, columns).
        self.screen.resize(rows, cols)

    # -- geometry ----------------------------------------------------------

    @property
    def cols(self) -> int:
        return self.screen.columns

    @property
    def rows(self) -> int:
        return self.screen.lines

    @property
    def app_cursor(self) -> bool:
        """True when the program has enabled DECCKM (application cursor keys).

        A full-screen / curses program that has called ``keypad(True)`` puts the
        terminal in DECCKM (``ESC[?1h``); pyte records this as private mode 1 in
        ``screen.mode`` (the value ``32``). In that state the app expects SS3
        cursor sequences (``ESC O A``) — sending CSI (``ESC [ A``) moves nothing.
        :meth:`session.PtySession.send_keys` reads this to pick the right form.
        """
        try:
            return 32 in self.screen.mode
        except Exception:
            return False

    # -- plain text --------------------------------------------------------

    @property
    def display(self) -> List[str]:
        """List of rendered lines (wide-char aware, right-padded to ``cols``).

        Fast path is ``pyte.Screen.display``. But pyte's renderer does
        ``wcwidth(char[0])`` unconditionally, which raises ``IndexError`` when a
        cell's ``data`` is the empty string — a state reachable from certain
        malformed byte runs (wide char + CR + invalid UTF-8 tail). One such cell
        would otherwise blind every ``display``/``snapshot``/``to_text`` call
        until it happened to be overwritten. We fall back to a crash-safe
        per-cell render (byte-identical to pyte on well-formed screens; verified)
        that treats an empty cell as a blank.
        """
        try:
            return list(self.screen.display)
        except Exception:
            return safe_screen_display(self.screen)

    def text(self) -> str:
        """The full screen joined with newlines (trailing padding preserved).

        Goes through the hardened :attr:`display` (not ``screen.display``) so a
        malformed empty-data cell can never crash text extraction — which also
        protects ``content_hash`` and the readiness stability loop that build on
        it.
        """
        return "\n".join(self.display)

    # -- cursor ------------------------------------------------------------

    @property
    def cursor(self) -> Tuple[int, int]:
        """Cursor as ``(row, col)``, both 0-based."""
        return (self.screen.cursor.y, self.screen.cursor.x)

    @property
    def cursor_hidden(self) -> bool:
        return bool(self.screen.cursor.hidden)

    @property
    def title(self) -> str:
        return self.screen.title or ""

    @property
    def base_reverse(self) -> bool:
        """Screen-wide reverse baseline (DECSCNM). Highlight is measured vs this."""
        return bool(self.screen.default_char.reverse)

    # -- attributes --------------------------------------------------------

    def cell(self, row: int, col: int) -> CellAttrs:
        """Return attributes for one cell.

        Safe against the sparse buffer: ``screen.buffer`` is a real ``defaultdict``
        (indexing a missing *row* would insert it), so we only index rows within
        range; missing *cells* fall back to the screen default char without
        mutating anything.
        """
        if not (0 <= row < self.screen.lines and 0 <= col < self.screen.columns):
            dc = self.screen.default_char
            return CellAttrs(dc.data, dc.fg, dc.bg, dc.bold, dc.reverse)
        ch = self.screen.buffer[row][col]  # StaticDefaultDict: missing col -> default
        return CellAttrs(ch.data, ch.fg, ch.bg, ch.bold, ch.reverse)

    def row_cells(self, row: int) -> List[CellAttrs]:
        """Return the attribute cells for a whole row, left to right."""
        if not (0 <= row < self.screen.lines):
            return []
        buf = self.screen.buffer[row]
        out = []
        for col in range(self.screen.columns):
            ch = buf[col]
            out.append(CellAttrs(ch.data, ch.fg, ch.bg, ch.bold, ch.reverse))
        return out

    # -- stability ---------------------------------------------------------

    def content_hash(self) -> int:
        """CRC32 of the plain-text display.

        Excludes cursor position and all attributes, so cursor movement and
        attribute-only churn (blink/reverse cycling) do not count as changes for
        stability detection.
        """
        return zlib.crc32(self.text().encode("utf-8", "replace"))
