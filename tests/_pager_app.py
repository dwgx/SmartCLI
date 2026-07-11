"""A tiny less/more-style pager: read-only text + a bottom status prompt.

Draws a window of body lines, keeps a '--More--' status line pinned to the
bottom row (so smartcli_core anchors it as the status bar), and switches to
'(END)' once the last page is shown. Keys: Space/f page down, b page up,
g top, G bottom, q quit -- exactly the vocabulary PagerPattern.drive uses
(it sends Space for 'to_end').
"""
import sys, msvcrt

PAGE = 18          # body rows shown per screen (row 24 is the status line)
BOTTOM_ROW = 24    # 1-based terminal row for the status prompt

# Deterministic, ASCII-only body so classification stays crisp (no %, no '/',
# no ':' prompt, no y/N -- nothing that trips confirm/progress/search_filter).
_WORDS = ("the quick brown fox jumps over the lazy dog while paging through "
          "the document one screenful at a time").split()
LINES = [f"Line {i + 1:03d}: " + " ".join(_WORDS[: 3 + (i % 6)])
         for i in range(45)]
TOTAL = len(LINES)

top = 0            # index of the first body line currently shown


def _at_bottom() -> bool:
    return top + PAGE >= TOTAL


def draw():
    sys.stdout.write("\x1b[2J\x1b[H")          # clear + home
    for r in range(PAGE):
        idx = top + r
        if idx < TOTAL:
            sys.stdout.write(LINES[idx] + "\r\n")
        else:
            sys.stdout.write("~\r\n")          # vi-style past-end filler
    status = "(END)" if _at_bottom() else "--More--"
    sys.stdout.write(f"\x1b[{BOTTOM_ROW};1H{status}")   # pin to bottom row
    sys.stdout.flush()


def _page_down():
    global top
    if not _at_bottom():
        top = min(top + PAGE, max(0, TOTAL - PAGE))


def _page_up():
    global top
    top = max(0, top - PAGE)


def _read_key():
    """One logical key: swallows Windows/ANSI escape sequences to a token."""
    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):                 # Windows fn/arrow prefix
        ch2 = msvcrt.getwch()
        return {"Q": "pgdn", "I": "pgup"}.get(ch2, "")   # PgDn / PgUp
    if ch == "\x1b":                           # ANSI CSI sequence
        if msvcrt.getwch() == "[":
            seq = ""
            while True:
                c = msvcrt.getwch()
                seq += c
                if c.isalpha() or c == "~":
                    break
            return {"6~": "pgdn", "5~": "pgup"}.get(seq, "")
        return ""
    return ch


draw()
while True:
    key = _read_key()
    if key in (" ", "f", "pgdn"):
        _page_down(); draw()
    elif key in ("b", "pgup"):
        _page_up(); draw()
    elif key == "g":
        top = 0; draw()
    elif key == "G":
        top = max(0, TOTAL - PAGE); draw()
    elif key == "q":
        sys.stdout.write("\x1b[2J\x1b[HQUIT\r\n")
        sys.stdout.flush()
        break
