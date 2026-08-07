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
from pathlib import Path

# tomllib is stdlib only from 3.11, and this project's floor is 3.10 — the very
# fact this gate asserts. Fall back to tomli, then to a narrow regex reader, so
# the gate itself runs on the oldest supported interpreter. (First version of
# this file imported tomllib unconditionally and failed on every py3.10 CI leg.)
try:
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - depends on interpreter
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]


def _load_pyproject(text: str) -> dict:
    """Parse just what this gate needs, without requiring a TOML library."""
    if tomllib is not None:
        return tomllib.loads(text)
    # Minimal reader: [project].dependencies / requires-python and the two tool
    # targets. Deliberately narrow — it exists so the gate still runs on 3.10
    # without adding a test-time dependency.
    out: dict = {"project": {}, "tool": {"mypy": {}, "ruff": {}}}
    deps = re.search(r"^dependencies\s*=\s*\[(.*?)^\]", text, re.S | re.M)
    names: list[str] = []
    if deps:
        for line in deps.group(1).splitlines():
            # Strip comments FIRST: pyproject explains the mcp cap in a comment
            # that itself contains a quoted string, and a naive findall over the
            # whole block picked it up as a dependency.
            code = line.split("#", 1)[0]
            names.extend(re.findall(r'"([^"]+)"', code))
    out["project"]["dependencies"] = names
    rp = re.search(r'^requires-python\s*=\s*"([^"]+)"', text, re.M)
    out["project"]["requires-python"] = rp.group(1) if rp else ""
    mv = re.search(r'^python_version\s*=\s*"([^"]+)"', text, re.M)
    out["tool"]["mypy"]["python_version"] = mv.group(1) if mv else ""
    tv = re.search(r'^target-version\s*=\s*"([^"]+)"', text, re.M)
    out["tool"]["ruff"]["target-version"] = tv.group(1) if tv else ""
    return out

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
_PYPROJECT = _load_pyproject((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
project = _PYPROJECT["project"]
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
tool = _PYPROJECT["tool"]
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

# Each draft is parsed in ITS OWN syntax. A single pip-shaped regex used to be run
# over both, which meant the Homebrew half could never fail: a Ruby formula declares
# dependencies as `resource "<name>" do ... url ".../<name>-<ver>.tar.gz" ... end`,
# never as `name >= 1.0`. Worse, its entry guard (`if name not in text`) did not skip
# the file either, because the bare word "mcp" appears in the formula's comments and
# in its `desc`. So the branch was always entered, always passed, and printed a PASS
# that read as if the formula respected pyproject's cap.
CONDA_RECIPE = "packaging/conda-forge/recipe/meta.yaml"
HOMEBREW_FORMULA = "packaging/homebrew/smartcli-toolkit.rb"

path = ROOT / CONDA_RECIPE
if path.exists() and capped:
    text = path.read_text(encoding="utf-8").lower()
    for name, spec in capped.items():
        # conda/pip syntax: a requirement line ending in a bare lower bound.
        if not re.search(rf"^\s*-\s*{re.escape(name)}\b", text, re.MULTILINE):
            continue  # recipe does not list it at all — fine
        bare = re.search(rf"{re.escape(name)}\s*>=\s*[\d.]+\s*$", text, re.MULTILINE)
        check(bare is None,
              f"{CONDA_RECIPE}: '{name}' is not left unbounded "
              f"(pyproject caps it {spec})",
              detail="recipe states a bare >= lower bound; add the same upper cap")

path = ROOT / HOMEBREW_FORMULA
if path.exists() and capped:
    text = path.read_text(encoding="utf-8")
    low = text.lower()
    # A Homebrew python formula pins each dependency by the VERSION IN ITS RESOURCE
    # URL, so that is what has to respect the cap. Parse the stanzas.
    stanzas = dict(re.findall(
        r'resource\s+"([^"]+)"\s+do(.*?)\n\s*end', text, re.S))
    is_draft = ("DRAFT" in text and "TODO" in text)
    for name, spec in capped.items():
        body = next((b for n, b in stanzas.items() if n.lower() == name), None)
        if body is None:
            # No stanza. Legitimate ONLY while the file still advertises itself as
            # an unfinished draft — its header says it "only vendors pyte" and tells
            # the publisher to run `brew update-python-resources` first. Once those
            # markers are gone the formula is publishable, and a capped runtime
            # dependency with no resource stanza would install a broken venv.
            check(is_draft,
                  f"{HOMEBREW_FORMULA}: '{name}' has no resource stanza",
                  detail="the formula no longer marks itself DRAFT/TODO, so a "
                         "missing stanza for a required dependency would ship")
            continue
        m = re.search(rf"{re.escape(name)}[-_](\d[\d.]*)\.tar\.gz", body, re.I)
        check(m is not None,
              f"{HOMEBREW_FORMULA}: '{name}' resource url states a version",
              detail="cannot tell which version the stanza pins")
        if m:
            pinned = m.group(1)
            upper = re.search(r"<\s*([\d.]+)", spec)
            ok = True
            if upper:
                def _key(v: str) -> tuple[int, ...]:
                    return tuple(int(x) for x in v.split(".") if x.isdigit())
                ok = _key(pinned) < _key(upper.group(1))
            check(ok,
                  f"{HOMEBREW_FORMULA}: '{name}' pins {pinned}, respecting "
                  f"pyproject's {spec}",
                  detail=f"pinned {pinned} violates the cap {spec}")


if FAILURES:
    print(f"\ntest_dependency_sync FAIL -- {len(FAILURES)} check(s):")
    for f in FAILURES:
        print("   -", f)
    print("\nOne dependency fact should have one value. If a consumer genuinely "
          "needs a different constraint, say why in a comment next to it.")
    sys.exit(1)
print("\nPASS: dependency facts agree across every place they are restated.")
sys.exit(0)
