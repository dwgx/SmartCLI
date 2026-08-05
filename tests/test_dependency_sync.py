#!/usr/bin/env python3
"""test_dependency_sync.py — anti-drift gate: one dependency fact, one value.

The runtime dependency set is declared in more than one place because different
consumers read different files, and those copies drift. It has already bitten
twice:

* `mcp` was capped below 2.0 in `pyproject.toml` but left unbounded in
  `requirements.txt` — and `requirements.txt` is what the **Docker image**
  installs. The published image would still resolve mcp 2.x, fail its guarded
  import, and exit with "the 'mcp' package is required" while mcp was installed.
  That image is exactly what MCP directories run to validate the server.
* `python >=3.10` / `mcp >=1.0` in the conda-forge recipe drifted from the same
  facts in `pyproject.toml`.

Both are the same failure: a fact restated instead of referenced. This gate
compares the restatements so the next divergence fails here instead of in a
published artifact.

Scope, deliberately narrow:
  * `requirements.txt` must match `pyproject.toml`'s runtime `dependencies`
    exactly — same names, same specifiers, same environment markers. This pair
    has no reason to differ; the Docker image and a pip install must get the
    same resolve.
  * The packaging drafts (conda-forge, Homebrew) are checked more loosely: they
    are un-submitted templates pinned to an older release on purpose, so this
    only asserts that where they *do* state a bound for a dependency
    pyproject also bounds, they do not contradict it.
  * `requires-python` must agree everywhere it is restated.

Pure/in-memory: reads files, no network, no subprocess. Exit 0 = pass.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FAILURES: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    if not cond:
        FAILURES.append(label)
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail and not cond else ""))


def norm(spec: str) -> str:
    """Normalise a requirement line for comparison (whitespace, quote style)."""
    s = " ".join(spec.split())
    s = s.replace('"', "'")
    return s.lower()


# --------------------------------------------------------------------------
project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
pyproject_deps = [norm(d) for d in project["dependencies"]]
requires_python = project["requires-python"].strip()

req_lines = [
    norm(ln) for ln in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    if ln.strip() and not ln.lstrip().startswith("#")
]

print("--- requirements.txt mirrors pyproject's runtime dependencies ---")
print(f"    pyproject: {pyproject_deps}")
print(f"    requirements.txt: {req_lines}")

check(sorted(req_lines) == sorted(pyproject_deps),
      "requirements.txt == pyproject [project.dependencies]",
      detail=(f"only in pyproject: {sorted(set(pyproject_deps) - set(req_lines))} | "
              f"only in requirements: {sorted(set(req_lines) - set(pyproject_deps))}"))


# --------------------------------------------------------------------------
print("\n--- requires-python is not restated inconsistently ---")

PY_FLOOR = re.search(r"3\.(\d+)", requires_python)
assert PY_FLOOR, f"cannot parse requires-python: {requires_python!r}"
floor_minor = int(PY_FLOOR.group(1))
print(f"    pyproject requires-python = {requires_python} (floor 3.{floor_minor})")

# Every `python >=3.N` in the packaging drafts must not claim a LOWER floor than
# the package actually supports — that is the direction that ships a broken
# install (conda resolving 3.9 for a package needing 3.10).
for rel in ("packaging/conda-forge/recipe/meta.yaml",):
    path = ROOT / rel
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    claims = re.findall(r"python\s*>=\s*3\.(\d+)", text)
    bad = [c for c in claims if int(c) < floor_minor]
    check(not bad, f"{rel}: no python floor below 3.{floor_minor}",
          detail=f"found 3.{', 3.'.join(bad)}")

# mypy/ruff target the same floor as the package.
tool = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]
mypy_v = str(tool.get("mypy", {}).get("python_version", ""))
check(mypy_v == f"3.{floor_minor}",
      f"[tool.mypy] python_version == 3.{floor_minor}", detail=f"got {mypy_v!r}")
ruff_t = str(tool.get("ruff", {}).get("target-version", ""))
check(ruff_t == f"py3{floor_minor}",
      f"[tool.ruff] target-version == py3{floor_minor}", detail=f"got {ruff_t!r}")


# --------------------------------------------------------------------------
print("\n--- packaging drafts do not contradict a bound pyproject sets ---")

# Build {name: specifier} for deps pyproject constrains with an upper bound.
capped: dict[str, str] = {}
for dep in project["dependencies"]:
    m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(.*)$", dep.split(";")[0].strip())
    if m and "<" in m.group(2):
        capped[m.group(1).lower()] = m.group(2).strip()

if not capped:
    print("    (pyproject sets no upper bounds — nothing to cross-check)")
else:
    print(f"    upper-bounded in pyproject: {capped}")

for rel in ("packaging/conda-forge/recipe/meta.yaml",
            "packaging/homebrew/smartcli-toolkit.rb"):
    path = ROOT / rel
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8").lower()
    for name, spec in capped.items():
        if name not in text:
            continue  # draft does not list it at all — fine
        # If the draft mentions the dep, it must not state a bare lower bound
        # that would let the broken major through.
        bare = re.search(rf"{re.escape(name)}\s*>=\s*[\d.]+\s*$",
                         text, re.MULTILINE)
        check(bare is None,
              f"{rel}: '{name}' is not left unbounded (pyproject caps it {spec})",
              detail="draft states a bare >= lower bound; add the same upper cap")


if FAILURES:
    print(f"\ntest_dependency_sync FAIL -- {len(FAILURES)} check(s):")
    for f in FAILURES:
        print("   -", f)
    print("\nOne dependency fact should have one value. If a consumer genuinely "
          "needs a different constraint, say why in a comment next to it.")
    sys.exit(1)
print("\nPASS: dependency facts agree across every place they are restated.")
sys.exit(0)
