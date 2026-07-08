"""Screen classification: rank every registered pattern against a snapshot and
render a human-readable explanation of what the screen appears to be."""
from __future__ import annotations

from typing import List, Tuple

from smartcli_core import Snapshot

from .base import Pattern
from . import registry


def classify(snapshot: Snapshot, threshold: float = 0.05) -> List[Tuple[Pattern, float]]:
    """All patterns with confidence > *threshold*, highest first.

    A pattern whose ``matches`` raises is scored 0 (a broken recipe must never
    poison classification for the rest).
    """
    scored = []
    for pat in registry.all_patterns():
        try:
            conf = float(pat.matches(snapshot))
        except Exception:
            conf = 0.0
        conf = 0.0 if conf < 0 else 1.0 if conf > 1 else conf
        if conf > threshold:
            scored.append((pat, conf))
    scored.sort(key=lambda pc: pc[1], reverse=True)
    return scored


def explain(snapshot: Snapshot) -> str:
    """Human/agent-readable description: screen facts + ranked paradigms.

    Reuses the Snapshot's semantic fields (cursor, selected row, menu spans,
    status bar, errors) so the caller does not have to re-derive them.
    """
    rows, cols = snapshot.size
    lines = []

    # ---- raw facts ----
    facts = [f"screen {rows}x{cols}",
             f"cursor at r{snapshot.cursor[0]}c{snapshot.cursor[1]}"
             + (" (hidden)" if snapshot.cursor_hidden else "")]
    if snapshot.title:
        facts.append(f'title "{snapshot.title}"')
    if snapshot.selected is not None:
        sel = snapshot.selected
        facts.append(f'highlighted row {sel.row}: "{sel.text[:60]}"'
                     f" ({snapshot.selected_reason})")
    if snapshot.menu_items:
        facts.append(f"{len(snapshot.menu_items)} highlighted span(s)")
    if snapshot.status_bar:
        facts.append(f'bottom line: "{snapshot.status_bar[:60]}"')
    if snapshot.errors:
        facts.append(f"{len(snapshot.errors)} error-looking line(s)")
    if snapshot.screen_reverse:
        facts.append("screen-wide reverse video (DECSCNM)")
    lines.append("facts: " + "; ".join(facts))

    # ---- ranked paradigms ----
    ranked = classify(snapshot)
    if not ranked:
        lines.append("paradigm: nothing matched -- likely free-flowing output "
                     "or an idle/blank screen. Consider wait-regex for a "
                     "known marker, or just read the text.")
    else:
        best, conf = ranked[0]
        lines.append(f"paradigm: {best.name} ({conf:.2f}) -- {best.description}")
        if len(ranked) > 1:
            alts = ", ".join(f"{p.name}({c:.2f})" for p, c in ranked[1:4])
            lines.append(f"also plausible: {alts}")

    return "\n".join(lines)
