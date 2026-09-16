"""N1 POSIX child: ask a question FIRST, then produce bounded output.

The X3 fixture wrote 512 KiB and only then sent ESC[6n, so "CPR unanswered" could
not be separated from "the payload never finished". Here the query comes first:
a daemon that services the transport while nobody asks must answer it promptly,
and the bounded payload that follows must also complete on its own.

The child writes its own report file, so the observer never grades itself.
"""
from __future__ import annotations

import argparse
import json
import os
import select
import time
import tty

STEP = 4096


def report(path: str, **fields) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(fields, fh)
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bytes", type=int, default=256 * 1024)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cpr-timeout", type=float, default=5.0)
    args = ap.parse_args()

    tty.setraw(0)
    start = time.monotonic()
    state = {"cpr_answered": False, "cpr_wait_s": None, "written": 0, "done": False,
             "cpr_reply": "", "seconds": 0.0}
    report(args.out, **state)

    # 1) the query first: only a servicing daemon can answer it
    os.write(1, b"\x1b[6n")
    buf = b""
    deadline = time.monotonic() + args.cpr_timeout
    while time.monotonic() < deadline:
        r, _, _ = select.select([0], [], [], 0.1)
        if r:
            buf += os.read(0, 64)
            if b"R" in buf and b"[" in buf:
                state["cpr_answered"] = True
                break
    state["cpr_wait_s"] = round(time.monotonic() - start, 3)
    state["cpr_reply"] = buf.decode("latin-1")[:32]
    report(args.out, **state)

    # 2) then a bounded payload, with a progress report per chunk
    chunk = b"." * STEP
    while state["written"] < args.bytes:
        n = os.write(1, chunk[:args.bytes - state["written"]])
        state["written"] += n
        state["seconds"] = round(time.monotonic() - start, 3)
        report(args.out, **state)
    state["done"] = True
    state["seconds"] = round(time.monotonic() - start, 3)
    report(args.out, **state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
