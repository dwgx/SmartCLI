"""Exact README-USAGE.md order, run from repo root."""
import sys
sys.path.insert(0, "skills/drive-tui")   # patterns/ auto-adds the repo root for smartcli_core

# patterns MUST be imported first: its __init__.py inserts the repo root onto
# sys.path as a side effect, which is what makes `smartcli_core` importable.
from patterns import classify, explain, all_patterns, get, load_all
from smartcli_core import PtySession
print("README literal import order OK")
