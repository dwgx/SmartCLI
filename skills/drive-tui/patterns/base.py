"""Pattern base class + result type.

A Pattern encapsulates one interaction paradigm (menu, pager, REPL, ...):

* ``matches(snapshot) -> 0..1``: cheap, side-effect-free recognition from a
  single semantic snapshot. Guidance (research/R4): bind signals to the CURSOR
  ROW and cell attributes (``selected``/``menu_items``), not bare text --
  prompts and ``[y/N]`` strings also appear in scrollback and echoed input.
* ``drive(session, intent, **kw) -> PatternResult``: operate the live session
  toward *intent* using the perceive->act->wait->confirm loop. NEVER sleep
  blind; always re-snapshot after acting; always bound waits.

Patterns are stateless between calls: everything they need arrives via the
session/snapshot, so one instance can serve many sessions.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Optional

from smartcli_core import PtySession, Snapshot


@dataclass
class PatternResult:
    """Outcome of one drive() run.

    ok:       intent achieved (verified from the screen, not assumed).
    detail:   one-line human/agent-readable account of what happened.
    snapshot: the LAST snapshot taken (evidence; may be None on spawn failure).
    data:     pattern-specific payload (e.g. pager text, selected label).
    """

    ok: bool
    detail: str
    snapshot: Optional[Snapshot] = None
    data: dict = field(default_factory=dict)

    def brief(self) -> str:
        return f"[{'OK' if self.ok else 'FAIL'}] {self.detail}"


class Pattern(ABC):
    """One interaction paradigm. Subclass, set metadata, implement two methods."""

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    tags: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def matches(self, snapshot: Snapshot) -> float:
        """Confidence 0..1 that *snapshot* shows this paradigm. No side effects."""

    @abstractmethod
    def drive(self, session: PtySession, intent: Any = None, **kw) -> PatternResult:
        """Operate *session* toward *intent*. Returns evidence-backed result."""

    # ---- shared helpers for subclasses ------------------------------------
    @staticmethod
    def cursor_row_text(snapshot: Snapshot) -> str:
        """Text of the row the cursor sits on ('' when blank/collapsed)."""
        cy = snapshot.cursor[0]
        for entry in snapshot.lines:
            if entry != "..." and entry[0] == cy:
                return entry[1]
        return ""

    @staticmethod
    def cursor_logical_text(snapshot: Snapshot) -> str:
        """Text of the LOGICAL line the cursor sits on, rejoining soft wraps.

        On a narrow terminal a single logical prompt (``... [y/N] ``, a progress
        line, a status hint) auto-wraps across several PHYSICAL rows, so the
        cursor's own row can be a bare continuation fragment (``N]``) with the
        signal token split across the wrap boundary above it. Recognition that
        reads only ``cursor_row_text`` then silently drops to zero confidence at
        small sizes while scoring full at 80/120 -- a size-dependent blind spot.

        A terminal soft-wraps by filling a row edge to edge, so a physical row
        whose rstripped width equals the screen's column count is (almost always)
        a wrap PARENT whose text continues on the next row. This walks the
        maximal contiguous run of such full-width rows spanning the cursor and
        concatenates them, reconstructing the logical line the program emitted.
        Falls back to the plain cursor row when nothing is wrapped, so the wide-
        terminal path is byte-for-byte unchanged.
        """
        _rows, cols = snapshot.size
        cy = snapshot.cursor[0]
        by_row: dict[int, str] = {}
        for entry in snapshot.lines:
            if entry != "...":
                by_row[entry[0]] = entry[1]  # type: ignore[index]

        # A full-width row (rstripped length >= cols) soft-wrapped into the next.
        def _full(r: int) -> bool:
            return r in by_row and len(by_row[r]) >= cols

        anchor = cy
        if cy not in by_row:
            # The cursor row is blank -- but if the row just above is full-width
            # it wrapped a trailing fragment (e.g. a lone space) down onto this
            # collapsed row; anchor on that parent so the logical line is still
            # recovered. Otherwise the cursor is on genuinely empty space.
            if _full(cy - 1):
                anchor = cy - 1
            else:
                return ""
        a = anchor
        while _full(a - 1):        # a-1 wrapped into a -> part of this logical line
            a -= 1
        b = anchor
        while _full(b) and (b + 1) in by_row:  # this row wrapped into the next
            b += 1
        if a == b:                 # not wrapped: preserve exact legacy text
            return by_row[anchor]
        return "".join(by_row.get(r, "") for r in range(a, b + 1))

    @staticmethod
    def last_rows_text(snapshot: Snapshot, n: int = 3) -> list[str]:
        """The last *n* non-blank visible lines, top-down."""
        rows = [e for e in snapshot.lines if e != "..."]
        return [e[1] for e in rows[-n:]]

    @staticmethod
    def visible_text(snapshot: Snapshot) -> str:
        return "\n".join(e[1] for e in snapshot.lines if e != "...")

    @staticmethod
    def rx(pattern: str, text: str, flags: int = 0) -> Optional[re.Match]:
        return re.search(pattern, text, flags)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Pattern {self.name}>"
