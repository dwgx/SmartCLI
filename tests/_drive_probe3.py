"""drive-tui prober part 3: menu_select against a live ANSI menu."""
import sys, os
from pathlib import Path
os.chdir(Path(__file__).resolve().parents[1])
sys.path.insert(0, ".")
sys.path.insert(0, "skills/drive-tui")

from smartcli_core import PtySession
from patterns import classify, explain, get, load_all
load_all()

s = PtySession()
s.start([sys.executable, "tests/_menu_app.py"])
ok, _ = s.wait_for(r"Pick a fruit")
print("menu ready:", ok)
s.wait_stable(quiet_ms=200, max_wait_ms=1500)

snap = s.snapshot()
print("=== explain ===")
print(explain(snap))
print("=== classify ===")
for pat, conf in classify(snap):
    print(f"{pat.name:14} {conf:.2f}")

menu = get("menu_select")
# navigate to "Cherry" by substring
res = menu.drive(s, intent="Cherry")
print("=== menu.drive('Cherry') ===")
print("ok:", res.ok, "| detail:", res.detail)
print("chosen_text:", res.data.get("chosen_text"), "| path:", res.data.get("path"))
print("after screen tail:")
print(res.data.get("after"))
s.close()
print("PART3 DONE")
