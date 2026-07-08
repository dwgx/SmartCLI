"""Wizard paradigm -- a multi-step / multi-screen flow (installer, setup guide).

WHY the signals are STEP LANGUAGE on the cursor/status line (matches):
    A wizard announces itself: "Step 1 of 5", a "Next >" button, "Press enter
    to continue", a numbered installer screen. These live on the cursor row or
    the status/nav line, so :meth:`matches` scores those, not body prose that
    might contain the word "step".

WHY this recipe COMPOSES the others (drive):
    Each wizard screen is really one of the simpler paradigms in disguise -- a
    confirm, a form, a progress wait, a menu. Rather than re-implement them,
    :meth:`drive` runs :func:`classify` on each screen and dispatches to the
    matching recipe via ``patterns.registry`` (imported LAZILY inside drive to
    avoid an import cycle: recipes import the framework, the framework loads
    recipes). A step can also be given as raw keys to send.

WHY the loop is HARD-bounded + marker-terminated (drive):
    A wizard with a mis-detected screen could advance forever. The loop is
    capped at ``len(steps)`` (plus a small slack for auto-advance screens) and
    stops early the moment a done/finish marker appears or the child exits.
    After each step we re-snapshot and require the screen to have CHANGED before
    counting progress; a stuck screen ends the run rather than spinning.

EXTENSION recipe: extend the step vocabulary in ``_run_step`` (a step dict may
carry ``pattern``+``value`` to force a recipe, or ``keys`` to send literally);
add finish words to ``_DONE_RE`` and advance hints to ``_ADVANCE_RE``.
"""
from __future__ import annotations

import re
from typing import Any, List, Optional

from smartcli_core import PtySession, Snapshot

from ..base import Pattern, PatternResult
from ..registry import register

_STEP_RE = re.compile(r"\bstep\s+\d+\s*(?:of|/)\s*\d+\b", re.I)
_NEXT_RE = re.compile(r"\bnext\s*>|>\s*next\b|\[\s*next\s*\]", re.I)
_ADVANCE_RE = re.compile(r"press\s+(enter|return|any\s+key)\s+to\s+continue|"
                         r"continue\b|proceed\b", re.I)
_DONE_RE = re.compile(r"\b(finish|finished|complete[d]?|done|"
                      r"installation\s+complete|setup\s+complete|"
                      r"all\s+set)\b", re.I)


@register
class WizardPattern(Pattern):
    """A multi-step installer/setup flow, advanced screen by screen."""

    name = "wizard"
    description = ("A multi-step wizard/installer: 'Step N of M', 'Next >', "
                   "'Press enter to continue' -- driven screen by screen, each "
                   "dispatched to the sub-paradigm that fits it.")
    tags = ("wizard", "multistep", "installer")

    # ---- recognition (cursor row + status/nav line) ----------------------
    def matches(self, snapshot: Snapshot) -> float:
        cur = Pattern.cursor_row_text(snapshot)
        status = (snapshot.status_bar or "")
        best = 0.0
        for text, home in ((cur, 0.9), (status, 0.9)):
            if not text:
                continue
            if _STEP_RE.search(text):
                best = max(best, home)
            if _NEXT_RE.search(text):
                best = max(best, home - 0.1)
            if _ADVANCE_RE.search(text):
                best = max(best, 0.5)
        # "Step N of M" anywhere on screen is a decent corroborator even off the
        # cursor row (installers often print it as a banner).
        if best < 0.9 and _STEP_RE.search(Pattern.visible_text(snapshot)):
            best = max(best, 0.55)
        return 1.0 if best > 1.0 else best

    # ---- drive: classify each screen -> dispatch -> advance --------------
    def drive(self, session: PtySession, intent: Any = None,
              advance_key: str = "Enter", max_steps: Optional[int] = None,
              **kw) -> PatternResult:
        """intent: a list of per-step actions. Each item may be:

          * a dict ``{"pattern": "confirm", "value": True}`` -> force that
            recipe with that intent,
          * a dict ``{"keys": ["Down", "Enter"]}`` -> send those keys literally,
          * ``None`` / ``{}`` -> auto: classify the screen and let the best
            recipe drive it (fallback: press ``advance_key``).
        """
        # Lazy import breaks the recipe<->framework import cycle.
        from .. import registry as _registry
        from ..classify import classify as _classify

        steps: List[Any] = list(intent) if isinstance(intent, (list, tuple)) else []
        scripted = len(steps)
        # Bound (contract: "loop bounded by step count"). With an explicit plan
        # the cap IS the plan length -- we never auto-drive past what was asked.
        # With no plan we auto-advance up to a sane ceiling, guarded by
        # loop-detection below so a repainting-but-unchanging screen can't spin.
        cap = max_steps if max_steps is not None else (scripted if scripted else 12)

        session.wait_stable(quiet_ms=150, max_wait_ms=1500)
        completed: List[dict] = []
        seen_keys: set[str] = set()

        for i in range(cap):
            snap = session.snapshot()
            screen_key = self._screen_key(snap)

            # Done marker on the cursor/status line ends the wizard cleanly.
            if self._is_done(snap):
                completed.append({"index": i, "action": "done-marker",
                                  "screen": screen_key})
                break
            if not session.is_alive():
                completed.append({"index": i, "action": "child-exited"})
                break

            # Auto (unscripted) loop-guard: if we've already acted on this exact
            # screen once and have no scripted step forcing another action, the
            # wizard is stuck (or effectively finished) -- stop rather than spin.
            step = steps[i] if i < scripted else None
            if step is None and screen_key in seen_keys:
                completed.append({"index": i, "action": "no-progress",
                                  "screen": screen_key})
                break
            seen_keys.add(screen_key)

            action = self._run_step(session, snap, step, advance_key,
                                    _registry, _classify)
            completed.append({"index": i, **action})

            # Confirm progress: the screen must change, else we are stuck.
            session.wait_stable(quiet_ms=150, max_wait_ms=2000)
            new_key = self._screen_key(session.snapshot())
            if new_key == screen_key and i >= scripted - 1:
                # No change AND no more scripted steps -> nothing left to do.
                completed[-1]["stalled"] = True
                break

        snap = session.snapshot()
        done = self._is_done(snap) or not session.is_alive()
        # Count real dispatched steps (exclude terminal-marker bookkeeping rows).
        _markers = {"done-marker", "child-exited", "no-progress"}
        ran = sum(1 for c in completed if c.get("action") not in _markers)
        # "Done" == reached a finish marker, or every scripted step was executed.
        ok = done or (scripted > 0 and ran >= scripted)
        detail = (f"ran {ran} step(s)"
                  + (f" of {scripted} scripted" if scripted else " (auto)")
                  + f"; {'reached done marker' if done else 'stopped'}")
        return PatternResult(
            ok=bool(ok), detail=detail, snapshot=snap,
            data={"steps": completed, "scripted": scripted,
                  "reached_done": done, "cap": cap},
        )

    # ---- helpers ----------------------------------------------------------
    @staticmethod
    def _is_done(snapshot: Snapshot) -> bool:
        cur = Pattern.cursor_row_text(snapshot)
        status = snapshot.status_bar or ""
        return bool(_DONE_RE.search(cur) or _DONE_RE.search(status))

    @staticmethod
    def _screen_key(snapshot: Snapshot) -> str:
        """A cheap change-detector: cursor row text + status line."""
        return Pattern.cursor_row_text(snapshot) + "\x00" + (snapshot.status_bar or "")

    def _run_step(self, session: PtySession, snap: Snapshot, step: Any,
                  advance_key: str, _registry, _classify) -> dict:
        """Execute one step, returning a record of what was done."""
        # 1) Explicit keys win.
        if isinstance(step, dict) and step.get("keys"):
            keys = list(step["keys"])
            session.send_keys(keys)
            return {"action": "keys", "keys": keys}

        # 2) Explicit sub-pattern.
        if isinstance(step, dict) and step.get("pattern"):
            name = step["pattern"]
            value = step.get("value", step.get("intent"))
            try:
                pat = _registry.get(name)
                res = pat.drive(session, intent=value,
                                **{k: v for k, v in step.items()
                                   if k not in ("pattern", "value", "intent", "keys")})
                return {"action": "pattern", "pattern": name,
                        "ok": res.ok, "detail": res.detail}
            except Exception as e:  # a bad sub-step must not crash the wizard
                return {"action": "pattern-error", "pattern": name, "error": str(e)}

        # 3) Auto: classify the current screen and let the best recipe drive it,
        #    excluding 'wizard' itself to avoid recursion.
        ranked = [(p, c) for (p, c) in _classify(snap) if p.name != self.name]
        if ranked and ranked[0][1] >= 0.6:
            best, conf = ranked[0]
            try:
                res = best.drive(session, intent=None)
                return {"action": "auto", "pattern": best.name,
                        "conf": round(conf, 2), "ok": res.ok}
            except Exception as e:
                return {"action": "auto-error", "pattern": best.name, "error": str(e)}

        # 4) Fallback: just advance (Enter / Next).
        session.send_keys([advance_key])
        return {"action": "advance", "key": advance_key}
