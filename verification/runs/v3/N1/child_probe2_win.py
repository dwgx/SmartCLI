"""N1 Windows child: ask a CPR question, then produce bounded output.

Same shape as the POSIX sibling, with the Windows console API instead of termios.
The child writes its own report file, so the observer never grades itself.

Run: python child_probe2_win.py --bytes N --out PATH
"""
from __future__ import annotations

import argparse
import json
import msvcrt
import os
import sys
import time

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

    # The console must be in raw VT input mode, or an injected ESC[6n reply is
    # swallowed by the console's line editor and the fixture would report "not
    # answered" for a reason that has nothing to do with the daemon.
    raw_ok = False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)          # STD_INPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200
            ENABLE_LINE_INPUT = 0x0002
            ENABLE_ECHO_INPUT = 0x0004
            new_mode = (mode.value | ENABLE_VIRTUAL_TERMINAL_INPUT) & ~(
                ENABLE_LINE_INPUT | ENABLE_ECHO_INPUT)
            raw_ok = bool(kernel32.SetConsoleMode(handle, new_mode))
    except Exception:
        raw_ok = False

    start = time.monotonic()
    state = {"cpr_answered": False, "cpr_wait_s": None, "written": 0, "done": False,
             "cpr_reply": "", "seconds": 0.0, "raw_console": raw_ok}
    report(args.out, **state)

    # 1) the query first: only a servicing daemon can answer it
    sys.stdout.write("\x1b[6n")
    sys.stdout.flush()
    buf = ""
    deadline = time.monotonic() + args.cpr_timeout
    while time.monotonic() < deadline:
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            buf += ch
            if "R" in buf and "[" in buf:
                state["cpr_answered"] = True
                break
        else:
            time.sleep(0.02)
    state["cpr_wait_s"] = round(time.monotonic() - start, 3)
    state["cpr_reply"] = repr(buf[:32])
    report(args.out, **state)

    # 2) then a bounded payload, one progress report per chunk
    chunk = "." * STEP
    out = sys.stdout
    while state["written"] < args.bytes:
        out.write(chunk[: args.bytes - state["written"]])
        out.flush()
        state["written"] += min(STEP, args.bytes - state["written"])
        state["seconds"] = round(time.monotonic() - start, 3)
        report(args.out, **state)
    state["done"] = True
    state["seconds"] = round(time.monotonic() - start, 3)
    report(args.out, **state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
