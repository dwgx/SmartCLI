"""drive-tui prober part 4: confirm on a [y/N] prompt, both default and explicit."""
import sys, os
from pathlib import Path
os.chdir(Path(__file__).resolve().parents[1])
sys.path.insert(0, ".")
sys.path.insert(0, "skills/drive-tui")

from smartcli_core import PtySession
from patterns import classify, explain, get, load_all
load_all()

def run(intent, label):
    s = PtySession()
    s.start([sys.executable, "tests/_confirm_app.py"])
    ok, _ = s.wait_for(r"\[y/N\]")
    s.wait_stable(quiet_ms=150, max_wait_ms=1200)
    snap = s.snapshot()
    ranked = classify(snap)
    top = ranked[0] if ranked else (None, 0)
    print(f"--- {label}: prompt_ready={ok} top={top[0].name if top[0] else None}({top[1]:.2f})")
    conf = get("confirm")
    res = conf.drive(s, intent=intent)
    print(f"    drive(intent={intent!r}) ok={res.ok} detail={res.detail}")
    # read final output
    s.wait_stable(quiet_ms=200, max_wait_ms=1500)
    final = s.snapshot()
    body = [e[1] for e in final.lines if e != "..."]
    print("    final body:", body)
    s.close()

run(None, "default (Enter=No)")
run(True, "explicit yes")
run("no", "explicit no-word")
print("PART4 DONE")
