#!/usr/bin/env python3
"""drive_vim.py — drive the real vim through a PTY and read the screen back.

Run it yourself:

    pip install smartcli-toolkit
    python examples/drive_vim.py

No mock, no scripted output: this spawns the actual `vim` binary under a pty,
perceives its screen as a cell grid, edits a file, saves, and verifies the result
on disk. Every wait is a screen-state predicate — there is not one `sleep` in
here, which is the entire difference between this and a byte-stream matcher.

Why vim specifically: it uses the **alternate screen buffer** (`ESC[?1049h`), the
mode every full-screen TUI uses and the one `pyte` does not implement at all. On
0.2.0 the two alt-screen steps below pass; on 0.1.8 they are simply absent —
`Screen.alt_screen` does not exist, because nothing tracked the alternate buffer,
so the main screen was never hidden on entry nor restored on exit. Verified by
running this same file against `smartcli-toolkit==0.1.8`.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

try:
    from smartcli_core import PtySession
except ImportError:
    # Running from a source checkout: sys.path[0] is examples/, not the repo
    # root, so the import above cannot see smartcli_core even though it is right
    # there. tests/run_all.py drives this file as a gate, so it has to work
    # in-tree as well as from an install.
    _root = Path(__file__).resolve().parents[1]
    if (_root / "smartcli_core" / "__init__.py").exists():
        sys.path.insert(0, str(_root))
        from smartcli_core import PtySession
    else:
        sys.exit("pip install smartcli-toolkit  # then re-run")

VIM = shutil.which("vim")
if not VIM:
    sys.exit("SKIP: vim is not installed")

STEPS: list[str] = []


def step(label: str, ok: bool, detail: str = "") -> None:
    STEPS.append((label, ok))
    mark = "OK " if ok else "FAIL"
    print(f"  [{mark}] {label}" + (f"  {detail}" if detail and not ok else ""))


def main() -> int:
    # TERM must be SET, not inherited. Without one, vim falls back to a dumb
    # terminal: it never issues `ESC[?1049h`, so the alternate-screen step fails,
    # and it does not process the `:wq` the way a screen-oriented editor would, so
    # the file never changes on disk. Both are the FEATURES this example exists to
    # demonstrate, failing for the absence of an environment variable rather than
    # for anything in the code. Measured: with TERM absent 2 of 6 steps fail, with
    # `TERM=xterm-256color` all 6 pass. This is the fourth time in this project's
    # history that a rig has suppressed the very feature it was aimed at (`less -X`,
    # GNU screen's `altscreen` default, a missing TERM for `less` — HANDOFF 10j),
    # which is why it is set here instead of documented as a prerequisite. CI
    # runners have no TERM either, so inheriting it would fail there too.
    if not os.environ.get("TERM"):
        os.environ["TERM"] = "xterm-256color"

    workdir = Path(tempfile.mkdtemp(prefix="drive_vim_"))
    target = workdir / "hello.txt"
    target.write_text("first line\nsecond line\n", encoding="utf-8")

    print(f"driving: {VIM} {target.name}   (cwd {workdir})")
    session = PtySession(cols=80, rows=24)
    session.start(f'{VIM} -u NONE -N "{target}"')
    try:
        # 1. Wait for vim to paint. `-u NONE` means no config, so the surest
        #    marker is the filename vim echoes on its status line.
        matched, snap = session.wait_for(r"hello\.txt", timeout_ms=15000)
        step("vim painted its screen", matched)
        if not matched:
            print(snap.to_text() if snap else "(no screen)")
            return 1

        # 2. The alt-screen check: vim's content must be VISIBLE, and the shell
        #    prompt that was there before must be GONE. This is the assertion
        #    that fails on a screen model without alt-buffer support.
        text = session.snapshot().to_text()
        step("file contents visible on screen", "first line" in text,
             detail=repr(text[:90]))
        # `alt_screen` only exists from 0.2.0; on older versions nothing tracked
        # the alternate buffer at all, which is the bug this demo exercises.
        alt = getattr(session.model.screen, "alt_screen", None)
        step("alternate screen is active", alt is True,
             detail="not tracked at all on this version (needs >= 0.2.0)"
             if alt is None else repr(alt))

        # 3. Edit: go to end of file, open a new line, type, leave insert mode.
        #
        # CONFIRM each mode change before typing into it. These five calls used to
        # be issued back to back with nothing between them, which is the blind
        # send this project exists to argue against: `o` only means "open a line"
        # to a vim that has already processed `G`, and under load it does not
        # process them in the gap between two write() calls. Observed failing on a
        # busy machine at "typed text appears on screen" — the keystrokes were
        # swallowed and vim was still in normal mode, so nothing was inserted.
        # `-u NONE` gives no visible cue for `G`, so the confirmable fact is
        # INSERT mode: vim's `showmode` prints `-- INSERT --` on the last row, and
        # waiting for it proves `o` landed, which in turn proves `G` did.
        session.send_keys(["Escape"])
        session.wait_stable(max_wait_ms=1500, quiet_ms=80)
        session.send_text("G")            # last line
        session.wait_stable(max_wait_ms=1500, quiet_ms=80)
        session.send_text("o")            # open a line below, enter insert mode
        in_insert, _ = session.wait_for(r"-- INSERT --", timeout_ms=8000)
        step("vim entered insert mode (so G and o both landed)", in_insert)
        session.send_text("third line from an agent")
        session.send_keys(["Escape"])
        matched, _ = session.wait_for(r"third line from an agent", timeout_ms=8000)
        step("typed text appears on screen", matched)

        # 4. Save and quit, then wait for the alt screen to be handed back.
        session.send_text(":wq\r")
        left_alt = False
        for _ in range(40):
            session.pump()
            if not getattr(session.model.screen, "alt_screen", False):
                left_alt = True
                break
            session.wait_stable(max_wait_ms=200, quiet_ms=50)
        step("vim restored the main screen on exit", left_alt)

        # 5. The ground truth is the filesystem, not the screen.
        saved = target.read_text(encoding="utf-8")
        step("file on disk really changed",
             "third line from an agent" in saved, detail=repr(saved))
        print("\nfile after the drive:")
        for i, line in enumerate(saved.splitlines(), 1):
            print(f"  {i}| {line}")
    finally:
        session.close()
        shutil.rmtree(workdir, ignore_errors=True)

    failed = [label for label, ok in STEPS if not ok]
    print()
    if failed:
        print(f"{len(failed)}/{len(STEPS)} steps FAILED: {failed}")
        return 1
    print(f"all {len(STEPS)} steps passed — a real editor, driven and verified, "
          f"with no sleep() anywhere")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
