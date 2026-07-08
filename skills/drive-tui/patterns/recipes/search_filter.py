"""Fuzzy search / incremental filter paradigm -- fzf, Ctrl-R, telescope,
command palettes: a query/prompt line plus a candidate list that shrinks live
as you type.

WHY the tell is prompt-line + a shrinking list (matches):
    The defining behaviour is *incremental narrowing*: type a char, the list
    gets shorter and an ``X/Y`` match count drops. A single snapshot cannot
    observe that motion, so :meth:`matches` scores the STATIC skeleton fzf
    leaves on screen -- a prompt line (``> `` at col 0, or a search glyph), an
    ``X/Y`` info count, a row pointer (``>`` / ``▌``) -- and binds them to the
    cursor row / status region, NOT to bare body text (a prompt string also
    echoes into scrollback). ``drive`` is what actually *confirms* the filter by
    watching the count fall.

WHY typing is confirmed char-by-char, bounded (drive):
    To pick a known item we type just enough of its distinctive substring for
    ``Y`` to collapse toward 1, re-snapshotting after each char to (a) prove the
    list is filtering and (b) stop early once it is narrow enough -- no wasted
    keystrokes, and we never blind-sleep. Every wait is bounded; on request we
    Enter to accept the top match. If the child never behaves like a filter we
    report ``ok=False`` with the evidence rather than pretending.

EXTENSION recipe: a new fuzzy UI dialect = teach ``_count_pair`` its info-line
format (the ``X/Y`` regex) and ``_POINTER_RE`` its pointer glyph; the drive loop
is dialect-agnostic.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from smartcli_core import PtySession, Snapshot

from ..base import Pattern, PatternResult
from ..registry import register

# "> query" prompt at the very left of a row (fzf default; palettes reuse it).
_PROMPT_RE = re.compile(r"^\s{0,2}([>›»❯▶🔍/])\s")
# fzf info line: "  42/128" (matched/total), often after a separator run.
_COUNT_RE = re.compile(r"\b(\d+)\s*/\s*(\d+)\b")
# Current-row pointer glyph at the left.
_POINTER_RE = re.compile(r"^\s{0,2}([>▌❯➤])\s")
# Horizontal separator fzf draws between list and info line.
_SEP_RE = re.compile(r"[─—-]{4,}")


def _rows(snapshot: Snapshot) -> List[Tuple[int, str]]:
    """Visible (row, text) pairs, blank-collapse markers dropped."""
    return [(e[0], e[1]) for e in snapshot.lines if e != "..."]  # type: ignore[index]


def _count_pair(snapshot: Snapshot) -> Optional[Tuple[int, int]]:
    """Best-guess ``(matched, total)`` from an ``X/Y`` info line.

    Prefer a line that also carries a separator run (fzf's info row) or sits
    adjacent to the prompt; fall back to any ``a/b`` with ``a <= b``.
    """
    best: Optional[Tuple[int, int]] = None
    for _row, text in _rows(snapshot):
        m = _COUNT_RE.search(text)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a > b or b == 0:
            continue
        if _SEP_RE.search(text):  # the real fzf info line -- trust it
            return (a, b)
        if best is None:
            best = (a, b)
    return best


def _prompt_row(snapshot: Snapshot) -> Optional[int]:
    """Row of the QUERY prompt (where the user types), not a candidate pointer.

    The pointer glyph on the selected candidate (``> item``) matches the same
    prompt regex as the query line (``> query``), so returning the first hit can
    mistake the top result for the prompt. The query line is the one the CURSOR
    is parked on, so among prompt-glyph rows we prefer the one nearest the cursor
    row; a lone match is returned unconditionally.
    """
    hits = [row for row, text in _rows(snapshot) if _PROMPT_RE.match(text)]
    if not hits:
        return None
    cy = snapshot.cursor[0]
    return min(hits, key=lambda r: (abs(r - cy), r))


def _pointer_row(snapshot: Snapshot) -> Optional[int]:
    """Row of the SELECTED candidate's pointer glyph, excluding the query
    prompt row (``> query`` matches the pointer regex too). In fzf ``default``
    the list grows above the prompt and the pointer sits at the bottom of the
    list (nearest the prompt); in ``reverse`` it sits below. Either way the
    pointer is the prompt-adjacent glyph row that is NOT the prompt itself.
    """
    prow = _prompt_row(snapshot)
    hits = [row for row, text in _rows(snapshot)
            if _POINTER_RE.match(text) and row != prow]
    if not hits:
        return None
    if prow is None:
        return hits[0]
    return min(hits, key=lambda r: (abs(r - prow), r))


def _info_row(snapshot: Snapshot) -> Optional[int]:
    """Row of the fzf ``X/Y`` info line (matched/total), if present. Trusts a
    separator run first, else the nearest ``a/b`` (a<=b) to the prompt."""
    prow = _prompt_row(snapshot)
    cand: List[int] = []
    for row, text in _rows(snapshot):
        m = _COUNT_RE.search(text)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a > b or b == 0:
            continue
        if _SEP_RE.search(text):
            return row
        cand.append(row)
    if not cand:
        return None
    if prow is None:
        return cand[0]
    return min(cand, key=lambda r: (abs(r - prow), r))


@register
class SearchFilterPattern(Pattern):
    """A query/prompt line above a candidate list that filters as you type."""

    name = "search_filter"
    description = ("Fuzzy/incremental filter (fzf, Ctrl-R, palette): a prompt "
                   "line ('>' or a search glyph) plus a candidate list that "
                   "shrinks live as you type, usually with an X/Y match count.")
    tags = ("fuzzy", "filter", "incremental")

    # ---- recognition ------------------------------------------------------
    def matches(self, snapshot: Snapshot) -> float:
        score = 0.0
        prow = _prompt_row(snapshot)
        if prow is not None:
            score += 0.4
            # Prompt should be at/near the cursor row (user is typing there).
            if abs(snapshot.cursor[0] - prow) <= 1:
                score += 0.15
        counts = _count_pair(snapshot)
        if counts is not None:
            score += 0.35
            # An info line drawn in standout/reverse is a strong fzf tell.
            for span in snapshot.menu_items:
                if _COUNT_RE.search(span.text):
                    score += 0.1
                    break
        if _pointer_row(snapshot) is not None:
            score += 0.15
        # A candidate list = at least a couple of rows besides the prompt.
        if prow is not None and len(_rows(snapshot)) >= 3:
            score += 0.1
        # Prompt AND an X/Y count together is almost certainly a fuzzy filter.
        if prow is not None and counts is not None:
            score += 0.1
        return 1.0 if score > 1.0 else score

    # ---- helpers ----------------------------------------------------------
    @staticmethod
    def _top_results(snapshot: Snapshot, limit: int = 10) -> List[str]:
        """Candidate rows (prompt + info line excluded), pointer glyph stripped.

        Layout-agnostic: fzf ``default`` grows the list ABOVE the prompt,
        ``reverse`` puts it below -- so we simply drop the prompt row and the
        separator/info row and keep everything else in reading order.
        """
        prow = _prompt_row(snapshot)
        irow = _info_row(snapshot)  # drop the X/Y info line by row identity --
                                    # classic fzf's "  3/3" carries no separator.
        out: List[str] = []
        for row, text in _rows(snapshot):
            if prow is not None and row == prow:
                continue
            if irow is not None and row == irow:
                continue
            if not text.strip():
                continue
            out.append(_POINTER_RE.sub("", text).rstrip())
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _selected_text(snapshot: Snapshot) -> Optional[str]:
        """Text of the pointer-selected candidate (glyph stripped), or None."""
        prow = _pointer_row(snapshot)
        if prow is None:
            return None
        for row, text in _rows(snapshot):
            if row == prow:
                return _POINTER_RE.sub("", text).strip() or None
        return None

    # ---- drive ------------------------------------------------------------
    def drive(self, session: PtySession, intent=None, **kw) -> PatternResult:
        """Type a query into the filter and watch the list narrow.

        intent: the query string to type. Required (a filter with no query is a
            no-op); passing None/'' fails loud.

        kw:
            incremental (bool, default True) -- type char-by-char, re-snapshot
                after each, and stop early once the match count reaches
                ``stop_at`` (default 1). False = send the whole query, then
                settle once.
            stop_at (int, default 1) -- narrow-enough threshold on matched Y.
            accept (bool, default False) -- press Enter to pick the top match
                after filtering.
            settle_ms (int, default 400) -- per-char settle bound.

        Returns the top results seen in ``data['results']`` plus the final
        match count and whether the filter was observed to narrow.
        """
        if intent is None or str(intent) == "":
            raise ValueError("search_filter.drive needs a non-empty query intent")
        query = str(intent)
        incremental = bool(kw.get("incremental", True))
        stop_at = kw.get("stop_at", 1)
        accept = bool(kw.get("accept", False))
        settle_ms = kw.get("settle_ms", 400)
        if not isinstance(stop_at, int) or stop_at < 1:
            raise ValueError(f"stop_at must be a positive int, got {stop_at!r}")
        if not isinstance(settle_ms, int) or settle_ms < 1:
            raise ValueError(f"settle_ms must be a positive int, got {settle_ms!r}")

        start = _count_pair(session.snapshot())
        typed = 0
        last_count = start

        if incremental:
            for ch in query:
                session.send_text(ch)
                typed += 1
                session.wait_stable(quiet_ms=int(settle_ms * 0.4),
                                    max_wait_ms=settle_ms)
                last_count = _count_pair(session.snapshot()) or last_count
                if last_count is not None and last_count[0] <= stop_at:
                    break  # narrow enough -- stop wasting keystrokes
        else:
            session.send_text(query)
            typed = len(query)
            session.wait_stable(quiet_ms=int(settle_ms * 0.5),
                                max_wait_ms=max(settle_ms, 800))
            last_count = _count_pair(session.snapshot()) or last_count

        snap = session.snapshot()
        # "Did it filter?" -- require an OBSERVED drop in matched count; a list
        # that started at/under stop_at never actually narrowed.
        narrowed = (start is not None and last_count is not None
                    and last_count[0] < start[0])
        results = self._top_results(snap)

        picked = None
        if accept:
            # The pointer-selected candidate is the real pick (fzf default puts
            # it nearest the prompt, NOT at results[0]). Capture it BEFORE Enter,
            # because the fuzzy UI tears down on accept.
            picked = self._selected_text(snap)
            if picked is None:
                picked = results[0] if results else None
            session.send_keys(["Enter"])
            session.wait_stable(quiet_ms=200, max_wait_ms=1500)
            snap = session.snapshot()

        # ok means the filter genuinely responded: we saw it narrow, or it was
        # already at/under the target with a real count -- not just "any screen".
        ok = narrowed or (last_count is not None and last_count[0] <= stop_at)
        detail = (f"typed {typed}/{len(query)} char(s); "
                  + (f"matches {last_count[0]}/{last_count[1]}"
                     if last_count else "no count line")
                  + (f"; accepted {picked!r}" if accept else ""))
        return PatternResult(
            ok=ok, detail=detail, snapshot=snap,
            data={"query": query, "typed": typed,
                  "count_start": start, "count_end": last_count,
                  "narrowed": narrowed, "results": results,
                  "picked": picked})

