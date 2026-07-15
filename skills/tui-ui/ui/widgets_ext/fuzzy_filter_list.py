"""fuzzy_filter_list.py — fzf-style fuzzy-filtered list widget.

The interaction at the heart of fzf / gum filter / atuin / k9s: a list of
candidates narrowed by a query, matched as a subsequence (query chars appear in
order, not necessarily adjacent), scored so contiguous and word-start matches
rank higher, with the matched characters highlighted and the selected row
reversed. A drop-in tui-ui widget; renders to a Canvas like any other.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from ..core import Canvas, BOLD, REVERSE
from ..registry import register
from ..widgets import Widget


def fuzzy_match(query: str, text: str) -> Optional[Tuple[int, List[int]]]:
    """Subsequence match of ``query`` in ``text`` (case-insensitive).

    Returns (score, matched_indices) or None if not all query chars appear in
    order. Score rewards contiguous runs and word-start matches (fzf-like), so a
    tight prefix match beats a scattered one. Higher score = better.
    """
    if not query:
        return (0, [])
    q = query.lower()
    t = text.lower()
    idxs: List[int] = []
    score = 0
    ti = 0
    prev = -2
    run = 0
    for qc in q:
        found = -1
        while ti < len(t):
            if t[ti] == qc:
                found = ti
                break
            ti += 1
        if found < 0:
            return None
        idxs.append(found)
        # contiguous with the previous match -> bonus that grows with the run
        if found == prev + 1:
            run += 1
            score += 5 + run * 2
        else:
            run = 0
            score += 1
        # word-start bonus (start of string, or after a separator)
        if found == 0 or text[found - 1] in " -_/.:":
            score += 8
        prev = found
        ti = found + 1
    # prefer shorter matches (tighter span) as a tiebreaker
    span = idxs[-1] - idxs[0] + 1
    score += max(0, 20 - span)
    return (score, idxs)


@register
class FuzzyFilterList(Widget):
    """A candidate list narrowed by a fuzzy query, with a highlighted selection.

    Set ``query`` to filter (empty shows all), ``selected`` to pick the row.
    Matched characters are bolded; the selected row is drawn reversed.
    """
    key = "fuzzy_filter_list"
    summary = "fzf-style fuzzy-filtered list with match highlighting"

    def __init__(self, items: Sequence[str], query: str = "", selected: int = 0,
                 width: Optional[int] = None, height: Optional[int] = None,
                 prompt: str = "> ", theme=None):
        from ..core import get_theme
        self.items = list(items)
        self.query = query
        self.selected = selected
        self.width = width
        self.height = height
        self.prompt = prompt
        self.theme = theme or get_theme("dashboard")

    def _filtered(self) -> List[Tuple[str, List[int]]]:
        """Items matching the query, best score first, with matched indices."""
        if not self.query:
            return [(it, []) for it in self.items]
        scored = []
        for it in self.items:
            m = fuzzy_match(self.query, it)
            if m is not None:
                scored.append((m[0], it, m[1]))
        scored.sort(key=lambda s: -s[0])
        return [(it, idxs) for _score, it, idxs in scored]

    # -- widget protocol ---------------------------------------------------
    def measure(self, avail_w, avail_h):
        w = self.width or avail_w
        h = self.height or avail_h
        return (max(4, w), max(2, h))

    def render(self, region_w, region_h):
        th = self.theme
        cv = Canvas(region_w, max(1, region_h), bg=th.bg)
        rows = self._filtered()
        # line 0: the query prompt
        cv.put_text(0, 0, (self.prompt + self.query)[:region_w],
                    fg=th.accent if hasattr(th, "accent") else th.fg, bg=th.bg)
        n_visible = region_h - 1
        sel = max(0, min(self.selected, len(rows) - 1)) if rows else 0
        # scroll so the selection stays visible
        top = max(0, min(sel - n_visible // 2, max(0, len(rows) - n_visible)))
        for row_i in range(n_visible):
            i = top + row_i
            if i >= len(rows):
                break
            text, match_idx = rows[i]
            y = row_i + 1
            is_sel = (i == sel)
            base_attr = REVERSE if is_sel else 0
            if is_sel:
                cv.fill_rect(0, y, region_w, 1, " ", fg=th.fg, bg=th.fg, attrs=REVERSE)
            match_set = set(match_idx)
            for cx, ch in enumerate(text[:region_w]):
                attr = base_attr | (BOLD if cx in match_set else 0)
                fg = th.accent if (cx in match_set and hasattr(th, "accent")) else th.fg
                cv.set(cx, y, ch, fg=fg, bg=th.bg, attrs=attr)
        return cv

    @classmethod
    def sample(cls, theme):
        items = ["main.py", "README.md", "src/core/engine.py", "tests/test_api.py",
                 "docs/guide.md", "src/utils/helpers.py", "pyproject.toml",
                 "src/core/render.py", "Makefile", ".gitignore"]
        return cls(items, query="core", selected=0, theme=theme)
