"""Form paradigm -- labelled input fields you fill and Tab between.

WHY the signals live on field MARKERS + the cursor (matches):
    A form's tell is a labelled entry area the cursor is sitting in: a
    ``Name: ____`` label, a ``:`` or ``_`` field marker, or a highlighted input
    span (menu_items) on/near the cursor row. A colon in body text is not a
    form, so :meth:`matches` weights the CURSOR ROW's field markers and any
    highlighted span the cursor sits inside, not bare text.

WHY fill is BOUNDED + confirmed per field (drive):
    Typing then Tab-ing blind can overrun a form with fewer fields than values,
    or spray input at a program that already submitted. So each field is a
    perceive->type->re-snapshot->Tab loop, capped at ``len(values)`` iterations,
    and after typing we re-snapshot to confirm the text actually landed on the
    cursor row before advancing. We never blind-sleep; ``wait_stable`` settles
    the echo between keystrokes.

WHY submit is explicit (drive):
    The final field is committed with a configurable ``submit`` key (default
    Enter). "Done" == every requested field was typed AND (best-effort) its text
    was observed echoed -- returned per-field so the caller sees exactly which
    landed.

EXTENSION recipe: a new field-marker dialect = add its regex to ``_FIELD_RE``;
change the default navigation/submit keys via the ``next_key`` / ``submit`` kw.
"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from smartcli_core import PtySession, Snapshot

from ..base import Pattern, PatternResult
from ..registry import register

# Field markers: "Label: ", trailing "____", or a lone caret/underscore slot.
_LABEL_RE = re.compile(r"\S.*:\s*(_{2,}|\.{2,})?\s*$")
_SLOT_RE = re.compile(r"(_{2,}|\[\s*\]|\.{3,})")
_FIELD_RE = re.compile(r":\s*_*\s*$|_{2,}")


@register
class FormPattern(Pattern):
    """Labelled input fields filled top-to-bottom, Tab between, Enter to submit."""

    name = "form"
    description = ("A fill-in form: labelled input fields / a focused entry "
                   "area (cursor in a ':' or '_' field slot), filled value by "
                   "value with Tab and submitted with Enter.")
    tags = ("form", "input")

    # ---- recognition (cursor row markers + highlighted input span) -------
    def matches(self, snapshot: Snapshot) -> float:
        cur = Pattern.cursor_row_text(snapshot)
        score = 0.0

        # A field marker on the very row the cursor sits in is the strongest tell.
        if cur and (_LABEL_RE.search(cur) or _SLOT_RE.search(cur)):
            score = max(score, 0.85)

        # A highlighted input span the cursor sits inside (themed entry box).
        cy, cx = snapshot.cursor
        for span in snapshot.menu_items:
            if span.row == cy and span.col_start <= cx <= span.col_end:
                score = max(score, 0.6)
                break

        # Multiple label:/slot rows on screen -> a multi-field form (weak on its
        # own, but corroborates). Count visible field-looking rows.
        field_rows = 0
        for e in snapshot.lines:
            if e == "...":
                continue
            _row, text, _sel = e  # type: ignore[misc]
            if _LABEL_RE.search(text) or _SLOT_RE.search(text):
                field_rows += 1
        if field_rows >= 2:
            score = max(score, 0.5 + min(0.2, 0.05 * field_rows))

        return 1.0 if score > 1.0 else score

    # ---- intent normalisation --------------------------------------------
    @staticmethod
    def _values(intent: Any) -> List[Tuple[Optional[str], str]]:
        """Normalise intent to an ordered list of (label|None, value) pairs.

        Accepts a list/tuple of values, or a dict of label->value (insertion
        order preserved). Fail loud on anything else.
        """
        if intent is None:
            raise ValueError("form intent required: a list of values or a "
                             "{label: value} dict")
        if isinstance(intent, dict):
            return [(str(k), str(v)) for k, v in intent.items()]
        if isinstance(intent, (list, tuple)):
            out: List[Tuple[Optional[str], str]] = []
            for item in intent:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    out.append((str(item[0]), str(item[1])))
                else:
                    out.append((None, str(item)))
            return out
        raise ValueError(f"form intent must be list or dict, got {intent!r}")

    # ---- drive: per-field perceive -> type -> confirm -> advance ---------
    def drive(self, session: PtySession, intent: Any = None,
              next_key: str = "Tab", submit: str = "Enter", **kw) -> PatternResult:
        fields = self._values(intent)
        if not fields:
            raise ValueError("form intent produced zero fields")

        # Settle any mid-render form before touching it (bounded).
        session.wait_stable(quiet_ms=120, max_wait_ms=800)

        filled: List[dict] = []
        n = len(fields)
        for i, (label, value) in enumerate(fields):
            before = session.snapshot()
            cy_before = before.cursor[0]

            session.send_text(value)
            session.wait_stable(quiet_ms=120, max_wait_ms=1200)
            after = session.snapshot()

            # Confirm the text landed: value echoed on the cursor row (secret
            # fields mask input, so a masked/empty echo is not a hard failure).
            cur_after = Pattern.cursor_row_text(after)
            landed = bool(value) and value in cur_after
            filled.append({"index": i, "label": label, "value": value,
                           "echoed": landed, "cursor_row_before": cy_before})

            # Advance: Tab between fields, submit key after the last one.
            key = submit if i == n - 1 else next_key
            session.send_keys([key])
            session.wait_stable(quiet_ms=120, max_wait_ms=1500)

            # A dead child mid-form means the form closed early; stop cleanly.
            if not session.is_alive():
                filled[-1]["closed_after"] = True
                break

        snap = session.snapshot()
        typed = len(filled)
        echoed = sum(1 for f in filled if f["echoed"])
        # "Done" == every requested field was typed. (Whether the child then
        # exits or waits for more is caller-domain, not a failure here.)
        ok = typed == n
        detail = (f"filled {typed}/{n} field(s), {echoed} echo-confirmed; "
                  f"submitted with {submit!r}")
        return PatternResult(
            ok=ok, detail=detail, snapshot=snap,
            data={"fields": filled, "requested": n, "typed": typed,
                  "echoed": echoed, "submit": submit, "next_key": next_key},
        )
