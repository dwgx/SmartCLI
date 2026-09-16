"""X2 (Windows/ConPTY baseline, refined): where does 4 MiB of child output live while
nobody snapshots the session?

One ConPTY session, a fixed bounded script (default 4 MiB, capped at 8 MiB), 10 s
wall budget. The child writes in 64 KiB chunks and keeps its OWN progress file, so
the parent can compare "what the child managed to write" against "what the backend
queue holds" without grading itself.

This is a BASELINE of the current (unfixed) A04 shape: it measures where the bytes
sit and how long the first parse takes. It claims nothing about RSS, and no fix is
applied here.

Run on Windows: python X2/windows_conpty_probe.py
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import queue as queue_mod
import sys
import tempfile
import time

ap = argparse.ArgumentParser()
ap.add_argument("--repo", type=pathlib.Path, default=pathlib.Path(r"D:\Project\SmartCLI"))
ap.add_argument("--mib", type=float, default=4.0)
ap.add_argument("--idle", type=float, default=3.0)
args = ap.parse_args()

limit_mib = min(args.mib, 8.0)
sys.path.insert(0, str(args.repo))
from smartcli_core import PtySession  # noqa: E402

payload_bytes = int(limit_mib * 1024 * 1024)
# The child resolves the report path ITSELF (tempdir + fixed name): embedding an
# absolute Windows path in a `-c` argument survives ConPTY quoting badly, and a
# child that never starts would be misread as "the transport held the bytes".
report = pathlib.Path(tempfile.gettempdir()) / "x2-child-report.json"
if report.exists():
    report.unlink()
script = (
    "import json, os, sys, tempfile, time\n"
    "path = os.path.join(tempfile.gettempdir(), 'x2-child-report.json')\n"
    f"total = {payload_bytes}\n"
    "chunk = b'X' * 65536\n"
    "written = 0\n"
    "t0 = time.monotonic()\n"
    "while written < total:\n"
    "    n = sys.stdout.buffer.write(chunk[:total - written])\n"
    "    sys.stdout.buffer.flush()\n"
    "    written += n if n else len(chunk[:total - written])\n"
    "    open(path, 'w').write(json.dumps({'written': written, 'done': written >= total,\n"
    "        't': round(time.monotonic() - t0, 3)}))\n"
    "sys.stdout.write('\\nMARKER-X2-DONE\\n')\n"
    "sys.stdout.flush()\n"
    "time.sleep(6)\n"
)


def queue_depth(backend):
    q = getattr(backend, "_queue", None)
    if not isinstance(q, queue_mod.Queue):
        return None, None
    with q.mutex:
        items = list(q.queue)
    return len(items), sum(len(i) for i in items if isinstance(i, (bytes, bytearray)))


def child_state():
    if report.exists():
        try:
            return json.loads(report.read_text())
        except json.JSONDecodeError:
            return None
    return None


sess = PtySession(cols=80, rows=24)
try:
    sess.start([sys.executable, "-c", script])
    samples = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < args.idle:            # nobody asks the session anything
        items, nbytes = queue_depth(sess.backend)
        samples.append({"t": round(time.monotonic() - t0, 2), "items": items,
                        "queued_bytes": nbytes, "child_written": (child_state() or {}).get("written")})
        time.sleep(0.25)

    t1 = time.monotonic()
    snap = sess.snapshot()                             # first client contact
    first_snapshot_s = time.monotonic() - t1
    items_after, bytes_after = queue_depth(sess.backend)

    t2 = time.monotonic()
    text = ""
    while time.monotonic() - t2 < 6.0:
        sess.pump()
        text = sess.model.text()
        if "MARKER-X2-DONE" in text:
            break
        time.sleep(0.05)
    settle_s = time.monotonic() - t2

    result = {
        "case": "X2-windows-conpty-baseline",
        "evidence": "E4-native-windows (real ConPTY session, one at a time)",
        "backend": type(sess.backend).__name__,
        "python": sys.version.split()[0],
        "payload_mib": limit_mib,
        "child_final": child_state(),
        "samples_while_idle": samples[-6:],
        "max_queued_bytes_while_idle": max((s["queued_bytes"] or 0) for s in samples) if samples else None,
        "queue_items_before_first_snapshot": items_after,
        "queue_bytes_before_first_snapshot": bytes_after,
        "first_snapshot_seconds": round(first_snapshot_s, 3),
        "marker_seen": "MARKER-X2-DONE" in text,
        "marker_seconds_after_contact": round(settle_s, 3),
        "snapshot_header": snap.to_text().splitlines()[0][:120],
        "notes": "no fix applied; measures where idle output sits and what the first parse costs",
    }
    print(json.dumps(result, indent=2))
finally:
    sess.close()
