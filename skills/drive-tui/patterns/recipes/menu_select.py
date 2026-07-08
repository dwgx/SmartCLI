"""Menu-select recipe -- arrow-key navigation of a highlighted list.

A menu screen has ONE highlighted row (reverse-video / distinct bg / bold) that
moves as you press Up/Down; Enter activates it. The snapshot already reduces the
colour grid to :attr:`Snapshot.selected` / :attr:`selected_line` /
:attr:`menu_items`, so recognition is a cheap read of those semantic fields --
we never re-scan cells and never key off bare text (list labels also appear in
plain output).

The hard part is DRIVING honestly. We do not assume Up moves the highlight up by
one: some apps wrap, some reorder, some consume the key. So the loop is
perceive->act->CONFIRM: read the selected row, send ONE arrow toward the target,
re-snapshot, and check the selection actually moved the way we expected. If it
didn't move at all we stop (dead key / non-navigable). If it wrapped or jumped we
recompute from the new position. The whole thing is bounded by a step budget so a
list that refuses to move can never spin forever.

Extension recipe: intent is a TARGET -- an int row-index into the menu items, or
a substring matched (case-insensitive) against item text. Add richer targeting
by extending :meth:`_resolve_target`.

STATUS: matches() and the move-and-confirm loop are exercised by a live throwaway
ANSI menu in this repo's self-test; see the RETURN notes from the build.
"""
from __future__ import annotations

from typing import Any, List, Optional

from smartcli_core import PtySession, Snapshot

from .. import registry
from ..base import Pattern, PatternResult


@registry.register
class MenuSelectPattern(Pattern):
    """A single-highlight list navigated with Up/Down and chosen with Enter."""

    name = "menu_select"
    description = ("vertical list with one highlighted row; navigate with "
                   "Up/Down arrows and activate with Enter")
    tags = ("menu", "list", "navigation")

    # -- recognition -------------------------------------------------------
    def matches(self, snapshot: Snapshot) -> float:
        """Confidence from a real highlighted row existing in the snapshot.

        Signals, strongest first: a ``selected`` span flagged by reverse/bg (the
        model's ``reverse_or_bg`` reason -- an actual highlight, not the cursor
        line), and several ``menu_items`` stacked in a column (a list, not a
        one-off banner). The cursor-line fallback alone is NOT a menu.

        Anti-signal (why this is not naive): the model scores BOLD as a highlight,
        so a bold REPL prompt (``>>> ``) or a bold heading trips ``menu_items``.
        A lone highlighted row that is ALSO the *visible cursor row* is therefore
        treated as a prompt/heading, not a selection bar -- a genuine full-screen
        menu either hides the cursor or highlights a row the cursor isn't on.
        """
        if snapshot.selected is None or snapshot.selected_line is None:
            return 0.0
        if snapshot.selected_reason != "reverse_or_bg":
            # only the cursor-line heuristic fired -> this is not a menu
            return 0.0

        items = snapshot.menu_items or []
        distinct_rows = {s.row for s in items}
        sel = snapshot.selected
        lone = len(distinct_rows) <= 1
        on_visible_cursor_row = (not snapshot.cursor_hidden
                                 and snapshot.selected_line == snapshot.cursor[0])
        if lone and on_visible_cursor_row:
            return 0.10  # bold prompt / heading, not a navigable list

        conf = 0.55  # a genuine highlighted row exists
        # Menus stack vertically: several highlighted spans on distinct rows is
        # the strongest list signal; a single reverse bar is still menu-ish.
        conf += 0.25 if len(distinct_rows) >= 2 else 0.10
        # Classic full-screen menus hide the cursor while a bar tracks selection.
        if snapshot.cursor_hidden:
            conf += 0.10
        # A short selected label (not a full-width status bar) is menu-ish.
        if 0 < len(sel.text.strip()) <= 40:
            conf += 0.10
        return min(1.0, conf)

    # -- driving -----------------------------------------------------------
    def drive(self, session: PtySession, intent: Any = None, **kw) -> PatternResult:
        """Move the highlight to ``intent`` and press Enter.

        intent:
            int -> target index into the current menu rows (0-based, in row order).
            str -> case-insensitive substring matched against menu row text.
        kw:
            max_steps (int):   arrow-press budget (default: 2*len+4, min 8).
            settle_ms (int):   quiet window after each arrow (default 120).
            press (bool):      send Enter on success (default True).
            enter_wait_ms (int): stability wait after Enter (default 600).
        """
        if intent is None:
            raise ValueError("menu_select.drive: intent required (int index or "
                             "substring to match against menu items)")

        settle_ms = int(kw.get("settle_ms", 120))
        press = bool(kw.get("press", True))
        enter_wait_ms = int(kw.get("enter_wait_ms", 600))

        snap = session.snapshot()
        rows = self._menu_rows(snap)
        if not rows:
            return PatternResult(False, "no highlighted menu rows to navigate",
                                 snapshot=snap, data={"rows": []})

        target_row = self._resolve_target(intent, rows, snap)
        if target_row is None:
            return PatternResult(
                False, f"target {intent!r} not found among {len(rows)} menu rows",
                snapshot=snap,
                data={"rows": [t for _, t in rows], "target": intent})

        max_steps = int(kw.get("max_steps", max(8, 2 * len(rows) + 4)))

        cur_row = snap.selected_line
        if cur_row is None:
            # No highlighted row to navigate from (a plain list with no
            # selection bar, or the bar dropped between matches() and drive()).
            # Every other error path here returns cleanly; this one must too.
            return PatternResult(False, "no highlighted row to navigate from",
                                 snapshot=snap,
                                 data={"rows": [t for _, t in rows], "target": intent})
        moved_path: List[int] = [cur_row]
        stalls = 0
        steps = 0

        while cur_row != target_row and steps < max_steps:
            key = "Down" if target_row > cur_row else "Up"
            session.send_keys([key])
            steps += 1
            session.wait_ready(marker=None, quiet_ms=settle_ms,
                               max_wait_ms=1500, min_wait_ms=40)
            snap = session.snapshot()
            new_row = snap.selected_line
            if new_row is None:
                # highlight vanished -- the app left menu mode; stop, don't thrash.
                return PatternResult(
                    False, f"selection disappeared after {steps} {key} press(es)",
                    snapshot=snap,
                    data={"path": moved_path, "target": target_row, "steps": steps})
            if new_row == cur_row:
                # key didn't move the highlight. One retry tolerates a dropped
                # key; a second identical stall means it won't move -> bail.
                stalls += 1
                if stalls >= 2:
                    return PatternResult(
                        False,
                        f"selection stuck at row {cur_row} after {steps} presses "
                        f"(won't move toward {target_row})",
                        snapshot=snap,
                        data={"path": moved_path, "target": target_row,
                              "steps": steps})
            else:
                stalls = 0
            cur_row = new_row
            moved_path.append(cur_row)

        reached = cur_row == target_row
        if not reached:
            return PatternResult(
                False, f"did not reach row {target_row} within {max_steps} steps "
                f"(stopped at {cur_row})",
                snapshot=snap,
                data={"path": moved_path, "target": target_row, "steps": steps})

        chosen_text = self._row_text(snap, cur_row) or dict(rows).get(cur_row, "")

        if press:
            session.send_keys(["Enter"])
            reason, snap = session.wait_ready(
                marker=None, quiet_ms=150, max_wait_ms=enter_wait_ms, min_wait_ms=60)
        else:
            reason = "NO_ENTER"

        return PatternResult(
            ok=True,
            detail=f"selected row {cur_row} {chosen_text!r} in {steps} step(s); "
                   f"enter={reason.lower()}",
            snapshot=snap,
            data={
                "chosen_row": cur_row,
                "chosen_text": chosen_text,
                "steps": steps,
                "path": moved_path,
                "pressed_enter": press,
                "after": snap.to_text(),
            },
        )

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _menu_rows(snap: Snapshot) -> List[tuple]:
        """Ordered ``(row, text)`` of the option list, for index/substring targeting.

        Two cases:
        * Multi-highlight menu (>=2 highlighted rows): the highlighted spans ARE
          the option list -- unambiguous, use them directly.
        * Single reverse-bar menu: only the selected row is highlighted, so we
          recover the list as the CONTIGUOUS block of visible rows containing the
          selection. Blank lines / borders (which the snapshot collapses to the
          ``"..."`` marker) delimit that block, so a title line or footer above/
          below a blank separator is naturally excluded -- keeping int indices
          aligned to the real options.
        """
        items = snap.menu_items or []
        by_row = {}
        for s in items:
            by_row.setdefault(s.row, s.text.strip())
        if len(by_row) >= 2:
            return sorted(by_row.items())

        # Single-highlight: return the contiguous group holding selected_line.
        groups: List[List[tuple]] = []
        cur: List[tuple] = []
        for entry in snap.lines:
            if entry == "...":
                if cur:
                    groups.append(cur)
                    cur = []
                continue
            r, text, _sel = entry
            if text.strip():
                cur.append((r, text.strip()))
        if cur:
            groups.append(cur)

        sel = snap.selected_line
        if sel is not None:
            for g in groups:
                if any(r == sel for r, _ in g):
                    return g
        # no highlight to anchor on: fall back to the largest group
        return max(groups, key=len) if groups else []

    def _resolve_target(self, intent: Any, rows: List[tuple],
                        snap: Snapshot) -> Optional[int]:
        """Map ``intent`` to an absolute row index in the current screen."""
        if isinstance(intent, bool):  # guard: bool is an int subclass
            raise ValueError("menu_select: intent bool is ambiguous; use int/str")
        if isinstance(intent, int):
            if not (0 <= intent < len(rows)):
                return None
            return rows[intent][0]
        if isinstance(intent, str):
            needle = intent.strip().lower()
            if not needle:
                raise ValueError("menu_select: empty string target")
            for r, text in rows:
                if needle in text.lower():
                    return r
            return None
        raise ValueError(f"menu_select: intent must be int or str, got {type(intent).__name__}")

    @staticmethod
    def _row_text(snap: Snapshot, row: int) -> str:
        for entry in snap.lines:
            if entry != "..." and entry[0] == row:
                return entry[1].strip()
        return ""
