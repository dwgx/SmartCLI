"""Thin wrapper over ``pyte`` that turns a byte stream into an inspectable grid.

:class:`ScreenModel` owns a single long-lived ``pyte.ByteStream`` + ``pyte.Screen``
pair. Feed raw PTY bytes with :meth:`feed`; the stream is stateful and stream-safe
so partial ANSI escapes and split multibyte UTF-8 across reads are handled
correctly. Never recreate the stream per read.

Exposes plain text (``pyte.screen.display``), the cursor, a stability hash, and a
per-cell attribute reader that copes with the sparse dict-of-dicts buffer.
"""

from __future__ import annotations

import unicodedata
import zlib
from typing import NamedTuple

import pyte
from pyte import modes as mo

from wcwidth import wcwidth as wcwidth_cached  # pyte's own width dependency


class _ByteStream(pyte.ByteStream):
    """``pyte.ByteStream`` that dispatches NEL (``ESC E``) to ``next_line``.

    pyte maps ``ESC E`` to ``linefeed``, which only carriage-returns when LNM is
    set — but NEL is defined to always index AND return to column 0. Plain LF
    shares ``linefeed`` and must keep its column, so the two cannot be fixed in
    one method; the dispatch itself has to differ.
    """

    escape = {**pyte.Stream.escape, "E": "next_line"}


class _Screen(pyte.Screen):
    """``pyte.Screen`` with two real-terminal divergences fixed.

    **1. IL/DL must not move the cursor column.** ``pyte``'s
    ``insert_lines``/``delete_lines`` call ``carriage_return()``, snapping the
    cursor to column 0. Real terminals keep the column: after
    ``ESC[5;8H ESC[1L abc``, both tmux 3.6b and GNU screen render
    ``"       abc"`` (column 8) while pyte rendered ``"abc"`` (column 0).
    Two independent emulators agreeing settles it — ECMA-48 is ambiguous enough
    here that reasoning alone would not have. Found by
    ``tests/_diff_fuzz_tmux.py`` (generative differential fuzz), which is
    exactly the class of bug hand-written cases miss: TUIs that repaint a list
    by inserting a line and then writing at the current column landed their text
    in the wrong column for us, so a recipe reading a "selected" row could read
    the wrong text.

    **2. A zero-width joiner must not truncate the batch.**
    ``pyte.Screen.draw`` walks the batch character by character and, for a
    character that is neither width-1, width-2, nor a true combining mark, does
    ``else: break`` — abandoning **every remaining character in that batch**.
    Two extremely common codepoints land in that hole: VARIATION SELECTOR-16
    (U+FE0F, ``wcwidth`` 0, ``combining`` 0) and ZERO WIDTH JOINER (U+200D).

    So a program printing ``"MENU ♀️ Settings  Quit"`` in one write lost
    everything after the emoji: the agent perceived ``"MENU ♀"`` and would act
    on a menu whose other entries it could not see. Found by
    ``tests/_diff_tmux_pyte.py``, which diffs our grid against a real tmux pane
    — tmux keeps the whole line, so this was a genuine perception gap, not a
    representation difference.

    Fix: intercept those codepoints and append them to the previous cell's
    ``data``, exactly as pyte already does for combining marks, then let pyte
    draw the rest of the batch normally. The cursor does not advance (width 0),
    and a wide character's empty stub slot is stepped over so the mark attaches
    to the glyph itself. Controls (C0/C1, ESC) are never intercepted — the
    stream FSM must still see them.
    """

    # NOT changed: IL/DL when the cursor sits OUTSIDE a DECSTBM scroll region.
    # The generative fuzz flagged it, but the two reference emulators DISAGREE
    # with each other there: for `x ESC[8;9r ESC[2L`, tmux 3.6b performs the
    # insert (x shifts to row 2) while GNU screen discards it entirely. When
    # mature emulators diverge, the sequence is under-specified and there is no
    # ground truth to match — so we keep pyte's behaviour rather than picking a
    # side, and `_diff_fuzz_tmux.py` documents it as a known divergence. Real
    # TUIs do not drive IL from outside their own region.

    def index(self) -> None:
        """IND — line feed, but a cursor OUTSIDE the scroll region must not scroll it.

        pyte's ``index`` compares the cursor against the DECSTBM bottom margin
        and, on a match, scrolls the region. When the cursor is *below* the
        region entirely, that is wrong: the cursor should simply move down (or
        stay on the last row), leaving the region untouched. Measured on tmux
        3.6b: with region 3..6, text written at row 7 that autowraps continues on
        row 8, while pyte wrapped it back inside the region to row 5 — so
        anything a program painted below a scroll region (status bars, prompts
        under a pager) landed on the wrong rows for us. Found by
        ``tests/_diff_fuzz_tmux.py``.
        """
        top, bottom = self.margins or (0, self.lines - 1)
        if self.cursor.y > bottom:
            if self.cursor.y < self.lines - 1:
                self.cursor.y += 1
                self.dirty.add(self.cursor.y)
            return
        super().index()

    def cursor_up(self, count: int | None = None) -> None:
        """CUU — a cursor already OUTSIDE the region is not clamped into it.

        pyte clamps to the DECSTBM top margin unconditionally, so a cursor below
        the region could not move above it. Real terminals only apply the margin
        clamp while the cursor is inside the region (measured on tmux 3.6b:
        region 9..10, cursor at row 2, ``ESC[2A`` reaches row 0; pyte pinned it
        at row 8). Found by ``tests/_diff_fuzz_tmux.py``.
        """
        top, bottom = self.margins or (0, self.lines - 1)
        if not (top <= self.cursor.y <= bottom):
            self.cursor.y = max(self.cursor.y - (count or 1), 0)
            return
        super().cursor_up(count)

    def next_line(self) -> None:
        """NEL (``ESC E``) — index AND carriage return, unconditionally.

        pyte routes ``ESC E`` to ``linefeed``, which only returns to column 0
        when LNM is set; NEL is defined to always do both. So ``ESC[2;5H ESC E``
        left us writing at column 4 where tmux 3.6b writes at column 0. Found by
        ``tests/_diff_fuzz_tmux.py``. (Registered below via the stream's escape
        map so the dispatch actually reaches this method.)
        """
        self.index()
        self.carriage_return()

    def delete_characters(self, count: int | None = None) -> None:
        """DCH — deleting a two-column glyph must remove BOTH of its cells.

        pyte deletes one cell per requested count without regard to width, so
        deleting a wide character left its stub behind as a stray blank and every
        following column shifted by one (measured: ``中x`` + CR + ``ESC[1P``
        gives ``"x"`` on tmux 3.6b, we produced ``" x"``). Found by
        ``tests/_diff_fuzz_tmux.py``.
        """
        line = self.buffer[self.cursor.y]
        x = self.cursor.x
        extra = 0
        if x < self.columns:
            cur = line[x].data
            if cur and (wcwidth_cached(cur[0]) == 2
                        or (len(cur) > 1 and "️" in cur)):
                extra = 1  # its stub travels with it
        super().delete_characters((count or 1) + extra)

    def _shift_lines(self, start: int, bottom: int, count: int, down: bool) -> None:
        """Move whole rows within [start, bottom], filling the vacated ones.

        pyte's own IL walks the range popping source rows after copying them,
        which for ``count > 1`` leaves rows *missing* from its sparse buffer
        rather than present-and-blank. A later DL then renumbered around those
        holes and deleted the wrong row: ``ESC[3L Q ESC[1M`` left ``Q`` on screen
        for us where tmux 3.6b and GNU screen both end up blank. Rebuilding the
        affected span explicitly keeps every row present, so row indices stay
        meaningful. Found by ``tests/_diff_fuzz_tmux.py``.
        """
        span = list(range(start, bottom + 1))
        rows = [self.buffer.get(y) for y in span]
        if down:
            moved = [None] * count + rows[:-count] if count <= len(rows) else [None] * len(rows)
        else:
            moved = rows[count:] + [None] * count if count <= len(rows) else [None] * len(rows)
        for y, row in zip(span, moved):
            if row is None:
                self.buffer.pop(y, None)
                # Touch the row so it exists as a real blank line, not a hole.
                self.buffer[y]  # defaultdict factory materialises it
            else:
                self.buffer[y] = row
        self.dirty.update(span)

    def insert_lines(self, count: int | None = None) -> None:
        top, bottom = self.margins or (0, self.lines - 1)
        if top <= self.cursor.y <= bottom:
            self._shift_lines(self.cursor.y, bottom, min(count or 1,
                                                         bottom - self.cursor.y + 1),
                              down=True)
            return
        col = self.cursor.x
        super().insert_lines(count)
        self.cursor.x = col  # real terminals keep the column; pyte homes it

    def delete_lines(self, count: int | None = None) -> None:
        col = self.cursor.x
        super().delete_lines(count)
        self.cursor.x = col

    def _clear_split_wide(self) -> None:
        """Blank a two-column glyph the cursor is about to half-overwrite.

        Writing into either half of a wide character must destroy the WHOLE
        glyph — a terminal cannot show half of it. Real terminals blank both
        cells: after ``中`` + ``ESC[1D`` + ``X``, tmux 3.6b and GNU screen both
        render ``" X"``. pyte instead left the wide char in place and dropped the
        new character entirely, so we rendered ``"中"`` — the write vanished, and
        an agent reading that row saw stale text with nothing reporting a
        problem. Found by ``tests/_diff_fuzz_tmux.py``.
        """
        line = self.buffer[self.cursor.y]
        x = self.cursor.x
        if x >= self.columns:
            return
        blank = self.cursor.attrs._replace(data=" ")
        # Cursor sits on the stub half: blank the base to our left too.
        if line[x].data == "" and x - 1 >= 0:
            line[x - 1] = blank
            line[x] = blank
            self.dirty.add(self.cursor.y)
            return
        # Cursor sits on the base half of a wide glyph: blank its stub as well.
        cur = line[x].data
        if cur and (wcwidth_cached(cur[0]) == 2 or (len(cur) > 1 and "️" in cur)):
            line[x] = blank
            if x + 1 < self.columns and line[x + 1].data == "":
                line[x + 1] = blank
            self.dirty.add(self.cursor.y)

    def draw(self, data: str) -> None:
        from wcwidth import wcwidth  # pyte's own width dependency

        pending: list[str] = []
        for char in data:
            code = ord(char)
            is_control = code < 0x20 or 0x80 <= code <= 0x9F
            if (not is_control and wcwidth(char) == 0
                    and unicodedata.combining(char) == 0):
                if pending:
                    super().draw("".join(pending))
                    pending = []
                line = self.buffer[self.cursor.y]
                idx = self.cursor.x - 1
                if idx >= 0 and line[idx].data == "":
                    idx -= 1  # step over the stub slot of a wide character
                if idx >= 0:
                    prev = line[idx]
                    line[idx] = prev._replace(data=prev.data + char)
                    self.dirty.add(self.cursor.y)
                    if char == "️" and wcwidth(prev.data[:1]) == 1:
                        # VARIATION SELECTOR-16 requests EMOJI presentation, which
                        # real terminals render two cells wide even when wcwidth
                        # reports 1 for the base character (measured: tmux 3.6b and
                        # GNU screen both advance 2 for U+2640 U+FE0F). Claim the
                        # stub cell and advance so every following column matches
                        # the real terminal — otherwise one emoji shifts the whole
                        # rest of the line by one.
                        if self.cursor.x < self.columns:
                            line[self.cursor.x] = \
                                self.cursor.attrs._replace(data="")
                            self.cursor.x = min(self.cursor.x + 1, self.columns)
                continue
            if pending:
                super().draw("".join(pending))
                pending = []
            # A two-column glyph that cannot fit before the right margin wraps
            # WHOLE to the next line; pyte squeezes it into the last cell.
            # Measured on tmux 3.6b: an emoji written at column 40 of a 40-col
            # screen appears on the next row, not split across the margin.
            if (wcwidth(char) == 2 and self.cursor.x == self.columns - 1
                    and mo.DECAWM in self.mode):
                self.carriage_return()
                self.linefeed()
            # A write that lands on half of a wide glyph must destroy all of it.
            self._clear_split_wide()
            super().draw(char)
        if pending:
            super().draw("".join(pending))


def safe_screen_display(screen: pyte.Screen) -> list[str]:
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
        out: list[str] = []
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
            # Skip the stub slot for anything occupying two columns. pyte checks
            # only ``char[0]``, which misses an emoji-presentation cluster like
            # U+2640 U+FE0F: its base is wcwidth 1, yet real terminals advance
            # two columns (measured on tmux 3.6b and GNU screen), and _Screen.draw
            # reserves the stub accordingly. Without this, the stub renders as an
            # extra blank and every following column is off by one.
            is_wide = wcwidth(char[0]) == 2 or (len(char) > 1 and "️" in char)
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
        self.screen = _Screen(cols, rows)
        # ByteStream decodes UTF-8 incrementally, so multibyte chars split across
        # feed() boundaries are reassembled correctly.
        self.stream = _ByteStream(self.screen)
        # Count of feed() batches pyte failed to parse (malformed control seqs).
        # Observable so a SYSTEMIC failure (e.g. a regression that makes every
        # feed raise) is not silently indistinguishable from the occasional
        # garbled byte run it is meant to tolerate.
        self.feed_errors = 0
        # Device-query replies (DSR-CPR "ESC[6n", DA "ESC[c") that pyte generates
        # while parsing. pyte routes them to Screen.write_process_input, which is a
        # no-op by default — so a program that SYNCHRONOUSLY waits for a cursor-
        # position report can stall/degrade because nothing answers. We capture
        # them here (pyte builds the correct reply from its own cursor/attrs) and
        # PtySession.pump() writes them back to the PTY. See drain_replies().
        self._reply_buf = bytearray()
        self.screen.write_process_input = self._collect_reply

    def _collect_reply(self, data) -> None:
        """pyte hands us the bytes/str it wants sent back to the process."""
        if isinstance(data, str):
            data = data.encode("utf-8", "replace")
        self._reply_buf.extend(data)

    def drain_replies(self) -> bytes:
        """Return and clear any pending device-query replies pyte generated.

        PtySession.pump() calls this after feed() and writes the result back to
        the PTY, so DSR-CPR / DA queries from the driven program get answered.
        """
        if not self._reply_buf:
            return b""
        out = bytes(self._reply_buf)
        self._reply_buf.clear()
        return out

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
        # pyte stores private modes as (mode << 5); DECCKM is private mode 1,
        # so it lands as 1<<5 = 32 in screen.mode (no named constant is exported).
        _DECCKM = 1 << 5
        try:
            return _DECCKM in self.screen.mode
        except Exception:
            return False

    # -- plain text --------------------------------------------------------

    @property
    def display(self) -> list[str]:
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
    def cursor(self) -> tuple[int, int]:
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

    def row_cells(self, row: int) -> list[CellAttrs]:
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

    def visual_hash(self) -> int:
        """CRC32 of visible cells, their attributes, and the cursor state.

        Unlike :meth:`content_hash`, this changes when a TUI moves a selection
        using reverse video/background color or only moves the cursor. It is a
        separate primitive so text-only stability detection keeps ignoring blink
        and cosmetic attribute churn.
        """
        crc = 0
        for row in range(self.screen.lines):
            line = self.screen.buffer[row]
            for col in range(self.screen.columns):
                char = line[col]
                fields = (
                    char.data,
                    char.fg,
                    char.bg,
                    bool(char.bold),
                    bool(char.italics),
                    bool(char.underscore),
                    bool(char.strikethrough),
                    bool(char.reverse),
                    bool(char.blink),
                )
                crc = zlib.crc32(repr(fields).encode("utf-8", "replace"), crc)
        cursor_state = (self.screen.cursor.y, self.screen.cursor.x, self.cursor_hidden)
        return zlib.crc32(repr(cursor_state).encode("ascii"), crc)
