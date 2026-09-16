"""T03 on a REAL POSIX pty: does the production write deliver every byte exactly once?

Independent referee: the child reads stdin in raw mode and writes its own
length+sha256 report to a file. The payload (256 KiB) is far larger than the pty
buffer, so the kernel forces the short/blocked writes the injected tests simulate;
the parent counts how many times the production loop had to wait for writability.

Run (inside a Linux container):  python T03/posix/test_posix_write.py --repo /repo
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import sys
import tempfile
import time

ap = argparse.ArgumentParser()
ap.add_argument("--repo", type=Path, required=True)
ap.add_argument("--bytes", type=int, default=256 * 1024)
ap.add_argument("--child", type=Path, default=Path(__file__).with_name("child_receiver.py"))
args = ap.parse_args()

sys.path.insert(0, str(args.repo))
from smartcli_core.pty_backend import IncompleteWrite, PosixPtyBackend  # noqa: E402

report_path = Path(tempfile.mkdtemp(prefix="t03-posix-")) / "child.json"
payload = bytes((i * 7 + 3) % 256 for i in range(args.bytes))

backend = PosixPtyBackend()
waits = {"n": 0, "again": 0}
real_select = select.select


def counting_select(r, w, x, timeout=None):
    """Count writability waits but never fake the result: the real select runs."""
    waits["n"] += 1
    return real_select(r, w, x, timeout)


select.select = counting_select          # only for this process
try:
    backend.spawn([sys.executable, str(args.child), "--expect", str(len(payload)),
                   "--out", str(report_path)], cols=120, rows=30)
    time.sleep(0.5)                      # let the child install raw mode
    t0 = time.monotonic()
    error = None
    try:
        backend.write(payload)           # ONE call, production method
    except IncompleteWrite as exc:
        error = exc
    elapsed = time.monotonic() - t0

    deadline = time.monotonic() + 10.0
    child = None
    while time.monotonic() < deadline:
        if report_path.exists():
            try:
                child = json.loads(report_path.read_text(encoding="utf-8"))
                break
            except json.JSONDecodeError:
                pass
        time.sleep(0.05)
finally:
    select.select = real_select
    backend.terminate()

expected_sha = hashlib.sha256(payload).hexdigest()
result = {
    "case": "T03-posix-real-pty",
    "evidence": "E4 (real pty.fork + real kernel buffers)",
    "io_mode": "native transport; production PosixPtyBackend.write",
    "planned_bytes": len(payload),
    "planned_sha256": expected_sha,
    "write_call_error": None if error is None else f"{type(error).__name__}: {error}",
    "written_bytes_reported": None if error is None else error.written_bytes,
    "write_seconds": round(elapsed, 3),
    "writability_waits": waits["n"],
    "child_report": child,
    "pass": bool(child and child.get("received") == len(payload)
                 and child.get("sha256") == expected_sha and error is None),
}
print(json.dumps(result, indent=2))
sys.exit(0 if result["pass"] else 1)
