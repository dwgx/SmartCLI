"""Self-test for the three /effort widgets: registration + shape + truecolor.

Run from skills/tui-ui:  python _selftest_effort_widgets.py
Asserts:
  * all three widgets are @register-ed and discoverable
  * GradientRule emits DIFFERENT colors across its width (a real gradient)
  * SliderTrack draws a solid rail + ▲ marker under the selected stop
  * RadialGlow is BRIGHTER at center than at a corner (rounded radial falloff)
  * every widget emits truecolor SGR bytes (\\x1b[38;2 / \\x1b[48;2)
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui import registry
from ui.core import Canvas, get_theme


def _lum(rgb):
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


TRUECOLOR = re.compile(r"\x1b\[(?:38|48);2;\d+;\d+;\d+m")


def main() -> int:
    registry.load_all(force=True)
    for mod, tb in registry.load_errors():
        print(f"LOAD ERROR in {mod}:\n{tb}")
    names = registry.widget_names()
    theme = get_theme("synthwave")
    ok = True

    for key in ("gradient_rule", "slider_track", "radial_glow"):
        assert key in names, f"{key} not registered! known={names}"
    print("[PASS] all three widgets registered:", [k for k in names])

    # --- GradientRule: different colors across width ---
    from ui.widgets_ext.gradient_rule import GradientRule, EFFORT_VIOLET_STOPS
    gr = GradientRule(EFFORT_VIOLET_STOPS, theme=theme)
    cv = gr.render(60, 1)
    row = cv.grid[0]
    left = row[0].fg
    mid = row[30].fg
    right = row[59].fg
    assert row[0].char == "─", f"not solid: {row[0].char!r}"
    assert left != mid != right and left != right, f"gradient flat: {left} {mid} {right}"
    ansi = cv.to_ansi()
    assert TRUECOLOR.search(ansi), "GradientRule emitted no truecolor bytes"
    print(f"[PASS] GradientRule solid '─', colors L={left} M={mid} R={right} (distinct), truecolor OK")

    # --- SliderTrack: solid rail + marker under selected stop ---
    from ui.widgets_ext.slider_track import SliderTrack
    positions = [31, 41, 51, 60, 70, 83]
    st = SliderTrack(["low", "medium", "high", "xhigh", "max", "ultracode"],
                     positions=positions, selected=3, width=124,
                     track_start=30, divider_col=73, theme=theme)
    cv = st.render(124, 3)
    track = cv.grid[st.TRACK_ROW]
    assert track[40].char == "─", f"rail not solid at 40: {track[40].char!r}"
    assert track[73].char == "┊", f"divider missing at 73: {track[73].char!r}"
    marker_row = cv.grid[st.MARKER_ROW]
    assert marker_row[60].char == "▲", f"marker not at col 60: {marker_row[60].char!r}"
    others = [x for x in range(124) if marker_row[x].char == "▲"]
    assert others == [60], f"expected single marker at 60, got {others}"
    ansi = cv.to_ansi()
    assert TRUECOLOR.search(ansi), "SliderTrack emitted no truecolor bytes"
    print(f"[PASS] SliderTrack solid rail, ┊@73, single ▲@{others[0]}, truecolor OK")

    # --- RadialGlow: brighter at center than corner ---
    from ui.widgets_ext.radial_glow import RadialGlow
    W, H = 40, 11
    glow = RadialGlow(W, H, radius=16.0, theme=theme)
    cv = glow.render(W, H)
    cx, cy = W // 2, H // 2
    center_bg = cv.grid[cy][cx].bg
    corner_bg = cv.grid[0][0].bg
    cl, kl = _lum(center_bg), _lum(corner_bg)
    assert cl > kl, f"center ({cl:.1f}) not brighter than corner ({kl:.1f})"
    # rounded: a mid-edge cell should be brighter than the corner (feathered, not square)
    edge_mid_bg = cv.grid[cy][0].bg
    assert _lum(edge_mid_bg) >= kl, "corner should be dimmest (rounded falloff)"
    ansi = cv.to_ansi()
    assert TRUECOLOR.search(ansi), "RadialGlow emitted no truecolor bytes"
    print(f"[PASS] RadialGlow center lum={cl:.1f} > corner lum={kl:.1f} (rounded radial), truecolor OK")

    # --- RadialGlow.paint_bg preserves text (composites BEHIND) ---
    tc = Canvas(W, H, bg=theme.bg)
    tc.put_text(cx - 4, cy, "ultracode", fg=(233, 222, 255))
    glow.paint_bg(tc, 0, 0, W, H)
    lit = tc.grid[cy][cx - 4]
    assert lit.char == "u", f"glow overwrote text: {lit.char!r}"
    assert lit.fg == (233, 222, 255), f"glow changed text fg: {lit.fg}"
    assert lit.bg is not None and _lum(lit.bg) > kl, "paint_bg did not light text bg"
    print(f"[PASS] RadialGlow.paint_bg kept text crisp (char='u' fg={lit.fg}), lit bg behind it")

    # --- pulse animation actually changes the field over t ---
    g0 = RadialGlow(W, H, radius=16.0, t=0.0, theme=theme)
    g1 = RadialGlow(W, H, radius=16.0, t=0.5, theme=theme)
    probe_x = cx + 13  # inside at peak radius, outside at the trough
    e0 = g0.intensity_at(probe_x, cy, W, H)
    e1 = g1.intensity_at(probe_x, cy, W, H)
    assert e1 > e0, f"pulse peak (t=.5, {e1:.3f}) not larger than trough (t=0, {e0:.3f})"
    print(f"[PASS] RadialGlow breathing: edge intensity trough={e0:.3f} < peak={e1:.3f}")

    print("\nALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
