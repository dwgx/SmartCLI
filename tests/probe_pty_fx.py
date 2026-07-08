"""Probe: what bytes does one fx play run emit through the PTY? (exploration)"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smartcli_core import PtySession  # noqa: E402

cmd = [sys.executable, str(ROOT / "skills/cmd-art/fx/cli.py"),
       "play", "donut", "--seconds", "1.2", "--fps", "10",
       "--width", "60", "--height", "18"]
raw = bytearray()
t0 = time.time()
with PtySession(cols=70, rows=22) as sess:
    sess.start(cmd)
    while time.time() - t0 < 25:
        data = sess.pump()
        if data:
            raw.extend(data)
        if not sess.is_alive():
            for _ in range(10):  # drain
                d = sess.pump()
                if d:
                    raw.extend(d)
                time.sleep(0.05)
            break
        time.sleep(0.02)
    alive = sess.is_alive()

print("bytes:", len(raw))
print("alive_after:", alive)
print("runtime_s:", round(time.time() - t0, 2))
for marker, label in [
    (b"\x1b[?1049h", "alt_enter"),
    (b"\x1b[?1049l", "alt_leave"),
    (b"\x1b[?25l", "cursor_hide"),
    (b"\x1b[?25h", "cursor_show"),
    (b"\x1b[38;2;", "truecolor_fg"),
    (b"\x1b[48;2;", "truecolor_bg"),
    (b"\x1b[H", "home"),
]:
    print(f"{label}: {marker in raw}")
print("tail-120:", bytes(raw[-120:]))
