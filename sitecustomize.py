"""sitecustomize.py — auto-start coverage in EVERY Python subprocess.

Python imports a module named ``sitecustomize`` automatically at interpreter
startup if it is importable. tools/coverage_run.py puts the repo root on the
child processes' PYTHONPATH and sets COVERAGE_PROCESS_START=.coveragerc, so this
hook fires in each subprocess that tests/run_all.py spawns and starts coverage
before the test code runs. Without it, coverage would only see the driver
process and miss the actual work (which happens in the children).

Outside a coverage run (COVERAGE_PROCESS_START unset), this is a no-op, so it is
harmless to have on the path during normal development.
"""
import os

if os.environ.get("COVERAGE_PROCESS_START"):
    try:
        import coverage

        coverage.process_startup()
    except Exception:
        # Never let a coverage hiccup break a real subprocess run.
        pass
