# RUN/A04-P/last.md — bounded idle-service prototype (design only)

Worker: session `01a0a700`. Repository files changed by this prototype: **ZERO**
(`scope_guard.py check --brief A04-P` → `changed_files: []`, `max_changed_files: 0`, exit 0).
No thread, socket, PTY/ConPTY, subprocess, dependency or Docker was created.

## Deliverables

| file | content |
|---|---|
| `prototype.py` | reference model: `Transport`, `ByteQueue` (byte cap + high/low watermarks), `Reader` (windows/posix shapes), `Owner` (budgeted turn), `Daemon` (fast verbs, interleave, resize attribution), `Control` (close/EOF beside the data queue), `Observer` |
| `test_prototype.py` | 17 tests: 12 invariants + 5 prescribed negative controls |
| `DESIGN_DELTA.md` | symbol-level migration proposal and the max-touch estimate |
| `last.md` | this receipt |
| `scope-baseline.json` | capture taken at A04-P start |

## Command and result

`python -B -m unittest discover -s <RUN>/A04-P -p "test_prototype.py"` → exit 0, **Ran 17 tests, OK**.

## Invariants demonstrated, each with the control that breaks it

| invariant | negative control |
|---|---|
| pending payload ≤ cap; the reader pauses at the high-water mark and is refused at the cap | uncapped queue + no watermark → `max_pending` grows past the design cap and the reader never waits |
| a tail refused for capacity is re-offered after a drain (no byte lost or duplicated) | (asserted directly: 30/30 bytes delivered once, in order) |
| the POSIX owner consumes the master fd while idle, and answers device queries then | idle service off → a finite fixture never completes without a client |
| one owner turn parses ≤ N bytes in ≤4 KiB read units | asserted on every turn (`max_turn ≤ turn_bytes`, `max_read_size ≤ 4`) |
| close/EOF travel beside the data queue | EOF queued behind a full data queue → `close_unconfirmed`, forever |
| fast verbs are answered inside a long wait's poll gap | interleave off → the fast request is starved for the whole wait |
| a second long wait still queues and is not advertised as supported | asserted: `wait_regex` is deferred, not served |
| resize never satisfies an action-specific wait | resize counted as an action → the wait reports `satisfied_by: "resize"` |
| two read-only observers judge one committed revision; neither reads transport | an observer reading the transport is detectable (reads = 1) |

## NOT_RUN matrix

| scope | status | reason |
|---|---|---|
| `windows_conpty` | **BASELINE MEASURED** (2026-09-16) | `X2/last.md`: queue grows unbounded while unpolled (271 307 B / 2 906 items in 7.5 s), delivery batched+delayed, a 1 MiB burst reaches the client as ~12 KB — `runtime_fixed` is still **false** |
| `posix_pty` | **BASELINE MEASURED** (2026-09-16) | `X3/last.md`: nobody polls → the child stalls at 12 288 B and the CPR query goes unanswered; owner loop → 512 KiB in 0.93 s with `ESC[30;89R` answered |
| `actual_daemon_loopback` | NOT_RUN | the prototype is a model; the real `_serve_forever` was not executed |
| `native_timing` | NOT_RUN | all timing is a virtual counter; no RSS/latency claim |
| `run_all.py` | NOT_RUN | not called (per the brief) |

Evidence level: **E2 reference model** for the prototype itself; the two platform baselines above are E4 measurements of the CURRENT code (no fix was applied). It does not raise any A04 claim above the source-level
inference it came from. Only the owner-approved X2 (Windows ConPTY, one session, bounded output) and
X3 (POSIX idle progress + interleave) could do that, and neither is authorized here.

## Open questions left for the owner

1. Budget at `read_nonblocking` (transport) or at `PtySession.pump` (consumer)? The transport budget
   changes what "no more data" means for readiness, so the pending/backlog signal must land first.
2. The Windows path re-encodes `pywinpty`'s `str` output, so a byte cap applies to re-encoded
   payload — no byte-exact claim is possible there.
3. Close policy when a native read cannot be interrupted: the model requires a bounded wait plus an
   explicit `close_unconfirmed`, never a silent success.
4. `tui._reply`'s `POST_AUTH_TIMEOUT = 60.0` and the unbounded `jobs`/`readers` structures remain
   open as **A06/A05**; ingress budgeting does not fix them.
