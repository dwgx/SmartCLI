"""A tiny full-screen ANSI menu: reverse-video bar, Up/Down nav, Enter selects."""
import sys, msvcrt

ITEMS = ["Apple", "Banana", "Cherry", "Date", "Elderberry"]
sel = 0

def draw():
    sys.stdout.write("\x1b[2J\x1b[H")          # clear + home
    sys.stdout.write("Pick a fruit (Up/Down, Enter):\r\n\r\n")
    for i, it in enumerate(ITEMS):
        if i == sel:
            sys.stdout.write(f"\x1b[7m  {it}  \x1b[0m\r\n")   # reverse video bar
        else:
            sys.stdout.write(f"  {it}  \r\n")
    sys.stdout.write("\x1b[?25l")               # hide cursor (classic menu)
    sys.stdout.flush()

draw()
while True:
    ch = msvcrt.getwch()
    if ch == "\x00" or ch == "\xe0":            # arrow prefix on Windows
        ch2 = msvcrt.getwch()
        if ch2 == "H":                          # Up
            sel = (sel - 1) % len(ITEMS)
        elif ch2 == "P":                        # Down
            sel = (sel + 1) % len(ITEMS)
        draw()
    elif ch == "\x1b":                          # ANSI arrow (ESC [ A/B)
        ch2 = msvcrt.getwch()
        if ch2 == "[":
            ch3 = msvcrt.getwch()
            if ch3 == "A":
                sel = (sel - 1) % len(ITEMS)
            elif ch3 == "B":
                sel = (sel + 1) % len(ITEMS)
            draw()
    elif ch in ("\r", "\n"):
        sys.stdout.write("\x1b[2J\x1b[H\x1b[?25h")
        sys.stdout.write(f"CHOSE: {ITEMS[sel]}\r\n")
        sys.stdout.flush()
        break
