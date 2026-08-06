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
from pyte.screens import Char

from wcwidth import wcwidth as wcwidth_cached  # pyte's own width dependency


def _pyte_dch_handles_wide() -> bool:
    """Does the installed ``pyte`` already widen DCH over a two-column glyph?

    Unlike the alternate screen there is no attribute to test for, so this asks
    the question behaviourally, once, on a throwaway 4x1 screen: delete the wide
    glyph in ``中x`` and see whether ``x`` ends up at column 0 (the stub travelled
    with its base) or vanishes.

    It exists because ``_Screen.delete_characters`` widens the count itself, and
    doing that on top of a pyte that already does it deletes one cell too many —
    silently eating a character. With ``pyte>=0.8.1`` unpinned, that would arrive
    as a dependency upgrade, not a code change. Measured against a pyte carrying
    the fix: the override turned ``"x"`` into ``""``.
    """
    try:
        probe = pyte.Screen(4, 1)
        pyte.ByteStream(probe).feed("\u4e2dx".encode() + b"\r\x1b[1P")
        return probe.buffer[0][0].data == "x"
    except Exception:
        # Never let a probe break import; the override is correct for every
        # released pyte, so assume the historical behaviour on doubt.
        return False


#: Evaluated once at import: see _pyte_dch_handles_wide.
_PYTE_DCH_HANDLES_WIDE: bool = _pyte_dch_handles_wide()


class _ByteStream(pyte.ByteStream):
    """``pyte.ByteStream`` with NEL dispatch and SGR sub-parameter tolerance."""

    escape = {**pyte.Stream.escape, "E": "next_line"}

    # SGR sub-parameters use ':' as the separator (ITU-T T.416): `ESC[4:3m` is a
    # curly underline, `ESC[38:2::R:G:Bm` a truecolor foreground. pyte's parser
    # does not know ':' at all, so it aborted the sequence and DREW THE REST AS
    # TEXT — `ESC[4:3mU` put the literal "3mU" on screen. Modern programs emit
    # this routinely (Neovim, kitty, delta), so an agent driving them read
    # escape-sequence debris as content. Measured against tmux 3.6b, which
    # renders just the styled character.
    #
    # We normalise ':' to ';' before the parser sees it, which keeps the sequence
    # a valid SGR of the same intent: the attribute may degrade (a curly
    # underline becomes a plain one) but no debris reaches the grid and the
    # cursor advances correctly. Only CSI ... m is rewritten, so nothing else
    # that could legitimately contain ':' (OSC strings, DCS payloads) is touched.
    _SGR_COLON = __import__("re").compile(rb"\x1b\[([\d;:]*:[\d;:]*)m")

    def feed(self, data: bytes) -> None:
        if b":" in data:
            data = self._SGR_COLON.sub(
                lambda m: b"\x1b[" + m.group(1).replace(b":", b";") + b"m", data)
        super().feed(data)


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

    # xterm private modes that switch to the ALTERNATE screen buffer. pyte
    # implements none of them, so `ESC[?1049h` merely set an unknown mode bit and
    # a full-screen program (vim, less, htop — every TUI drive-tui exists to
    # drive) painted its alternate screen ON TOP of the main one. On exit the
    # main screen was never restored, so an agent read a merged, impossible
    # screen. Measured against tmux 3.6b, which follows xterm: 1049 saves the
    # cursor and clears the alternate buffer on entry and restores both on exit;
    # 1047/47 switch buffers without the cursor save.
    _ALT_MODES = (1049, 1047, 47)

    #: Private mode 1048 — save/restore the cursor as DECSC/DECRC do, WITHOUT
    #: switching buffers. It is the other half of 1049, which xterm documents as
    #: 1047 combined with 1048.
    #:
    #: EVIDENCE LEVEL, stated because it is weaker than everything else in this
    #: class: the xterm specification defines it, but NEITHER reference emulator
    #: implements it. Measured — a `1048h`/`1048l` pair does not restore the
    #: cursor in tmux 3.6b or GNU screen 4.00.03, while the same movement through
    #: DECSC/DECRC does in both (so the probe can detect a restore; the absence is
    #: real, not a rig artifact). Every full-screen program in practice emits 1049.
    #:
    #: Supported anyway because this layer's job is to perceive what a program
    #: SENT, and a program that sends 1048 means DECSC. The alternative — matching
    #: the references by ignoring it — would make us silently drop a documented
    #: sequence. Kept deliberately separate from _ALT_MODES so it can never affect
    #: buffer switching, and locked by a test that names the divergence.
    #:
    #: Note for whoever sees the behaviour change: once ``_PYTE_HAS_ALT`` is true
    #: this class hands 1048 to the base class, whose pending implementation uses
    #: a single dedicated slot rather than a stack — so repeated ``1048h`` will
    #: OVERWRITE rather than nest. Both are defensible (xterm says "as DECSC",
    #: and DECSC is a stack; a single slot cannot strand savepoints), neither
    #: reference emulator implements 1048 at all, so there is no ground truth to
    #: prefer one. Recorded here so the drift is not mistaken for a regression.
    _CURSOR_ONLY_MODE = 1048

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._alt_active = False
        self._saved_main: dict | None = None
        # (row, col, attrs). The pen travels with the position because 1049 is
        # defined as "save cursor as in DECSC", and DECSC saves the graphic
        # rendition too. Without it, a TUI that left reverse video or a colour
        # on made every character the shell wrote afterwards inherit it.
        self._saved_cursor: tuple[int, int, Char] | None = None
        # How many 1048 saves WE pushed onto pyte's savepoint stack, so an
        # unpaired 1048l cannot pop somebody else's savepoint or fall through
        # to restore_cursor's empty-stack homing.
        self._cursor_only_depth = 0

    def _enter_alt(self, save_cursor: bool) -> None:
        if self._alt_active:
            return
        self._saved_main = dict(self.buffer)
        self._saved_cursor = ((self.cursor.y, self.cursor.x, self.cursor.attrs)
                              if save_cursor else None)
        self.buffer.clear()
        self._alt_active = True
        # NOTE: the cursor is deliberately NOT homed. xterm clears the alternate
        # buffer but leaves the cursor where it was, and tmux 3.6b agrees:
        # `main\r\n` then ESC[?1049h then ALT puts ALT on row 1, not row 0.
        self.dirty.update(range(self.lines))

    def _leave_alt(self) -> None:
        if not self._alt_active:
            return
        self.buffer.clear()
        if self._saved_main is not None:
            self.buffer.update(self._saved_main)
        self._saved_main = None
        self._alt_active = False
        if self._saved_cursor is not None:
            y, x, attrs = self._saved_cursor
            # CLAMP. The screen may have been resized while the program owned
            # the alternate screen, and restoring a row that no longer exists
            # left the cursor permanently outside the buffer: every subsequent
            # write landed on a row `display` never renders, so the agent read a
            # screen that had silently stopped updating. Found by review after
            # the resize fix here clipped the saved BUFFER but not the saved
            # CURSOR — one half of the same defect.
            self.cursor.y = min(max(y, 0), self.lines - 1)
            self.cursor.x = min(max(x, 0), self.columns - 1)
            self.cursor.attrs = attrs
            self._saved_cursor = None
        self.dirty.update(range(self.lines))

    def reset(self) -> None:
        """Overloaded so RIS leaves the alternate screen.

        ``pyte.Screen.reset`` clears ``buffer`` but knows nothing about the
        alternate-screen state kept here, so after ``ESC c`` the flag stayed set:
        the next program's smcup was a silent no-op (it paints onto what the
        agent believes is the primary screen), and a later rmcup resurrected the
        pre-RIS screen. Real terminals return to the primary buffer on RIS.
        """
        super().reset()
        self._alt_active = False
        self._saved_main = None
        self._saved_cursor = None
        self._cursor_only_depth = 0

    def resize(self, lines: int | None = None,
               columns: int | None = None) -> None:
        """Resize, clipping the SAVED primary screen the same way as the live one.

        ``pyte.Screen.resize`` only touches ``self.buffer``, which during
        alternate-screen mode is the alternate buffer — the saved primary screen
        is invisible to it. So a terminal resized while a full-screen program was
        running (the user drags the window while ``vim``/``less``/``htop`` is up,
        or ``drive-tui``'s own ``resize`` action fires) restored a primary screen
        of the old shape on exit: the wrong ROWS, because pyte drops rows from
        the top while an untouched save keeps its original numbering, plus
        over-wide cells that `display` hides but a later grow-back would reveal.

        Found by re-auditing this class against the same defect in the upstream
        patch for pyte issue #90, where the offscreen buffer had the same hole.

        KNOWN DIVERGENCE, deliberately not "fixed". With DECSTBM margins set that
        exclude row 0, a shrink through the alternate screen restores different
        rows than the same shrink without one. The cause is in pyte: it shrinks by
        homing the cursor and calling ``delete_lines``, which does nothing when the
        cursor sits outside the scroll region, so the live buffer keeps its TOP rows
        (``AAA/BBB``) where the unmargined case keeps its bottom ones
        (``CCC/DDD``) — and with margins ``(1, 3)`` it keeps a single row.

        Matching that here was rejected rather than overlooked. Real terminals
        REFLOW on resize instead of clipping, and they reset DECSTBM as part of it
        — pyte itself calls ``set_margins()`` at the end of ``resize`` — so using
        the outgoing margins to decide which rows to drop has no counterpart to
        measure against. Copying an unverifiable rule into the second buffer would
        add a hacky buffer swap and would still not be right, only symmetric. This
        is the same call the project makes for IL/DL from outside a scroll region,
        where the two reference emulators disagree: record the divergence, do not
        pick a side. See tests/test_terminal_fidelity.py, which pins the
        no-margins case and documents this one without asserting on it.
        """
        old_lines, old_columns = self.lines, self.columns
        # `or` rather than `is None`: pyte's own resize does `lines = lines or
        # self.lines`, so 0 means "unchanged" there. Testing `is None` here made
        # resize(0, 0) — a no-op for the live screen — clip the saved primary
        # screen to nothing.
        new_lines = lines or old_lines
        new_columns = columns or old_columns
        super().resize(lines, columns)

        saved = self._saved_main
        if saved is None:
            return
        if new_lines < old_lines:
            # Match pyte: shrinking drops rows from the TOP, so the surviving
            # rows shift up and renumber. Reading low-to-high is safe because
            # the source index always leads the destination.
            drop = old_lines - new_lines
            for y in range(new_lines):
                row = saved.pop(y + drop, None)
                if row is not None:
                    saved[y] = row
                else:
                    saved.pop(y, None)
            for y in range(new_lines, old_lines):
                saved.pop(y, None)
        if new_columns < old_columns:
            for line in saved.values():
                for x in range(new_columns, old_columns):
                    line.pop(x, None)

    #: True when the installed ``pyte`` implements the alternate screen buffer
    #: itself, so this subclass must NOT switch as well.
    #:
    #: pyte has not implemented it in any release up to 0.8.2 (issue #90, open
    #: since 2017), which is why the implementation below exists. An upstream
    #: patch is pending, and the day it ships in a release every installation
    #: with the usual ``pyte>=0.8.1`` requirement picks it up automatically —
    #: at which point doing the work twice restores a BLANK primary screen on
    #: every full-screen program exit, i.e. exactly the bug this class was
    #: written to prevent, reintroduced silently by a dependency upgrade.
    #:
    #: Detected once at import rather than pinning ``pyte<0.8.3``: a version cap
    #: would keep users off the fix forever and has to be revised every release,
    #: whereas the capability check is correct both before and after, and needs
    #: no maintenance. When it reports True the base class does the switching and
    #: ``_alt_active`` simply mirrors ``screen.alternate_screen``.
    _PYTE_HAS_ALT: bool = hasattr(pyte.Screen, "alternate_screen")

    @property
    def alt_screen(self) -> bool:
        """True while the alternate screen buffer is active.

        Reads through to the base class where that implements the feature, so the
        answer is right whichever layer performed the switch.
        """
        if self._PYTE_HAS_ALT:
            return bool(super().alternate_screen)  # type: ignore[misc]
        return self._alt_active

    def set_mode(self, *modes: int, **kwargs) -> None:
        if kwargs.get("private"):
            if not self._PYTE_HAS_ALT:
                for mode in modes:
                    if mode in self._ALT_MODES:
                        self._enter_alt(save_cursor=(mode == 1049))
            # 1048 is cursor-only. Skipped when the base class implements it
            # itself, or the cursor would be saved twice.
            if self._CURSOR_ONLY_MODE in modes and not self._PYTE_HAS_ALT:
                self.save_cursor()
                self._cursor_only_depth += 1
        super().set_mode(*modes, **kwargs)

    def reset_mode(self, *modes: int, **kwargs) -> None:
        if kwargs.get("private"):
            if not self._PYTE_HAS_ALT:
                for mode in modes:
                    if mode in self._ALT_MODES:
                        self._leave_alt()
            # Only restore against a save WE made. pyte's restore_cursor homes
            # the cursor when its stack is empty (its documented DECRC
            # behaviour), so an unpaired `ESC[?1048l` — which both reference
            # emulators ignore outright — would otherwise teleport the cursor to
            # the top-left. The depth counter keeps DECSC's stack semantics for
            # repeated 1048h while making the unpaired case inert.
            if (self._CURSOR_ONLY_MODE in modes and not self._PYTE_HAS_ALT
                    and self._cursor_only_depth > 0):
                self._cursor_only_depth -= 1
                self.restore_cursor()
        super().reset_mode(*modes, **kwargs)

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
        if _PYTE_DCH_HANDLES_WIDE:
            # The installed pyte already widens the count itself; adding to it
            # would delete one cell too many. See _pyte_dch_handles_wide.
            super().delete_characters(count)
            return
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
        """DL — deleting must BLANK the rows it vacates, not leave them behind.

        ``insert_lines`` above already routes through :meth:`_shift_lines` to keep
        every row present in pyte's sparse buffer. DL had the mirror-image hole and
        did not: pyte copies ``buffer[y] = buffer.pop(y + count)`` only ``if
        y + count in self.buffer``, so when the source row was never written the
        DESTINATION keeps its old contents instead of going blank.

        Two visible consequences, both measured against tmux 3.6b AND GNU screen
        4.00.03, which agree on all of them: ``Q`` + CR + ``ESC[1M`` left ``Q`` on
        screen where both references clear it, and ``A/B/C`` + ``ESC[2M`` deleted
        only ONE row, leaving ``['C', 'B']`` where both give ``['C']``.

        The earlier IL-side fix masked this: the repro recorded for it happened to
        materialise the rows first, so it passed while the minimal case stayed
        broken. Found by triaging which of this project's fixes are genuinely
        absent upstream.
        """
        top, bottom = self.margins or (0, self.lines - 1)
        if top <= self.cursor.y <= bottom:
            self._shift_lines(self.cursor.y, bottom,
                              min(count or 1, bottom - self.cursor.y + 1),
                              down=False)
            return
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

    def _clear_orphan_stub(self) -> None:
        """Blank a stub cell whose wide base was just overwritten.

        Drawing a two-column glyph over the BASE of an existing one leaves the
        old glyph's stub stranded one cell further right: it still reads as the
        empty-string continuation of a character that no longer exists, so every
        column after it renders one place off. Real terminals blank it.

        Concretely: with ``│││♀️♀️♀️`` on screen, writing ``中文中文`` from column
        0 put ``文``'s stub on the first emoji's base and left that emoji's own
        stub behind, so we rendered ``中文中文││ ▄`` where tmux 3.6b and GNU
        screen (which agree here) render ``中文中文││▄▄``. Found by
        ``tests/_diff_fuzz_tmux.py`` — it took a VS16 cluster plus a DECSTBM
        change plus two ICH rounds to expose, which is exactly the kind of
        accumulation hand-written cases never reach.
        """
        x = self.cursor.x
        if 0 < x < self.columns:
            line = self.buffer[self.cursor.y]
            if line[x].data == "" and line[x - 1].data not in ("", None):
                prev = line[x - 1].data
                if not (wcwidth_cached(prev[0]) == 2
                        or (len(prev) > 1 and "️" in prev)):
                    line[x] = self.cursor.attrs._replace(data=" ")
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
            self._clear_orphan_stub()
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
        # Per-row visual_hash CRCs (see visual_hash): polling recomputed every
        # cell of every row 33x/second even when nothing had changed.
        self._visual_row_crcs: list[int | None] = []
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
    def alt_screen(self) -> bool:
        """True while a full-screen program owns the screen.

        The single most useful fact about a screen after "what does it say": a
        driving agent decides differently when ``vim``/``less``/``htop`` is up
        than at a shell prompt — whether ``q`` quits or types a letter, whether
        arrow keys navigate or edit. It was previously reachable only as
        ``model.screen.alt_screen``, i.e. by reaching through to the pyte object.
        """
        return bool(self.screen.alt_screen)

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

        INCREMENTAL: ``wait_visual_change`` polls this every 30 ms, and hashing
        every cell of every row cost 16.6 ms on a 300x100 screen — 55% of the
        polling budget, spent almost entirely on rows that had not changed. We
        keep a per-row CRC and recompute only the rows ``pyte`` marks dirty
        (``Screen.dirty``, which nothing else in this codebase consumes, so we
        may drain it). The returned value is identical to the exhaustive
        computation — ``tests/test_perf_contract.py`` asserts that equivalence
        against a from-scratch model as well as the timing ceilings.
        """
        rows = self.screen.lines
        columns = self.screen.columns
        buffer = self.screen.buffer
        row_crcs = self._visual_row_crcs
        if len(row_crcs) != rows:  # first call, or a resize
            row_crcs = self._visual_row_crcs = [None] * rows
            todo: list[int] = list(range(rows))
        else:
            todo = [y for y in self.screen.dirty if 0 <= y < rows]
            todo.extend(y for y in range(rows) if row_crcs[y] is None)
        for row in todo:
            line = buffer[row]
            parts = []
            for col in range(columns):
                char = line[col]
                parts.append(
                    f"{char.data}\x00{char.fg}\x00{char.bg}\x00"
                    f"{char.bold:d}{char.italics:d}{char.underscore:d}"
                    f"{char.strikethrough:d}{char.reverse:d}{char.blink:d}"
                )
            row_crcs[row] = zlib.crc32("\x01".join(parts).encode("utf-8", "replace"))
        self.screen.dirty.clear()
        crc = 0
        for row_crc in row_crcs:
            crc = zlib.crc32((row_crc or 0).to_bytes(4, "big"), crc)
        cursor_state = (self.screen.cursor.y, self.screen.cursor.x, self.cursor_hidden)
        return zlib.crc32(repr(cursor_state).encode("ascii"), crc)


