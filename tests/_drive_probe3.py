"""drive-tui prober part 3: menu_select against a live ANSI menu."""
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


s = PtySession()
try:
    s.start([sys.executable, "tests/_menu_app.py"])
    ok, _ = s.wait_for(r"Pick a fruit")
    check(ok, "menu app reached 'Pick a fruit'")
    s.wait_stable(quiet_ms=200, max_wait_ms=1500)

    snap = s.snapshot()
    print("=== explain ===")
    print(explain(snap))
    print("=== classify ===")
    ranked = classify(snap)
    for pat, conf in ranked:
        print(f"{pat.name:14} {conf:.2f}")
    check(any(p.name == "menu_select" for p, _ in ranked),
          "classify() recognizes the arrow menu as 'menu_select'")

    menu = get("menu_select")
    # navigate to "Cherry" by substring
    res = menu.drive(s, intent="Cherry")
    print("=== menu.drive('Cherry') ===")
    print("ok:", res.ok, "| detail:", res.detail)
    print("chosen_text:", res.data.get("chosen_text"), "| path:", res.data.get("path"))
    print("after screen tail:")
    print(res.data.get("after"))
    check(res.ok, "menu.drive('Cherry') reported ok")
    check("Cherry" in str(res.data.get("chosen_text")),
          "menu.drive selected the row containing 'Cherry'")
finally:
    s.close()

if FAILURES:
    print(f"PART3 FAIL -- {len(FAILURES)} assertion(s) failed:")
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("PART3 DONE (all assertions passed)")
sys.exit(0)
