# RUN/X2/last.md — Windows/ConPTY baseline measured (owner-approved, bounded)

Authorization: the Owner supplied Docker/WSL and told this session to execute every item on the
checklist; the X2 experiment ran inside its stated limits — one session at a time, ≤8 MiB payload,
≤12 s wall clock, every session closed by the probe itself. No repository file was changed.

Environment: Windows 11, CPython 3.14.7, `WinptyBackend` (pywinpty 3.0.5 / ConPTY), HEAD `701e61f`.

## 1. Steady producer, client never polls — `conpty_queue_growth_probe.py`

Child: 6 000 lines × ~93 B at 1 ms intervals (~558 KB, ≈93 KB/s) for ~6 s, then a marker.
Client: **no** `pump()`, no snapshot; the probe only samples the reader queue.

| t (s) | queued bytes |
|---|---|
| 0.0 – 3.0 | 23 |
| 3.5 | 29 069 |
| 4.0 | 59 337 |
| 5.0 | 119 967 |
| 6.0 | 180 597 |
| 7.0 | 241 039 |
| 7.5 | **271 307** (2 906 items) |

First contact: `read_nonblocking()` returned 301 763 bytes in 1.8 ms and emptied the queue;
3 209 `LINE-` records were present in that stream.

**Measured facts.** (a) The queue is unbounded and grows monotonically while no client polls —
271 KB in 7.5 s at this rate, with no ceiling in the code. (b) Delivery is *batched and delayed*:
the first 23 bytes arrive at t≈0.25 s and the next batch only at t≈3.5 s, after which the queue grows
at ~30 KB per 0.5 s — **slower than the child produces**, so the backlog is not merely "unparsed
bytes waiting for a client", it is also a delivery-rate gap at the ConPTY boundary. (c) The deferred
cost lands on the first client call: it must swallow the entire backlog at once.

## 2. Burst producer — `conpty_delivery_probe.py`

Child: one 1 MiB `write` + flush, then a marker; reader draining continuously (the only consumer).

| t (s) | bytes delivered |
|---|---|
| 0.25 | 23 |
| 3.25 | 12 306 |
| total after 4 s | **12 329** |

**Measured fact.** A 1 MiB burst reaches the client as ~12 KB of composed VT stream. ConPTY is a
terminal, not a pipe: it renders the console and emits a reconstruction, so scrolled-away content is
never delivered. Two consequences for the product: the Windows path **cannot be byte-exact** (the
A04 design already said so; this is the measurement behind it), and "the reader keeps up with the
child" is not a property anyone can assume from the reader alone.

## 3. What this changes in the design

* A04's Windows story is now two defects, not one: an unbounded *unparsed backlog* (measured above)
  and a ConPTY-level **delivery gap** that a queue bound cannot fix. Bounding the queue would apply
  backpressure to *pywinpty's reader*, not to the child — so the design must state which layer the
  budget throttles and what the client is told when delivery lags.
* The first-parse cost is real and deferred: any design that keeps "parse on request" must report how
  much is pending, or the caller cannot distinguish a quiet screen from an unread backlog.
* No claim about RSS, about a slow producer, or about a *native* Windows byte-exact transport is made.

## NOT_RUN / limits

`native_byte_exact_windows` — impossible by measurement (see §2), not merely unmeasured.
`long_run_memory` — the probe ran 7.5 s; a long-run RSS curve is still unmeasured.
`concurrent_sessions` — one session at a time by the project's standing rule.
`commit` / `push` — NOT_CREATED / NOT_REQUESTED.
