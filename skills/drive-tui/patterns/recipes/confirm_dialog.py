"""Confirm paradigm -- a yes/no prompt you answer with a single key.

WHY the signals live on the CURSOR ROW + STATUS BAR only (matches):
    ``[y/N]``, ``(yes/no)`` and "Are you sure" appear all the time in help
    text, READMEs and echoed scrollback. The one trustworthy tell of a *live*
    confirm is that the question sits on the row the cursor is parked on (the
    program is blocking on a read there) or on the bottom status line. So
    :meth:`matches` scores ONLY ``cursor_row_text`` and ``status_bar``; the same
    string anywhere in the body is ignored.

WHY the default-capital convention matters (drive):
    ``[y/N]`` means "Enter == No", ``[Y/n]`` means "Enter == Yes". When the
    caller gives no explicit intent we answer with that default. When intent IS
    explicit we send the letter regardless of the default.

WHY act->confirm, never fire-and-forget (drive):
    Some prompts accept a bare ``y`` char, others want ``y`` + Enter. We send
    the letter, re-snapshot, and only if the SAME prompt is still on screen (not
    a *new* prompt that happens to look similar) do we follow with Enter. "Done"
    == the prompt line actually changed or the child exited -- a live boolean
    from the screen, never assumed.

EXTENSION recipe: a new prompt dialect = add its regex to ``_YN_RE`` /
``_ASK_RE`` below; the default-capital logic keys off ``_DEF_YES_RE`` /
``_DEF_NO_RE`` and needs nothing else.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from smartcli_core import PtySession, Snapshot

from ..base import Pattern, PatternResult
from ..registry import register

# Bracketed / parenthesised yes-no menus -- the strongest tell.
_YN_RE = re.compile(r"[\[(]\s*y(?:es)?\s*/\s*n(?:o)?\s*[\])]", re.I)
# Bare question prompts that block for a y/n answer.
_ASK_RE = re.compile(r"\b(are\s+you\s+sure|proceed|continue|overwrite|"
                     r"confirm|delete|really)\b.*\?", re.I)
# Default = No (capital N) vs default = Yes (capital Y). Case-SENSITIVE.
_DEF_NO_RE = re.compile(r"[\[(]\s*y\s*/\s*N\s*[\])]")
_DEF_YES_RE = re.compile(r"[\[(]\s*Y\s*/\s*n\s*[\])]")

_YES_WORDS = {"y", "yes", "true", "1", "ok", "accept"}
_NO_WORDS = {"n", "no", "false", "0", "cancel", "decline"}


@register
class ConfirmPattern(Pattern):
    """A yes/no dialog answered by a single key, honouring the default."""

    name = "confirm"
    description = ("A yes/no confirmation prompt ('[y/N]', '(yes/no)', "
                   "'Proceed?', 'Are you sure') on the cursor/status line, "
                   "answered with a single key.")
    tags = ("dialog", "yesno")

    # ---- recognition (cursor row + status bar only) ----------------------
    @staticmethod
    def _prompt_text(snapshot: Snapshot) -> str:
        """The prompt line: prefer the cursor row, fall back to the status bar.

        These are the only two places a *live* (blocking) confirm can be.
        Reads the LOGICAL cursor line (wrap-joined) so a ``[y/N]`` token split
        across a soft-wrap boundary on a narrow terminal is still seen whole.
        """
        row = Pattern.cursor_logical_text(snapshot).strip()
        if _YN_RE.search(row) or _ASK_RE.search(row):
            return row
        status = (snapshot.status_bar or "").strip()
        if _YN_RE.search(status) or _ASK_RE.search(status):
            return status
        # Neither carried a signal; return the cursor row so callers can still
        # diff it across sends (empty when the cursor row is blank).
        return row or status

    def matches(self, snapshot: Snapshot) -> float:
        # Logical (wrap-joined) cursor line: a narrow terminal soft-wraps a long
        # "... [y/N]" prompt so the physical cursor row is a bare fragment; the
        # signal token would be missed at 40 cols but seen at 80/120.
        row = Pattern.cursor_logical_text(snapshot).strip()
        status = (snapshot.status_bar or "").strip()
        best = 0.0
        for text, home in ((row, 0.95), (status, 0.9)):
            if not text:
                continue
            if _YN_RE.search(text):
                best = max(best, home)
            elif _ASK_RE.search(text):
                # A blocking question WITHOUT an explicit y/n menu is weaker
                # (could be rhetorical output); still a real signal on the
                # cursor/status line.
                best = max(best, home - 0.35)
        return best

    # ---- intent resolution ------------------------------------------------
    @staticmethod
    def _default_yes(prompt: str) -> bool:
        if _DEF_NO_RE.search(prompt):
            return False
        if _DEF_YES_RE.search(prompt):
            return True
        return False  # convention: unmarked confirms default to No

    def _resolve(self, intent: Any, prompt: str) -> bool:
        """Normalise intent to a yes(True)/no(False) bool. Fail loud on garbage."""
        if intent is None:
            return self._default_yes(prompt)
        if isinstance(intent, bool):
            return intent
        if isinstance(intent, str):
            v = intent.strip().lower()
            if v in _YES_WORDS:
                return True
            if v in _NO_WORDS:
                return False
        raise ValueError(
            f"confirm intent must be True/False or a y/n word, got {intent!r}")

    # ---- drive: perceive -> act -> wait -> confirm ------------------------
    def drive(self, session: PtySession, intent: Any = None, **kw) -> PatternResult:
        # intent=None => honor the prompt's capital-letter default ([y/N]=No,
        # [Y/n]=Yes) via _resolve, matching this module's documented contract.
        # Let a mid-render prompt settle before reading it (bounded, no blind sleep).
        snap = session.snapshot()
        if not self._prompt_text(snap):
            session.wait_stable(quiet_ms=120, max_wait_ms=800)
            snap = session.snapshot()

        prompt_before = self._prompt_text(snap)
        yes = self._resolve(intent, prompt_before)
        key = "y" if yes else "n"

        # Act: single letter first (the common case).
        session.send_text(key)
        session.wait_stable(quiet_ms=150, max_wait_ms=1500)
        snap = session.snapshot()

        dismissed = self._dismissed(session, snap, prompt_before)
        if not dismissed:
            # Same question still active -> a line-mode child (ConPTY caveat:
            # it just ECHOED our letter and is still blocked on readline) wants
            # the answer committed with Enter.
            session.send_keys(["Enter"])
            session.wait_stable(quiet_ms=150, max_wait_ms=1500)
            snap = session.snapshot()
            dismissed = self._dismissed(session, snap, prompt_before)

        answer = "yes" if yes else "no"
        detail = (f"answered {answer!r} ('{key}') to \"{prompt_before[:50]}\"; "
                  f"{'dialog dismissed' if dismissed else 'prompt still visible'}")
        return PatternResult(
            ok=dismissed, detail=detail, snapshot=snap,
            data={"answer": answer, "yes": yes, "key": key,
                  "prompt": prompt_before, "dismissed": dismissed},
        )

    @staticmethod
    def _question_core(text: str) -> str:
        """The question minus its y/n menu and any trailing echoed answer.

        Lets us tell 'same prompt, our letter merely echoed' (line-mode child
        still blocked) apart from 'a genuinely different prompt is now up'.
        """
        m = _YN_RE.search(text)
        if m:
            text = text[:m.start()]
        return re.sub(r"\s+", " ", text).strip().lower()

    @classmethod
    def _dismissed(cls, session: PtySession, snap: Snapshot,
                   prompt_before: str) -> bool:
        """True if the child exited or THIS question is no longer the active one.

        A trailing echo of the answer ('[y/N] y') keeps the same question core,
        so it is NOT counted as dismissed -- which is what triggers the Enter a
        line-mode child needs. A repaint to a different question IS dismissed.
        """
        if not session.is_alive():
            return True
        after = cls._prompt_text(snap)
        return cls._question_core(after) != cls._question_core(prompt_before)
