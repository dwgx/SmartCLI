"""Progress paradigm -- a spinner / progress bar / percentage you wait out.

WHY the signals are animation glyphs + a live percent (matches):
    The tell of a "working..." screen is a spinner frame (``|/-\\`` or a braille
    ``⠋⠙⠹…`` run), a bar (``[####----]``), or a percentage on the cursor/status
    line. A stray ``%`` in body text is weak, so :meth:`matches` weights the
    cursor row and status bar and treats a spinner glyph there as the strong
    signal.

WHY this is "a smart wait", and why it is HARD-bounded (drive):
    Waiting for a spinner to "finish" by watching for stability is a trap: many
    spinners animate forever, so the screen hash never settles. This recipe
    therefore prefers an explicit completion regex (``session.wait_for``) when
    the caller can name the done-marker. With no marker it falls back to
    ``wait_stable`` -- but ALWAYS under a hard ``max_wait_ms`` ceiling, and it
    reports ``completed`` vs ``timeout`` honestly from what the wait returned.
    An animation that never stops yields ``timeout``, not a false ``completed``.

    We never blind-sleep: both waits pump the PTY. We do not send any keys --
    this is a pure observer; the child drives itself to completion.

EXTENSION recipe: a new spinner alphabet = add its chars to ``_SPINNER_CHARS``;
a new bar dialect = add its regex to ``_BAR_RE``. The wait logic is dialect-free.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from smartcli_core import PtySession, Snapshot

from ..base import Pattern, PatternResult
from ..registry import register

# Spinner frame glyphs: ASCII twirl + Unicode braille + common dot/arc sets.
_ASCII_SPINNER = set("|/-\\")
# Unambiguous (non-ASCII) spinner glyphs: braille + dot/arc sets.
_UNI_SPINNER = set("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏") | set("◐◓◑◒") | set("⣾⣽⣻⢿⡿⣟⣯⣷")
_SPINNER_CHARS = _ASCII_SPINNER | _UNI_SPINNER
_BAR_RE = re.compile(r"\[[#=>\-\.\s]{4,}\]|[#█▓▒░]{4,}")
_PCT_RE = re.compile(r"\b\d{1,3}\s*%")
_WORD_RE = re.compile(r"\b(loading|working|please\s+wait|installing|"
                      r"downloading|building|processing|fetching)\b", re.I)


def _has_spinner(text: str) -> bool:
    """True if the line carries a spinner glyph.

    Unicode spinner glyphs (braille/dots/arcs) are unambiguous -- an isolated
    one anywhere counts. The ASCII twirl set (|/-\\) is overloaded (bullets,
    paths, table borders, ratios), so it only counts when the twirl char is the
    ONLY non-space token on the row (a real ASCII spinner stands alone, maybe
    with a trailing label) -- this rejects "- fetch the thing" and "a / b".
    """
    for ch in text:
        if ch in _UNI_SPINNER:
            return True
    stripped = text.strip()
    # ASCII twirl only counts as the SOLE token on the row. A spinner animates
    # in place (a snapshot catches one lone glyph); "|  label" is not attempted
    # because "- label" is indistinguishable from a bullet, and "/ " from a path.
    if stripped in _ASCII_SPINNER:
        return True
    return False


@register
class ProgressPattern(Pattern):
    """A spinner / progress bar / percentage screen you wait to completion."""

    name = "progress"
    description = ("A busy indicator: a spinner (|/-\\ or braille), a progress "
                   "bar, or a percentage on the cursor/status line -- waited "
                   "out to completion under a hard ceiling.")
    tags = ("spinner", "progress", "wait")

    # ---- recognition (cursor row + status bar) ---------------------------
    def matches(self, snapshot: Snapshot) -> float:
        # Logical (wrap-joined) cursor line so a long "Building foo... 42%" that
        # soft-wraps on a narrow terminal keeps its bar/percent token intact --
        # a lone spinner glyph never fills the width, so its detection is
        # unaffected (short rows are returned verbatim).
        cur = Pattern.cursor_logical_text(snapshot)
        status = (snapshot.status_bar or "")
        best = 0.0
        for text, home in ((cur, 0.9), (status, 0.85)):
            if not text:
                continue
            if _has_spinner(text):
                best = max(best, home)
            if _BAR_RE.search(text):
                best = max(best, home - 0.05)
            if _PCT_RE.search(text):
                best = max(best, home - 0.3)
            if _WORD_RE.search(text):
                best = max(best, 0.4)
        return 1.0 if best > 1.0 else best

    # ---- drive: pure smart wait (no keys sent) ---------------------------
    def drive(self, session: PtySession, intent: Any = None,
              max_wait_ms: int = 60000, quiet_ms: int = 400, **kw) -> PatternResult:
        """Wait until done.

        intent: a completion regex (str). If given, we race it via
            ``wait_for``. If None, we ``wait_stable`` (the animation stopping)
            under the same hard ceiling.
        max_wait_ms: hard ceiling for either strategy (default 60s). This is the
            guard against spinners that never stabilise.
        """
        if intent is not None and not isinstance(intent, str):
            raise ValueError(
                f"progress intent must be a completion regex str or None, "
                f"got {intent!r}")

        if intent:
            matched, snap = session.wait_for(
                intent, timeout_ms=max_wait_ms, **{
                    k: v for k, v in kw.items()
                    if k in ("poll_ms", "min_wait_ms", "flags")})
            reason = "completed" if matched else "timeout"
            ok = matched
            how = f"marker {intent!r}"
        else:
            # No marker: success == the screen going quiet (animation stopped).
            # A forever-spinner exhausts max_wait and returns False -> timeout.
            settled = session.wait_stable(
                quiet_ms=quiet_ms, max_wait_ms=max_wait_ms,
                **{k: v for k, v in kw.items()
                   if k in ("poll_ms", "grace_ms", "min_wait_ms")})
            snap = session.snapshot()
            reason = "completed" if settled else "timeout"
            ok = settled
            how = "screen-stable"

        # A child that exited on its own is unambiguously complete.
        if not session.is_alive():
            reason = "completed"
            ok = True
            how += " (+child exited)"

        detail = (f"{reason} via {how} under {max_wait_ms}ms ceiling")
        return PatternResult(
            ok=ok, detail=detail, snapshot=snap,
            data={"reason": reason, "strategy": how,
                  "max_wait_ms": max_wait_ms,
                  "child_alive": session.is_alive()},
        )
