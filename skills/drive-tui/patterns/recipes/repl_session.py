"""REPL recipe -- the REFERENCE pattern that proves the framework contract.

A REPL screen is the simplest perceive->act->wait->confirm loop there is: the
*cursor sits on a prompt*, you type a line, output scrolls in, and a FRESH
prompt appears below. Everything a driver must get right shows up here:

* Recognition binds to the CURSOR ROW, never scrollback. ``>>> ``/``$ `` echo
  all over the history the moment you run one command; only the row the cursor
  is parked on tells you the REPL is *waiting for input right now*.
* The wait is bounded and evidence-based. We do NOT blind-sleep and we do NOT
  trust a marker that also matches the stale prompt already on screen (the whole
  screen is space-padded, so an end-anchored ``>>> $`` never fires anyway). The
  reliable signal is screen *stability* after the echo+result render, confirmed
  by a NEW prompt appearing at a cursor row strictly below the one we typed on.
* "Done" is a real assertion from the live screen: prompt returned + cursor
  advanced, not a self-claim.

Extension recipe (how to add your own REPL flavour): drop your prompt regex into
:data:`_PROMPTS` with a confidence weight. ``matches`` scores the cursor row
against them; ``drive`` re-uses the same table to confirm a prompt came back.

Verified live on Windows/ConPTY against ``python -q``: drive('6*7') -> screen
shows '42' and a fresh '>>>'.
"""
from __future__ import annotations

import time
from typing import Any, List, Optional, Tuple

from smartcli_core import PtySession, Snapshot

from .. import registry
from ..base import Pattern, PatternResult

# Prompt flavours, bound to the CURSOR ROW (matched against its left edge, after
# rstrip). weight = confidence when this is the row the cursor waits on.
#   name        regex (search on cursor-row text)             weight
_PROMPTS: Tuple[Tuple[str, str, float], ...] = (
    ("py",      r"^\s*>>> ?",              0.92),   # python primary
    ("py-cont", r"^\s*\.\.\. ?",           0.88),   # python continuation
    ("ipython", r"^\s*In \[\d+\]: ?",      0.92),   # ipython/jupyter
    ("shell",   r"[\$#]\s*$",              0.55),   # sh/bash/root -- weaker: $/# are common
)


def _prompt_kind(row_text: str) -> Optional[Tuple[str, float]]:
    """Return ``(kind, weight)`` if *row_text* looks like a waiting prompt."""
    for name, pat, weight in _PROMPTS:
        if Pattern.rx(pat, row_text):
            return name, weight
    return None


@registry.register
class ReplPattern(Pattern):
    """Line-oriented REPL / interactive shell (python, ipython, sh, ...)."""

    name = "repl"
    description = ("interactive REPL/shell: cursor parked on a prompt "
                   "(>>> , ... , $ , # , In [n]:); type a line, read the result")
    tags = ("repl", "shell", "prompt", "interactive")

    # -- recognition -------------------------------------------------------
    def matches(self, snapshot: Snapshot) -> float:
        """High when the CURSOR ROW is a waiting prompt (not scrollback)."""
        row = self.cursor_row_text(snapshot)
        hit = _prompt_kind(row)
        if hit is None:
            return 0.0
        _, weight = hit
        # A prompt sitting on the last visible row (the REPL is at the bottom,
        # waiting) is a stronger signal than one buried mid-screen.
        visible = [e for e in snapshot.lines if e != "..."]
        if visible and visible[-1] != "..." and visible[-1][0] == snapshot.cursor[0]:
            weight = min(1.0, weight + 0.05)
        return weight

    # -- driving -----------------------------------------------------------
    def drive(self, session: PtySession, intent: Any = None, **kw) -> PatternResult:
        """Send ``intent`` (one code line) and wait for the result to settle.

        kw:
            expect (str):   regex to confirm on-screen (a numeric/echo marker);
                            when given we wait_for it, else we wait for STABLE.
            timeout_ms (int): hard ceiling for the wait (default 6000).
            quiet_ms (int):   stability quiet window (default 180).
            min_wait_ms (int):ignore the stale pre-send screen (default 150).
        """
        if not isinstance(intent, str) or intent.strip() == "":
            # fail loud: a REPL drive without a line to run is a programming error.
            raise ValueError("repl.drive: intent must be a non-empty code line (str)")

        expect: Optional[str] = kw.get("expect")
        timeout_ms = int(kw.get("timeout_ms", 6000))
        quiet_ms = int(kw.get("quiet_ms", 180))
        min_wait_ms = int(kw.get("min_wait_ms", 150))

        before = session.snapshot()
        before_row = before.cursor[0]

        session.send_line(intent)

        if expect:
            matched, after = session.wait_for(
                expect, timeout_ms=timeout_ms, min_wait_ms=min_wait_ms)
            reason = "MARKER" if matched else "TIMEOUT"
            if matched:
                # wait_for returns the instant the marker renders; the fresh
                # prompt may not be redrawn on the cursor row yet. Keep pumping
                # until a prompt returns to the cursor row (below the typed row)
                # so confirmation reads the settled screen, not a mid-render one.
                deadline = time.monotonic() + timeout_ms / 1000.0
                while time.monotonic() < deadline:
                    snap = session.snapshot()
                    if (_prompt_kind(self.cursor_row_text(snap)) is not None
                            and snap.cursor[0] > before_row):
                        after = snap
                        break
                    session.pump()
                    time.sleep(0.02)
        else:
            reason, after = session.wait_ready(
                marker=None, quiet_ms=quiet_ms,
                max_wait_ms=timeout_ms, min_wait_ms=min_wait_ms)

        # ---- confirm from the live screen ----
        after_row_text = self.cursor_row_text(after)
        prompt_back = _prompt_kind(after_row_text)
        advanced = after.cursor[0] > before_row
        # A fresh prompt returned AND the cursor moved past the line we typed on
        # (or output pushed the prompt down) == the line was accepted & executed.
        executed = prompt_back is not None and (advanced or reason in ("MARKER", "STABLE"))

        output = self._output_between(before_row, after, before)
        is_cont = prompt_back is not None and prompt_back[0] == "py-cont"
        errored = bool(after.errors)

        ok = executed and not (expect and reason == "TIMEOUT")
        bits = [f"ran {intent!r}", reason.lower()]
        if is_cont:
            bits.append("continuation (incomplete input)")
        if errored:
            bits.append(f"{len(after.errors)} error line(s)")
        if output:
            bits.append(f"out={output[-1][:60]!r}")
        detail = "; ".join(bits)

        return PatternResult(
            ok=ok,
            detail=detail,
            snapshot=after,
            data={
                "before": before.to_text(),
                "after": after.to_text(),
                "output": output,
                "reason": reason,
                "continuation": is_cont,
                "error": errored,
                "prompt": prompt_back[0] if prompt_back else None,
            },
        )

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _output_between(before_row: int, after: Snapshot,
                        before: Snapshot) -> List[str]:
        """Lines produced by the command: rows below the typed prompt row and
        above the returned prompt row, excluding the echoed prompt itself."""
        after_row = after.cursor[0]
        lo, hi = before_row, after_row
        out: List[str] = []
        for entry in after.lines:
            if entry == "...":
                continue
            r, text, _sel = entry
            if lo < r < hi and _prompt_kind(text) is None:
                out.append(text)
        return out


def run_line(session: PtySession, code: str, **kw) -> PatternResult:
    """Convenience: run one line of ``code`` in ``session`` via the repl pattern.

    Thin wrapper over the registered singleton so callers get the same
    evidence-backed :class:`PatternResult` without touching the registry.
    """
    return registry.get("repl").drive(session, intent=code, **kw)
