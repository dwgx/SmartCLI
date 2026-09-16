"""Fixture for B2, track A: confirm-over-control-socket.

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
    while not raw.endswith(b"\n"):
        chunk = conn.recv(4096)
        if not chunk:
            break
        raw += chunk
    conn.sendall(b'{"ack": true}\n')
msg = json.loads(raw.decode("utf-8") or "{}")
answer = str(msg.get("answer", "")).strip()[:1].lower()

print(f"ANSWER {answer!r}")
if answer == "y":
    target.write_text("written after confirmation\n", encoding="utf-8")
    print(f"WROTE {target.name} bytes={target.stat().st_size} file_written=True")
else:
    print(f"NO-WRITE {target.name} file_written=False")
print("CHANNEL control_socket")
print("BYE")
