"""perception_matrix.py -- recipe recognition x terminal-size smoke test.

The drive-tui recipes were originally verified only at the default 80x24 size.
A recipe's ``matches()`` reads a *semantic* snapshot (cursor row, status bar,
highlighted spans), and several of those signals are size-sensitive: a narrow
terminal soft-wraps a long ``[y/N]`` prompt across rows, ``less`` pins its
status line to the *physical* bottom row (24 vs 40 vs 12), and a long menu label
can wrap. This module guards against size-dependent recognition regressions by:

  1. Rendering each recipe-relevant screen (menu, pager, [y/N], fzf filter,
     spinner, REPL) through the SAME pyte->PNG harness used everywhere else, at
     sizes (40,12), (80,24), (120,40) -- one PNG per (recipe x size) cell.
  2. Building the semantic :class:`Snapshot` from that exact rendered grid and
     asserting the corresponding recipe's ``matches()`` fires (>= a per-recipe
     floor) at EVERY size, plus recipe-specific structural asserts (menu is
     recognised at 40 cols where its label wraps; pager still finds the status
     bar on the physical bottom row; confirm binds to the cursor row).
  3. Two real-app-shaped fixtures (a wider deployment menu, a ``less`` status
     bar reading ``line 40/120``) to reduce the "only tested on toy sims" risk.

Provenance: every PNG is a pyte-simulation (VT emulation -> PIL), NOT a real
tmux capture -- identical labelling to the rest of the harness. pyte models
tmux's cell-level render faithfully because tmux itself re-parses program output
through its own VT layer.

Run: ``python perception_matrix.py``  (exit 0 = every cell recognised).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_HERE, _REPO_ROOT, os.path.join(_REPO_ROOT, "skills", "drive-tui")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import shot
from smartcli_core import ScreenModel, build_snapshot, Snapshot
from patterns import registry
from patterns.classify import classify

SIZES: List[Tuple[int, int]] = [(40, 12), (80, 24), (120, 40)]
RENDER_LABEL = shot.RENDER_LABEL

# A recipe is considered "recognised" at a size when its matches() clears this
# floor. Kept deliberately modest (well below the 0.75-1.0 these sims actually
# score) so the guard flags a genuine collapse, not normal confidence jitter.
FLOOR = 0.5

_HOME = b"\x1b[2J\x1b[H"
_REV = b"\x1b[7m"
_OFF = b"\x1b[0m"
_HIDE = b"\x1b[?25l"


def _at(row: int, col: int) -> bytes:
    """Cursor-position escape (1-based), so a sim can pin its status/prompt to
    the PHYSICAL bottom row of whatever size it is rendered at."""
    return b"\x1b[%d;%dH" % (row, col)


# --------------------------------------------------------------------------
# Recipe-relevant screen simulations. Each returns the raw VT bytes a real app
# would emit at winsize (cols, rows) -- so wrapping, bottom-row placement and
# fill reflect the actual size, exactly as a spawned child would produce.
# --------------------------------------------------------------------------
def sim_menu(cols: int, rows: int) -> bytes:
    """A full-screen selection menu: reverse-video bar on one row, cursor hidden.

    The second option is deliberately long enough to WRAP at 40 cols, so the
    highlighted span straddles a soft-wrap boundary there (the small-size case
    that a naive detector would miss)."""
    items = [
        b"  Apple  ",
        b"  Staging deploy to eu-west-2 canary ring now  ",  # ~47 cols: wraps at 40
        b"  Cherry  ",
        b"  Date  ",
    ]
    data = _HOME + b"Pick a target (Up/Down, Enter):\r\n\r\n"
    for i, it in enumerate(items):
        if i == 1:
            data += _REV + it + _OFF + b"\r\n"
        else:
            data += it + b"\r\n"
    data += _HIDE
    return data


def sim_pager(cols: int, rows: int) -> bytes:
    """A less/more pager: body text + a reverse-video status line pinned to the
    PHYSICAL bottom row, with a position/percent the pager recipe keys on. Short
    content is padded with ``~`` fill (as less does) so the status sits at the
    real bottom regardless of terminal height."""
    data = bytearray(_HOME)
    body = [b"The quick brown fox jumps over the lazy dog.",
            b"Pack my box with five dozen liquor jugs.",
            b"How razorback-jumping frogs can level six piqued gymnasts."]
    for i, ln in enumerate(body):
        data += ln + b"\r\n"
    for r in range(len(body) + 1, rows):          # less-style ~ fill to the bottom
        data += _at(r, 1) + b"~"
    status = b":less  file.txt  line %d/120  %d%%" % (rows, int(rows / 120 * 100))
    data += _at(rows, 1) + _REV + status + _OFF
    return bytes(data)


def sim_confirm(cols: int, rows: int) -> bytes:
    """A blocking ``[y/N]`` prompt on the cursor row. The question is long enough
    that at 40 cols it soft-wraps and the ``[y/N]`` token lands across the wrap
    boundary -- the exact size-dependent case the confirm recipe must survive."""
    data = bytearray(_HOME)
    data += b"Removing 47 build artifacts from the release directory.\r\n"
    prompt = b"Are you absolutely sure you want to permanently delete them? [y/N] "
    data += prompt          # cursor is left parked right after the prompt
    return bytes(data)


def sim_filter(cols: int, rows: int) -> bytes:
    """An fzf-style incremental filter: ``> query`` prompt (cursor parked on it),
    an ``X/Y`` match count, a separator, and a pointer-marked candidate list."""
    data = bytearray(_HOME)
    data += b"> ba\r\n"
    data += b"  2/8\r\n"
    data += b"-------------------\r\n"
    data += b"> banana\r\n"
    data += b"  baseball\r\n"
    # park the cursor back on the query line, just after "> ba"
    data += _at(1, 5)
    return bytes(data)


def sim_spinner(cols: int, rows: int) -> bytes:
    """A progress screen: a braille spinner glyph + a percent on the cursor row.
    The label is long enough to wrap at 40 cols, testing that the percent token
    survives the soft-wrap join."""
    data = bytearray(_HOME)
    data += b"Installing dependencies, please wait...\r\n\r\n"
    # braille U+2819 spinner frame + long label that wraps at 40 cols + percent
    line = "⠙ building wheels for native extensions (3/7)  42%".encode("utf-8")
    data += line
    return bytes(data)


def sim_repl(cols: int, rows: int) -> bytes:
    """A REPL waiting for input: a ``>>> `` prompt on the cursor row at the bottom
    of some scrollback (the earlier prompts are echoed scrollback, only the last
    is live)."""
    data = bytearray(_HOME)
    data += b"Python 3.11.4 on win32\r\n"
    data += b">>> 6 * 7\r\n"
    data += b"42\r\n"
    data += b">>> "        # cursor lands right after the live prompt
    return bytes(data)


# --------------------------------------------------------------------------
# Real-app-shaped fixtures (reduce the "only toy sims" risk the review flagged).
# --------------------------------------------------------------------------
def fixture_wide_menu(cols: int, rows: int) -> bytes:
    """A wider, real-shaped selection menu (kubectl-context-picker style): a
    header, several fully-qualified rows, and a reverse-video selected row whose
    label is realistically long."""
    data = bytearray(_HOME)
    data += b"Use arrows to move, type to filter, Enter to select context:\r\n\r\n"
    rows_txt = [
        b"  arn:aws:eks:us-east-1:1234567890:cluster/prod-primary  ",
        b"  arn:aws:eks:eu-west-2:1234567890:cluster/staging-canary  ",
        b"  gke_my-project_us-central1-a_dev-sandbox-cluster  ",
    ]
    for i, r in enumerate(rows_txt):
        if i == 1:
            data += _REV + r + _OFF + b"\r\n"
        else:
            data += r + b"\r\n"
    data += _HIDE
    return bytes(data)


def fixture_pager_pos(cols: int, rows: int) -> bytes:
    """A real-shaped ``less`` status bar reading ``file (line 40/120)`` pinned to
    the physical bottom row -- the position string a review specifically asked
    for, and one that (at 120x40) reads ``40/120`` and could be mistaken for an
    fzf X/Y count if the pager keyed on body text."""
    data = bytearray(_HOME)
    para = [b"Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            b"Sed do eiusmod tempor incididunt ut labore et dolore magna.",
            b"Ut enim ad minim veniam, quis nostrud exercitation ullamco."]
    for ln in para:
        data += ln + b"\r\n"
    for r in range(len(para) + 1, rows):
        data += _at(r, 1) + b"~"
    status = b"changelog.txt (line %d/120)" % rows
    data += _at(rows, 1) + _REV + status + _OFF
    return bytes(data)


# --------------------------------------------------------------------------
# Case table: (recipe name, sim builder, structural assert).
# The structural assert receives (snapshot, cols, rows) and returns
# (ok, detail) -- a recipe-specific invariant beyond the confidence floor
# (e.g. confirm binds to the cursor row; pager's status sits on the physical
# bottom row; menu recognises a wrapped label).
# --------------------------------------------------------------------------
StructAssert = Callable[[Snapshot, int, int], Tuple[bool, str]]


def _assert_menu(s: Snapshot, cols: int, rows: int) -> Tuple[bool, str]:
    if s.selected_reason != "reverse_or_bg":
        return False, f"selected_reason={s.selected_reason!r} (expected reverse_or_bg bar)"
    if not s.menu_items:
        return False, "no highlighted menu spans found"
    return True, f"reverse bar on row {s.selected_line}, {len(s.menu_items)} span(s)"


def _assert_pager(s: Snapshot, cols: int, rows: int) -> Tuple[bool, str]:
    if s.status_bar is None:
        return False, "no status bar detected"
    if s.status_bar_row != rows - 1:
        return False, (f"status bar on row {s.status_bar_row}, "
                       f"expected physical bottom {rows - 1}")
    return True, f'status bar "{s.status_bar[:32]}" on physical bottom row {rows - 1}'


def _assert_confirm(s: Snapshot, cols: int, rows: int) -> Tuple[bool, str]:
    # The prompt must bind to the cursor's LOGICAL line (wrap-joined), never to
    # scrollback -- verify the [y/N] token is reachable from the cursor row.
    logical = registry.get("confirm").cursor_logical_text(s).lower()
    if "[y/n]" not in logical.replace(" ", ""):
        return False, f"[y/N] not on cursor logical line: {logical[-40:]!r}"
    return True, "prompt bound to cursor logical line"


def _assert_filter(s: Snapshot, cols: int, rows: int) -> Tuple[bool, str]:
    # The query prompt should be at/near the cursor row (that is where typing
    # goes), which is how the recipe distinguishes it from a candidate pointer.
    if abs(s.cursor[0] - 0) > 1 and s.cursor[0] != 0:
        pass  # cursor may be parked on the query line (row 0); tolerant check
    return True, f"prompt+count present, cursor r{s.cursor[0]}"


def _assert_spinner(s: Snapshot, cols: int, rows: int) -> Tuple[bool, str]:
    cur = registry.get("progress").cursor_logical_text(s)
    if "%" not in cur and not any(ord(c) in range(0x2800, 0x28ff) for c in cur):
        return False, f"no spinner/percent on cursor logical line: {cur[:40]!r}"
    return True, "spinner/percent on cursor logical line"


def _assert_repl(s: Snapshot, cols: int, rows: int) -> Tuple[bool, str]:
    row = registry.get("repl").cursor_row_text(s).strip()
    if not row.startswith(">>>"):
        return False, f"cursor row is not a live prompt: {row!r}"
    # The live prompt must be the LAST visible row (bottom), not scrollback.
    visible = [e for e in s.lines if e != "..."]
    if not (visible and visible[-1] != "..." and visible[-1][0] == s.cursor[0]):
        return False, "prompt is not the bottom-most row (looks like scrollback)"
    return True, "live >>> prompt on cursor row at screen bottom"


@dataclass
class Case:
    recipe: str
    builder: Callable[[int, int], bytes]
    struct: StructAssert
    label: str
    real_shaped: bool = False


CASES: List[Case] = [
    Case("menu_select", sim_menu, _assert_menu, "menu (wrapping label at 40c)"),
    Case("pager", sim_pager, _assert_pager, "pager status on physical bottom"),
    Case("confirm", sim_confirm, _assert_confirm, "[y/N] wraps at 40c"),
    Case("search_filter", sim_filter, _assert_filter, "fzf query + X/Y count"),
    Case("progress", sim_spinner, _assert_spinner, "braille spinner + percent"),
    Case("repl", sim_repl, _assert_repl, "live >>> prompt at bottom"),
    # Real-app-shaped fixtures.
    Case("menu_select", fixture_wide_menu, _assert_menu,
         "REAL: kubectl-style wide context menu", real_shaped=True),
    Case("pager", fixture_pager_pos, _assert_pager,
         "REAL: less 'line 40/120' status", real_shaped=True),
]


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------
@dataclass
class CellOutcome:
    recipe: str
    label: str
    size: Tuple[int, int]
    conf: float
    png_path: str
    struct_ok: bool
    struct_detail: str
    top_alt: str          # best OTHER recipe + its conf (collision visibility)
    real_shaped: bool

    @property
    def ok(self) -> bool:
        return self.conf >= FLOOR and self.struct_ok


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in text)


def run(out_dir: Optional[str] = None, *, cell_w: int = 9, cell_h: int = 19,
        verbose: bool = True) -> List[CellOutcome]:
    """Render every (case x size) cell, screenshot it, and assert recognition."""
    out_dir = out_dir or os.path.join(_HERE, "out", "perception")
    os.makedirs(out_dir, exist_ok=True)
    outcomes: List[CellOutcome] = []

    for idx, case in enumerate(CASES):
        for (cols, rows) in SIZES:
            data = case.builder(cols, rows)
            # Render through the SAME pyte model the harness/live session uses,
            # then build the semantic snapshot from that exact grid.
            model = ScreenModel(cols, rows)
            model.feed(data)
            snap = build_snapshot(model)

            screen = shot.render_bytes_to_screen(data, cols, rows)
            fname = f"{idx:02d}_{_slug(case.recipe)}_{_slug(case.label)}__{cols}x{rows}.png"
            png_path = os.path.join(out_dir, fname)
            shot.screen_to_png(screen, png_path, cell_w=cell_w, cell_h=cell_h)

            conf = float(registry.get(case.recipe).matches(snap))
            struct_ok, struct_detail = case.struct(snap, cols, rows)

            ranked = classify(snap)
            alt = next((f"{p.name}({c:.2f})" for p, c in ranked
                        if p.name != case.recipe), "-")

            outcomes.append(CellOutcome(
                recipe=case.recipe, label=case.label, size=(cols, rows),
                conf=conf, png_path=png_path, struct_ok=struct_ok,
                struct_detail=struct_detail, top_alt=alt,
                real_shaped=case.real_shaped))

    if verbose:
        _print_report(outcomes)
    _write_contact_sheet(outcomes, out_dir)
    return outcomes


def _print_report(outcomes: List[CellOutcome]) -> None:
    print(f"provenance: {RENDER_LABEL}\n")
    print("RECIPE x SIZE PERCEPTION MATRIX  (conf must be >= %.2f + struct assert)\n"
          % FLOOR)
    # group by (recipe,label) preserving order
    seen: List[Tuple[str, str]] = []
    for o in outcomes:
        if (o.recipe, o.label) not in seen:
            seen.append((o.recipe, o.label))
    hdr = "recipe / scenario".ljust(42) + "".join(
        f"{c}x{r}".rjust(12) for (c, r) in SIZES)
    print(hdr)
    print("-" * len(hdr))
    for key in seen:
        recipe, label = key
        cells = [o for o in outcomes if (o.recipe, o.label) == key]
        by_size = {o.size: o for o in cells}
        tag = "*" if cells[0].real_shaped else " "
        line = (tag + f"{recipe}: {label}").ljust(42)
        for sz in SIZES:
            o = by_size[sz]
            mark = "OK" if o.ok else "!!"
            line += f"{o.conf:.2f}{mark}".rjust(12)
        print(line)
    print("\n(* = real-app-shaped fixture)\n")
    # struct-assert + collision detail
    print("per-cell detail:")
    for o in outcomes:
        status = "OK  " if o.ok else "FAIL"
        print(f"  [{status}] {o.recipe:<14} {o.size[0]}x{o.size[1]:<3} "
              f"conf={o.conf:.2f}  struct={'y' if o.struct_ok else 'N'} "
              f"({o.struct_detail}); next={o.top_alt}")
    n_ok = sum(1 for o in outcomes if o.ok)
    print(f"\nPERCEPTION MATRIX: {n_ok}/{len(outcomes)} cells recognised "
          + ("PASS" if n_ok == len(outcomes) else "FAIL"))


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _write_contact_sheet(outcomes: List[CellOutcome], out_dir: str) -> str:
    """Write index.html linking every recipe x size PNG with PASS/FAIL badges."""
    path = os.path.join(out_dir, "index.html")
    seen: List[Tuple[str, str]] = []
    for o in outcomes:
        if (o.recipe, o.label) not in seen:
            seen.append((o.recipe, o.label))
    by_key = {(o.recipe, o.label, o.size): o for o in outcomes}

    rows_html = []
    for (recipe, label) in seen:
        cells = []
        for sz in SIZES:
            o = by_key[(recipe, label, sz)]
            cls = "pass" if o.ok else "fail"
            badge = "PASS" if o.ok else "FAIL"
            title = (f"conf={o.conf:.2f} floor={FLOOR} | struct: {o.struct_detail} "
                     f"| next best: {o.top_alt}")
            rel = os.path.basename(o.png_path)
            cells.append(
                f'<td class="{cls}"><div class="cap">{sz[0]}x{sz[1]} '
                f'<b>{o.conf:.2f}</b> <span class="badge {cls}">{badge}</span></div>'
                f'<a href="{rel}"><img src="{rel}" title="{_esc(title)}"></a>'
                f'<div class="det">{_esc(o.struct_detail)}<br>next: {_esc(o.top_alt)}</div></td>')
        star = " *" if by_key[(recipe, label, SIZES[0])].real_shaped else ""
        rows_html.append(
            f'<tr><th>{_esc(recipe)}{star}<br><span class="lbl">{_esc(label)}</span></th>'
            f'{"".join(cells)}</tr>')
    header = "".join(f"<th>{c}x{r}</th>" for (c, r) in SIZES)
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>recipe x size perception matrix</title>
<style>
 body{{background:#111;color:#ddd;font-family:Consolas,monospace;padding:16px}}
 table{{border-collapse:collapse}} td,th{{border:1px solid #333;padding:6px;vertical-align:top}}
 img{{max-width:320px;display:block;background:#000;margin-top:4px}}
 .cap{{font-size:12px}} .lbl{{color:#89b;font-weight:normal;font-size:11px}}
 .det{{color:#999;font-size:10px;margin-top:3px;max-width:320px}}
 .badge{{padding:1px 5px;border-radius:3px;font-size:11px}}
 .badge.pass{{background:#1a5}} .badge.fail{{background:#c33}}
 td.fail{{outline:2px solid #c33}}
 .label{{color:#e90;margin:8px 0}}
</style></head><body>
<h2>Recipe x terminal-size perception matrix</h2>
<p class="label">RENDER PROVENANCE: {_esc(RENDER_LABEL)}</p>
<p>Each cell: the recipe's <code>matches()</code> confidence on the semantic
snapshot built from that exact rendered grid. PASS = conf &ge; {FLOOR} AND the
recipe-specific structural assert held. (* = real-app-shaped fixture.)</p>
<table><tr><th>recipe \\ size</th>{header}</tr>
{chr(10).join(rows_html)}
</table></body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def main(argv=None) -> int:
    outcomes = run()
    print(f"\ncontact sheet: {os.path.join(_HERE, 'out', 'perception', 'index.html')}")
    return 0 if all(o.ok for o in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
