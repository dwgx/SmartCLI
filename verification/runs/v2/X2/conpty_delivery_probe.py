"""X2 diagnostic: where do 1 MiB of ConPTY output actually go while nobody reads?

Reads through the production `read_nonblocking()` (no parsing, no snapshot) on a
fixed 250 ms cadence so the delivery timeline is visible. One session, bounded
output, closed at the end.

Run on Windows: python X2/conpty_delivery_probe.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

REPO = pathlib.Path(r"D:\Project\SmartCLI")
sys.path.insert(0, str(REPO))
from smartcli_core.pty_backend import get_default_backend  # noqa: E402

MIB = 1
script = (
    "import sys, time\n"
    f"sys.stdout.write('X' * {MIB * 1024 * 1024})\n"
    "sys.stdout.write('\\nMARKER-DELIVERY\\n')\n"
    "sys.stdout.flush()\n"
    "time.sleep(5)\n"
)

backend = get_default_backend()
backend.spawn([sys.executable, "-c", script], cols=80, rows=24)
samples = []
total = 0
t0 = time.monotonic()
try:
    while time.monotonic() - t0 < 4.0:
        data = backend.read_nonblocking()
        total += len(data)
        samples.append({"t": round(time.monotonic() - t0, 2), "chunk": len(data), "total": total})
        time.sleep(0.25)
finally:
    backend.terminate()

print(json.dumps({"samples": samples, "total_bytes": total,
                  "first_nonzero_at": next((s["t"] for s in samples if s["chunk"]), None),
                  "note": "read_nonblocking() was the only consumer; no parsing happened"}, indent=1))
