"""drive-tui prober: REPL spawn + classify + run_line, per README-USAGE.md."""
import sys, os
from pathlib import Path
os.chdir(Path(__file__).resolve().parents[1])
sys.path.insert(0, ".")  # repo root, as when run from repo root
sys.path.insert(0, "skills/drive-tui")

from smartcli_core import PtySession
from patterns import classify, explain, all_patterns, get, load_all
from patterns.recipes.repl_session import run_line
from patterns import registry

load_all()
print("PATTERNS:", [p.name for p in all_patterns()])
print("LOAD_ERRORS:", registry.load_errors())

s = PtySession()
s.start([sys.executable, "-q"])
ok, snap0 = s.wait_for(r">>> ")
print("wait_for >>> matched:", ok)

snap = s.snapshot()
print("=== explain ===")
print(explain(snap))
print("=== classify ===")
for pat, conf in classify(snap):
    print(f"{pat.name:14} {conf:.2f}")

res = run_line(s, "6*7")
print("=== run_line 6*7 ===")
print("ok:", res.ok, "| out:", res.data.get("output"))
print("detail:", res.detail)

# a second line to be sure
res2 = run_line(s, "print('hi'+'there')")
print("=== run_line print ===")
print("ok:", res2.ok, "| out:", res2.data.get("output"))

s.close()
print("DONE")
