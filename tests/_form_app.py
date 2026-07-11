"""A tiny fill-in form: labelled fields filled top-to-bottom, Tab between,
Enter to submit -- exactly the vocabulary FormPattern.drive uses.

Each field is a ``Label: <echoed value>`` row; the terminal cursor is parked
on the active field's row (right after its echoed value) so FormPattern's
matches() sees a ':' field marker on the cursor row, and its per-field
"value echoed on the cursor row" check passes. On Enter (submit after the
last field) it redraws a confirmation screen echoing every value back, then
stays alive so the driver can snapshot the result.
"""
import sys, msvcrt

FIELDS = ["Name", "Email"]           # filled in order, Tab-separated
FIRST_ROW = 3                        # 1-based row of the first field (row1 title, row2 blank)

values = ["" for _ in FIELDS]
active = 0
done = False


def draw():
    sys.stdout.write("\x1b[2J\x1b[H")            # clear + home
    sys.stdout.write("Please fill in the form:\r\n\r\n")
    for i, name in enumerate(FIELDS):
        sys.stdout.write(f"{name}: {values[i]}\r\n")
    if active < len(FIELDS):
        # Park the cursor on the active field row, just past "Label: value".
        row = FIRST_ROW + active
        col = len(FIELDS[active]) + 2 + len(values[active]) + 1   # "Label: " + value, 1-based
        sys.stdout.write(f"\x1b[{row};{col}H")
    sys.stdout.flush()


def draw_done():
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.write("Form submitted:\r\n\r\n")
    for i, name in enumerate(FIELDS):
        sys.stdout.write(f"{name} = {values[i]}\r\n")
    sys.stdout.flush()


draw()
while True:
    ch = msvcrt.getwch()
    if done:
        if ch == "q":
            break
        continue
    if ch in ("\r", "\n"):                       # submit (recipe sends Enter after last field)
        done = True
        draw_done()
    elif ch == "\t":                             # advance to next field
        if active < len(FIELDS) - 1:
            active += 1
        draw()
    elif ch == "\x08":                           # backspace
        if active < len(FIELDS):
            values[active] = values[active][:-1]
        draw()
    elif ch.isprintable():
        if active < len(FIELDS):
            values[active] += ch
        draw()
