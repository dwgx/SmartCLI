"""Fixture for B3, track A: the same 3-item menu, presses over a control socket."""
import json
import socket
import sys
from pathlib import Path

ITEMS = ["open", "save", "quit"]
state_path = Path(sys.argv[1])
port = int(sys.argv[2])


def out(text):
    sys.stdout.write(text)
    sys.stdout.flush()


def draw(sel):
    out("\x1b[2J\x1b[H\x1b[?25l")
    out("SELECT an action (control socket, Enter):\r\n")
    for i, name in enumerate(ITEMS):
        label = ("> " if i == sel else "  ") + name
        if i == sel:
            out("\x1b[7m" + f"{label:<20}" + "\x1b[0m\r\n")
        else:
            out(" " + f"{label:<20}" + "\r\n")
    out(f"selected_index={sel}\r\n")


srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", port))
srv.listen(4)
print(f"CONTROL 127.0.0.1:{port} listening")

presses = []
sel = 0
draw(sel)

while True:
    conn, _ = srv.accept()
    raw = b""
    with conn:
        while not raw.endswith(b"\n"):
            chunk = conn.recv(4096)
            if not chunk:
                break
            raw += chunk
        msg = json.loads(raw.decode("utf-8") or "{}")
        press = str(msg.get("press", ""))
        presses.append(press)
        if press == "down":
            sel = (sel + 1) % len(ITEMS)
            draw(sel)
            conn.sendall(b'{"ack": "down", "selected_index": ' + str(sel).encode() + b'}\n')
        elif press == "up":
            sel = (sel - 1) % len(ITEMS)
            draw(sel)
            conn.sendall(b'{"ack": "up", "selected_index": ' + str(sel).encode() + b'}\n')
        elif press == "enter":
            conn.sendall(b'{"ack": "enter", "selected": "' + ITEMS[sel].encode() + b'"}\n')
            break
        else:
            conn.sendall(b'{"ack": "ignored"}\n')

picked = ITEMS[sel]
out("\x1b[2J\x1b[H\x1b[?25h")
out(f"PRESSES_RECEIVED {presses!r}\r\n")
out(f"SELECTED: {picked}\r\n")
state_path.write_text(json.dumps({"selection": picked, "exited": True,
                                  "channel": "control_socket", "presses_received": presses},
                                 indent=1), encoding="utf-8")
out(f"WROTE {state_path.name} bytes={state_path.stat().st_size} selection={picked}\r\n")
out("BYE\r\n")
sys.exit(0)
