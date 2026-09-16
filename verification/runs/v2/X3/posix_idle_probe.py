"""X3 / A04-POSIX: does the child make progress while NO client polls the session?

The child writes a bounded payload in 4 KiB steps, refreshing its own report file
after every step, then asks for a cursor-position report (ESC[6n) and waits for the
answer. The parent either (A) leaves the session alone for a couple of seconds or
(B) runs the OWNER loop (session.pump()) and measures.

The referee is the child's report file, written by the child itself -- not the
parent's view of the screen.

Run (inside a Linux container): python X3/posix_idle_probe.py --repo /repo
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument("--repo", type=Path, required=True)
ap.add_argument("--bytes", type=int, default=512 * 1024)
ap.add_argument("--idle-seconds", type=float, default=2.0)
ap.add_argument("--child", type=Path, default=Path(__file__).with_name("child_writer.py"))
args = ap.parse_args()

sys.path.insert(0, str(args.repo))
from smartcli_core import PtySession  # noqa: E402

CHILD = args.child


def run_case(pump: bool):
    import tempfile
    report = Path(tempfile.mkdtemp(prefix="x3-")) / "child.json"
    sess = PtySession(cols=100, rows=30)
    try:
        sess.start([sys.executable, str(CHILD), "--bytes", str(args.bytes),
                    "--out", str(report)])
        t0 = time.monotonic()
        if pump:
            # The owner loop: read + feed + answer device queries, bounded by wall time.
            while time.monotonic() - t0 < 10.0:
                sess.pump()
                data = json.loads(report.read_text()) if report.exists() else {}
                if data.get("done") and data.get("cpr_answered"):
                    break
        else:
            time.sleep(args.idle_seconds)      # NO polling at all
        elapsed = time.monotonic() - t0
        child = json.loads(report.read_text(encoding="utf-8")) if report.exists() else None
        return {
            "pumped": pump,
            "elapsed_s": round(elapsed, 3),
            "child": child,
            "session_alive": sess.is_alive(),
            "parsed_chars": len(sess.model.text()),
        }
    finally:
        sess.close()


print(json.dumps({"case": "idle-posix", "result": run_case(pump=False)}, indent=2))
print(json.dumps({"case": "owner-loop-posix", "result": run_case(pump=True)}, indent=2))
