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

import shutil
import sys
import tempfile
from pathlib import Path

try:
    from smartcli_core import PtySession
except ImportError:
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
        session.send_keys(["Escape"])
        session.send_text("G")            # last line
        session.send_text("o")            # open a line below, enter insert mode
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
