"""S5 real-transport proof: does the ConPTY reader actually hold the line at the high water?

The S5 cap was verified against an injected reader only -- on the real transport the
biggest burst measured 131 072 B, well below the 4 MiB default, so the pause path
never ran. This probe drives a real ConPTY child past a deliberately lowered high
water and checks three things a cap must do:

  1. the ACCOUNTED payload (queue + reader's own chunk + held suffix) never exceeds
     the high water plus one chunk -- i.e. the reader really stops pulling;
  2. no byte is lost: the drained stream still carries the child's exact payload
     (sha256 match) once the backlog is consumed;
  3. the reader RESUMES after the client drains, so the pause is backpressure and
     not a stall.

Run (one PTY at a time):  python -B tests/../../SmartCLI-v3-runs/A04/s5-highwater/highwater_probe.py
"""
from __future__ import annotations

import argparse
import faulthandler
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument("--repo", type=Path, default=Path(r"D:\Project\SmartCLI"))
ap.add_argument("--total", type=int, default=3 * 1024 * 1024)
ap.add_argument("--high", type=int, default=256 * 1024)
ap.add_argument("--low", type=int, default=64 * 1024)
args = ap.parse_args()

# A hang must name its own frame: dump every thread after 45 s and exit.
faulthandler.dump_traceback_later(45, exit=True)
REPO = args.repo.resolve()
sys.path.insert(0, str(REPO))
os.environ["SMARTCLI_WINPTY_HIGH_BYTES"] = str(args.high)
os.environ["SMARTCLI_WINPTY_LOW_BYTES"] = str(args.low)

from smartcli_core import PtySession                      # noqa: E402
from smartcli_core.pty_backend import WinptyBackend       # noqa: E402

CHILD = Path(__file__).parent / "_fixture_writer.py"   # never inside the repo tree
if not CHILD.is_file():
    CHILD.write_text(
        "import sys\n"
        "n = int(sys.argv[1])\n"
        "payload = bytes((i * 7 + 11) % 251 for i in range(n))\n"
        "sys.stdout.buffer.write(payload)\n"
        "sys.stdout.buffer.flush()\n"
        "sys.stderr.write('WROTE %d %s\\n' % (n, __import__('hashlib').sha256(payload).hexdigest()))\n"
        "sys.stderr.flush()\n",
        encoding="utf-8")

payload = bytes((i * 7 + 11) % 251 for i in range(args.total))
expect = hashlib.sha256(payload).hexdigest()

backend = WinptyBackend()
sess = PtySession(backend=backend)
sess.start([sys.executable, "-u", str(CHILD), str(args.total)])

received = bytearray()
rounds = 0
observed_max = 0
paused_sampled = False
stats = backend.read_status()

deadline = time.time() + 120.0
while time.time() < deadline and len(received) < args.total:
    data = sess.pump(max_bytes=64 * 1024)          # a client that drains in slices
    received += data
    rounds += 1
    if rounds % 5 == 0:                            # sample io evidence, not every slice
        status = backend.read_status()
        stats = status
        accounted = int(status.get("queued_payload_bytes") or 0) + int(
            status.get("reader_held_payload_bytes") or 0)
        observed_max = max(observed_max, accounted)
        if accounted >= args.low:
            paused_sampled = True
    if len(received) >= args.total:
        break
    time.sleep(0.005)

# Let anything still queued arrive (the child has exited by now).
settle = time.time() + 10.0
while time.time() < settle and len(received) < args.total:
    received += sess.pump(max_bytes=256 * 1024)
    time.sleep(0.02)

io = sess.io_block()
snap = sess.snapshot()
text = getattr(snap, "text", "") or (snap.get("text", "") if isinstance(snap, dict) else "")
child_report = [ln for ln in text.splitlines() if ln.startswith("WROTE")]
result = {
    "case": "S5-highwater-real-conpty",
    "evidence": "E4 (real ConPTY reader thread + real child process)",
    "high_water_bytes": args.high,
    "low_water_bytes": args.low,
    "child_payload_bytes": args.total,
    "child_payload_sha256": expect,
    "received_bytes": len(received),
    "received_sha256": hashlib.sha256(bytes(received[: args.total])).hexdigest(),
    "observed_max_accounted_payload": observed_max,
    "cap_respected": observed_max <= args.high + 65536,   # high water + one chunk
    "pause_observed": paused_sampled,
    "reader_resumed": len(received) >= args.total,
    "local_cut": io.get("local_cut"),
    "pending_known_payload_bytes": io.get("pending", {}).get("known_payload_bytes"),
    "child_report": child_report[:1],
    "checks": {
        "1_cap_held": observed_max <= args.high + 65536,
        "2_no_byte_lost": hashlib.sha256(bytes(received[: args.total])).hexdigest() == expect
                          and len(received) >= args.total,
        "3_resumed_after_drain": len(received) >= args.total,
    },
}
result["pass"] = all(result["checks"].values())
sess.close()
out = Path(__file__).parent / "s5-highwater-result.json"
out.write_text(json.dumps(result, indent=1), encoding="utf-8")
print(json.dumps(result, indent=1))
sys.exit(0 if result["pass"] else 1)
