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

# widgets: the same live registry `python -m ui widgets` prints from. This IS a
# hard gate — the 15->17 drift (fuzzy_filter_list + preview_pane shipped in
# v0.1.6, docs kept saying 15 across README, 3 localized READMEs, 5 site pages
# and README-USAGE) survived precisely because this count was informational.
from ui import registry as ui_registry  # noqa: E402
ui_registry.load_all()
N_WIDGETS = len(ui_registry.widget_names())

print(f"live counts: fx={N_FX} recipes={N_RECIPES} widgets={N_WIDGETS}")

# --- docs that state an fx effect count --------------------------------------
# Every "<N> effects" / "list all <N> effects" in shipping docs must equal N_FX.
DOCS = [
    ROOT / "README.md",
    ROOT / "README-USAGE.md",
    ROOT / "HANDOFF.md",
    ROOT / "NEXT-STEPS.md",
    ROOT / "CLAUDE.md",
    ROOT / "docs" / "i18n" / "README.zh-Hans.md",
    ROOT / "docs" / "i18n" / "README.zh-Hant.md",
    ROOT / "docs" / "i18n" / "README.ja.md",
    ROOT / "docs" / "i18n" / "README.ko.md",
    ROOT / "skills" / "cmd-art" / "SKILL.md",
]

# Docs that state a WIDGET count. Same drift class, wider blast radius: the site
# pages are shipped HTML, so they are scanned too.
WIDGET_DOCS = [
    ROOT / "README.md",
    ROOT / "README-USAGE.md",
    ROOT / "CLAUDE.md",
    ROOT / "skills" / "tui-ui" / "SKILL.md",
    ROOT / "docs" / "i18n" / "README.zh-Hans.md",
    ROOT / "docs" / "i18n" / "README.zh-Hant.md",
    ROOT / "docs" / "i18n" / "README.ja.md",
    ROOT / "docs" / "i18n" / "README.ko.md",
    ROOT / "docs" / "MACOS-VERIFY.md",
    ROOT / "docs" / "site" / "index.html",
    ROOT / "docs" / "site" / "index.zh-Hans.html",
    ROOT / "docs" / "site" / "index.zh-Hant.html",
    ROOT / "docs" / "site" / "index.ja.html",
    ROOT / "docs" / "site" / "index.ko.html",
]

# Agent-facing docs ship to other machines, so a hard-coded path from one dev box
# is a dead pointer for every reader. Time-stamped archives are exempt: they
# record what was true then and are explicitly frozen.
PORTABLE_DOC_GLOBS = [
    "README.md", "README-USAGE.md", "INSTALL.md", "CLAUDE.md", "CONTRIBUTING.md",
    "SECURITY.md", "docs/i18n/*.md", "skills/*/SKILL.md", "skills/*/references/*.md",
    "knowledge/*/*.md", "knowledge/INDEX.md",
]
BANNED_PATHS = ("D:/Project/SmartCLI", "D:\\Project\\SmartCLI")

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
#: Explicit, per-line opt-out. A line carrying this marker is exempt from every
#: count scan — used for prose that deliberately quotes a WRONG number while
#: explaining a past drift.
IGNORE_MARKER = "doc-counts:ignore"


def _is_meta(line: str) -> bool:
    """Is this line exempt from the count scans?

    Requires an EXPLICIT marker. It used to infer intent, exempting any line
    containing "stale"/"should be", or containing the correct fx count together
    with any of "older lines|why|still says|drift". That over-reached badly: it
    exempted HANDOFF.md's "**Live counts (re-verified against code ...)**" line —
    the line that document designates as its authoritative record — because the
    same sentence mentions the anti-drift gates. So the one line most likely to be
    consulted as ground truth was the one line never checked.

    Mutation-proven before the change: rewriting that line to "18 effects /
    1 widgets" left the gate reporting PASS.
    """
    return IGNORE_MARKER in line


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


# Widget claims are scanned over the WHOLE text, not line by line: the localized
# feature paragraphs wrap mid-claim ("**17 个\n组件**"), which a per-line regex
# silently misses — that is how the 15->17 drift survived in four translations.
WIDGET_RES = [
    re.compile(r"(\d+)\s*(?:reusable\s+)?widgets\b", re.IGNORECASE),   # 17 widgets
    re.compile(r"list all (\d+) widgets", re.IGNORECASE),
    re.compile(r"(\d+)\s*个\s*组件"),          # zh-Hans
    re.compile(r"(\d+)\s*種\s*widget", re.IGNORECASE),  # zh-Hant
    re.compile(r"(\d+)\s*種の\s*ウィジェット"),   # ja
    re.compile(r"(\d+)\s*개\s*위젯"),           # ko
    re.compile(r"Widget catalog \((\d+)\)", re.IGNORECASE),
]

#: Recipe counts. This family exists because N_RECIPES was computed, printed in the
#: PASS banner as if gated, and never asserted: `grep -rn N_RECIPES` found it only in
#: two f-strings. The banner read "all shipping docs agree with the code (fx=30,
#: recipes=8, widgets=17)" — asserting an agreement nothing had tested, sitting between
#: two numbers that WERE tested, so it read as covered.
RECIPE_RES = [
    re.compile(r"(\d+)\s*recipes\b", re.IGNORECASE),      # 8 recipes
    re.compile(r"(\d+)\s*个\s*(?:recipe|配方)"),           # zh-Hans
    re.compile(r"(\d+)\s*種\s*recipe", re.IGNORECASE),     # zh-Hant
    re.compile(r"(\d+)\s*種の\s*レシピ"),                  # ja
    re.compile(r"(\d+)\s*개\s*레시피"),                    # ko
]

#: Docs that state a RECIPE count.
RECIPE_DOCS = [
    ROOT / "README.md",
    ROOT / "README-USAGE.md",
    ROOT / "CLAUDE.md",
    ROOT / "HANDOFF.md",
    ROOT / "skills" / "drive-tui" / "SKILL.md",
    ROOT / "docs" / "i18n" / "README.zh-Hans.md",
    ROOT / "docs" / "i18n" / "README.zh-Hant.md",
    ROOT / "docs" / "i18n" / "README.ja.md",
    ROOT / "docs" / "i18n" / "README.ko.md",
]


def _scan_widgets(text):
    bad = []
    for rx in WIDGET_RES:
        for m in rx.finditer(text):
            if int(m.group(1)) == N_WIDGETS:
                continue
            line_no = text.count("\n", 0, m.start()) + 1
            claim = " ".join(m.group(0).split())
            if _is_meta(text.splitlines()[line_no - 1]):
                continue
            bad.append(f"line {line_no}: '{claim}' (should be {N_WIDGETS})")
    return bad


def _scan_recipes(text):
    bad = []
    for rx in RECIPE_RES:
        for m in rx.finditer(text):
            if int(m.group(1)) == N_RECIPES:
                continue
            line_no = text.count("\n", 0, m.start()) + 1
            claim = " ".join(m.group(0).split())
            if _is_meta(text.splitlines()[line_no - 1]):
                continue
            bad.append(f"line {line_no}: '{claim}' (should be {N_RECIPES})")
    return bad


def _scan_banned_paths(text):
    bad = []
    for i, line in enumerate(text.splitlines(), 1):
        for banned in BANNED_PATHS:
            if banned in line:
                bad.append(f"line {i}: hard-coded dev-box path '{banned}'")
    return bad


for doc in DOCS:
    if not doc.exists():
        continue
    text = doc.read_text(encoding="utf-8", errors="replace")
    rel = doc.relative_to(ROOT)
    bad = _scan(text)
    check(not bad, f"{rel}: fx effect counts all == {N_FX}"
          + ("" if not bad else " -> " + "; ".join(bad)))

for doc in WIDGET_DOCS:
    if not doc.exists():
        continue
    text = doc.read_text(encoding="utf-8", errors="replace")
    rel = doc.relative_to(ROOT)
    bad = _scan_widgets(text)
    check(not bad, f"{rel}: widget counts all == {N_WIDGETS}"
          + ("" if not bad else " -> " + "; ".join(bad)))

for doc in RECIPE_DOCS:
    if not doc.exists():
        continue
    text = doc.read_text(encoding="utf-8", errors="replace")
    rel = doc.relative_to(ROOT)
    bad = _scan_recipes(text)
    check(not bad, f"{rel}: recipe counts all == {N_RECIPES}"
          + ("" if not bad else " -> " + "; ".join(bad)))

# --- portable docs must not hard-code one machine's absolute paths -----------
portable = []
for pattern in PORTABLE_DOC_GLOBS:
    portable.extend(sorted(ROOT.glob(pattern)))
for doc in portable:
    text = doc.read_text(encoding="utf-8", errors="replace")
    rel = doc.relative_to(ROOT)
    bad = _scan_banned_paths(text)
    check(not bad, f"{rel}: no hard-coded dev-box paths"
          + ("" if not bad else " -> " + "; ".join(bad)))

if FAILURES:
    print(f"\ntest_doc_counts FAIL -- {len(FAILURES)} doc(s) drifted from code:")
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print(f"\nPASS: all shipping docs agree with the code "
      f"(fx={N_FX}, recipes={N_RECIPES}, widgets={N_WIDGETS}); "
      f"{len(portable)} portable docs free of dev-box paths")
sys.exit(0)
