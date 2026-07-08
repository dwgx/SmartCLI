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

    # -- feeding -----------------------------------------------------------

    def feed(self, data: bytes) -> None:
        """Feed raw bytes from the PTY into the screen. Safe with partial data."""
        if data:
            self.stream.feed(data)

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

    # -- plain text --------------------------------------------------------

    @property
    def display(self) -> List[str]:
        """List of rendered lines (wide-char aware, right-padded to ``cols``)."""
        return list(self.screen.display)

    def text(self) -> str:
        """The full screen joined with newlines (trailing padding preserved)."""
        return "\n".join(self.screen.display)

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
