#!/usr/bin/env python3
"""_diff_two_refs.py — three-way differential: tmux AND GNU screen vs our model.

`_diff_tmux_pyte.py` proves we match tmux. That is weaker than it sounds: a
single reference cannot distinguish "correct" from "identical to tmux". This
probe adds a SECOND independent emulator (GNU screen, a different codebase with
its own VT parser) and only treats a behaviour as ground truth when **both
references agree**:

    both refs agree + we match      -> PASS (real agreement)
    both refs agree + we differ     -> FAIL (our bug)
    refs disagree with each other   -> UNDEFINED (recorded, not judged)

That third bucket is the point. During the fuzz work two behaviours landed there
— IL/DL issued from outside a DECSTBM region, and the display width of a ZWJ
emoji cluster — and in both cases picking a side would have meant hard-coding one
terminal's opinion as truth. Documenting them is the honest outcome.

Both references are driven the same way so the comparison is fair: rendered
inside a tmux pane (for screen, tmux is only the capture mechanism — screen owns
the emulation), with `stty -onlcr -echo` so the tty layer cannot rewrite the
payload and no shell echo lands on the grid.

RED LINE COMPLIANCE: one emulator process at a time, killed between cases and in
a finally block, zero residue asserted at the end.

Exit 0 = every case where the references agree, we agree too.
SKIP (exit 0) when either reference is unavailable.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smartcli_core.screen_model import ScreenModel  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SESSION = "smartcli_2ref"
COLS, ROWS = 40, 10
RESET = b"\x1bc\x1b[!p\x1b[r\x1b[H\x1b[2J\x1b[0m\x1b[?7h"

FAILURES: list[str] = []
UNDEFINED: list[tuple[str, str, str]] = []
SKIPPED_DECODE: list[str] = []
AGREED = 0


def tmux(*args: str, check_rc: bool = True) -> subprocess.CompletedProcess:
    cp = subprocess.run(["tmux", "-f", "/dev/null", *args],
                        capture_output=True, text=True, timeout=60)
    if check_rc and cp.returncode != 0:
        raise RuntimeError(f"tmux {args[0]}: {cp.stderr.strip()}")
    return cp


def cleanup() -> None:
    subprocess.run(["tmux", "-f", "/dev/null", "kill-session", "-t", SESSION],
                   capture_output=True, text=True, timeout=60)
    subprocess.run(["screen", "-wipe"], capture_output=True, timeout=60)


def normalize(lines: list[str]) -> list[str]:
    """Representation-only normalizations (see _diff_tmux_pyte.py for each why)."""
    out = [unicodedata.normalize("NFC", ln.expandtabs(8)).rstrip() for ln in lines]
    while out and out[-1] == "":
        out.pop()
    return out


def _capture_stable(target: str, tries: int = 60, need: int = 3) -> str:
    prev, stable = None, 0
    for _ in range(tries):
        cur = tmux("capture-pane", "-p", "-t", target).stdout
        if cur == prev:
            stable += 1
            if stable >= need:
                break
        else:
            stable = 0
        prev = cur
        time.sleep(0.05)
    return prev or ""


def ref_grid(payload: bytes, use_screen: bool) -> list[str]:
    """Render payload in tmux, or in GNU screen hosted inside a tmux pane."""
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "p.bin"
        f.write_bytes(RESET + payload)
        inner = f'stty -onlcr -echo; cat {f}; sleep 40'
        if use_screen:
            rc = Path(td) / "screenrc"
            # `altscreen` defaults to OFF in GNU screen (man screen: "Initial
            # setting is `off'"). Without it screen ignores 47/1047/1049
            # entirely, so the alt-screen cases below were comparing against a
            # reference with the feature DISABLED — every one of them reported a
            # reference-vs-reference disagreement (UNDEFINED) for a rig reason,
            # not a semantic one. Exactly the "suspect the rig first" failure
            # this probe's own docstring warns about.
            rc.write_text("startup_message off\nvbell off\naltscreen on\n")
            cmd = f'screen -c {rc} sh -c "{inner}"'
        else:
            cmd = f'sh -c "{inner}"'
        cleanup()
        tmux("new-session", "-d", "-s", SESSION, "-x", str(COLS), "-y", str(ROWS),
             "sh", "-c", cmd)
        try:
            # screen needs longer to paint its first frame than a bare shell.
            if use_screen:
                time.sleep(1.2)
            return _capture_stable(SESSION).split("\n")
        finally:
            cleanup()


def ours(payload: bytes) -> list[str]:
    m = ScreenModel(cols=COLS, rows=ROWS)
    m.feed(RESET + payload)
    return m.display


def compare(name: str, payload: bytes) -> None:
    global AGREED
    a = normalize(ref_grid(payload, use_screen=False))   # tmux
    b = normalize(ref_grid(payload, use_screen=True))    # GNU screen
    mine = normalize(ours(payload))
    if a != b:
        # Distinguish a real semantic disagreement from a decoding limitation:
        # GNU screen renders U+FFFD for astral-plane (4-byte UTF-8) codepoints,
        # so any emoji outside the BMP makes it differ from tmux for reasons that
        # say nothing about terminal semantics. Verified: screen handles CJK and
        # VS16 (both BMP) identically to tmux, and only fails on astral codepoints.
        if "�" in "".join(b) and "�" not in "".join(a):
            SKIPPED_DECODE.append(name)
            print(f"  [SKIP ] {name}: screen cannot decode an astral codepoint "
                  f"(not a semantic disagreement)")
            return
        UNDEFINED.append((name, str(a[:1]), str(b[:1])))
        print(f"  [UNDEF] {name}: references disagree — not judged")
        print(f"          tmux={a[:1]} screen={b[:1]} ours={mine[:1]}")
        return
    AGREED += 1
    if mine == a:
        print(f"  [PASS ] {name}: both references agree, we match")
        return
    detail = ""
    for i in range(max(len(a), len(mine))):
        x = a[i] if i < len(a) else "<none>"
        y = mine[i] if i < len(mine) else "<none>"
        if x != y:
            detail = f"row {i}: refs={x!r} ours={y!r}"
            break
    FAILURES.append(f"{name}: {detail}")
    print(f"  [FAIL ] {name}: both references agree and we DIFFER\n          {detail}")


# --------------------------------------------------------------------------
# Cases. Weighted toward mechanisms where a single reference could mislead:
# every fix made during the fuzz work, plus the surfaces drive-tui depends on.
# --------------------------------------------------------------------------

CASES: list[tuple[str, bytes]] = [
    # Baselines — if these disagree the rig is wrong, not the code.
    ("plain CRLF", b"hello\r\nworld\r\n"),
    ("CUP addressing", b"\x1b[3;5Hmark"),
    ("erase display", b"junk\r\n\x1b[H\x1b[2Jclean"),
    ("erase line", b"abcdefghij\r\x1b[3C\x1b[K"),
    ("autowrap", b"z" * 45),
    ("exactly full row", b"y" * 40 + b"Z"),
    ("tab stops", b"a\tb\tc"),
    ("backspace overwrite", b"abcd\x08\x08XY"),
    ("SGR runs", b"\x1b[31mred\x1b[0m-\x1b[1mbold\x1b[0m"),
    ("box drawing", "┌──┐\r\n│ab│\r\n└──┘".encode()),
    ("CJK wide", "中文测试\r\nabcd".encode()),
    ("CJK+ASCII columns", "a中b文c\r\nabcdefg".encode()),
    ("scroll past bottom", b"".join(f"L{i}\r\n".encode() for i in range(14))),

    # Every divergence fixed during the fuzz work, now re-checked against TWO
    # references. If any of these regress, both refs will say so together.
    ("IL keeps column", b"\x1b[5;8H\x1b[1Labc"),
    ("DL keeps column", b"\x1b[5;8H\x1b[1Mabc"),
    ("IL count>1 then DL", b"\x1b[3LQ\x1b[1M"),
    ("half-overwrite CJK", "中".encode() + b"\x1b[1DX"),
    ("half-overwrite emoji", "\U0001F600".encode() + b"\x1b[1DX"),
    ("DCH on wide glyph", "中x".encode() + b"\r\x1b[1P"),
    ("DCH on ascii", b"abcx\r\x1b[1P"),
    ("NEL returns to col 0", b"\x1b[2;5H\x1bE0123"),
    ("bare LF keeps column", b"aaa\nbbb\nccc"),
    ("CUU outside region", b"\r\n\x1b[9;10r\r\n\x1b[2A0123"),
    ("autowrap below region", b"\x1b[3;6r\x1b[7;37Hxxxxxxxx"),
    ("wide glyph at margin", b"\x1b[1;40H" + "\U0001F600".encode()),
    ("wide glyph exact fit", b"\x1b[1;39H" + "\U0001F600".encode()),
    ("orphaned stub", "♀️".encode() * 3 + b"\r\x1b[3@" + "│".encode() * 3
     + b"\x1b[5;7r" + "中文".encode() * 2 + b"\x1b[3@" + "│".encode() * 2
     + "▄".encode() * 2),

    # Surfaces drive-tui depends on that the curated probe does not cover.
    ("DECSTBM scroll region", b"\x1b[2;4r\x1b[2Hone\r\ntwo\r\nthree\r\nfour"),
    ("ICH pushes right", b"abcdef\r\x1b[3@"),
    ("ICH over wide", "中文".encode() + b"\r\x1b[3@"),
    ("DECSC/DECRC", b"\x1b[2;2Hab\x1b7\x1b[5;5Hxy\x1b8ZZ"),
    ("reverse index", b"\x1b[3Hmiddle\x1bMabove"),
    ("CR overwrite", b"50%\r100%"),
    ("VS16 emoji width", "a♀️b".encode()),
    ("combining accent", "éabc".encode()),

    # The alternate screen buffer and SGR sub-parameters (both added 2026-07-27).
    ("alt screen enter", b"main\r\n\x1b[?1049hALT"),
    ("alt screen round-trip", b"main1\r\nmain2\r\n\x1b[?1049hALT\x1b[?1049l"),
    ("SGR colon subparams", b"\x1b[4:3munder\x1b[0m"),
    ("DECCKM application cursor", b"\x1b[?1hprompt"),
    ("bracketed paste mode", b"\x1b[?2004hpasted"),
]


def main() -> int:
    for tool in ("tmux", "screen"):
        if subprocess.run(["which", tool], capture_output=True).returncode != 0:
            print(f"SKIP: {tool} not on PATH (this probe needs both references)")
            return 0

    tv = subprocess.run(["tmux", "-V"], capture_output=True, text=True).stdout.strip()
    sv = subprocess.run(["screen", "--version"], capture_output=True,
                        text=True).stdout.strip() or "GNU screen"
    print("=" * 72)
    print("THREE-WAY differential: two independent emulators vs our model")
    print(f"  ref A: {tv}")
    print(f"  ref B: {sv}")
    print("=" * 72)
    print("\nA behaviour counts as ground truth only when BOTH references agree.")
    print("Where they disagree the case is recorded as UNDEFINED, not judged.\n")

    try:
        for name, payload in CASES:
            compare(name, payload)
    finally:
        cleanup()

    cp = subprocess.run(["tmux", "-f", "/dev/null", "list-sessions"],
                        capture_output=True, text=True)
    leaked = [ln for ln in cp.stdout.splitlines() if ln.startswith(SESSION)]
    if leaked:
        print(f"\n  [FAIL] leaked sessions: {leaked}")
        return 1
    print("\n  [PASS ] zero leaked emulator sessions")

    print(f"\n{AGREED - len(FAILURES)}/{AGREED} cases where both references agree, "
          f"we agree too")
    if SKIPPED_DECODE:
        print(f"\n{len(SKIPPED_DECODE)} case(s) skipped: GNU screen cannot decode "
              f"astral-plane codepoints, so it cannot arbitrate them")
        for name in SKIPPED_DECODE:
            print(f"   - {name}")
        print("   (these ARE covered against tmux alone by _diff_tmux_pyte.py)")
    if UNDEFINED:
        print(f"\n{len(UNDEFINED)} UNDEFINED (the references disagree with each "
              f"other — no ground truth to match):")
        for name, a, b in UNDEFINED:
            print(f"   - {name}: tmux={a} screen={b}")
    if FAILURES:
        print(f"\nDIVERGENCES ({len(FAILURES)}) — both references agree against us:")
        for f in FAILURES:
            print("   -", f)
        return 1
    print("\nPASS: on every behaviour two independent emulators agree about, "
          "our screen model agrees with them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
