"""Render the three widgets + an assembled /effort frame through pyte -> PNG.

Uses the harness at tools/screenshot (shot.py). Writes PNGs to tools/screenshot/out.
This is a pyte VT-emulation render (faithful cell grid), NOT a real Windows
Terminal capture — final animation cadence / anti-aliasing must be eyeballed by
the user in a real terminal.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)                                  # ui package
sys.path.insert(0, os.path.join(REPO, "tools", "screenshot"))  # shot.py

import shot  # noqa: E402
from ui.core import BOLD, Canvas, get_theme  # noqa: E402
from ui.widgets_ext.gradient_rule import GradientRule, EFFORT_VIOLET_STOPS  # noqa: E402
from ui.widgets_ext.slider_track import SliderTrack  # noqa: E402
from ui.widgets_ext.radial_glow import RadialGlow  # noqa: E402

OUT = os.path.join(REPO, "tools", "screenshot", "out")
os.makedirs(OUT, exist_ok=True)
theme = get_theme("synthwave")
COLS, ROWS = 124, 12

STAGE_COLS = {"low": 31, "medium": 41, "high": 51, "xhigh": 60, "max": 70, "ultracode": 83}
STAGE_ACCENT = {
    "low": (0xFF, 0xC1, 0x07), "medium": (0x4E, 0xBA, 0x65), "high": (0x8E, 0x92, 0xB8),
    "xhigh": (0xA0, 0x7C, 0xE9), "max": (0xFA, 0xC3, 0x5F), "ultracode": (0xC4, 0xA8, 0xFF),
}
STAGES = ["low", "medium", "high", "xhigh", "max", "ultracode"]
positions = [STAGE_COLS[s] for s in STAGES]


def save(cv: Canvas, name: str):
    data = shot.render_frame_to_bytes(cv.to_ansi())
    screen = shot.render_bytes_to_screen(data, cv.w, cv.h)
    path = os.path.join(OUT, name)
    shot.screen_to_png(screen, path, draw_cursor=False)
    print("wrote", path)


def build_effort_frame(selected_idx: int, t: float) -> Canvas:
    """Assemble the /effort region: rule, labels, track, marker, stages, glow, hint."""
    cv = Canvas(COLS, ROWS, bg=theme.bg)
    sel = STAGES[selected_idx]

    # R-1 main rule (row 0): full-width violet gradient solid.
    rule = GradientRule(EFFORT_VIOLET_STOPS, theme=theme)
    cv.blit(rule.render(COLS, 1), 0, 0)

    # R0 Effort label (row 1).
    cv.put_text(4, 1, "Effort", fg=(240, 240, 240), attrs=BOLD)
    # R2 Faster / Smarter (row 3).
    cv.put_text(30, 3, "Faster", fg=(230, 230, 230))
    cv.put_text(85, 3, "Smarter", fg=(230, 230, 230))

    # R3/R4/R5 slider track + marker + stage labels (rows 4,5,6).
    track = SliderTrack(
        STAGES, positions=positions, selected=selected_idx, width=124,
        track_start=30, divider_col=73, divider_color="#5A5A6A",
        track_color="#6E7080", track_color2="#A07CE9",
        label_colors=[STAGE_ACCENT[s] if (s == sel or s == "ultracode") else "#6E7080"
                      for s in STAGES],
        marker_color=STAGE_ACCENT[sel], theme=theme,
    )
    sub = track.render(124, 3)  # rows: track,marker,labels
    cv.blit(sub, 0, 4)

    # Draw ALL text FIRST (subtitle + brightened ultracode label), so the glow
    # can be composited BEHIND it last via paint_bg (text stays crisp on top).
    if sel == "ultracode":
        u = STAGE_COLS["ultracode"]
        cv.put_text(u - len("ultracode") // 2, 6, "ultracode",
                    fg=(233, 222, 255), attrs=BOLD)          # bright near-white
        cv.put_text(75, 7, "xhigh + workflows", fg=(138, 138, 153))  # R6 subtitle

    # R8 hint (row 9).
    cv.put_text(4, 9, "←/→ to adjust · Enter to confirm · Esc to cancel",
                fg=(138, 138, 153))

    # Ultracode glow: composite as a BACKGROUND field behind rows 3..9, LAST,
    # after every glyph is placed. paint_bg only touches .bg, so text is crisp.
    if sel == "ultracode":
        glow = RadialGlow(
            COLS, ROWS, center=(83.0, 6.0), radius=17.0, aspect=2.1,
            base_bg=theme.bg, t=t, pulse_min=0.6, pulse_max=1.0,
            exponent=2.4, gamma=1.1, theme=theme,
        )
        glow.paint_bg(cv, 0, 3, COLS, 7)   # rows 3..9; main rule (row 0) stays crisp
    return cv


# Standalone widget shots.
save(GradientRule(EFFORT_VIOLET_STOPS, theme=theme).render(80, 1), "w_gradient_rule.png")
save(SliderTrack(STAGES, positions=positions, selected=2, width=124, track_start=30,
                 divider_col=73, track_color="#6E7080", track_color2="#A07CE9",
                 theme=theme).render(124, 3), "w_slider_track.png")
save(RadialGlow(60, 13, radius=22.0, aspect=2.1, base_bg=theme.bg, theme=theme).render(60, 13),
     "w_radial_glow.png")

# Assembled /effort frames.
save(build_effort_frame(0, 0.0), "effort_low.png")
save(build_effort_frame(3, 0.0), "effort_xhigh.png")
save(build_effort_frame(5, 0.0), "effort_ultracode_C_trough.png")
save(build_effort_frame(5, 0.5), "effort_ultracode_B_peak.png")
save(build_effort_frame(5, 0.25), "effort_ultracode_A_mid.png")
print("DONE")
