"""S5 fair high-water probe: the question issue #15 leaves open, on a transport that
cannot drop data.

The original ``highwater_probe.py`` asked the right question and drove it with a
fixture that writes all 262 144 bytes in ONE write. On this box ConPTY/pywinpty hands
over ~12 KB of a burst that large and drops the rest (measured with raw pywinpty, no
SmartCLI in the loop: 8 KiB in one write arrives whole, 32 KiB and above arrive as
~12 KB). That makes the old probe unable to distinguish "the client stalled" from "the
transport dropped the payload", and it dies in its own 45 s watchdog before printing a
result.

This probe never lets the transport be the reason:

  * the child publishes SMALL slices with a pause between them (4 KiB every 20 ms by
    default), which this transport carries losslessly;
  * the child prints its own byte count and sha256 to stderr at BOTH ends of the
    payload (BEGIN / WROTE), so what it actually wrote is checkable;
  * the payload is printable ASCII 33..126, so the ``conpty_reconstructed_utf8``
    representation (no LF/CR translation, no codepage re-encode) is byte-preserving;
  * the client is deliberately slower than the producer for the throttled phase, so
    the reader really does reach the high water and pause -- that state is the whole
    point -- and then drains the backlog fast once the child has finished.

PASS = the child's own report and the parent's payload agree, every byte of the payload
region is present with a matching sha256, the sampled accounted payload never exceeds
high water + one chunk, and no single ``pump(max_bytes=...)`` call ever waited longer
than ``--max-turn-s``.

The per-turn trace is printed as it happens: a stall is visible in the last line even
if the process is killed by the watchdog.

Run (one PTY at a time):
    python -B fair_highwater_probe.py --repo <tree> --total 196608 --high 65536 --low 16384
"""
from __future__ import annotations

import argparse
import faulthandler
import hashlib
import json
import os
import re
from pathlib import Path
import statistics
import sys
import tempfile
import time

ap = argparse.ArgumentParser()
ap.add_argument("--repo", type=Path, default=Path(r"D:\Project\SmartCLI"))
ap.add_argument("--total", type=int, default=192 * 1024, help="child payload bytes (<= 256 KiB)")
ap.add_argument("--slice", type=int, default=4096, help="child's write slice")
ap.add_argument("--feed-pause", type=float, default=0.02, help="child's pause between slices")
ap.add_argument("--high", type=int, default=64 * 1024)
ap.add_argument("--low", type=int, default=16 * 1024)
ap.add_argument("--budget", type=int, default=4096, help="pump(max_bytes=...) per call")
ap.add_argument("--client-pause", type=float, default=0.05,
                help="sleep between turns while throttled (must make the client slower")
ap.add_argument("--max-turn-s", type=float, default=1.0)
ap.add_argument("--deadline-s", type=float, default=60.0)
ap.add_argument("--watchdog-s", type=float, default=110.0)
args = ap.parse_args()

#: One READER chunk: ``_read_loop`` checks the budget, then asks ConPTY for up to this
#: many bytes and queues them without re-checking (smartcli_core/pty_backend.py). So
#: the strict cap invariant is HIGH + this, not HIGH + the child's slice -- the child's
#: pace decides how full one reader chunk is, not the ceiling.
READER_CHUNK = 65536

# The watchdog must not be the thing that ends the run: the deadline is well inside it,
# so a stalled run still prints its trace and its JSON.
faulthandler.dump_traceback_later(args.watchdog_s, exit=True)

REPO = args.repo.resolve()
sys.path.insert(0, str(REPO))
os.environ["SMARTCLI_WINPTY_HIGH_BYTES"] = str(args.high)
os.environ["SMARTCLI_WINPTY_LOW_BYTES"] = str(args.low)

from smartcli_core import PtySession                              # noqa: E402
from smartcli_core.pty_backend import WinptyBackend               # noqa: E402

# The child lives in the temp dir, never in the repository or next to this probe: this
# directory belongs to the parent and gets exactly one new file (this one).
CHILD_DIR = Path(tempfile.mkdtemp(prefix="smartcli-fair-highwater-"))
CHILD = CHILD_DIR / "_fair_writer.py"
CHILD.write_text(
    "import hashlib, sys, time\n"
    "n, slice_len, pause = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3])\n"
    "payload = bytes(33 + (i * 7 + 11) % 94 for i in range(n))\n"
    "digest = hashlib.sha256(payload).hexdigest()\n"
    "sys.stderr.write('BEGIN %d %s\\n' % (n, digest))\n"
    "sys.stderr.flush()\n"
    "for off in range(0, n, slice_len):\n"
    "    sys.stdout.buffer.write(payload[off:off + slice_len])\n"
    "    sys.stdout.buffer.flush()\n"
    "    if pause:\n"
    "        time.sleep(pause)\n"
    "sys.stderr.write('WROTE %d %s\\n' % (n, digest))\n"
    "sys.stderr.flush()\n",
    encoding="utf-8")

payload = bytes(33 + (i * 7 + 11) % 94 for i in range(args.total))
expect_sha = hashlib.sha256(payload).hexdigest()
head = payload[:64]                      # alignment anchor, 64 bytes of unique-ish ASCII
REPORT = re.compile(rb"(BEGIN|WROTE) (\d+) ([0-9a-f]{64})")

backend = WinptyBackend()
sess = PtySession(backend=backend)
sess.start([sys.executable, "-u", str(CHILD), str(args.total), str(args.slice),
            str(args.feed_pause)])

print(f"# transport: WinptyBackend, high={args.high} low={args.low} budget={args.budget} "
      f"client_pause={args.client_pause} total={args.total} slice={args.slice} "
      f"feed_pause={args.feed_pause}", flush=True)
print(f"# turn  got   received   acc(accounted)  cut              ms", flush=True)

received = bytearray()
align = -1                     # offset of the payload inside the stream, once known
turns: list[int] = []
turn_ms: list[float] = []
max_accounted = 0
pause_observed = False
pause_turns = 0
drained_phase = False
child_report: dict[str, str] = {}
start = time.monotonic()
deadline = start + args.deadline_s
turn = 0
while time.monotonic() < deadline:
    if align < 0:
        align = received.find(head)
    # Throttled while the payload is still arriving (that is what keeps the reader at
    # its cap); unthrottled afterwards, only to pick up the child's closing report.
    payload_complete = align >= 0 and len(received) >= align + args.total
    if payload_complete:
        drained_phase = True

    t0 = time.monotonic()
    data = sess.pump(max_bytes=args.budget)
    dt = time.monotonic() - t0
    turn += 1
    received += data
    turns.append(len(data))
    turn_ms.append(dt * 1000.0)

    sample = (turn % 8 == 0) or not data
    if sample:
        status = backend.read_status()
        accounted = int(status.get("queued_payload_bytes") or 0) + int(
            status.get("reader_held_payload_bytes") or 0)
        max_accounted = max(max_accounted, accounted)
        if accounted >= args.low:
            pause_observed = True
            pause_turns += 1
        cut = sess.io_block()["local_cut"]
        print(f"{turn:6d} {len(data):5d} {len(received):9d} {accounted:14d}  "
              f"{cut:<16} {dt * 1000:8.2f}", flush=True)
    else:
        print(f"{turn:6d} {len(data):5d} {len(received):9d} {'-':>14}  {'-':<16} "
              f"{dt * 1000:8.2f}", flush=True)

    for match in REPORT.finditer(bytes(received)):
        child_report[match.group(1).decode()] = (
            f"{int(match.group(2))} {match.group(3).decode()}")

    if align >= 0 and len(received) >= align + args.total and "WROTE" in child_report:
        break
    if not drained_phase:
        time.sleep(args.client_pause)

wall = time.monotonic() - start
faulthandler.cancel_dump_traceback_later()

# --- what the child says it wrote, and what actually arrived ------------------
report_begin = child_report.get("BEGIN", "")
report_wrote = child_report.get("WROTE", "")
child_n = int(report_wrote.split(" ")[0]) if report_wrote else None
child_sha = report_wrote.split(" ")[1] if report_wrote else None
region = bytes(received[align:align + args.total]) if align >= 0 else b""
region_sha = hashlib.sha256(region).hexdigest()

checks = {
    "1_child_report_agrees": bool(report_begin) and report_begin == report_wrote
                             and child_n == args.total and child_sha == expect_sha,
    "2_every_byte_delivered": align >= 0 and len(region) == args.total
                              and region_sha == child_sha,
    "3_cap_held": max_accounted <= args.high + READER_CHUNK,
    "4_no_turn_over_budget": max(turn_ms) / 1000.0 <= args.max_turn_s,
}
result = {
    "case": "S5-fair-highwater-real-conpty",
    "repo": str(REPO),
    "high_water_bytes": args.high,
    "low_water_bytes": args.low,
    "cap_tolerance_bytes": args.high + READER_CHUNK,
    "reader_chunk_bytes": READER_CHUNK,
    "budget_bytes": args.budget,
    "client_pause_s": args.client_pause,
    "child_payload_bytes": args.total,
    "child_payload_sha256": expect_sha,
    "child_report_begin": report_begin,
    "child_report_wrote": report_wrote,
    "received_bytes": len(received),
    "payload_offset": align,
    "delivered_payload_bytes": len(region),
    "delivered_payload_sha256": region_sha,
    "turn_count": turn,
    "empty_turns": sum(1 for n in turns if n == 0),
    "turn_ms_max": round(max(turn_ms), 3),
    "turn_ms_median": round(statistics.median(turn_ms), 3),
    "max_accounted_payload": max_accounted,
    "pause_observed": pause_observed,
    "sampled_turns_at_or_above_low": pause_turns,
    "wall_seconds": round(wall, 3),
    "checks": checks,
}
result["pass"] = all(checks.values())
print(json.dumps(result, indent=1), flush=True)
sys.exit(0 if result["pass"] else 1)
