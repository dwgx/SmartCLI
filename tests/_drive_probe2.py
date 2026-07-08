"""drive-tui prober part 2: broken-recipe fail-soft + menu_select + confirm."""
import sys, os, glob, textwrap
from pathlib import Path
os.chdir(Path(__file__).resolve().parents[1])
sys.path.insert(0, ".")
sys.path.insert(0, "skills/drive-tui")

from smartcli_core import PtySession
from patterns import classify, explain, get, load_all
from patterns import registry

RECIPE_DIR = r"skills/drive-tui/patterns/recipes"
broken = os.path.join(RECIPE_DIR, "zzbroken_probe.py")

# ---- 1) recreate a broken recipe and force a reload; must be SKIPPED ----
with open(broken, "w") as f:
    f.write("raise RuntimeError('boom at import')\n")
try:
    # clear the module cache so it re-imports
    for m in list(sys.modules):
        if "recipes.zzbroken_probe" in m:
            del sys.modules[m]
    registry._LOADED = False
    registry._LOAD_ERRORS.clear()
    load_all(force=True)
    names = [p.name for p in registry.all_patterns()]
    print("AFTER BROKEN RECIPE -> patterns:", names)
    print("load_errors count:", len(registry.load_errors()))
    for mod, tb in registry.load_errors():
        print("  errmod:", mod, "| last:", tb.strip().splitlines()[-1])
    # classify must still work with a broken recipe present
    s = PtySession(); s.start([sys.executable, "-q"]); s.wait_for(r">>> ")
    snap = s.snapshot()
    ranked = classify(snap)
    print("classify still works, top:", ranked[0][0].name, round(ranked[0][1],2))
    s.close()
finally:
    os.remove(broken)
    # Remove sourceless bytecode too; pkgutil can still discover/import it.
    for pyc in glob.glob(os.path.join(RECIPE_DIR, "__pycache__", "zzbroken_probe*.pyc")):
        try:
            os.remove(pyc)
        except FileNotFoundError:
            pass
    print("BROKEN RECIPE REMOVED; classify_crashed:", False)
print("PART2 DONE")
