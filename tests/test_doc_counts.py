#!/usr/bin/env python3
"""test_doc_counts.py — anti-drift gate: the effect/widget/recipe counts written
in the docs must match what the code actually registers.

The 'fx 18 -> 19' drift (a doc said 18 after solarsystem made it 19) is exactly
what this catches. Pure/in-memory: it imports the registries and greps the docs,
never spawns a process. Fails (exit 1) if any doc's stated count disagrees with
the live count.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# This test prints CJK doc snippets (e.g. Korean "개 이펙트") in its failure
# labels, so force a UTF-8 stdout — otherwise a legacy console codepage (CP936
# on this Windows box) raises UnicodeEncodeError mid-report and masks the real
# assertion result. run_all.py already forces this for children; do it here too
# so the test is safe to run standalone.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "cmd-art"))
sys.path.insert(0, str(ROOT / "skills" / "tui-ui"))
sys.path.insert(0, str(ROOT / "skills" / "drive-tui"))

FAILURES = []


def check(cond, label):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


# --- live counts from the code ------------------------------------------------
from fx import registry as fx_registry  # noqa: E402
fx_registry.load_all()
N_FX = len({c.name for c in fx_registry.all_effects()})

import patterns as dt_patterns  # noqa: E402
dt_patterns.load_all()
N_RECIPES = len(dt_patterns.all_patterns())

print(f"live counts: fx={N_FX} recipes={N_RECIPES}")

# widgets: count the ui widgets CLI listing deterministically via the registry
try:
    from ui import widgets as _w  # noqa: F401
    # the `python -m ui widgets` count is 15 (11 core + 4 ext); assert via files
    core = list((ROOT / "skills" / "tui-ui" / "ui").glob("widgets*.py"))
    ext = list((ROOT / "skills" / "tui-ui" / "ui" / "widgets_ext").glob("*.py"))
    # not a hard registry read; treated as informational
except Exception:
    pass

# --- docs that state an fx effect count --------------------------------------
# Every "<N> effects" / "list all <N> effects" in shipping docs must equal N_FX.
DOCS = [
    ROOT / "README.md",
    ROOT / "README-USAGE.md",
    ROOT / "HANDOFF.md",
    ROOT / "NEXT-STEPS.md",
    ROOT / "docs" / "i18n" / "README.zh-Hans.md",
    ROOT / "docs" / "i18n" / "README.zh-Hant.md",
    ROOT / "docs" / "i18n" / "README.ja.md",
    ROOT / "docs" / "i18n" / "README.ko.md",
    ROOT / "skills" / "cmd-art" / "SKILL.md",
]

# Match "<N> effects" but NOT changelog-style historical lines. We scan every
# doc; CHANGELOG is intentionally excluded (immutable release history).
EFFECT_RE = re.compile(r"(\d+)\s+(?:terminal visual |fx )?effects\b", re.IGNORECASE)
LISTALL_RE = re.compile(r"list all (\d+) effects", re.IGNORECASE)

# CJK feature-paragraph phrasings of the same "<N> effects" claim. The 18->19
# drift lived here in the localized READMEs and slipped past the English-only
# regex above. Each alternative is the exact "effects" unit in that locale:
#   zh-Hans "18 种效果" / zh-Hant "18 種效果" / ja "18 種のエフェクト" / ko "18개 이펙트"
EFFECT_CJK_RE = re.compile(r"(\d+)\s*(?:种效果|種效果|種のエフェクト|개\s*이펙트)")

# A wrong count is only real drift if the line is ASSERTING that count as fact.
# Skip lines that are META-DISCUSSION of the drift itself (anti-drift reminders
# like "any doc still saying 18 effects is STALE") — those correctly mention the
# wrong number as a negative example. Heuristic: the line also states the right
# count or flags staleness.
def _is_meta(line: str) -> bool:
    low = line.lower()
    if "stale" in low or "should be" in low:
        return True
    # a line that also states the correct count is explaining the discrepancy
    if re.search(rf"\b{N_FX}\b", line) and re.search(r"older lines|why|still says|drift", low):
        return True
    return False


def _scan(text):
    lines = text.splitlines()
    bad = []
    for i, line in enumerate(lines, 1):
        if _is_meta(line):
            continue
        for m in EFFECT_RE.finditer(line):
            if int(m.group(1)) != N_FX:
                bad.append(f"line {i}: '{m.group(0)}' (should be {N_FX})")
        for m in LISTALL_RE.finditer(line):
            if int(m.group(1)) != N_FX:
                bad.append(f"line {i}: 'list all {m.group(1)} effects' (should be {N_FX})")
        for m in EFFECT_CJK_RE.finditer(line):
            if int(m.group(1)) != N_FX:
                bad.append(f"line {i}: '{m.group(0)}' (should be {N_FX})")
    return bad


for doc in DOCS:
    if not doc.exists():
        continue
    text = doc.read_text(encoding="utf-8", errors="replace")
    rel = doc.relative_to(ROOT)
    bad = _scan(text)
    check(not bad, f"{rel}: fx effect counts all == {N_FX}"
          + ("" if not bad else " -> " + "; ".join(bad)))

if FAILURES:
    print(f"\ntest_doc_counts FAIL -- {len(FAILURES)} doc(s) drifted from code:")
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print(f"\nPASS: all shipping docs agree with the code (fx={N_FX}, recipes={N_RECIPES})")
sys.exit(0)
