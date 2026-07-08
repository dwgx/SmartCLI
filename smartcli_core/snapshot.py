"""Semantic, token-cheap snapshot of a terminal screen for an LLM agent.

A raw screen dump loses the single most actionable fact in a TUI: *which row is
selected*. Reverse-video and themed selection bars are invisible in plain text.
:func:`build_snapshot` scans the per-cell attributes, reduces them to a few
meaning-bearing fields (selected row, menu spans, errors, status bar), and throws
the color grid away.

The :class:`Snapshot` dataclass carries the reduced view and renders two
representations:

* :meth:`Snapshot.to_text` -- a compact view for feeding an LLM: the visible
  screen (blank runs collapsed) plus a one-line header describing cursor,
  selection and status bar.
* :meth:`Snapshot.to_json` -- the full structured form for programmatic use.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .screen_model import ScreenModel

_ERROR_RE = re.compile(r"\b(error|failed|traceback|exception)\b", re.I)
_RED_FGS = {"red", "brightred"}


@dataclass
class Span:
    """A contiguous run of highlighted columns on one row (``col_end`` exclusive)."""

    row: int
    col_start: int
    col_end: int
    text: str


@dataclass
class Snapshot:
    """Reduced semantic view of a terminal screen.

    Attributes:
        size: ``(rows, cols)``.
        lines: rendered non-blank lines; collapsed blank runs are the literal
            marker ``"..."``. Kept as ``(row, text, sel)`` tuples so positional
            reasoning survives collapsing.
        cursor: ``(row, col)``, 0-based.
        cursor_hidden: whether the terminal cursor is hidden.
        selected_line: best-guess active row index, or ``None``.
        status_bar: bottom hint/status line text, or ``None``.
        title: OSC window title, or ``None``.
        menu_items: every highlighted span in reading order.
        errors: lines flagged as errors, as ``(row, text, reason)``.
        screen_reverse: DECSCNM (screen-wide reverse) active.
    """

    size: Tuple[int, int]
    lines: List[object]  # list[tuple[int, str, bool]] | "..."
    cursor: Tuple[int, int]
    cursor_hidden: bool = False
    selected_line: Optional[int] = None
    selected: Optional[Span] = None
    selected_reason: Optional[str] = None
    status_bar: Optional[str] = None
    status_bar_row: Optional[int] = None
    title: Optional[str] = None
    menu_items: List[Span] = field(default_factory=list)
    errors: List[Tuple[int, str, str]] = field(default_factory=list)
    screen_reverse: bool = False

    # -- rendering ---------------------------------------------------------

    def to_text(self) -> str:
        """Compact LLM-facing view: header line + visible screen.

        The header summarises cursor, selection, status bar and any errors so the
        agent gets the semantics without a per-cell color grid.
        """
        rows, cols = self.size
        header_bits = [f"cursor=r{self.cursor[0]}c{self.cursor[1]}"]
        if self.cursor_hidden:
            header_bits.append("cursor:hidden")
        if self.selected is not None:
            sel = self.selected
            header_bits.append(
                f"selected=r{sel.row}[{sel.col_start}:{sel.col_end}]"
                f'"{sel.text}"({self.selected_reason})'
            )
        elif self.selected_line is not None:
            header_bits.append(f"selected=r{self.selected_line}")
        if self.status_bar:
            header_bits.append(f'status="{self.status_bar}"')
        if self.title:
            header_bits.append(f'title="{self.title}"')
        if self.errors:
            header_bits.append(f"errors={len(self.errors)}")
        if self.screen_reverse:
            header_bits.append("screen_reverse")

        header = f"[screen {rows}x{cols}] " + "  ".join(header_bits)

        body_lines = []
        for entry in self.lines:
            if entry == "...":
                body_lines.append("...")
                continue
            row, text, sel = entry  # type: ignore[misc]
            marker = "*" if sel else " "
            body_lines.append(f"{row:>3}{marker}| {text}")

        return header + "\n" + "\n".join(body_lines)

    def to_json(self, indent: Optional[int] = None) -> str:
        """Full structured JSON. Empty/None fields are omitted to save tokens."""
        rows, cols = self.size
        obj: dict = {
            "size": {"rows": rows, "cols": cols},
            "cursor": {
                "row": self.cursor[0],
                "col": self.cursor[1],
                "hidden": self.cursor_hidden,
            },
            "lines": [
                "..." if e == "..." else {
                    "row": e[0],  # type: ignore[index]
                    "text": e[1],  # type: ignore[index]
                    **({"sel": True} if e[2] else {}),  # type: ignore[index]
                }
                for e in self.lines
            ],
        }
        if self.title:
            obj["title"] = self.title
        if self.selected is not None:
            obj["selected"] = {
                "row": self.selected.row,
                "col_start": self.selected.col_start,
                "col_end": self.selected.col_end,
                "text": self.selected.text,
                "reason": self.selected_reason,
            }
        regions: dict = {}
        if self.status_bar is not None:
            regions["status_bar"] = {
                "row": self.status_bar_row,
                "text": self.status_bar,
            }
        if self.menu_items:
            regions["menu_items"] = [
                {
                    "row": s.row,
                    "col_start": s.col_start,
                    "col_end": s.col_end,
                    "text": s.text,
                }
                for s in self.menu_items
            ]
        if regions:
            obj["regions"] = regions
        hints: dict = {
            "has_hidden_cursor": self.cursor_hidden,
            "screen_reverse": self.screen_reverse,
        }
        if self.errors:
            hints["errors"] = [
                {"row": r, "text": t, "reason": reason}
                for (r, t, reason) in self.errors
            ]
        obj["hints"] = hints
        return json.dumps(obj, indent=indent, ensure_ascii=False)


def _contiguous_spans(cols: List[int]) -> List[Tuple[int, int]]:
    """``[0,1,2,5,6]`` -> ``[(0,3),(5,7)]`` (end exclusive)."""
    spans: List[Tuple[int, int]] = []
    for x in sorted(cols):
        if spans and x == spans[-1][1]:
            spans[-1] = (spans[-1][0], x + 1)
        else:
            spans.append((x, x + 1))
    return spans


def build_snapshot(model: ScreenModel) -> Snapshot:
    """Build a :class:`Snapshot` from a :class:`ScreenModel`.

    The reverse-video predicate is measured relative to the screen's baseline
    (``default_char.reverse``) so a full-screen-reverse app (DECSCNM) does not
    report every line as selected.
    """
    screen = model.screen
    rows, cols = screen.lines, screen.columns
    display = model.display
    base_reverse = model.base_reverse

    # ---- per-cell attribute scan, reduced to per-line facts ----
    line_hi_spans: List[List[Tuple[int, int]]] = []
    line_red: List[bool] = []
    for y in range(rows):
        cells = model.row_cells(y)
        hi_cols: List[int] = []
        red = False
        for x, ch in enumerate(cells):
            is_blank = ch.data == " "
            # Selection/highlight signal: reverse-video, a distinct background,
            # or bold. Foreground colour alone is deliberately NOT treated as a
            # highlight — syntax-coloured REPL/output lines use non-default fg
            # everywhere and would flood menu detection with false positives.
            highlit = (
                (ch.reverse != base_reverse)
                or (ch.bg != "default")
                or ch.bold
            )
            if is_blank and not highlit:
                # plain padding: ignore
                pass
            elif highlit:
                hi_cols.append(x)
            if ch.fg in _RED_FGS:
                red = True
        line_hi_spans.append(_contiguous_spans(hi_cols))
        line_red.append(red)

    # ---- lines array with blank collapsing ----
    lines_out: List[object] = []
    blank_run = False
    for y in range(rows):
        text = display[y].rstrip()
        if text == "":
            if not blank_run and lines_out:  # collapse; drop leading blanks
                lines_out.append("...")
                blank_run = True
            continue
        blank_run = False
        sel = bool(line_hi_spans[y])
        lines_out.append((y, text, sel))
    while lines_out and lines_out[-1] == "...":
        lines_out.pop()

    # ---- menu items: every highlighted span with its text ----
    menu_items: List[Span] = []
    for y in range(rows):
        for (a, b) in line_hi_spans[y]:
            menu_items.append(Span(y, a, b, display[y][a:b].strip()))

    # ---- selected: widest highlighted span, else cursor line ----
    selected: Optional[Span] = None
    selected_reason: Optional[str] = None
    if menu_items:
        selected = max(menu_items, key=lambda s: s.col_end - s.col_start)
        selected_reason = "reverse_or_bg"
    elif not screen.cursor.hidden:
        cy = screen.cursor.y
        selected = Span(cy, 0, cols, display[cy].rstrip())
        selected_reason = "cursor_line"

    # ---- status bar: last non-blank row if it sits in the bottom 1-2 rows ----
    status_bar: Optional[str] = None
    status_bar_row: Optional[int] = None
    last_nonblank = None
    for y in range(rows - 1, -1, -1):
        if display[y].rstrip():
            last_nonblank = y
            break
    if last_nonblank is not None and last_nonblank >= rows - 2:
        status_bar = display[last_nonblank].rstrip()
        status_bar_row = last_nonblank

    # ---- errors: red fg lines or keyword matches ----
    errors: List[Tuple[int, str, str]] = []
    for y in range(rows):
        text = display[y].rstrip()
        if not text:
            continue
        if line_red[y]:
            errors.append((y, text, "red_fg"))
        elif _ERROR_RE.search(text):
            errors.append((y, text, "keyword"))

    return Snapshot(
        size=(rows, cols),
        lines=lines_out,
        cursor=(screen.cursor.y, screen.cursor.x),
        cursor_hidden=bool(screen.cursor.hidden),
        selected_line=(selected.row if selected is not None else None),
        selected=selected,
        selected_reason=selected_reason,
        status_bar=status_bar,
        status_bar_row=status_bar_row,
        title=(screen.title or None),
        menu_items=menu_items,
        errors=errors,
        screen_reverse=base_reverse,
    )
