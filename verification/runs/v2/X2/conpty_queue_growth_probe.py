"""X2: the question the design actually needs answered.

The A04 design assumed the Windows reader accumulates an unbounded queue while no
client polls. The burst fixture showed the opposite (ConPTY collapses a burst and
delivers ~12 KB late), so this probe measures the realistic shape: a child that
produces output STEADILY for a bounded time (line-oriented, which ConPTY can pass
through) while the client never pumps. It samples the reader queue depth and the
child's own byte count, then does one snapshot and reports what the first parse
costs.

One session, <=1 MiB total, <=12 s, closed at the end.

Run on Windows: python X2/conpty_queue_growth_probe.py
"""
from __future__ import annotations

import json
import pathlib
import queue as queue_mod
import sys
import time

REPO = pathlib.Path(r"D:\Project\SmartCLI")
sys.path.insert(0, str(REPO))
from smartcli_core.pty_backend import get_default_backend  # noqa: E402

LINES = 6000          # ~100 KB of payload in ~100 B lines
script = (
    "import sys, time\n"
    f"for i in range({LINES}):\n"
    "    sys.stdout.write('LINE-%06d ' % i + '.' * 80 + '\\n')\n"
    "    sys.stdout.flush()\n"
    "    time.sleep(0.001)\n"
    "sys.stdout.write('MARKER-STEADY-DONE\\n'); sys.stdout.flush()\n"
    "time.sleep(6)\n"
)

backend = get_default_backend()
backend.spawn([sys.executable, "-c", script], cols=80, rows=24)


def depth():
    q = getattr(backend, "_queue", None)
    if not isinstance(q, queue_mod.Queue):
        return None, None
    with q.mutex:
        items = list(q.queue)
    return len(items), sum(len(i) for i in items if isinstance(i, (bytes, bytearray)))


samples = []
t0 = time.monotonic()
try:
    while time.monotonic() - t0 < 8.0:            # never read: the queue is the only sink
        items, nbytes = depth()
        samples.append({"t": round(time.monotonic() - t0, 2), "items": items, "queued_bytes": nbytes})
        time.sleep(0.5)

    t1 = time.monotonic()
    drained = backend.read_nonblocking()          # first contact: drain the backlog
    drain_s = time.monotonic() - t1
    items_after, bytes_after = depth()
    result = {
        "case": "X2-windows-conpty-steady",
        "backend": type(backend).__name__,
        "payload_lines": LINES,
        "child_output_expected_bytes": LINES * 93 + 18,
        "queue_depth_samples": samples,
        "max_queued_bytes": max((s["queued_bytes"] or 0) for s in samples),
        "drained_bytes_on_first_contact": len(drained),
        "drain_seconds": round(drain_s, 4),
        "queue_items_after": items_after,
        "queue_bytes_after": bytes_after,
        "line_check": sum(1 for ln in drained.decode("utf-8", "replace").splitlines()
                          if ln.startswith("LINE-")),
    }
    print(json.dumps(result, indent=1))
finally:
    backend.terminate()
