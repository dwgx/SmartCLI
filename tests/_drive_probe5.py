"""part 5: search_filter live + README no-crash claims (no-highlight, int, press=False)."""
import sys, os
from pathlib import Path
os.chdir(Path(__file__).resolve().parents[1])
sys.path.insert(0, ".")
sys.path.insert(0, "skills/drive-tui")

from smartcli_core import PtySession
from patterns import classify, explain, get, load_all
load_all()

# ---- search_filter ----
s = PtySession()
s.start([sys.executable, "tests/_filter_app.py"])
s.wait_for(r"\d+/\d+")
s.wait_stable(quiet_ms=200, max_wait_ms=1500)
snap = s.snapshot()
ranked = classify(snap)
print("filter top:", ranked[0][0].name, round(ranked[0][1],2))
sf = get("search_filter")
res = sf.drive(s, intent="grape", accept=True)
print("search_filter ok:", res.ok, "| detail:", res.detail)
print("  count_start:", res.data.get("count_start"), "count_end:", res.data.get("count_end"), "picked:", res.data.get("picked"))
s.wait_stable(quiet_ms=200, max_wait_ms=1200)
final = s.snapshot()
print("  final:", [e[1] for e in final.lines if e != "..."])
s.close()

# ---- README claim: plain list, no highlight -> menu_select ok=False, no crash ----
s2 = PtySession()
s2.start([sys.executable, "-q"])
s2.wait_for(r">>> ")
# print a plain list (no reverse video) then leave cursor on prompt
s2.send_line("print('Apple\\nBanana\\nCherry')")
s2.wait_stable(quiet_ms=200, max_wait_ms=1500)
snap2 = s2.snapshot()
menu = get("menu_select")
try:
    r_plain = menu.drive(snap2 and s2, intent="Banana")
    print("menu on plain list ok:", r_plain.ok, "| detail:", r_plain.detail, "(no crash)")
except Exception as e:
    print("menu on plain list CRASHED:", type(e).__name__, e)

# ---- README claim: int index + press=False (on the real menu app) ----
s3 = PtySession()
s3.start([sys.executable, "tests/_menu_app.py"])
s3.wait_for(r"Pick a fruit")
s3.wait_stable(quiet_ms=200, max_wait_ms=1200)
try:
    r_idx = menu.drive(s3, intent=2, press=False)
    print("menu int index press=False ok:", r_idx.ok, "| detail:", r_idx.detail)
except Exception as e:
    print("menu int index CRASHED:", type(e).__name__, e)
s2.close(); s3.close()
print("PART5 DONE")
