## Symptom

`PtySession.pump(max_bytes=N)` never returns on the real ConPTY transport once the
reader crosses its high water. Verified twice with `faulthandler`: the main thread
sits in `smartcli_core/pty_backend.py` → `WinptyBackend._read_budgeted`, and the
process makes no progress for minutes (killed at 45 s / 200 s).

## Minimal repro

`D:\Project\SmartCLI-v3-runs\A04\s5-highwater\highwater_probe.py` (real ConPTY, real
child, no fakes):

```
set SMARTCLI_WINPTY_HIGH_BYTES=131072
set SMARTCLI_WINPTY_LOW_BYTES=32768
python -B highwater_probe.py --total 262144 --high 131072 --low 32768
```

Result: watchdog dump at 45 s, main thread inside `pump()` (line 72 of the probe,
`data = sess.pump(max_bytes=64 * 1024)`). With `--total 3145728 --high 262144` the
first attempt also failed to finish within its own 120 s deadline.

The same probe with the **default** high water (4 MiB) never reaches this state: the
N1 run measured a 131 072 B burst, well below the threshold, which is why the shipped
tests and the 55/55 aggregator are green.

## Mechanism (inferred from the code path and the dump)

`_read_budgeted` waits for the requested budget while the reader thread is paused at
the high water. The reader's pause condition is driven by the **accounted** payload
(queue + reader's own chunk + held suffix); the client's wait is driven by "give me
`max_bytes`". Nothing forces those two to meet:

- client: block until `max_bytes` bytes are available;
- reader: stop filling while accounted payload ≥ high water.

If the queue can never reach `max_bytes`, the client waits forever and the reader
never resumes, because resumption happens when the client *drains* — which the client
cannot do while it is waiting.

## Why the existing tests missed it

`tests/test_a04_winpty_backlog.py` drives a `FakeProc` whose `read()` always returns
immediately, so the reader never actually pauses; the injected transport makes
"budget unavailable" and "reader paused" mutually exclusive states. The real
transport is the only place they can meet.

## Impact

A daemon (or any client using `pump(max_bytes=...)`) hangs when the child produces
more than the high water faster than the client drains — which is exactly the case
the cap was added for. Default configuration needs a >4 MiB burst to enter it; the
lower the high water, the easier it is to hit. `_read_budgeted` must be bounded and
deadlock-free regardless of the water marks.

## Fix direction (not applied in this round)

`_read_budgeted` should return what is available after a bounded wait and **wake the
reader** when it has drained the queue below the low water, so a paused reader is a
backpressure signal, not a stall: never wait for a budget the transport cannot
produce, and never hold a client in a state only the client can release.

## Evidence

- `D:\Project\SmartCLI-v3-runs\A04\s5-highwater\highwater_probe.py` (the probe)
- `D:\Project\SmartCLI-v3-runs\A04\s5-highwater\read_status_stall.py` (a single-call
  control: `read_status()` alone returns in 0.00 s, so the stall is in the client's
  budgeted read, not in the io-evidence path)
- `D:\Project\SmartCLI-v3-runs\A04\RECEIPTS.md` (S5 section, first failure recorded)
