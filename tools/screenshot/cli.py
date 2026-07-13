"""cli.py -- command line for the pyte -> PNG screenshot smoke-test harness.

Subcommands
-----------
* ``shot <argv...>``   -- one-off: capture a command's output and write one PNG.
* ``matrix <spec>``    -- full (size x depth) matrix for a target + contact sheet.
* ``fx <effect>``      -- screenshot a single fx effect frame (no child process).
* ``selftest``         -- render a portable PTY hello + one fx frame, assert PNGs exist
                          and non-empty, and run a check. Used by the smoke phase.

Target spec for ``matrix``:
  * ``cmd:<argv...>``  -- spawn a command and capture its output.
  * ``fx:<effect>``    -- render one frame of an fx effect.
  * ``file:<path>``    -- read raw VT bytes from a file.
  * ``edge:<name>``    -- a built-in content edge-case fixture (matrix.CONTENT_EDGE_CASES).

Everything is BOUNDED: captures have a hard time cap; nothing loops forever.
All output is honestly labelled pyte-simulation, NOT a real-tmux capture.
"""

from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import checks as checks_mod
import matrix as matrix_mod
import shot
from smartcli_core.screen_model import safe_screen_display  # shot put repo root on path

_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
_CMD_ART = os.path.join(_REPO_ROOT, "skills", "cmd-art")


# --------------------------------------------------------------------------
# fx frame rendering (in-process, no child)
# --------------------------------------------------------------------------
def render_fx_frame(effect_name: str, cols: int, rows: int,
                    t: float = 0.7, frame_index: int = 12) -> bytes:
    """Render one frame of an fx effect to feedable bytes (no PTY, no loop)."""
    if _CMD_ART not in sys.path:
        sys.path.insert(0, _CMD_ART)
    import fx.registry as registry
    from fx.base import FrameCtx
    from fx.theme import get_theme

    registry.load_all()
    cls = registry.get(effect_name)
    effect = cls()
    effect.setup()
    try:
        ctx = FrameCtx(t=t, frame_index=frame_index, width=cols,
                       height=max(1, rows - 1), theme=get_theme(cls.preferred_theme),
                       params=cls.param_defaults())
        frame = effect.render(ctx)
    finally:
        try:
            effect.teardown()
        except Exception:
            pass
    return shot.render_frame_to_bytes(frame)


# --------------------------------------------------------------------------
# target spec -> Target
# --------------------------------------------------------------------------
def resolve_target(spec: str, cols: int, rows: int, *, seconds: float,
                   alt_screen: bool) -> matrix_mod.Target:
    """Turn a target spec string into a :class:`matrix.Target` (raw bytes)."""
    if spec.startswith("fx:"):
        name = spec[3:]
        data = render_fx_frame(name, cols, rows)
        return matrix_mod.Target(name=f"fx-{name}", data=data, alt_screen=alt_screen)
    if spec.startswith("file:"):
        path = spec[5:]
        with open(path, "rb") as f:
            data = f.read()
        return matrix_mod.Target(name=os.path.basename(path), data=data, alt_screen=alt_screen)
    if spec.startswith("edge:"):
        name = spec[5:]
        data = matrix_mod.CONTENT_EDGE_CASES[name]
        return matrix_mod.Target(name=f"edge-{name}", data=data, alt_screen=alt_screen)
    if spec.startswith("cmd:"):
        argv = spec[4:]
        data = shot.capture_cmd(argv, cols, rows, seconds=seconds, alt_screen=alt_screen)
        return matrix_mod.Target(name=f"cmd-{_first_word(argv)}", data=data, alt_screen=alt_screen)
    # Bare spec == a command line.
    data = shot.capture_cmd(spec, cols, rows, seconds=seconds, alt_screen=alt_screen)
    return matrix_mod.Target(name=f"cmd-{_first_word(spec)}", data=data, alt_screen=alt_screen)


def _first_word(s: str) -> str:
    parts = s.split()
    return matrix_mod._slug(parts[0]) if parts else "cmd"


# --------------------------------------------------------------------------
# subcommands
# --------------------------------------------------------------------------
def cmd_shot(args) -> int:
    argv = args.argv
    if not argv:
        print('error: shot needs a command, e.g. shot python -c "print(42)"',
              file=sys.stderr)
        return 2
    cmdline = " ".join(argv)
    data = shot.capture_cmd(cmdline, args.cols, args.rows,
                            seconds=args.seconds, alt_screen=args.alt_screen)
    screen = shot.render_bytes_to_screen(data, args.cols, args.rows)
    out = args.out or os.path.join(_HERE, "out", f"shot_{_first_word(cmdline)}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    w, h = shot.screen_to_png(screen, out, cell_w=args.cell_w, cell_h=args.cell_h)
    src_color = checks_mod.stream_has_color(data)
    results = (checks_mod.run_stream_checks(data)
               + checks_mod.run_screen_checks(screen, depth="truecolor",
                                              source_has_color=src_color))
    _print_checks(results)
    print(f"PNG: {out}  ({w}x{h}px, {os.path.getsize(out)} bytes)")
    print(f"provenance: {shot.RENDER_LABEL}")
    return 0 if all(ok for _, ok, _ in results) else 1


def cmd_matrix(args) -> int:
    out_dir = args.out or os.path.join(_HERE, "out", "matrix")
    # Only file:/edge: targets are genuinely size-independent raw bytes -- reuse
    # a single capture for them. cmd: re-captures per size (real winsize wrapping)
    # and fx: re-renders per size, because an fx frame takes ctx.width/ctx.height:
    # a frame rendered at 80x24 fed into a 40x12 screen scrolls off the top and
    # looks (falsely) blank. Rendering per size is the faithful path.
    if args.spec.startswith("file:") or args.spec.startswith("edge:"):
        target = resolve_target(args.spec, cols=SIZE0[0], rows=SIZE0[1],
                                seconds=args.seconds, alt_screen=args.alt_screen)
        results = matrix_mod.run_matrix(
            target, out_dir, cell_w=args.cell_w, cell_h=args.cell_h)
    else:
        results = _run_matrix_per_size(args, out_dir)
    _summarize_matrix(results, out_dir)
    return 0 if all(r.ok for r in results) else 1


def _run_matrix_per_size(args, out_dir):
    """cmd targets: capture once per size so wrapping reflects real winsize."""
    os.makedirs(out_dir, exist_ok=True)
    all_results = []
    per_size_targets = {}
    for (cols, rows) in matrix_mod.SIZES:
        t = resolve_target(args.spec, cols=cols, rows=rows,
                           seconds=args.seconds, alt_screen=args.alt_screen)
        per_size_targets[(cols, rows)] = t
    # Render each size with its own bytes, all depths, into one result list.
    name = per_size_targets[matrix_mod.SIZES[0]].name
    label = matrix_mod.shot.RENDER_LABEL
    is_fx = args.spec.startswith("fx:")
    for (cols, rows) in matrix_mod.SIZES:
        t = per_size_targets[(cols, rows)]
        base = shot.render_bytes_to_screen(t.data, cols, rows)
        stream_checks = checks_mod.run_stream_checks(t.data)
        src_color = checks_mod.stream_has_color(t.data)
        # fx frames are a single home+grid; measure raw-frame geometry before
        # pyte clamps it, so an over-wide/over-tall frame is caught (pyte's grid
        # is always clamped to cols and would hide the overflow).
        frame_checks = []
        if is_fx:
            frame_str = t.data.decode("utf-8", "replace").replace("\r\n", "\n")
            fok, fdet = checks_mod.frame_no_overflow(frame_str, cols, max(1, rows - 1))
            frame_checks = [("frame_no_overflow", fok, fdet)]
        for depth in matrix_mod.DEPTHS:
            screen = matrix_mod.apply_depth(base, depth)
            fname = f"{matrix_mod._slug(name)}__{cols}x{rows}__{depth}.png"
            png_path = os.path.join(out_dir, fname)
            w, h = shot.screen_to_png(screen, png_path,
                                      cell_w=args.cell_w, cell_h=args.cell_h)
            cc = list(stream_checks) + frame_checks + checks_mod.run_screen_checks(
                screen, depth=depth, expected_alt=t.alt_screen,
                source_has_color=src_color)
            all_results.append(matrix_mod.CellResult((cols, rows), depth, png_path, w, h, cc))
    merged = matrix_mod.Target(name=name, data=per_size_targets[matrix_mod.SIZES[0]].data,
                               alt_screen=args.alt_screen, label=label)
    matrix_mod.write_contact_sheets(merged, all_results, out_dir)
    return all_results


def cmd_fx(args) -> int:
    data = render_fx_frame(args.effect, args.cols, args.rows)
    screen = shot.render_bytes_to_screen(data, args.cols, args.rows)
    out = args.out or os.path.join(_HERE, "out", f"fx_{args.effect}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    w, h = shot.screen_to_png(screen, out, cell_w=args.cell_w, cell_h=args.cell_h)
    results = checks_mod.run_screen_checks(screen, depth="truecolor")
    _print_checks(results)
    print(f"PNG: {out}  ({w}x{h}px, {os.path.getsize(out)} bytes)")
    print(f"provenance: {shot.RENDER_LABEL}")
    return 0 if all(ok for _, ok, _ in results) else 1


def cmd_selftest(args) -> int:
    return run_selftest(os.path.join(_HERE, "out", "selftest"))


# --------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------
def run_selftest(out_dir: str) -> int:
    """Screenshot a PTY hello + one fx frame; assert PNGs exist & non-empty."""
    os.makedirs(out_dir, exist_ok=True)
    ok_all = True
    print(f"provenance: {shot.RENDER_LABEL}\n")

    # 1) Portable hello via a real PTY. `echo` is a shell builtin on Windows.
    data = shot.capture_cmd([sys.executable, "-c", "print('hello')"], 40, 6, seconds=4.0)
    screen = shot.render_bytes_to_screen(data, 40, 6)
    p1 = os.path.join(out_dir, "pty_hello.png")
    w1, h1 = shot.screen_to_png(screen, p1, cell_w=9, cell_h=19)
    sz1 = os.path.getsize(p1)
    text = "\n".join(safe_screen_display(screen))
    hello_ok = "hello" in text
    r1 = checks_mod.run_stream_checks(data) + checks_mod.run_screen_checks(
        screen, source_has_color=checks_mod.stream_has_color(data))
    print(f"[1] PTY hello -> {p1}  ({w1}x{h1}px, {sz1} bytes)")
    print(f"    'hello' on screen: {hello_ok}")
    _print_checks(r1, indent="    ")
    ok_all &= (sz1 > 0 and hello_ok and os.path.exists(p1)
               and all(ok for _, ok, _ in r1))

    # 2) one fx effect frame (plasma: full-screen truecolor).
    fx_bytes = render_fx_frame("plasma", 40, 12)
    fx_screen = shot.render_bytes_to_screen(fx_bytes, 40, 12)
    p2 = os.path.join(out_dir, "fx_plasma.png")
    w2, h2 = shot.screen_to_png(fx_screen, p2, cell_w=9, cell_h=19)
    sz2 = os.path.getsize(p2)
    r2 = checks_mod.run_screen_checks(fx_screen, depth="truecolor")
    print(f"\n[2] fx plasma frame -> {p2}  ({w2}x{h2}px, {sz2} bytes)")
    _print_checks(r2, indent="    ")
    ok_all &= (sz2 > 0 and os.path.exists(p2) and all(ok for _, ok, _ in r2))

    # 3) an edge-case content matrix cell (CJK), to prove no-mojibake check runs.
    edge = matrix_mod.CONTENT_EDGE_CASES["cjk_wide"]
    edge_screen = shot.render_bytes_to_screen(edge, 40, 4)
    p3 = os.path.join(out_dir, "edge_cjk.png")
    w3, h3 = shot.screen_to_png(edge_screen, p3, cell_w=9, cell_h=19)
    sz3 = os.path.getsize(p3)
    r3 = checks_mod.run_screen_checks(edge_screen, depth="truecolor", expect_content=True,
                                      source_has_color=checks_mod.stream_has_color(edge))
    print(f"\n[3] edge CJK frame -> {p3}  ({w3}x{h3}px, {sz3} bytes)")
    _print_checks(r3, indent="    ")
    ok_all &= (sz3 > 0 and os.path.exists(p3))

    # 4) recipe x terminal-size perception matrix: render each recipe-relevant
    #    screen at (40,12)/(80,24)/(120,40), screenshot it, and assert the
    #    matching recipe's matches() still fires + its structural invariant holds.
    #    Guards against size-dependent recognition bugs (soft-wrap, bottom-row).
    import perception_matrix as pm
    pm_dir = os.path.join(out_dir, "perception")
    pm_outcomes = pm.run(pm_dir, verbose=False)
    pm_ok = all(o.ok for o in pm_outcomes)
    n_ok = sum(1 for o in pm_outcomes if o.ok)
    print(f"\n[4] perception matrix -> {os.path.join(pm_dir, 'index.html')}")
    print(f"    {n_ok}/{len(pm_outcomes)} recipe x size cells recognised "
          f"({len(pm.CASES)} scenarios x {len(pm.SIZES)} sizes)")
    for o in pm_outcomes:
        if not o.ok:
            print(f"    [FAIL] {o.recipe} {o.size[0]}x{o.size[1]}: "
                  f"conf={o.conf:.2f} struct={o.struct_detail}")
    ok_all &= pm_ok

    print("\nSELFTEST:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


# --------------------------------------------------------------------------
# output helpers
# --------------------------------------------------------------------------
def _print_checks(results, indent: str = ""):
    for name, ok, detail in results:
        mark = "ok  " if ok else "FAIL"
        print(f"{indent}[{mark}] {name}: {detail}")


def _summarize_matrix(results, out_dir):
    passed = sum(1 for r in results if r.ok)
    print(f"matrix: {len(results)} cells, {passed} pass, {len(results) - passed} fail")
    print(f"contact sheet: {os.path.join(out_dir, 'index.html')}")
    print(f"                {os.path.join(out_dir, 'index.md')}")
    print(f"provenance: {shot.RENDER_LABEL}")
    for r in results:
        if not r.ok:
            fails = "; ".join(f"{n}: {d}" for n, ok, d in r.checks if not ok)
            print(f"  FAIL {os.path.basename(r.png_path)} -- {fails}")


SIZE0 = matrix_mod.SIZES[1]  # default single-capture size (80x24) for matrix probe


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="screenshot",
        description="pyte -> PNG screenshot smoke-test harness (pyte-simulation, NOT real tmux).")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("shot", help="one-off screenshot of a command")
    sp.add_argument("argv", nargs=argparse.REMAINDER, help="command to run")
    sp.add_argument("--cols", type=int, default=80)
    sp.add_argument("--rows", type=int, default=24)
    sp.add_argument("--seconds", type=float, default=3.0, help="capture time cap")
    sp.add_argument("--alt-screen", action="store_true")
    sp.add_argument("--cell-w", type=int, default=9)
    sp.add_argument("--cell-h", type=int, default=19)
    sp.add_argument("--out", help="output PNG path")
    sp.set_defaults(func=cmd_shot)

    sp = sub.add_parser("matrix", help="full size x depth matrix + contact sheet")
    sp.add_argument("spec", help="cmd:<argv> | fx:<effect> | file:<path> | edge:<name>")
    sp.add_argument("--seconds", type=float, default=3.0)
    sp.add_argument("--alt-screen", action="store_true")
    sp.add_argument("--cell-w", type=int, default=9)
    sp.add_argument("--cell-h", type=int, default=19)
    sp.add_argument("--out", help="output directory")
    sp.set_defaults(func=cmd_matrix)

    sp = sub.add_parser("fx", help="screenshot one fx effect frame")
    sp.add_argument("effect", help="effect name (e.g. plasma)")
    sp.add_argument("--cols", type=int, default=80)
    sp.add_argument("--rows", type=int, default=24)
    sp.add_argument("--cell-w", type=int, default=9)
    sp.add_argument("--cell-h", type=int, default=19)
    sp.add_argument("--out", help="output PNG path")
    sp.set_defaults(func=cmd_fx)

    sp = sub.add_parser("selftest", help="render portable PTY hello + fx frame, assert PNGs")
    sp.set_defaults(func=cmd_selftest)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
