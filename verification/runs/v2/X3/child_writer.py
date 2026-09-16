"""POSIX child for the X3 idle probe.

Writes `--bytes` in 4 KiB steps, refreshing a JSON report after every step so an
outside observer can see HOW FAR it got and WHEN it stopped. Then it asks for a
cursor-position report (ESC[6n) and waits up to 3 s for the terminal's answer --
that answer can only come from a process that reads and services the session.

The report is the child's own testimony, so the probe does not grade the parent
using the parent's own bookkeeping.
"""
from __future__ import annotations

import argparse
import json
import os
import select
import time
import tty

STEP = 4096


def write_report(path: str, **fields) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(fields, fh)
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bytes", type=int, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    tty.setraw(0)
    state = {"written": 0, "done": False, "blocked_at": None, "cpr_answered": False,
             "steps": 0, "seconds": 0.0}
    write_report(args.out, **state)

    blob = b"." * STEP
    start = time.monotonic()
    while state["written"] < args.bytes:
        before = time.monotonic()
        written = os.write(1, blob)
        blocked = time.monotonic() - before
        if blocked > 0.05 and state["blocked_at"] is None:
            state["blocked_at"] = state["written"]
        state["written"] += written
        state["steps"] += 1
        state["seconds"] = round(time.monotonic() - start, 3)
        write_report(args.out, **state)
    state["done"] = True
    write_report(args.out, **state)

    # Device query: the reply can only arrive if somebody services the session.
    os.write(1, b"\x1b[6n")
    deadline = time.monotonic() + 3.0
    buf = b""
    while time.monotonic() < deadline:
        r, _, _ = select.select([0], [], [], 0.1)
        if r:
            buf += os.read(0, 64)
            if b"R" in buf and b"[" in buf:
                state["cpr_answered"] = True
                break
    state["cpr_reply"] = buf.decode("latin-1")[:32]
    state["seconds"] = round(time.monotonic() - start, 3)
    write_report(args.out, **state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
