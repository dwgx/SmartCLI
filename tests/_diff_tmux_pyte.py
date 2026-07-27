#!/usr/bin/env python3
"""_diff_tmux_pyte.py — differential test: our pyte screen model vs REAL tmux.

The whole project rests on one unproven premise: that feeding bytes to pyte
yields the same cell grid a real terminal would show. Every wait primitive,
every selected-row detection, every snapshot is only as true as that premise.
Until now it was asserted, never measured — the screenshot harness honestly
labels itself `pyte-simulation`, which is exactly the point: a simulation
agreeing with itself proves nothing.

This probe feeds the SAME bytes to both emulators and compares the resulting
grids cell by cell:

    bytes ──> tmux pane (real VT emulator) ──> capture-pane ──┐
          └─> ScreenModel (pyte)          ──> display        ─┴─> diff

A disagreement is a real perception bug: the agent would "see" something the
user's terminal does not show.

RED LINE COMPLIANCE: one tmux session at a time, killed before the next case
starts, zero-residue asserted at the end. tmux runs with `-f /dev/null` so the
user's own config cannot skew the emulator.

Normalizations (honest, and deliberately narrow — each one was traced to a
representation or test-rig artifact, NOT to an emulation difference):
  * trailing spaces per line and trailing blank rows: pyte right-pads rows to
    the full width, tmux's capture-pane does not.
  * literal TAB: capture-pane emits the tab byte as-is where we have already
    expanded it to 8-column tab stops. Verified equal after ``expandtabs(8)``.
  * Unicode normalization: we store NFC-composed combining marks (pyte composes
    them); capture-pane may emit either form. Verified identical after NFC.
  * ``stty -onlcr`` in the payload runner: without it the pane's tty driver
    translates LF to CRLF *before* the emulator sees it, so a bare-LF case would
    compare CRLF behaviour on the tmux side and bare-LF on ours. With ONLCR off,
    real tmux stair-steps bare LF exactly as we do — confirming HARD RULE 7
    rather than contradicting it.
Anything else that differs is reported as a failure.

Exit 0 = every case agrees.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unicodedata
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smartcli_core.screen_model import ScreenModel  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SESSION = "smartcli_diff"
FAILURES: list[str] = []
CHECKS = 0


def check(cond: bool, label: str, detail: str = "") -> bool:
    global CHECKS
    CHECKS += 1
    if not cond:
        FAILURES.append(label)
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail and not cond else ""))
    return cond


def tmux(*args: str, check_rc: bool = True) -> subprocess.CompletedProcess:
    """Run tmux with the user's config ignored so emulation is vanilla."""
    cp = subprocess.run(["tmux", "-f", "/dev/null", *args],
                        capture_output=True, text=True, timeout=30)
    if check_rc and cp.returncode != 0:
        raise RuntimeError(f"tmux {args[0]} failed: {cp.stderr.strip()}")
    return cp


def kill_session() -> None:
    subprocess.run(["tmux", "-f", "/dev/null", "kill-session", "-t", SESSION],
                   capture_output=True, text=True, timeout=30)


def normalize(lines: list[str]) -> list[str]:
    """Apply only the representation-level normalizations (see module docstring)."""
    out = [unicodedata.normalize("NFC", ln.expandtabs(8)).rstrip() for ln in lines]
    while out and out[-1] == "":
        out.pop()
    return out


def tmux_grid(payload: bytes, cols: int, rows: int) -> list[str]:
    """Render payload in a REAL tmux pane and capture the resulting grid."""
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "payload.bin"
        f.write_bytes(payload)
        # `cat` emits the bytes; the pane's emulator interprets them. Then sleep
        # so the pane stays alive for capture (a dead pane closes the window).
        kill_session()
        # `stty -onlcr` is essential: without it the pane's tty driver rewrites
        # LF as CRLF before the emulator sees it, so bare-LF cases would not be
        # testing the emulator at all (see module docstring).
        tmux("new-session", "-d", "-s", SESSION, "-x", str(cols), "-y", str(rows),
             "sh", "-c", f"stty -onlcr; cat {f}; sleep 60")
        try:
            # Poll for stability instead of sleeping blindly — the same
            # discipline this project preaches for driving real programs.
            prev, stable = None, 0
            for _ in range(40):
                cur = tmux("capture-pane", "-p", "-t", SESSION).stdout
                if cur == prev:
                    stable += 1
                    if stable >= 3:
                        break
                else:
                    stable = 0
                prev = cur
                time.sleep(0.05)
            return (prev or "").split("\n")
        finally:
            kill_session()


def pyte_grid(payload: bytes, cols: int, rows: int) -> list[str]:
    m = ScreenModel(cols=cols, rows=rows)
    m.feed(payload)
    return m.display


def compare(name: str, payload: bytes, cols: int = 40, rows: int = 8) -> None:
    real = normalize(tmux_grid(payload, cols, rows))
    ours = normalize(pyte_grid(payload, cols, rows))
    if real == ours:
        check(True, f"{name}: grids identical ({len(real)} rows)")
        return
    # Report the first divergence precisely — that is the actionable part.
    detail = ""
    for i in range(max(len(real), len(ours))):
        r = real[i] if i < len(real) else "<no row>"
        o = ours[i] if i < len(ours) else "<no row>"
        if r != o:
            detail = f"row {i}: tmux={r!r} ours={o!r}"
            break
    else:
        detail = f"row count: tmux={len(real)} ours={len(ours)}"
    check(False, f"{name}: grids identical", detail)


# --------------------------------------------------------------------------
# Cases. Each targets a mechanism the project actually depends on.
# --------------------------------------------------------------------------

CASES: list[tuple[str, bytes, int, int]] = [
    # 1. The baseline: does plain text land in the same cells at all?
    ("plain CRLF text", b"hello\r\nworld\r\n", 40, 8),

    # 2. HARD RULE 7 in this repo: bare LF does not return to column 0. If pyte
    #    and tmux disagree here, every multi-line snapshot is skewed.
    ("bare LF stair-step", b"aaa\nbbb\nccc\n", 40, 8),

    # 3. CJK wide cells — the claim that columns never desync rests on this.
    ("CJK wide chars", "中文测试\r\nabcd\r\n".encode(), 40, 8),

    # 4. Mixed CJK + ASCII alignment (the self_test asserts columns line up).
    ("CJK+ASCII mixed", "a中b文c\r\nabcdefg\r\n".encode(), 40, 8),

    # 5. Cursor addressing (CUP) — recipes navigate by absolute position.
    ("CUP absolute move", b"\x1b[3;5Hmarker\r\n", 40, 8),

    # 6. Erase-in-display — TUIs repaint with this constantly.
    ("ED erase display", b"junk\r\njunk2\r\n\x1b[H\x1b[2Jclean\r\n", 40, 8),

    # 7. Erase-in-line.
    ("EL erase line", b"abcdefghij\r\x1b[3C\x1b[Kxy\r\n", 40, 8),

    # 8. Autowrap at the right margin — off-by-one here shifts whole screens.
    ("autowrap at margin", (b"x" * 45) + b"\r\n", 40, 8),

    # 9. Exactly-full line: the classic deferred-wrap ambiguity.
    ("exactly full row", (b"y" * 40) + b"Z\r\n", 40, 8),

    # 10. Tabs — form/menu layouts use them.
    ("tab stops", b"a\tb\tc\r\n", 40, 8),

    # 11. Backspace overwrite (password prompts, line editing).
    ("backspace overwrite", b"abcd\x08\x08XY\r\n", 40, 8),

    # 12. SGR colour runs must not consume cells.
    ("SGR colour runs", b"\x1b[31mred\x1b[0m-\x1b[1mbold\x1b[0m\r\n", 40, 8),

    # 13. Truecolor (what cmd-art emits).
    ("truecolor SGR", b"\x1b[38;2;255;0;128mpink\x1b[0m\r\n", 40, 8),

    # 14. Box drawing (tui-ui's entire output).
    ("box drawing", "┌──┐\r\n│ab│\r\n└──┘\r\n".encode(), 40, 8),

    # 15. Scrolling past the bottom — long output streams do this.
    ("scroll past bottom", b"".join(f"line{i}\r\n".encode() for i in range(12)), 40, 8),

    # 16. Explicit scroll region (DECSTBM) — pagers and progress bars use it.
    ("DECSTBM scroll region", b"\x1b[2;4r\x1b[2Hone\r\ntwo\r\nthree\r\nfour\r\n", 40, 8),

    # 17. Carriage-return overwrite in place (progress bars / spinners).
    ("CR overwrite in place", b"50%\r100%\r\n", 40, 8),

    # 18. Insert/delete line (DL/IL) — list widgets scroll with these.
    ("IL/DL line ops", b"a\r\nb\r\nc\r\n\x1b[1;1H\x1b[L", 40, 8),

    # 19. Delete char / insert char.
    ("DCH/ICH char ops", b"abcdef\r\x1b[2C\x1b[2P\r\n", 40, 8),

    # 20. Cursor save/restore (DECSC/DECRC).
    ("DECSC/DECRC save-restore", b"\x1b[2;2Hab\x1b7\x1b[5;5Hxy\x1b8ZZ\r\n", 40, 8),

    # 21. Reverse index (RI) — scroll-up inside a region.
    ("RI reverse index", b"\x1b[3Hmiddle\x1bMabove\r\n", 40, 8),

    # 22. A narrow terminal: off-by-one bugs surface at small widths.
    ("narrow 10-col wrap", (b"abcdefghijkl"), 10, 5),

    # 23. VS16 emoji presentation — a width claim I corrected in the docs.
    ("VS16 emoji", "a♀️b\r\nabc\r\n".encode(), 40, 8),

    # 24. ZWJ emoji sequence — the docs now claim 4 cells for this family.
    ("ZWJ emoji sequence", "x\U0001F469‍\U0001F4BBy\r\nabcdefg\r\n".encode(), 40, 8),

    # 25. Combining accent — one cell or two?
    ("combining accent", "éabc\r\nabcde\r\n".encode(), 40, 8),
]


def main() -> int:
    if not subprocess.run(["which", "tmux"], capture_output=True).returncode == 0:
        print("SKIP: tmux not on PATH (this probe needs a real tmux)")
        return 0

    ver = subprocess.run(["tmux", "-V"], capture_output=True, text=True).stdout.strip()
    print("=" * 72)
    print("Differential: real tmux vs our pyte ScreenModel")
    print(f"  {ver} | python {sys.version.split()[0]} | {sys.platform}")
    print("=" * 72)
    print("\nNOTE: only representation-level differences are normalized away")
    print("      (trailing pad, literal TAB, NFC; ONLCR off in the runner).")
    print("      Everything else counts as a real perception gap.\n")

    try:
        for name, payload, cols, rows in CASES:
            compare(name, payload, cols, rows)
    finally:
        kill_session()

    # Zero-residue assertion: no session of ours may survive.
    cp = subprocess.run(["tmux", "-f", "/dev/null", "list-sessions"],
                        capture_output=True, text=True)
    leaked = [ln for ln in cp.stdout.splitlines() if ln.startswith(SESSION)]
    check(not leaked, "zero leaked tmux sessions", detail=str(leaked))

    print(f"\n{CHECKS - len(FAILURES)}/{CHECKS} checks passed")
    if FAILURES:
        print(f"\nDIVERGENCES ({len(FAILURES)}) — each is a real perception gap:")
        for f in FAILURES:
            print("   -", f)
        return 1
    print("\nPASS: our screen model agrees with a real terminal on every case.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
