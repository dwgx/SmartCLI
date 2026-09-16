"""Minimal repro: does the io evidence path stall while the child is producing?

read_status() is what every io_block()/observation path asks for. This spawns a
child that writes continuously and calls read_status() ONCE while it is producing,
with a 10 s watchdog that dumps the blocking frame.
"""
from __future__ import annotations
import faulthandler, os, pathlib, sys, time

sys.path.insert(0, r"D:\Project\SmartCLI")
os.environ["SMARTCLI_WINPTY_HIGH_BYTES"] = str(128 * 1024)
os.environ["SMARTCLI_WINPTY_LOW_BYTES"] = str(32 * 1024)
from smartcli_core import PtySession
from smartcli_core.pty_backend import WinptyBackend

faulthandler.dump_traceback_later(10, exit=True)
backend = WinptyBackend()
sess = PtySession(backend=backend)
sess.start([sys.executable, "-u", "-c",
            "import sys,time\nbuf=bytes(4096)\nend=time.time()+30\n"
            "while time.time()<end:\n    sys.stdout.buffer.write(buf); sys.stdout.buffer.flush()"])
time.sleep(1.0)                       # the child is unmistakably producing now
print("child spawned and writing; calling read_status() once ...", flush=True)
t0 = time.time()
status = backend.read_status()
print(f"read_status() returned in {time.time()-t0:.2f}s: {status.get('queued_payload_bytes')} queued", flush=True)
faulthandler.cancel_dump_traceback_later()
sess.close()
