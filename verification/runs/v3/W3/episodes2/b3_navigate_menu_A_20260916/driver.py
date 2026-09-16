"""Episode B3_navigate_menu, track A (app-adapted).

Transport: a ConPTY session (the menu is painted and observed) plus the fixture's
*own enumerated application channel*: a loopback control socket that accepts the
same logical presses (``{"press": "down"}`` / ``{"press": "enter"}``) instead of
console keystrokes.

Enumerated app channel: ``127.0.0.1:<port>``, one JSON line per press, ack per
line.  The menu state machine, the reverse-video bar and the state file are the
same as in the U fixture; only the transport of the press differs, and each press
is counted as an ``app_channel`` action.

Run: python -B episodes2/b3_navigate_menu_A_20260916/driver.py
"""
from __future__ import annotations

import json
import random
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _harness as H  # noqa: E402

TASK = "B3_navigate_menu"
TRACK = "A"
TRANSPORT = "windows-conpty (WinptyBackend) + fixture control socket app channel"
RUN_ID = f"b3_navigate_menu_{TRACK}_{H.DATE}"

from smartcli_core import PtySession  # noqa: E402

RNG = random.Random(f"{H.SEED}|{TASK}")
SUFFIX = f"{RNG.randrange(0x1000, 0x10000):04x}"

FIXTURE_SRC = '''"""Fixture for B3, track A: the same 3-item menu, presses over a control socket."""
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
    out("\\x1b[2J\\x1b[H\\x1b[?25l")
    out("SELECT an action (control socket, Enter):\\r\\n")
    for i, name in enumerate(ITEMS):
        label = ("> " if i == sel else "  ") + name
        if i == sel:
            out("\\x1b[7m" + f"{label:<20}" + "\\x1b[0m\\r\\n")
        else:
            out(" " + f"{label:<20}" + "\\r\\n")
    out(f"selected_index={sel}\\r\\n")


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
        while not raw.endswith(b"\\n"):
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
            conn.sendall(b'{"ack": "down", "selected_index": ' + str(sel).encode() + b'}\\n')
        elif press == "up":
            sel = (sel - 1) % len(ITEMS)
            draw(sel)
            conn.sendall(b'{"ack": "up", "selected_index": ' + str(sel).encode() + b'}\\n')
        elif press == "enter":
            conn.sendall(b'{"ack": "enter", "selected": "' + ITEMS[sel].encode() + b'"}\\n')
            break
        else:
            conn.sendall(b'{"ack": "ignored"}\\n')

picked = ITEMS[sel]
out("\\x1b[2J\\x1b[H\\x1b[?25h")
out(f"PRESSES_RECEIVED {presses!r}\\r\\n")
out(f"SELECTED: {picked}\\r\\n")
state_path.write_text(json.dumps({"selection": picked, "exited": True,
                                  "channel": "control_socket", "presses_received": presses},
                                 indent=1), encoding="utf-8")
out(f"WROTE {state_path.name} bytes={state_path.stat().st_size} selection={picked}\\r\\n")
out("BYE\\r\\n")
sys.exit(0)
'''


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def press(port: int, name: str) -> dict:
    """One round trip on the app channel."""
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.sendall(json.dumps({"press": name}).encode() + b"\n")
        ack = sock.makefile("r", encoding="utf-8").readline().strip()
    return {"press": name, "ack": ack}


def main() -> int:
    ep = H.new_episode(TASK, TRACK, TRANSPORT)
    here, actions, observations, started = ep["dir"], ep["actions"], ep["observations"], ep["started"]
    state_file = here / f"episode_b3_{SUFFIX}.json"
    fixture = here / "menu_socket_fixture.py"
    port = free_port()

    fixture.write_text(FIXTURE_SRC, encoding="utf-8", newline="\n")
    if state_file.exists():
        state_file.unlink()
    setup = [{"what": "fixture program (control-socket channel)", "path": str(fixture),
              "sha256": H.sha256(fixture), "outside_pty": True},
             {"what": "enumerated app channel", "kind": "loopback control socket",
              "endpoint": f"127.0.0.1:{port}", "outside_pty": True},
             {"what": "program state file absent before the episode", "path": str(state_file),
              "exists": state_file.exists(), "outside_pty": True}]

    argv = [sys.executable, "-B", str(fixture), str(state_file), str(port)]
    sess = PtySession(cols=90, rows=24)
    sess.start(argv)

    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker="SELECT an action", max_wait_ms=10000)
    opened_screen = snap.to_text()
    selected_at_open = snap.selected.text if snap.selected else None
    observations.append({"step": "menu drawn, selection on the first item", "reason": reason,
                         "selected": selected_at_open, "screen": opened_screen})
    if reason == "TIMEOUT":
        return H.finalize(run_id=RUN_ID, task=TASK, track=TRACK, transport=TRANSPORT,
                          episode_dir=here, actions=actions, observations=observations,
                          setup=setup, claim=False, completion_basis="claim_withheld",
                          completion_detail={"in_episode_check": "the menu never drew"},
                          fixture_state={"selection": None, "exited": False},
                          fixture_state_source="filesystem",
                          session={"driver": "smartcli_core.PtySession", "argv": argv},
                          started=started, ui_claim=False,
                          track_note="app-adapted: control socket channel")

    actions["app_channel"] += 1
    down = press(port, "down")
    actions["wait"] += 1
    sess.wait_stable(quiet_ms=250, max_wait_ms=4000)
    actions["snapshot"] += 1
    snap = sess.snapshot()
    after_down = snap.to_text()
    selected_after_down = snap.selected.text if snap.selected else None
    observations.append({"step": "down over the control socket moved the selection bar",
                         "channel_round_trip": down, "selected": selected_after_down,
                         "screen": after_down})

    actions["app_channel"] += 1
    enter = press(port, "enter")
    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker="SELECTED: save", max_wait_ms=8000)
    after_enter = snap.to_text()
    observations.append({"step": "enter over the control socket picked save",
                         "channel_round_trip": enter, "reason": reason, "screen": after_enter})

    actions["wait"] += 1
    exit_info = H.wait_exit(sess, timeout_s=8.0)
    actions["snapshot"] += 1
    final_screen = sess.snapshot().to_text()
    observations.append({"step": "after exit", "screen": final_screen})

    close_state = sess.close()
    close_state_name = ("closed_confirmed" if close_state.get("closed_confirmed")
                        else "close_unconfirmed")

    written = state_file.exists()
    program_state = json.loads(state_file.read_text(encoding="utf-8")) if written else {}
    claim = bool(selected_after_down and "save" in selected_after_down
                 and "SELECTED: save" in final_screen and "BYE" in final_screen
                 and program_state.get("selection") == "save" and exit_info["exited"])
    fixture_state = {
        "selection": program_state.get("selection"),
        "exited": bool(exit_info["exited"]),
        "state_file": str(state_file),
        "state_file_written": written,
        "program_channel": program_state.get("channel"),
        "program_presses_received": program_state.get("presses_received"),
        "selected_at_open": selected_at_open,
        "selected_after_one_down": selected_after_down,
    }
    return H.finalize(
        run_id=RUN_ID, task=TASK, track=TRACK, transport=TRANSPORT, episode_dir=here,
        actions=actions, observations=observations, setup=setup, claim=claim,
        completion_basis="child_exit_observed" if claim else "claim_withheld",
        completion_detail={"in_episode_check": fixture_state},
        fixture_state=fixture_state,
        fixture_state_source=("the program's own state file (written by it) plus the runtime's "
                              "exit observation; the screen corroborates the navigation"),
        session={"driver": "smartcli_core.PtySession + fixture control socket",
                 "argv": argv, "cols": 90, "rows": 24, "cancel": False,
                 "process_exited": bool(exit_info["exited"]),
                 "exit_observed_by": exit_info["observation"], "exit_evidence": exit_info,
                 "close_state": close_state_name,
                 "close_observed": f"backend close_state()={close_state}",
                 "close_state_detail": close_state},
        started=started, ui_claim=False,
        track_note=("app-adapted (track A): both presses travelled over the program's own "
                    "control socket; no keystroke entered the UI"))


if __name__ == "__main__":
    raise SystemExit(main())
