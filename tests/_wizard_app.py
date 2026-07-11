"""A tiny multi-step wizard/installer: 'Step N of 3 ... Press Enter to
continue', ending on a 'Setup complete!' screen.

Shape is tuned for WizardPattern: the cursor is parked on the ``Step N of 3``
line (so matches() scores 0.9 off _STEP_RE on the cursor row), an advance hint
is pinned to the bottom status row, and each screen is deliberately NOT a
confirm/progress/pager/menu/search so the wizard's auto-classify falls through
to its Enter-advance fallback. The screen text changes every step (so the
loop-guard sees progress) and the final screen carries the 'complete' done
marker on the cursor row so _is_done() fires.

Keys: Enter advances; q exits the final screen.
"""
import sys, msvcrt

TOTAL = 3
BOTTOM_ROW = 24
DESCRIPTIONS = {
    1: "Choose your workspace directory.",
    2: "Select optional components.",
    3: "Review your selections.",
}

step = 1
finished = False


def draw_step():
    sys.stdout.write("\x1b[2J\x1b[H")                       # clear + home
    sys.stdout.write(f"Step {step} of {TOTAL}\r\n\r\n")     # row 1
    sys.stdout.write(DESCRIPTIONS[step] + "\r\n")           # row 3
    sys.stdout.write(f"\x1b[{BOTTOM_ROW};1HPress Enter to continue")  # status row
    sys.stdout.write("\x1b[1;1H")                           # park cursor on "Step N of 3"
    sys.stdout.flush()


def draw_done():
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.write("Setup complete!\r\n")                 # 'complete' == done marker
    sys.stdout.write("\x1b[1;1H")                           # park cursor on the done line
    sys.stdout.flush()


draw_step()
while True:
    ch = msvcrt.getwch()
    if finished:
        if ch == "q":
            break
        continue
    if ch in ("\r", "\n"):
        if step < TOTAL:
            step += 1
            draw_step()
        else:
            finished = True
            draw_done()
