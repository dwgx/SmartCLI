"""drive-tui prober part 4: confirm on a [y/N] prompt, both default and explicit."""
import sys, os
from pathlib import Path
os.chdir(Path(__file__).resolve().parents[1])
sys.path.insert(0, ".")
sys.path.insert(0, "skills/drive-tui")

from smartcli_core import PtySession
from patterns import classify, explain, get, load_all
load_all()

FAILURES = []


def check(cond, label):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def run(intent, label, expect):
    s = PtySession()
    try:
        s.start([sys.executable, "tests/_confirm_app.py"])
        ok, _ = s.wait_for(r"\[y/N\]")
        s.wait_stable(quiet_ms=150, max_wait_ms=1200)
        snap = s.snapshot()
        ranked = classify(snap)
        top = ranked[0] if ranked else (None, 0)
        print(f"--- {label}: prompt_ready={ok} top={top[0].name if top[0] else None}({top[1]:.2f})")
        check(ok, f"{label}: reached the [y/N] prompt")
        check(any(p.name == "confirm" for p, _ in ranked),
              f"{label}: classify() recognizes it as 'confirm'")
        conf = get("confirm")
        res = conf.drive(s, intent=intent)
        print(f"    drive(intent={intent!r}) ok={res.ok} detail={res.detail}")
        check(res.ok, f"{label}: confirm.drive reported ok")
        # read final output
        s.wait_stable(quiet_ms=200, max_wait_ms=1500)
        final = s.snapshot()
        body = [e[1] for e in final.lines if e != "..."]
        print("    final body:", body)
        joined = " ".join(body)
        check(expect in joined, f"{label}: final output shows '{expect}'")
    finally:
        s.close()


# _confirm_app.py prints "DELETING everything now" on yes, "Cancelled, nothing
# deleted" on no. Assert the right branch fired for each intent.
run(None, "default (Enter=No)", "Cancelled")
run(True, "explicit yes", "DELETING")
run("no", "explicit no-word", "Cancelled")

if FAILURES:
    print(f"PART4 FAIL -- {len(FAILURES)} assertion(s) failed:")
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("PART4 DONE (all assertions passed)")
sys.exit(0)
