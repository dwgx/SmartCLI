#!/usr/bin/env python3
"""test_golden_frames.py — golden-frame snapshot regression for tui-ui widgets.

Every registered widget is rendered to a DETERMINISTIC ANSI frame (its
``sample(theme)`` composed into a fixed-size ``Page``, exactly the path
``python -m ui demo`` uses) and compared byte-for-byte against a committed
baseline in ``tests/golden/<key>.txt``. This locks the 15 widgets against silent
visual regressions — today only degenerate-input crashes and the fx frame
contract are guarded; widget *output* was not.

Pure/in-memory: it imports the ui package and renders strings, never spawns a
process. Deterministic: widgets carry no random/time dependency (verified), and
the test renders each widget TWICE and fails if the two disagree, so a
non-deterministic widget can never silently bake flakiness into a baseline.

Usage:
    python tests/test_golden_frames.py            # check against baselines (exit 1 on drift)
    python tests/test_golden_frames.py --update    # (re)write baselines from current output
    python tests/test_golden_frames.py badge card  # limit to named widgets

The baselines are meant to be reviewed in the diff: when a widget's look changes
on purpose, run --update and the PR shows exactly which cells moved.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "tui-ui"))

# Force UTF-8 stdout: baselines and diffs contain box-drawing + CJK, which crash
# on a legacy Windows codepage (CP936) otherwise.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

from ui import registry  # noqa: E402
from ui.box import Box  # noqa: E402
from ui.core import get_theme  # noqa: E402
from ui.layout import Page  # noqa: E402

GOLDEN_DIR = ROOT / "tests" / "golden"

# Fixed render parameters — must stay constant or every baseline shifts. Chosen
# wide/tall enough that no widget sample clips at its default.
WIDTH, HEIGHT = 60, 12
THEME = "dashboard"

results: list[tuple[str, bool, str]] = []
skipped: list[str] = []

# Widgets whose rendered frame depends on an OPTIONAL dependency: their output
# differs between "dep present" (real render) and "dep absent" (graceful stdlib
# fallback), so a single baseline can't cover both. When the dep is missing we
# SKIP the widget rather than fail — the baseline is only meaningful when the dep
# matches the environment that generated it. (banner -> pyfiglet FIGlet fonts;
# the baseline is the pyfiglet render. CI installs .[all] so it's exercised.)
OPTIONAL_DEP = {"banner": "pyfiglet"}


def _dep_available(mod: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(mod) is not None


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))


def note_skip(name: str, detail: str) -> None:
    skipped.append(name)
    print(f"SKIP  {name}  -- {detail}")


def render_widget(cls) -> str:
    """Render ONE widget to a deterministic ANSI frame — mirrors ui.cli.cmd_demo:
    sample(theme) -> Box -> Page.to_ansi()."""
    theme = get_theme(THEME)
    widget = cls.sample(theme)
    page = Page(Box(content=widget, padding=(0, 0), bg=theme.bg),
                width=WIDTH, height=HEIGHT, bg=theme.bg)
    return page.to_ansi()


def _baseline_path(key: str) -> Path:
    return GOLDEN_DIR / f"{key}.txt"


def _read_lf(path: Path) -> str:
    """Read a baseline, normalizing any CRLF to LF so the comparison is
    platform-independent (a Windows checkout may present CRLF; the rendered
    frame is always LF)."""
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _first_diff(a: str, b: str) -> str:
    """Human-pointable description of where two frames first differ."""
    al, bl = a.splitlines(), b.splitlines()
    if len(al) != len(bl):
        return f"line count {len(al)} != baseline {len(bl)}"
    for i, (x, y) in enumerate(zip(al, bl)):
        if x != y:
            col = next((j for j, (cx, cy) in enumerate(zip(x, y)) if cx != cy),
                       min(len(x), len(y)))
            return f"line {i} differs at col {col}"
    return "identical length, content differs (trailing?)"


def check_widget(cls, update: bool) -> None:
    key = cls.key
    # If this widget's render depends on an optional dep that's absent, its
    # fallback output won't match the baseline (generated with the dep present).
    # Skip rather than fail — a missing optional dep is not a regression.
    dep = OPTIONAL_DEP.get(key)
    if dep and not _dep_available(dep) and not update:
        note_skip(f"golden {key}", f"optional dep '{dep}' absent — baseline needs it")
        return

    # Determinism gate: render twice, must be byte-identical. A widget that
    # depends on time/random would trip here instead of baking flakiness in.
    frame1 = render_widget(cls)
    frame2 = render_widget(cls)
    if frame1 != frame2:
        record(f"golden {key}", False,
               f"NON-DETERMINISTIC render ({_first_diff(frame1, frame2)}) — "
               "fix the widget or seed it before baselining")
        return

    path = _baseline_path(key)
    if update:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        existed = path.exists()
        old = _read_lf(path) if existed else None
        # Write with LF newlines explicitly (newline="") so a Windows run doesn't
        # bake CRLF into the baseline — the rendered frame uses \n, and git
        # normalizes these files to LF (.gitattributes), so the baseline must be
        # LF on every platform or the check would drift CRLF-vs-LF across OSes.
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(frame1)
        state = "unchanged" if old == frame1 else ("updated" if existed else "created")
        record(f"golden {key}", True, f"baseline {state}")
        return

    if not path.exists():
        record(f"golden {key}", False,
               f"NO baseline at {path.relative_to(ROOT)} — run with --update")
        return
    baseline = _read_lf(path)
    if frame1 == baseline:
        record(f"golden {key}", True, f"matches baseline ({len(frame1)} bytes)")
    else:
        record(f"golden {key}", False,
               f"DRIFT vs baseline: {_first_diff(frame1, baseline)} "
               "(intentional? run --update and review the diff)")


def main(argv: list[str]) -> int:
    update = "--update" in argv
    only = {a for a in argv if not a.startswith("-")}

    registry.load_all()
    for mod, _tb in registry.load_errors():
        print(f"warning: widget module {mod} failed to import", file=sys.stderr)

    widgets = [c for c in registry.all_widgets() if not only or c.key in only]
    if not widgets:
        print(f"error: no widgets matched {only or '(all)'}", file=sys.stderr)
        return 2

    for cls in widgets:
        check_widget(cls, update)

    failed = [r for r in results if not r[1]]
    skip_note = f", {len(skipped)} skipped (optional dep absent)" if skipped else ""
    print(f"\n{len(results) - len(failed)}/{len(results)} widgets "
          f"{'baselined' if update else 'match golden frames'} "
          f"(size {WIDTH}x{HEIGHT}, theme {THEME}){skip_note}")
    if failed and not update:
        print("golden-frame drift — review, then `--update` if intended:")
        for name, _ok, detail in failed:
            print(f"  - {name}: {detail}")
    return 1 if (failed and not update) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
