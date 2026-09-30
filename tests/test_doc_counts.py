#!/usr/bin/env python3
"""test_doc_counts.py — anti-drift gate: every count the shipping docs publish
must equal what the code actually has.

The 'fx 18 -> 19' drift (a doc said 18 after solarsystem made it 19) is exactly
what this catches. Pure/in-memory: it imports the registries, counts directories
and parses one source file, never spawns a process. Fails (exit 1) if any doc's
stated count disagrees with the live count.

The rule this file follows for EVERY family: the number is derived from a live
source, never from a constant typed here. A hand-written `N_THEMES = 8` in this
file would be a second copy of the truth that drifts the moment someone adds a
theme — the same defect as a hand-written 18 in a README. So each count below
names WHERE it came from, and each family names the files it scans.

Fractions, not percentages. "16 are gated" leaves a reader unable to tell 16-of-56
from 16-of-200. The discipline applied throughout this lane: whenever a number
counts part of a population, the denominator is published beside it, so a reader
can recompute the ratio instead of trusting it.
"""
from __future__ import annotations

import ast
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

# --- live counts from DIRECTORIES and SOURCE, not from a registry -------------
# These four families were ungated: a sibling audit flagged the MCP tool count and
# the knowledge-file count, and the theme / widget-split counts turned out to have
# the same shape. Each is derived from something that exists on disk, so the gate
# has a live source to compare the prose against.

# Themes: `python -m fx` and the docs both enumerate `theme.THEMES`, a plain dict.
from fx import theme as fx_theme  # noqa: E402
N_THEMES = len(fx_theme.THEMES)

# The widget count alone was gated; its 11-core/6-ext SPLIT was not, and a split is
# where a count drifts first — adding one ext widget makes "6 in widgets_ext/"
# wrong while "17 widgets" stays right. Split the same live registry by the module
# each widget class was defined in, which is exactly the distinction the prose draws.
N_WIDGETS_CORE = sum(
    1 for w in ui_registry.all_widgets()
    if not w.__module__.startswith("ui.widgets_ext")
)
N_WIDGETS_EXT = N_WIDGETS - N_WIDGETS_CORE

# MCP tool count: the number `tools/list` returns. It was stated as a bare "14
# tools" in HANDOFF/NEXT-STEPS/DISTRIBUTION-CHANNELS with nothing checking it —
# the same hole the effect count had. Derived by PARSING mcp_server.py, not by
# importing it: importing pulls in the `mcp` SDK and constructs a live server, and
# this gate must stay pure and dependency-free (it runs in the CI matrix where only
# requirements.txt is installed). An AST walk of the decorators is exact, cannot
# drift from the source, and needs nothing but the stdlib.
_mcp_src = (ROOT / "skills" / "drive-tui" / "scripts" / "mcp_server.py").read_text(
    encoding="utf-8")
N_MCP_TOOLS = 0
for _node in ast.parse(_mcp_src).body:
    if not isinstance(_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    for _dec in _node.decorator_list:
        _tgt = _dec.func if isinstance(_dec, ast.Call) else _dec
        if (isinstance(_tgt, ast.Attribute) and _tgt.attr == "tool"
                and isinstance(_tgt.value, ast.Name) and _tgt.value.id == "mcp"):
            N_MCP_TOOLS += 1

# Knowledge graph size: a plain directory count. README published "140+ .md
# files" for years — a floor, not a count, so a reader could not tell 140 from 143
# and nothing could tell them wrong. HANDOFF said the exact 143. Both are checked
# against the same live listing, the floor form as an inequality.
N_KNOWLEDGE_MD = len(list((ROOT / "knowledge").rglob("*.md")))

print(f"live counts: fx={N_FX} recipes={N_RECIPES} widgets={N_WIDGETS} "
      f"themes={N_THEMES} mcp_tools={N_MCP_TOOLS} knowledge_md={N_KNOWLEDGE_MD} "
      f"widget_split={N_WIDGETS_CORE}+{N_WIDGETS_EXT}")


# --- docs that state an fx effect count --------------------------------------
# Every "<N> effects" / "list all <N> effects" in shipping docs must equal N_FX.
# The 5 site pages are in this list for the same reason they are in WIDGET_DOCS:
# they are deployed by pages.yml, so a stale stat chip is a stale claim shipping
# to readers. Their localized chips needed the extra EFFECT_CJK_RE alternatives.
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
    ROOT / "docs" / "site" / "index.html",
    ROOT / "docs" / "site" / "index.zh-Hans.html",
    ROOT / "docs" / "site" / "index.zh-Hant.html",
    ROOT / "docs" / "site" / "index.ja.html",
    ROOT / "docs" / "site" / "index.ko.html",
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

# Docs that state a THEME count. Same shape as the effect/widget families, and the
# same blast radius: the 5 shipped site pages each carry an "8 themes" stat chip,
# and every localized README has one in prose.
THEME_DOCS = [
    ROOT / "README.md",
    ROOT / "CLAUDE.md",
    ROOT / "HANDOFF.md",
    ROOT / "NEXT-STEPS.md",
    ROOT / "docs" / "i18n" / "README.zh-Hans.md",
    ROOT / "docs" / "i18n" / "README.zh-Hant.md",
    ROOT / "docs" / "i18n" / "README.ja.md",
    ROOT / "docs" / "i18n" / "README.ko.md",
    ROOT / "docs" / "site" / "index.html",
    ROOT / "docs" / "site" / "index.zh-Hans.html",
    ROOT / "docs" / "site" / "index.zh-Hant.html",
    ROOT / "docs" / "site" / "index.ja.html",
    ROOT / "docs" / "site" / "index.ko.html",
]

# Docs that state the MCP TOOL count — the family a sibling audit flagged. HANDOFF
# and NEXT-STEPS say "14 tools"; DISTRIBUTION-CHANNELS says what a validator sees
# ("tools/list -> 14 tools"). That last one is the strongest claim in the repo: it
# is the number an MCP-directory validator compares against, and it was unchecked.
MCP_TOOL_DOCS = [
    ROOT / "HANDOFF.md",
    ROOT / "NEXT-STEPS.md",
    ROOT / "docs" / "DISTRIBUTION-CHANNELS.md",
]

# Docs that state the KNOWLEDGE-GRAPH file count. README/README-USAGE/i18n use the
# "140+ .md files" FLOOR form (a lower bound, so it can only be falsified from
# above); HANDOFF/NEXT-STEPS use the exact form. Both are checked against the same
# live `knowledge/**/*.md` listing.
KNOWLEDGE_DOCS = [
    ROOT / "README.md",
    ROOT / "README-USAGE.md",
    ROOT / "HANDOFF.md",
    ROOT / "NEXT-STEPS.md",
    ROOT / "docs" / "i18n" / "README.zh-Hans.md",
    ROOT / "docs" / "i18n" / "README.zh-Hant.md",
    ROOT / "docs" / "i18n" / "README.ja.md",
    ROOT / "docs" / "i18n" / "README.ko.md",
]

# Docs that state the widget CORE/EXT split ("11 core + 6 in ui/widgets_ext/").
# Distinct from WIDGET_DOCS: a doc can carry the right total and a wrong split.
WIDGET_SPLIT_DOCS = [
    ROOT / "HANDOFF.md",
    ROOT / "NEXT-STEPS.md",
    ROOT / "skills" / "tui-ui" / "SKILL.md",
]

# Agent-facing docs ship to other machines, so a hard-coded path from one dev box
# is a dead pointer for every reader. Time-stamped archives are exempt: they
# record what was true then and are explicitly frozen.
PORTABLE_DOC_GLOBS = [
    "README.md", "README-USAGE.md", "INSTALL.md", "CLAUDE.md", "CONTRIBUTING.md",
    "SECURITY.md", "docs/i18n/*.md", "skills/*/SKILL.md", "skills/*/references/*.md",
    "knowledge/*/*.md", "knowledge/INDEX.md",
]
#: A portable doc must not carry a machine-specific absolute path. Banned by
#: CLASS, not by the one path someone remembered to add: the repo root is
#: derived from this file (so it cannot go stale when the checkout moves), and
#: any Windows user-profile path is rejected. The first version of this rule
#: listed only the repo path, so a doc could name the developer's home
#: directory and still pass -- which is exactly what happened when the
#: verification/ archive was pointed at its off-repo location.
REPO_ROOT_STR = str(ROOT)
USER_PROFILE_RE = re.compile(
    r"[A-Za-z]:[\\/]Users[\\/][^\\/\s`'\"]+", re.IGNORECASE)

#: Substrings banned by exact match, in BOTH separator spellings. Deriving the
#: root from __file__ is what stops the rule going stale when the checkout
#: moves, but on Windows ``str(ROOT)`` comes out backslashed
#: (``D:\Project\SmartCLI``) while docs commonly write it forward-slashed
#: (``D:/Project/SmartCLI``). Matching only the native spelling silently
#: DISABLED the check this rule existed for -- found by injecting a
#: forward-slash path and watching the gate stay green. Case-folded too, so a
#: doc cannot dodge the rule by changing case.
def _spelling_variants(path_str):
    out = set()
    for s in (path_str, path_str.replace("\\", "/"), path_str.replace("/", "\\")):
        out.add(s)
        out.add(s.lower())
    return tuple(sorted(out))


BANNED_PATHS = _spelling_variants(REPO_ROOT_STR)

# Match "<N> effects" but NOT changelog-style historical lines. We scan every
# doc; CHANGELOG is intentionally excluded (immutable release history).
EFFECT_RE = re.compile(r"(\d+)\s+(?:terminal visual |fx )?effects\b", re.IGNORECASE)
LISTALL_RE = re.compile(r"list all (\d+) effects", re.IGNORECASE)

# CJK feature-paragraph phrasings of the same "<N> effects" claim. The 18->19
# drift lived here in the localized READMEs and slipped past the English-only
# regex above. Each alternative is the exact "effects" unit in that locale:
#   zh-Hans "18 种效果" / zh-Hant "18 種效果" / ja "18 種のエフェクト" / ko "18개 이펙트"
# The two bare-unit alternatives (特效 / 效果 with no counter word) are the SITE
# pages' stat chips, which localize the chip independently of the prose and so
# use a different unit again — zh-Hans "30 种特效", zh-Hant "30 效果". Without
# them the shipped site pages stated an effect count no pattern could see.
EFFECT_CJK_RE = re.compile(
    r"(\d+)\s*(?:种效果|種效果|種のエフェクト|개\s*이펙트|种特效|種特效|特效|效果)")

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
    # zh-Hans writes 种配方 (种, simplified), zh-Hant writes 種 recipe. An earlier
    # version of this line used 个 for zh-Hans and matched NOTHING, leaving that
    # locale's count ungated — the same vacuous-pattern shape this family was added
    # to close. Every alternative below is verified to have a live hit on disk;
    # a branch with zero hits is a branch that cannot fail.
    re.compile(r"(\d+)\s*[种種個个]\s*(?:配方|recipe)", re.IGNORECASE),
    re.compile(r"(\d+)\s*个\s*方案"),  # zh-Hans site stat chip ("8 个方案") — the
    # prose says 配方, the chip says 方案, and the chip is what ships.
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
    ROOT / "docs" / "site" / "index.html",
    ROOT / "docs" / "site" / "index.zh-Hans.html",
    ROOT / "docs" / "site" / "index.zh-Hant.html",
    ROOT / "docs" / "site" / "index.ja.html",
    ROOT / "docs" / "site" / "index.ko.html",
    ROOT / "docs" / "i18n" / "README.zh-Hans.md",
    ROOT / "docs" / "i18n" / "README.zh-Hant.md",
    ROOT / "docs" / "i18n" / "README.ja.md",
    ROOT / "docs" / "i18n" / "README.ko.md",
]

#: Theme counts. Ungated until now: `fx.theme.THEMES` had no gate, so the "8
#: themes" in README, CLAUDE.md, HANDOFF, all four localized READMEs and the
#: site pages' stat chips were hand-maintained. Every alternative below has at
#: least one live hit on disk — a pattern that matches nothing is a pattern that
#: cannot fail. The CJK set is per-locale because the site pages localize the
#: stat chip independently of the prose: zh-Hans says "8 套主题" on the site and
#: "8 种主题" in its README, zh-Hant says "8 主題" and "8 種主題".
THEME_RES = [
    re.compile(r"(\d+)\s*themes\b", re.IGNORECASE),                    # 8 themes
    re.compile(r"(\d+)\s*(?:种主题|種主題|套主题|主題|主题)"),  # zh site + zh READMEs
    re.compile(r"(\d+)\s*種の\s*テーマ"),                        # ja
    re.compile(r"(\d+)\s*개\s*테마"),                                  # ko
]

#: MCP tool count. The claim a validator checks: `tools/list` returns this many.
#: "14 tools" appeared in HANDOFF x4, NEXT-STEPS x2 and DISTRIBUTION-CHANNELS
#: with nothing comparing it to the server, which is the one number in this repo
#: a third party actually re-derives.
MCP_TOOL_RES = [
    re.compile(r"(\d+)\s+MCP\s+tools\b", re.IGNORECASE),
    re.compile(r"(\d+)\s+tools\b", re.IGNORECASE),  # "14 tools", "tools/list -> 14 tools"
]

#: Knowledge-graph size, in BOTH published forms. The "140+" floor appears in
#: README, README-USAGE and all four localized READMEs; the exact 143 in HANDOFF
#: and NEXT-STEPS. A floor is checked as an inequality (live >= claimed) and the
#: exact form as an equality, because a "140+" that the live count has fallen
#: below is a broken promise while a "140+" the count has outgrown is merely
# stale — and only the second is worth failing a build over. The regex spans a
# newline because the localized paragraphs wrap mid-claim ("140+ `.md`\n  files").
#: The dot is OPTIONAL because two docs write the bare "143 md files" with no
#: dot; requiring one silently dropped those from the scan, and a pattern that
#: stops matching a real claim is indistinguishable from a gate that never
#: existed. The looser form was swept across all 13 docs for false positives
#: before being adopted.
KNOWLEDGE_RES = [
    re.compile(r"(\d+)(\+?)\s*[*\s]*`?\.?md\b"),
]

#: The widget core/ext SPLIT. Gating "17 widgets" does not gate "11 core + 6 in
#: ui/widgets_ext/": dropping a module into widgets_ext/ changes the split and
#: not the total, so the split is where a stale number hides. The two halves are
#: checked as a PAIR, because a doc that is right about one and wrong about the
#: other has still misdescribed the tree.
WIDGET_SPLIT_CORE_RE = re.compile(r"(\d+)\s+core\b(?=\s*\+|\s+web-style)", re.IGNORECASE)
WIDGET_SPLIT_EXT_RE = re.compile(r"(\d+)\s+(?:live\s+)?in\s+`?ui/widgets_ext`?", re.IGNORECASE)


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


def _scan_against(text, patterns, expected, floor=False):
    """Scan `text` for count claims that disagree with `expected`.

    Whole-text (not per line) for the same reason the widget scan is: the
    localized paragraphs wrap mid-claim, and a per-line regex misses the join.
    `floor=True` treats the claim as a lower bound ("140+") and only fails when
    the live count has fallen BELOW it; otherwise the claim must equal `expected`
    exactly. A wrong count is only drift if the line asserts it as fact, so the
    explicit `doc-counts:ignore` marker still exempts a line.
    """
    bad = []
    for rx in patterns:
        for m in rx.finditer(text):
            claimed = int(m.group(1))
            if (claimed <= expected) if floor else (claimed == expected):
                continue
            line_no = text.count("\n", 0, m.start()) + 1
            claim = " ".join(m.group(0).split())
            if _is_meta(text.splitlines()[line_no - 1]):
                continue
            rel = "at most" if floor else "should be"
            bad.append(f"line {line_no}: '{claim}' (live is {expected}; claim is "
                       f"{rel} {claimed})")
    return bad


def _scan_knowledge(text):
    """Knowledge-graph size, in both published forms.

    The regex captures the trailing "+" as group 2, so one pass can tell a floor
    ("140+ .md files") from an exact claim ("143 .md files") and apply the right
    comparison to each. A regex that collapsed both would either fail on every
    honest floor or pass on every exact count.
    """
    bad = []
    for m in KNOWLEDGE_RES[0].finditer(text):
        claimed = int(m.group(1))
        floor = bool(m.group(2))
        ok = claimed <= N_KNOWLEDGE_MD if floor else claimed == N_KNOWLEDGE_MD
        if ok:
            continue
        line_no = text.count("\n", 0, m.start()) + 1
        if _is_meta(text.splitlines()[line_no - 1]):
            continue
        claim = " ".join(m.group(0).split())
        rel = "a floor above" if floor else "should be"
        bad.append(f"line {line_no}: '{claim}' (live is {N_KNOWLEDGE_MD}; claim is "
                   f"{rel} {claimed})")
    return bad


def _scan_widget_split(text):
    """The 11-core / 6-ext widget split, checked as a pair.

    Gating the total does not gate the split: adding a module to widgets_ext/
    moves one number and not the other, so "11 core + 6 in ui/widgets_ext/" is
    the claim that actually rots. Both halves are reported from one scan so a
    failure names which side is wrong.
    """
    bad = []
    for rx, expected, what in (
            (WIDGET_SPLIT_CORE_RE, N_WIDGETS_CORE, "core widgets"),
            (WIDGET_SPLIT_EXT_RE, N_WIDGETS_EXT, "widgets in ui/widgets_ext/"),
    ):
        for m in rx.finditer(text):
            if int(m.group(1)) == expected:
                continue
            line_no = text.count("\n", 0, m.start()) + 1
            if _is_meta(text.splitlines()[line_no - 1]):
                continue
            claim = " ".join(m.group(0).split())
            bad.append(f"line {line_no}: {what} '{claim}' "
                       f"(should be {expected})")
    return bad


def _scan_banned_paths(text):
    """Reject machine-specific absolute paths, by class rather than by example.

    Two independent checks, because they fail differently: an exact repo-root
    match catches a doc that names this checkout, and the user-profile regex
    catches one that names any developer's home directory. Either alone leaves
    a hole -- that is the lesson from the archive pointer this replaced.
    """
    bad = []
    for i, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        for banned in BANNED_PATHS:
            if banned.lower() in low:
                bad.append(f"line {i}: hard-coded repo path '{banned}'")
        m = USER_PROFILE_RE.search(line)
        if m:
            bad.append(f"line {i}: hard-coded user-profile path '{m.group(0)}'")
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

for doc in THEME_DOCS:
    if not doc.exists():
        continue
    text = doc.read_text(encoding="utf-8", errors="replace")
    rel = doc.relative_to(ROOT)
    bad = _scan_against(text, THEME_RES, N_THEMES)
    check(not bad, f"{rel}: theme counts all == {N_THEMES}"
          + ("" if not bad else " -> " + "; ".join(bad)))

for doc in MCP_TOOL_DOCS:
    if not doc.exists():
        continue
    text = doc.read_text(encoding="utf-8", errors="replace")
    rel = doc.relative_to(ROOT)
    bad = _scan_against(text, MCP_TOOL_RES, N_MCP_TOOLS)
    check(not bad, f"{rel}: MCP tool counts all == {N_MCP_TOOLS}"
          + ("" if not bad else " -> " + "; ".join(bad)))

for doc in KNOWLEDGE_DOCS:
    if not doc.exists():
        continue
    text = doc.read_text(encoding="utf-8", errors="replace")
    rel = doc.relative_to(ROOT)
    bad = _scan_knowledge(text)
    check(not bad,
          f"{rel}: knowledge counts consistent with {N_KNOWLEDGE_MD} live .md files"
          + ("" if not bad else " -> " + "; ".join(bad)))

for doc in WIDGET_SPLIT_DOCS:
    if not doc.exists():
        continue
    text = doc.read_text(encoding="utf-8", errors="replace")
    rel = doc.relative_to(ROOT)
    bad = _scan_widget_split(text)
    check(not bad,
          f"{rel}: widget split == {N_WIDGETS_CORE} core + {N_WIDGETS_EXT} in "
          f"ui/widgets_ext/"
          + ("" if not bad else " -> " + "; ".join(bad)))

# --- a quoted program output must match what the program actually prints ------
# README shows drive_vim.py's step list as evidence, which is the strongest claim
# in the onboarding path — and it went stale the moment the example gained a
# seventh step (a confirmation of insert mode, added because the example was
# sending keystrokes blind). Nothing was watching, so the doc quietly advertised
# six steps for output that has seven.
#
# This compares the QUOTED lines against the step labels in the source, purely
# statically: it parses `step("...")` calls out of examples/drive_vim.py rather
# than running it. Running it would spawn a real PTY and vim, which this gate is
# forbidden to do (CLAUDE.md's red line) and does not need to do — the labels are
# literals in the source.
STEP_CALL_RE = re.compile(r'^\s*step\(\s*"([^"]+)"', re.M)
QUOTED_OK_RE = re.compile(r"^#\s+\[OK \]\s*(.+?)\s*$", re.M)

example = ROOT / "examples" / "drive_vim.py"
readme = ROOT / "README.md"
if example.exists() and readme.exists():
    src_steps = STEP_CALL_RE.findall(example.read_text(encoding="utf-8"))
    doc_steps = QUOTED_OK_RE.findall(readme.read_text(encoding="utf-8"))
    if doc_steps:  # only enforce while README actually quotes the output
        check(doc_steps == src_steps,
              f"README's drive_vim output matches the example's {len(src_steps)} steps"
              + ("" if doc_steps == src_steps else
                 f" -> README quotes {len(doc_steps)}: {doc_steps!r}; "
                 f"source declares {len(src_steps)}: {src_steps!r}"))

# --- the release-download instructions must stay version-independent ---------
# README and INSTALL tell people to curl
# /releases/latest/download/smartcli-skills.zip. That endpoint needs an EXACT asset
# filename, so if a doc ever hard-codes a versioned name (smartcli-skills-0.2.3.zip)
# the link 404s for everyone the moment the next release ships — a broken install
# path is the worst possible drift, since it hits first-time users only.
# tools/build_skill_bundle.py uploads both names for this reason; this check makes
# sure the DOCS point at the stable one.
VERSIONED_ASSET_RE = re.compile(r"releases/latest/download/smartcli-skills-\d")
for rel in ("README.md", "INSTALL.md"):
    doc = ROOT / rel
    if not doc.exists():
        continue
    text = doc.read_text(encoding="utf-8", errors="replace")
    bad = [f"line {i}" for i, line in enumerate(text.splitlines(), 1)
           if VERSIONED_ASSET_RE.search(line)]
    check(not bad,
          f"{rel}: skill-bundle link uses the version-independent asset name"
          + ("" if not bad else " -> " + "; ".join(bad)
             + " hard-codes a version, which 404s after the next release"))

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
    print(f"\nFix the doc to match the code. If a line quotes a WRONG number on "
          f"purpose — explaining a past drift, quoting an upstream project's count — "
          f"put `{IGNORE_MARKER}` on that line to exempt it. The exemption is "
          f"explicit by design: this gate used to infer intent from nearby words like "
          f"'stale' or 'drift', and that silently exempted HANDOFF's own "
          f"authoritative Live-counts line.")
    sys.exit(1)
# The banner states each family's DENOMINATOR (how many files were scanned), not
# just its count. A bare "13 docs agree" is the defect this lane exists to close:
# it reads identically whether 13 of 13 files were checked or 13 of 40. Publishing
# `n/N` lets a reader recompute the coverage instead of trusting it, and makes a
# silently-shrunk scan list visible — if someone drops a doc from a list, the
# denominator moves and the number above it stops meaning what it meant.
_scanned = sum(1 for d in DOCS + WIDGET_DOCS + RECIPE_DOCS + THEME_DOCS
               + MCP_TOOL_DOCS + KNOWLEDGE_DOCS + WIDGET_SPLIT_DOCS if d.exists())
print(f"\nPASS: every count the shipping docs publish matches the live source.")
print(f"  families: fx={N_FX} recipes={N_RECIPES} widgets={N_WIDGETS} "
      f"themes={N_THEMES} mcp_tools={N_MCP_TOOLS} knowledge_md={N_KNOWLEDGE_MD} "
      f"widget_split={N_WIDGETS_CORE}+{N_WIDGETS_EXT}")
print(f"  coverage: {_scanned} doc(s) scanned across 7 count families; "
      f"{len(portable)} portable docs free of dev-box paths")
sys.exit(0)
