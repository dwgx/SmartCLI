"""POSIX child referee for the T03 write test: read exactly N bytes from stdin
(a raw-mode pty), then report length + sha256 to a file.

Using its own report file keeps the referee independent of the pty stream: the
parent compares the child's bytes, not the parent's own bookkeeping.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tty


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect", type=int, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    tty.setraw(0)                     # no echo, no canonical line editing
    digest = hashlib.sha256()
    got = 0
    while got < args.expect:
        chunk = os.read(0, 65536)
        if not chunk:                 # EOF before the expected length
            break
        digest.update(chunk)
        got += len(chunk)

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"received": got, "sha256": digest.hexdigest()}, fh)
    return 0 if got == args.expect else 1


if __name__ == "__main__":
    raise SystemExit(main())
