"""N1 driver: does the DAEMON service a finite fixture with no client asking?

The test body never calls pump/snapshot to make progress: it starts the real
`tui.py` daemon in a subprocess, sleeps, and only then makes its first request.
The verdict comes from the child's own report file (a query answered and a
payload completed *before* the first request) plus the daemon's io block.

Cases (≤3 per platform, one session each, ≤1 MiB, ≤12 s producer):
  A  daemon as shipped (budget profile)  -> query answered, payload complete
  B  daemon with the service turn removed (mutation) -> neither happens

Run inside the Linux container:
    python /runs/N1/n1_daemon_idle.py --repo /repo --runs /runs
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ap = argparse.ArgumentParser()
ap.add_argument("--repo", type=Path, required=True)
ap.add_argument("--runs", type=Path, required=True)
ap.add_argument("--bytes", type=int, default=256 * 1024)
ap.add_argument("--idle", type=float, default=2.5)
ap.add_argument("--label", default="daemon")
ap.add_argument("--settle", type=float, default=12.0)
ap.add_argument("--child", default="child_probe2.py")
args = ap.parse_args()

TUI = args.repo / "skills" / "drive-tui" / "scripts" / "tui.py"
CHILD = args.runs / "N1" / args.child
SID = f"n1-{args.label}-{os.getpid() % 100000}"
report = Path(tempfile.mkdtemp(prefix="n1-")) / "child.json"
env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1",
       "SMARTCLI_ROOT": str(args.repo)}

cmd = [sys.executable, str(CHILD), "--bytes", str(args.bytes), "--out", str(report)]
start = subprocess.run([sys.executable, str(TUI), "start", "--id", SID, "--cols", "100",
                        "--rows", "30", "--json", "--cmd",
                        " ".join([sys.executable, str(CHILD), "--bytes", str(args.bytes),
                                  "--out", str(report)])],
                       capture_output=True, text=True, env=env, timeout=60)
started = json.loads(start.stdout) if start.stdout.strip().startswith("{") else None

result = {"case": f"N1-posix-{args.label}", "start_rc": start.returncode,
          "start": started or start.stdout.strip()[:200], "start_stderr": start.stderr.strip()[:200]}
try:
    time.sleep(args.idle)                      # NO client request in this window
    before = json.loads(report.read_text()) if report.exists() else None
    snap = subprocess.run([sys.executable, str(TUI), "snapshot", "--id", SID, "--json"],
                          capture_output=True, text=True, env=env, timeout=60)
    after = json.loads(report.read_text()) if report.exists() else None
    # Let the DAEMON carry the fixture to completion. The test body only reads the
    # child's report file: it never calls pump/snapshot again, so any progress here
    # is the daemon servicing the session on its own.
    deadline = time.monotonic() + args.settle
    final = json.loads(report.read_text()) if report.exists() else None
    while time.monotonic() < deadline and not (final or {}).get("done"):
        time.sleep(0.25)
        final = json.loads(report.read_text()) if report.exists() else None
    snap_json = json.loads(snap.stdout) if snap.stdout.strip().startswith("{") else {}
    result.update({
        "child_before_first_request": before,
        "child_after_first_request": after,
        "child_final": final,
        "io_block": snap_json.get("io"),
        "snapshot_ok": snap_json.get("ok", "n/a (snapshot --json prints the Snapshot)"),
        "daemon_finished_the_fixture_unpumped": bool((final or {}).get("done")),
        "no_request_outcome": {
            "cpr_answered_before_contact": bool(before and before.get("cpr_answered")),
            "written_before_contact": (before or {}).get("written"),
            "done_before_contact": bool(before and before.get("done")),
        },
    })
finally:
    subprocess.run([sys.executable, str(TUI), "close", "--id", SID],
                   capture_output=True, text=True, env=env, timeout=60)
    result["closed"] = True

print(json.dumps(result, indent=1))
