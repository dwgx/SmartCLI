"""drive-tui prober part 6: the three never-live-driven recipes -- pager, form,
wizard -- each spawned under a real PtySession, classified, driven, and
asserted against the live screen. Mirrors _drive_probe3/4/5.py.

Closes the biggest test gap: pager/form/wizard previously only had their
matches()/classify exercised, never a live drive(). Exit 0 iff all three
recipes PASS; non-zero (with FAIL lines) on any failed assertion. ConPTY-safe:
strict wait_for with a 15s timeout for the first prompt (the child banner can
lag ~3s under ConPTY).
"""
import sys, os
from pathlib import Path
os.chdir(Path(__file__).resolve().parents[1])
sys.path.insert(0, ".")
sys.path.insert(0, "skills/drive-tui")

from smartcli_core import PtySession
from patterns import classify, get, load_all
load_all()

FAILURES = []


def check(cond, label):
    print(f"    [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)
    return cond


def _visible(snap):
    return "\n".join(e[1] for e in snap.lines if e != "...")


def _top(snap):
    ranked = classify(snap)
    return (ranked[0][0].name, ranked[0][1]) if ranked else (None, 0.0)


def _conf_for(snap, want):
    for pat, conf in classify(snap):
        if pat.name == want:
            return conf
    return 0.0


# ---------------------------------------------------------------- PAGER -----
def probe_pager():
    print("==== PAGER (paginate.PagerPattern) ====")
    s = PtySession()
    try:
        s.start([sys.executable, "tests/_pager_app.py"])
        ok, _ = s.wait_for(r"--More--", timeout_ms=15000)
        s.wait_stable(quiet_ms=200, max_wait_ms=2000)
        snap = s.snapshot()
        name, conf = _top(snap)
        pconf = _conf_for(snap, "pager")
        print(f"    prompt_ready={ok} classify_top={name}({conf:.2f}) "
              f"pager_conf={pconf:.2f} status={snap.status_bar!r}")
        check(ok, "pager first '--More--' prompt appeared")
        check(name == "pager" and pconf >= 0.6,
              f"classify picks 'pager' with conf>=0.6 (top={name}/{conf:.2f}, pager={pconf:.2f})")

        res = get("pager").drive(s, intent="to_end")
        print(f"    drive('to_end') ok={res.ok} detail={res.detail}")
        print(f"      pages={res.data.get('pages')} "
              f"end_reached={res.data.get('end_reached')} "
              f"final_status={res.data.get('status')!r}")
        check(res.ok, "pager drive('to_end') returned ok")
        check((res.data.get("pages") or 0) > 0,
              f"pager advanced >0 pages (got {res.data.get('pages')})")
        check(bool(res.data.get("end_reached")), "pager reached end_reached=True")
        check("(END)" in (res.data.get("status") or ""),
              "pager bottom marker '(END)' seen in final status line")
    finally:
        s.close()


# ---------------------------------------------------------------- FORM ------
def probe_form():
    print("==== FORM (form_fill.FormPattern) ====")
    s = PtySession()
    try:
        s.start([sys.executable, "tests/_form_app.py"])
        ok, _ = s.wait_for(r"Name:", timeout_ms=15000)
        s.wait_stable(quiet_ms=200, max_wait_ms=2000)
        snap = s.snapshot()
        name, conf = _top(snap)
        fconf = _conf_for(snap, "form")
        print(f"    prompt_ready={ok} classify_top={name}({conf:.2f}) "
              f"form_conf={fconf:.2f} cursor={snap.cursor}")
        check(ok, "form first 'Name:' prompt appeared")
        check(name == "form" and fconf >= 0.6,
              f"classify picks 'form' with conf>=0.6 (top={name}/{conf:.2f}, form={fconf:.2f})")

        res = get("form").drive(s, intent={"Name": "Alice", "Email": "a@b.c"})
        print(f"    drive({{Name:Alice, Email:a@b.c}}) ok={res.ok} detail={res.detail}")
        print(f"      typed={res.data.get('typed')} echoed={res.data.get('echoed')} "
              f"fields={res.data.get('fields')}")
        check(res.ok, "form drive returned ok (every field typed)")
        check(res.data.get("typed") == 2, f"form typed 2 fields (got {res.data.get('typed')})")
        check(res.data.get("echoed") == 2,
              f"form echo-confirmed 2 fields on the cursor row (got {res.data.get('echoed')})")

        s.wait_stable(quiet_ms=200, max_wait_ms=2000)
        vis = _visible(s.snapshot())
        print("      final body:", vis.replace("\n", " | "))
        check("Alice" in vis, "form echoed 'Alice' back on the confirmation screen")
        check("a@b.c" in vis, "form echoed 'a@b.c' back on the confirmation screen")
    finally:
        s.close()


# ---------------------------------------------------------------- WIZARD ----
def probe_wizard():
    print("==== WIZARD (wizard_flow.WizardPattern) ====")
    s = PtySession()
    try:
        s.start([sys.executable, "tests/_wizard_app.py"])
        ok, _ = s.wait_for(r"Step 1 of 3", timeout_ms=15000)
        s.wait_stable(quiet_ms=200, max_wait_ms=2000)
        snap = s.snapshot()
        name, conf = _top(snap)
        wconf = _conf_for(snap, "wizard")
        print(f"    prompt_ready={ok} classify_top={name}({conf:.2f}) wizard_conf={wconf:.2f}")
        check(ok, "wizard first 'Step 1 of 3' prompt appeared")
        check(name == "wizard" and wconf >= 0.6,
              f"classify picks 'wizard' with conf>=0.6 (top={name}/{conf:.2f}, wizard={wconf:.2f})")

        # Auto mode: the wizard classifies each screen (excluding itself) and,
        # finding no sub-paradigm, falls through to its Enter-advance -- driven
        # screen by screen with the loop-guard until the 'complete' done marker.
        res = get("wizard").drive(s, intent=None)
        print(f"    drive(auto) ok={res.ok} detail={res.detail}")
        print(f"      reached_done={res.data.get('reached_done')} "
              f"scripted={res.data.get('scripted')} steps={res.data.get('steps')}")
        check(res.ok, "wizard drive returned ok")
        check(bool(res.data.get("reached_done")),
              "wizard reached_done=True (finish marker hit)")

        vis = _visible(s.snapshot())
        print("      final body:", vis.replace("\n", " | "))
        check("complete" in vis.lower(), "wizard reached a 'Setup complete!' screen")
    finally:
        s.close()


probe_pager()
probe_form()
probe_wizard()

print()
if FAILURES:
    print(f"PART6 FAIL -- {len(FAILURES)} assertion(s) failed:")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("PART6 DONE -- pager/form/wizard all driven live and PASS")
sys.exit(0)
