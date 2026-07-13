"""part 5: search_filter live + README no-crash claims (no-highlight, int, press=False)."""
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


# ---- search_filter ----
s = PtySession()
try:
    s.start([sys.executable, "tests/_filter_app.py"])
    fok, _ = s.wait_for(r"\d+/\d+")
    check(fok, "filter app reached the N/N counter")
    s.wait_stable(quiet_ms=200, max_wait_ms=1500)
    snap = s.snapshot()
    ranked = classify(snap)
    print("filter top:", ranked[0][0].name, round(ranked[0][1], 2))
    check(any(p.name == "search_filter" for p, _ in ranked),
          "classify() recognizes the filter screen as 'search_filter'")
    sf = get("search_filter")
    res = sf.drive(s, intent="grape", accept=True)
    print("search_filter ok:", res.ok, "| detail:", res.detail)
    print("  count_start:", res.data.get("count_start"), "count_end:",
          res.data.get("count_end"), "picked:", res.data.get("picked"))
    check(res.ok, "search_filter.drive('grape') reported ok")
    s.wait_stable(quiet_ms=200, max_wait_ms=1200)
    final = s.snapshot()
    print("  final:", [e[1] for e in final.lines if e != "..."])
finally:
    s.close()

menu = get("menu_select")

# ---- README claim: plain list, no highlight -> menu_select must NOT crash ----
s2 = PtySession()
try:
    s2.start([sys.executable, "-q"])
    s2.wait_for(r">>> ")
    s2.send_line("print('Apple\\nBanana\\nCherry')")
    s2.wait_stable(quiet_ms=200, max_wait_ms=1500)
    crashed = False
    try:
        r_plain = menu.drive(s2, intent="Banana")
        print("menu on plain list ok:", r_plain.ok, "| detail:", r_plain.detail, "(no crash)")
    except Exception as e:
        crashed = True
        print("menu on plain list CRASHED:", type(e).__name__, e)
    check(not crashed, "menu_select on a plain (no-highlight) list does NOT crash")
finally:
    s2.close()

# ---- README claim: int index + press=False must NOT crash ----
s3 = PtySession()
try:
    s3.start([sys.executable, "tests/_menu_app.py"])
    s3.wait_for(r"Pick a fruit")
    s3.wait_stable(quiet_ms=200, max_wait_ms=1200)
    crashed2 = False
    try:
        r_idx = menu.drive(s3, intent=2, press=False)
        print("menu int index press=False ok:", r_idx.ok, "| detail:", r_idx.detail)
    except Exception as e:
        crashed2 = True
        print("menu int index CRASHED:", type(e).__name__, e)
    check(not crashed2, "menu_select with int index + press=False does NOT crash")
finally:
    s3.close()

if FAILURES:
    print(f"PART5 FAIL -- {len(FAILURES)} assertion(s) failed:")
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("PART5 DONE (all assertions passed)")
sys.exit(0)
