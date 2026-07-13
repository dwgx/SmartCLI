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

FAILURES = []


def check(cond, label):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


load_all()
print("PATTERNS:", [p.name for p in all_patterns()])
print("LOAD_ERRORS:", registry.load_errors())
check(registry.load_errors() == {} or not registry.load_errors(),
      "no pattern load errors")
check(any(p.name == "repl" for p in all_patterns()), "repl recipe registered")

s = PtySession()
try:
    s.start([sys.executable, "-q"])
    ok, snap0 = s.wait_for(r">>> ")
    check(ok, "wait_for >>> matched the REPL prompt")

    snap = s.snapshot()
    print("=== explain ===")
    print(explain(snap))
    print("=== classify ===")
    cls = classify(snap)
    for pat, conf in cls:
        print(f"{pat.name:14} {conf:.2f}")
    check(any(p.name == "repl" for p, _ in cls),
          "classify() recognizes the REPL screen as 'repl'")

    res = run_line(s, "6*7")
    print("=== run_line 6*7 ===")
    print("ok:", res.ok, "| out:", res.data.get("output"))
    print("detail:", res.detail)
    check(res.ok, "run_line(6*7) reported ok")
    check("42" in str(res.data.get("output")), "run_line(6*7) output contains 42")

    res2 = run_line(s, "print('hi'+'there')")
    print("=== run_line print ===")
    print("ok:", res2.ok, "| out:", res2.data.get("output"))
    check(res2.ok, "run_line(print) reported ok")
    check("hithere" in str(res2.data.get("output")),
          "run_line(print) output contains 'hithere'")
finally:
    s.close()

if FAILURES:
    print(f"PROBE1 FAIL -- {len(FAILURES)} assertion(s) failed:")
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("DONE (all assertions passed)")
sys.exit(0)
