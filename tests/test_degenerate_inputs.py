#!/usr/bin/env python
"""test_degenerate_inputs.py — regression locks for the degenerate-input crashes
found by the fx/tui-ui defect review (all in skill code, not smartcli_core).

Each check reproduces an input that used to raise (ZeroDivisionError / IndexError
/ ValueError) and asserts it now degrades gracefully instead of crashing. Fast,
no PTY, no animation loop.

Run:  python tests/test_degenerate_inputs.py   (exit 0 = pass)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "skills" / "tui-ui"))
sys.path.insert(0, str(_ROOT / "skills" / "cmd-art"))

_fails = []


def check_no_raise(fn, name):
    try:
        fn()
        print(f"[PASS] {name}")
    except Exception as e:  # noqa: BLE001 - we are asserting NO exception
        print(f"[FAIL] {name}  raised {type(e).__name__}: {e}")
        _fails.append(name)


def check(cond, name, detail=""):
    print(f"{'[PASS]' if cond else '[FAIL]'} {name}  {detail}")
    if not cond:
        _fails.append(name)


def main() -> int:
    from ui.field import Ripple
    from ui.widgets_ext.slider_track import SliderTrack
    from ui.widgets_ext.braille_chart import BrailleChart
    from fx.base import Param

    print("=" * 60)
    print("degenerate-input regression locks")
    print("=" * 60)

    # field.Ripple degenerate params (were ZeroDivisionError / IndexError)
    check_no_raise(lambda: Ripple(origin=(0, 0), wavelength=0.0, travel=10.0).sample(1, 1),
                   "Ripple wavelength=0 does not divide-by-zero")
    check_no_raise(lambda: Ripple(origin=(0, 0), wavelength=20.0, travel=10.0,
                                  falloff_radius=0.0).sample(1, 1),
                   "Ripple falloff_radius=0 does not divide-by-zero")
    check_no_raise(lambda: Ripple(origin=(0, 0), wavelength=20.0, travel=10.0,
                                  palette=[]).sample(0, 0),
                   "Ripple empty palette does not IndexError")

    # SliderTrack empty positions list (was ValueError max()/IndexError)
    check_no_raise(lambda: SliderTrack(["a", "b"], positions=[]).measure(20, 3),
                   "SliderTrack positions=[] measure does not crash")
    check_no_raise(lambda: SliderTrack(["a", "b"], positions=[]).render(20, 3),
                   "SliderTrack positions=[] render does not crash")

    # BrailleChart NaN in series (was ValueError NaN->int)
    check_no_raise(lambda: BrailleChart([float("nan"), 1, 2]).render(10, 3),
                   "BrailleChart NaN in series does not crash")

    # Param int coercion: zero-padded decimals work; hex kept; bad input clean err
    p = Param("count", "int")
    check(p.coerce("08") == 8, "Param int '08' -> 8 (not base-0 ValueError)", f"={p.coerce('08')}")
    check(p.coerce("010") == 10, "Param int '010' -> 10", f"={p.coerce('010')}")
    check(p.coerce("0x10") == 16, "Param int '0x10' -> 16 (hex preserved)", f"={p.coerce('0x10')}")
    # sign symmetry: +0x/-0x both honored (a prior fix narrowed this by omitting +)
    check(p.coerce("+0x10") == 16, "Param int '+0x10' -> 16 (plus-signed hex)", f"={p.coerce('+0x10')}")
    check(p.coerce("-0x10") == -16, "Param int '-0x10' -> -16 (minus-signed hex)", f"={p.coerce('-0x10')}")
    try:
        p.coerce("abc")
        check(False, "Param int 'abc' raises ValueError", "no error raised")
    except ValueError as e:
        check("count" in str(e) and "abc" in str(e),
              "Param int 'abc' -> clean ValueError naming param+value", f"{e}")

    print("-" * 60)
    if _fails:
        print(f"FAIL: {len(_fails)} check(s) failed: {_fails}")
        return 1
    print("PASS: all degenerate-input regression locks hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
