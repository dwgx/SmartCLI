"""Pager paradigm -- less / more / man / git-log style "read-only text + a
bottom status line you page through".

WHY the signals live on the STATUS BAR only (matches):
    The single reliable tell of a pager is its bottom command/status line:
    ``(END)``, ``--More--(37%)``, a lone ``:`` prompt, a ``file 37%`` / ``byte
    100/900`` position, or a ``q to quit`` hint. Body text is untrustworthy --
    a document being paged may literally contain the word "More" or a ``:`` or
    ``(END)``. So :meth:`matches` scores ONLY ``snapshot.status_bar`` (which the
    core already anchors to the bottom 1-2 rows); a signal found only in the
    body is ignored.

WHY paging is bounded + confirmed (drive / read_all):
    "Advance until the end" against an unknown pager can loop forever (follow
    mode, a status line that always shows a percent). Every loop here is capped
    by ``max_pages`` and, after each Space, re-snapshots and stops on ANY of:
    an end marker in the status bar, the child exiting, or the *body* going
    quiet for two consecutive advances (percent-only churn on the status line
    does not count as progress). We never blind-sleep -- :meth:`wait_stable`
    pumps the PTY and settles the screen between key sends.

EXTENSION recipe: a new pager dialect = add its end/prompt regex to
``_END_RE`` / ``_PROMPT_RE`` below; nothing else changes.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from smartcli_core import PtySession, Snapshot

from ..base import Pattern, PatternResult
from ..registry import register

# End-of-content markers as they appear in a pager's STATUS line.
_END_RE = re.compile(r"\(END\)|\bEND\b|100\s*%|\(ALL\)|\bBottom\b", re.I)
# "there is more below, press a key" prompts.
_MORE_RE = re.compile(r"--\s*More\s*--|\bMore\b|Press\s+space|Type\s+<?RET", re.I)
# A less-style lone command prompt at column 0.
_COLON_RE = re.compile(r"^:\s*$")
# Position/percent hints. A position must carry a TOTAL (``line 40/100`` /
# ``lines 1-24`` / ``byte 512/2048``) -- a bare ``line 19`` is indistinguishable
# from body text and must NOT trip the pager heuristic.
_PCT_RE = re.compile(r"\b\d{1,3}\s*%")
_POS_RE = re.compile(r"\b(lines?|byte)\s+\d+\s*[/-]\s*\d+", re.I)
_QUIT_RE = re.compile(r"q\b.*quit|quit.*\bq\b|q\s*[:=].*quit", re.I)


def _body_lines(snapshot: Snapshot) -> List[str]:
    """Visible body rows (rstripped), excluding the status-bar row.

    Paging progress is measured on the BODY, so the ever-changing percent on
    the status line never masquerades as "still advancing".
    """
    sr = snapshot.status_bar_row
    out: List[str] = []
    for e in snapshot.lines:
        if e == "...":
            continue
        row, text, _sel = e  # type: ignore[misc]
        if sr is not None and row == sr:
            continue
        out.append(text.rstrip())
    return out


@register
class PagerPattern(Pattern):
    """Read-only text with a bottom status line you advance a page at a time."""

    name = "pager"
    description = ("A pager (less/more/man/git-log): read-only text plus a "
                   "bottom status line -- ':' prompt, (END), --More--, a "
                   "percent/position, or a q-to-quit hint -- advanced by Space.")
    tags = ("pager", "scroll")

    # ---- recognition (status bar only) -----------------------------------
    def matches(self, snapshot: Snapshot) -> float:
        status = snapshot.status_bar
        if not status:
            return 0.0
        s = status.strip()
        if not s:
            return 0.0

        # Strongest tells: explicit pager prompts pinned to the bottom row.
        if _END_RE.search(s):
            return 0.95
        if _MORE_RE.search(s):
            return 0.9
        if _COLON_RE.match(s):
            return 0.85

        score = 0.0
        # A reverse-video / standout status line (less draws its prompt so).
        if snapshot.status_bar_row is not None:
            for span in snapshot.menu_items:
                if span.row == snapshot.status_bar_row:
                    score = max(score, 0.4)
                    break
        if _QUIT_RE.search(s):
            score += 0.45
        if _POS_RE.search(s):
            score += 0.4
        if _PCT_RE.search(s):
            score += 0.35
        # A bare ':' anywhere on an otherwise short bottom line (e.g. ":", or a
        # standout ": " with the cursor parked after it) is a weak less tell.
        elif s == ":" or (len(s) <= 3 and ":" in s):
            score += 0.5

        return 1.0 if score > 1.0 else score

    # ---- helpers ----------------------------------------------------------
    @staticmethod
    def _end_reached(snapshot: Snapshot) -> bool:
        s = (snapshot.status_bar or "").strip()
        return bool(s and _END_RE.search(s))

    def _advance_once(self, session: PtySession,
                      key: str = "Space") -> Snapshot:
        """Send one page-advance key and let the screen settle (no blind sleep)."""
        session.send_keys([key])
        session.wait_stable(quiet_ms=150, max_wait_ms=1500)
        return session.snapshot()

    # ---- drive ------------------------------------------------------------
    def drive(self, session: PtySession, intent=None, **kw) -> PatternResult:
        """Operate the pager.

        intent:
            'to_end' (default) -- Space/PageDown until (END) / child exit /
                the body stops changing, bounded by ``max_pages``.
            'next_page'        -- advance exactly one page.
            'search:<term>'    -- send ``/<term><Enter>`` (less/more search).

        kw: max_pages (int, default 200), key ('Space' | 'PageDown', default
            'Space'). Bad params fail loud.
        """
        intent = "to_end" if intent is None else str(intent)
        max_pages = kw.get("max_pages", 200)
        key = kw.get("key", "Space")
        if not isinstance(max_pages, int) or max_pages < 1:
            raise ValueError(f"max_pages must be a positive int, got {max_pages!r}")
        if key not in ("Space", "PageDown", "f"):
            raise ValueError(f"key must be Space/PageDown/f, got {key!r}")

        # ---- search:<term> ----
        if intent.startswith("search:"):
            term = intent[len("search:"):]
            if not term:
                raise ValueError("search intent needs a term: 'search:<term>'")
            session.send_text("/")
            session.send_text(term)
            session.send_keys(["Enter"])
            session.wait_stable(quiet_ms=200, max_wait_ms=2500)
            snap = session.snapshot()
            return PatternResult(
                ok=True, detail=f"searched for {term!r}", snapshot=snap,
                data={"intent": "search", "term": term,
                      "status": snap.status_bar,
                      "end_reached": self._end_reached(snap)})

        if intent == "next_page":
            before = session.snapshot()
            snap = self._advance_once(session, key)
            moved = _body_lines(snap) != _body_lines(before)
            end = self._end_reached(snap) or not session.is_alive()
            return PatternResult(
                ok=True, detail=f"advanced one page (moved={moved}, end={end})",
                snapshot=snap,
                data={"intent": "next_page", "pages": 1,
                      "moved": moved, "end_reached": end})

        if intent != "to_end":
            raise ValueError(
                f"unknown intent {intent!r}; use to_end/next_page/search:<term>")

        # ---- to_end: bounded advance, confirmed by body-change + end marker --
        # Perceive first: settle the current page so the initial body/status are
        # complete before we start comparing (bounded; no blind sleep).
        session.wait_stable(quiet_ms=120, max_wait_ms=1200)
        pages = 0
        end = False
        prev_body = _body_lines(session.snapshot())
        stale = 0
        while pages < max_pages:
            if self._end_reached(session.snapshot()) or not session.is_alive():
                end = True
                break
            snap = self._advance_once(session, key)
            pages += 1
            if self._end_reached(snap) or not session.is_alive():
                end = True
                break
            body = _body_lines(snap)
            if body == prev_body:
                stale += 1
                if stale >= 2:  # two quiet advances == no more content
                    end = True
                    break
            else:
                stale = 0
            prev_body = body

        snap = session.snapshot()
        detail = (f"paged to end in {pages} advance(s)" if end
                  else f"stopped at max_pages={max_pages} without an end marker")
        return PatternResult(
            ok=end, detail=detail, snapshot=snap,
            data={"intent": "to_end", "pages": pages, "end_reached": end,
                  "status": snap.status_bar})


def read_all(session: PtySession, max_pages: int = 200,
             key: str = "Space") -> Tuple[str, PatternResult]:
    """Accumulate the pager's full visible text across pages, dedup overlap.

    Returns ``(text, result)``. ``result`` is the same evidence-backed
    :class:`PatternResult` :meth:`PagerPattern.drive` would return for
    'to_end', so the caller keeps the last snapshot + pages/end facts.

    Overlap dedup: consecutive pages of a pager usually share a boundary line
    (less repaints the last visible line at the top of the next page). We stitch
    by finding the largest suffix of the accumulated tail that equals a prefix
    of the incoming page and dropping it -- so re-drawn boundary rows are not
    duplicated, while genuinely repeated body lines inside a single page are
    preserved.
    """
    pat = PagerPattern()
    if not isinstance(max_pages, int) or max_pages < 1:
        raise ValueError(f"max_pages must be a positive int, got {max_pages!r}")

    # Perceive: settle the first page before capturing it (bounded).
    session.wait_stable(quiet_ms=120, max_wait_ms=1200)
    acc: List[str] = list(_body_lines(session.snapshot()))
    pages = 0
    end = False
    stale = 0
    prev_body = list(acc)
    while pages < max_pages:
        if pat._end_reached(session.snapshot()) or not session.is_alive():
            end = True
            break
        snap = pat._advance_once(session, key)
        pages += 1
        body = _body_lines(snap)
        acc = _stitch(acc, body)
        reached = pat._end_reached(snap) or not session.is_alive()
        if body == prev_body:
            stale += 1
        else:
            stale = 0
        prev_body = body
        if reached or stale >= 2:
            end = True
            break

    snap = session.snapshot()
    text = "\n".join(acc)
    result = PatternResult(
        ok=end, detail=f"read {len(acc)} line(s) across {pages} advance(s)"
        + ("" if end else f" (hit max_pages={max_pages})"),
        snapshot=snap,
        data={"intent": "read_all", "pages": pages, "end_reached": end,
              "lines": len(acc)})
    return text, result


def _stitch(acc: List[str], nxt: List[str]) -> List[str]:
    """Append ``nxt`` to ``acc`` dropping the largest acc-suffix/nxt-prefix overlap."""
    if not acc:
        return list(nxt)
    if not nxt:
        return acc
    max_ov = min(len(acc), len(nxt))
    for ov in range(max_ov, 0, -1):
        if acc[-ov:] == nxt[:ov]:
            return acc + nxt[ov:]
    return acc + nxt

