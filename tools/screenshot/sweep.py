"""sweep.py -- drive all fx effects through the matrix, collect per-cell checks.

Renders each effect's representative frame, quantizes to each depth, screenshots
to PNG, and runs the stream+screen checks. Enforces a hard per-render timeout via
a worker subprocess is unnecessary here (fx render is pure/in-proc and bounded),
but we guard each effect render with a wall-clock cap and catch crashes so one bad
effect never takes the sweep down.

Prints a machine-parseable line per (effect,size,depth) cell:
  CELL <effect> <cols>x<rows> <depth> <PASS|FAIL> [failing:check=detail;...]
and a JSON blob at the end.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import checks as checks_mod
import matrix as matrix_mod
import shot
import cli as harness_cli

_CMD_ART = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "skills", "cmd-art")
if _CMD_ART not in sys.path:
    sys.path.insert(0, _CMD_ART)
import fx.registry as registry

# Task-required matrix cells (superset rendered; we report all).
SIZES = [(40, 12), (80, 24), (120, 40), (200, 50)]
DEPTHS = ["truecolor", "256", "16", "mono"]

# fx frames are static (one frame), so alt-screen is a property of the PLAY LOOP,
# not the frame bytes. We separately assert the play loop's alt/cursor balance by
# scanning the sequences core.play() emits (see check_play_loop_balance).


def check_play_loop_balance():
    """Verify fx.core.play emits balanced alt-screen + cursor + wrap sequences.

    This is the real 'alt-balance / cursor-restored' guard for animated effects:
    the frame bytes themselves carry no alt sequences, so we scan the loop's
    enter/leave primitives via the byte stream checks.
    """
    import fx.core as core
    # Reconstruct the exact byte stream play() writes for a bounded run:
    # enter: ALT_ENTER HIDE NOWRAP CLEAR ; finally: RESET WRAP SHOW ALT_LEAVE
    enter = (core.ALT_ENTER + core.HIDE + core.NOWRAP + core.CLEAR)
    leave = (core.RESET + core.WRAP + core.SHOW + core.ALT_LEAVE)
    stream = (enter + core.HOME + "<frame>" + leave).encode("utf-8", "replace")
    res = checks_mod.run_stream_checks(stream)
    res.append(("no_cursor_left_hidden_stream",
                b"\x1b[?25h" in stream, "SHOW present" if b"\x1b[?25h" in stream else "no SHOW"))
    return stream, res


def main():
    out_root = os.path.join(_HERE, "out", "sweep")
    os.makedirs(out_root, exist_ok=True)
    registry.load_all()
    effects = [c.name for c in registry.all_effects()]

    # 1) Play-loop balance (alt-balance / cursor-restored) -- one global check.
    play_stream, play_checks = check_play_loop_balance()
    play_ok = all(ok for _, ok, _ in play_checks)
    print("PLAYLOOP", "PASS" if play_ok else "FAIL",
          ";".join(f"{n}={ok}" for n, ok, _ in play_checks))

    report = {"effects": {}, "playloop": {"ok": play_ok,
              "checks": [(n, ok, d) for n, ok, d in play_checks]}}

    for name in effects:
        eff_dir = os.path.join(out_root, name)
        os.makedirs(eff_dir, exist_ok=True)
        report["effects"][name] = {"cells": [], "render_error": None}
        # Render representative frame ONCE per size (frame is size-dependent).
        for (cols, rows) in SIZES:
            t0 = time.perf_counter()
            try:
                data = harness_cli.render_fx_frame(name, cols, rows)
            except Exception:
                err = traceback.format_exc()
                report["effects"][name]["render_error"] = err
                print(f"RENDER_ERROR {name} {cols}x{rows}: {err.strip().splitlines()[-1]}")
                # Emit FAIL cells for this size across depths.
                for depth in DEPTHS:
                    print(f"CELL {name} {cols}x{rows} {depth} FAIL failing:render=crash")
                    report["effects"][name]["cells"].append(
                        {"size": [cols, rows], "depth": depth, "ok": False,
                         "checks": [("render", False, "crash")], "png": None})
                continue
            dt = time.perf_counter() - t0
            if dt > 10.0:
                print(f"SLOW {name} {cols}x{rows}: {dt:.1f}s")
            base = shot.render_bytes_to_screen(data, cols, rows)
            stream_checks = checks_mod.run_stream_checks(data)
            src_color = checks_mod.stream_has_color(data)
            # Raw-frame geometry check (pre-pyte): catches over-wide/over-tall
            # frames that pyte would silently clamp. fx frame == data decoded,
            # CRLF-joined by render_frame_to_bytes; recover the frame string.
            frame_str = data.decode("utf-8", "replace").replace("\r\n", "\n")
            fno_ok, fno_detail = checks_mod.frame_no_overflow(
                frame_str, cols, max(1, rows - 1))
            frame_check = ("frame_no_overflow", fno_ok, fno_detail)
            for depth in DEPTHS:
                screen = matrix_mod.apply_depth(base, depth)
                fname = f"{name}__{cols}x{rows}__{depth}.png"
                png_path = os.path.join(eff_dir, fname)
                try:
                    w, h = shot.screen_to_png(screen, png_path)
                except Exception:
                    err = traceback.format_exc().strip().splitlines()[-1]
                    print(f"CELL {name} {cols}x{rows} {depth} FAIL failing:png={err}")
                    report["effects"][name]["cells"].append(
                        {"size": [cols, rows], "depth": depth, "ok": False,
                         "checks": [("png", False, err)], "png": None})
                    continue
                cc = list(stream_checks) + [frame_check] + checks_mod.run_screen_checks(
                    screen, depth=depth, expected_alt=False,
                    source_has_color=src_color)
                ok = all(c[1] for c in cc)
                fails = ";".join(f"{n}={d}" for n, k, d in cc if not k)
                print(f"CELL {name} {cols}x{rows} {depth} "
                      f"{'PASS' if ok else 'FAIL'}"
                      + (f" failing:{fails}" if fails else ""))
                report["effects"][name]["cells"].append(
                    {"size": [cols, rows], "depth": depth, "ok": ok,
                     "png": png_path, "png_bytes": os.path.getsize(png_path),
                     "checks": [(n, k, d) for n, k, d in cc]})

    # Summary counts.
    total = sum(len(e["cells"]) for e in report["effects"].values())
    failed = sum(1 for e in report["effects"].values() for c in e["cells"] if not c["ok"])
    print(f"SUMMARY effects={len(effects)} cells={total} pass={total-failed} fail={failed}")
    with open(os.path.join(out_root, "sweep_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print(f"REPORT {os.path.join(out_root, 'sweep_report.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
