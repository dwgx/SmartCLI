"""Episode B2_confirm_prompt, track A (app-adapted).

Transport: a ConPTY session (the prompt is really painted and observed) plus the
fixture's *own enumerated application channel*: a loopback control socket that the
program opens itself and through which the confirmation is delivered.

Enumerated app channel: ``127.0.0.1:<port>``, one JSON line
``{"answer": "<letter>"}`` -- the fixture (written by this driver) binds it before
it prints the prompt.  No keystroke is sent into the UI; the answer travels over
the channel and is counted as an ``app_channel`` action.

Run: python -B episodes2/b2_confirm_prompt_A_20260916/driver.py
"""
from __future__ import annotations

import json
import random
import re
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _harness as H  # noqa: E402

TASK = "B2_confirm_prompt"
TRACK = "A"
TRANSPORT = "windows-conpty (WinptyBackend) + fixture control socket app channel"
RUN_ID = f"b2_confirm_prompt_{TRACK}_{H.DATE}"

from smartcli_core import PtySession  # noqa: E402

RNG = random.Random(f"{H.SEED}|{TASK}")
SUFFIX = f"{RNG.randrange(0x1000, 0x10000):04x}"

FIXTURE_SRC = '''"""Fixture for B2, track A: confirm-over-control-socket.

Same target semantics as the U fixture (writes the file only on `y`); the answer
arrives on the program's own control socket instead of on stdin.
"""
import json
import pathlib
import socket
import sys

target = pathlib.Path(sys.argv[1])
port = int(sys.argv[2])

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", port))
srv.listen(1)

print(f"Overwrite {target.name}? [y/N] ", end="", flush=True)
print(f"CONTROL 127.0.0.1:{port} listening", flush=True)

conn, _ = srv.accept()
raw = b""
with conn:
    while not raw.endswith(b"\\n"):
        chunk = conn.recv(4096)
        if not chunk:
            break
        raw += chunk
    conn.sendall(b'{"ack": true}\\n')
msg = json.loads(raw.decode("utf-8") or "{}")
answer = str(msg.get("answer", "")).strip()[:1].lower()

print(f"ANSWER {answer!r}")
if answer == "y":
    target.write_text("written after confirmation\\n", encoding="utf-8")
    print(f"WROTE {target.name} bytes={target.stat().st_size} file_written=True")
else:
    print(f"NO-WRITE {target.name} file_written=False")
print("CHANNEL control_socket")
print("BYE")
'''


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    ep = H.new_episode(TASK, TRACK, TRANSPORT)
    here, actions, observations, started = ep["dir"], ep["actions"], ep["observations"], ep["started"]
    target = here / f"episode_b2_{SUFFIX}.txt"
    fixture = here / "confirm_socket_fixture.py"
    port = free_port()

    fixture.write_text(FIXTURE_SRC, encoding="utf-8", newline="\n")
    if target.exists():
        target.unlink()
    setup = [{"what": "fixture program (control-socket channel)", "path": str(fixture),
              "sha256": H.sha256(fixture), "outside_pty": True},
             {"what": "enumerated app channel", "kind": "loopback control socket",
              "endpoint": f"127.0.0.1:{port}", "outside_pty": True},
             {"what": "target file absent before the episode", "path": str(target),
              "exists": target.exists(), "outside_pty": True}]

    argv = [sys.executable, "-B", str(fixture), str(target), str(port)]
    sess = PtySession(cols=90, rows=24)
    sess.start(argv)

    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker=r"\[y/N\]", max_wait_ms=10000)
    observations.append({"step": "confirmation prompt on screen", "reason": reason,
                         "screen": snap.to_text()})
    if reason == "TIMEOUT":
        return H.finalize(run_id=RUN_ID, task=TASK, track=TRACK, transport=TRANSPORT,
                          episode_dir=here, actions=actions, observations=observations,
                          setup=setup, claim=False, completion_basis="claim_withheld",
                          completion_detail={"in_episode_check": "the prompt never appeared"},
                          fixture_state={"answer": None, "file_written": target.exists()},
                          fixture_state_source="filesystem",
                          session={"driver": "smartcli_core.PtySession", "argv": argv},
                          started=started, ui_claim=False,
                          track_note="app-adapted: control socket channel")

    # ------------------------------------------- app channel: deliver the answer
    actions["app_channel"] += 1
    reply = None
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.sendall(b'{"answer": "y"}\n')
        reply = sock.makefile("r", encoding="utf-8").readline().strip()
    observations.append({"step": "answer delivered on the control socket",
                         "sent": '{"answer": "y"}', "reply": reply})

    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker="WROTE", max_wait_ms=8000)
    after_answer = snap.to_text()
    observations.append({"step": "program answered and reported its own write",
                         "reason": reason, "screen": after_answer})

    actions["snapshot"] += 1
    actions["wait"] += 1
    exit_info = H.wait_exit(sess, timeout_s=8.0)
    final_screen = sess.snapshot().to_text()
    observations.append({"step": "program exited", "screen": final_screen})

    close_state = sess.close()
    close_state_name = ("closed_confirmed" if close_state.get("closed_confirmed")
                        else "close_unconfirmed")

    m = re.search(r"ANSWER '(.*)'", final_screen)
    seen_answer = m.group(1) if m else None
    written = target.exists()
    claim = bool(seen_answer == "y" and "WROTE" in final_screen and written
                 and exit_info["exited"] and "BYE" in final_screen)
    fixture_state = {
        "answer": seen_answer,
        "file_written": written,
        "target": str(target),
        "bytes": target.stat().st_size if written else 0,
        "content": target.read_text(encoding="utf-8") if written else None,
        "program_reported_channel": "CHANNEL control_socket" in final_screen,
        "socket_ack": reply,
    }
    return H.finalize(
        run_id=RUN_ID, task=TASK, track=TRACK, transport=TRANSPORT, episode_dir=here,
        actions=actions, observations=observations, setup=setup, claim=claim,
        completion_basis="child_exit_observed" if claim else "claim_withheld",
        completion_detail={"in_episode_check": fixture_state},
        fixture_state=fixture_state,
        fixture_state_source=("the program's own PTY output for the answer; filesystem read "
                              "after the PTY was closed for file_written"),
        session={"driver": "smartcli_core.PtySession + fixture control socket",
                 "argv": argv, "cols": 90, "rows": 24, "cancel": False,
                 "process_exited": bool(exit_info["exited"]),
                 "exit_observed_by": exit_info["observation"], "exit_evidence": exit_info,
                 "close_state": close_state_name,
                 "close_observed": f"backend close_state()={close_state}",
                 "close_state_detail": close_state},
        started=started, ui_claim=False,
        track_note=("app-adapted (track A): the confirmation travelled over the program's "
                    "own control socket, not over the UI"))


if __name__ == "__main__":
    raise SystemExit(main())
