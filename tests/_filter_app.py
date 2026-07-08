"""fzf-like incremental filter: query prompt + candidate list + X/Y count."""
import sys, msvcrt

ITEMS = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "apple", "grape"]
query = ""

def draw():
    matched = [it for it in ITEMS if query.lower() in it.lower()]
    sys.stdout.write("\x1b[2J\x1b[H")
    # candidate list (reverse layout: list below prompt)
    sys.stdout.write(f"> {query}\r\n")
    sys.stdout.write(f"  {len(matched)}/{len(ITEMS)}\r\n")
    sys.stdout.write("-------------------\r\n")
    for i, it in enumerate(matched[:8]):
        ptr = ">" if i == 0 else " "
        sys.stdout.write(f"{ptr} {it}\r\n")
    # park the terminal cursor back on the query line (col after "> " + query),
    # exactly as fzf does — the query line is row 1.
    sys.stdout.write(f"\x1b[1;{3 + len(query)}H")
    sys.stdout.flush()

draw()
while True:
    ch = msvcrt.getwch()
    if ch in ("\r", "\n"):
        matched = [it for it in ITEMS if query.lower() in it.lower()]
        top = matched[0] if matched else ""
        sys.stdout.write(f"\x1b[2J\x1b[HPICKED: {top}\r\n")
        sys.stdout.flush()
        break
    elif ch == "\x08":  # backspace
        query = query[:-1]
        draw()
    elif ch.isprintable():
        query += ch
        draw()
