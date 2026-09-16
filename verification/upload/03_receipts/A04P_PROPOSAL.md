# PROPOSAL — A04 production slice (needs the Owner's approval before any repo file changes)

Status: **proposal only.** No repository file was touched for A04. Required by v2's rule that new
threads/queues/public API need a small proposal first, and by the A04-P brief that the prototype
authorizes zero repository changes.

## 1. Problem, measured (not inferred)

| platform | measurement | artifact |
|---|---|---|
| Windows / ConPTY | with no client polling, the backend's unparsed backlog grows without bound: 0 → 271 307 B / 2 906 items over 7.5 s, and delivery is batched *slower than the child produces* (~30 KB per 0.5 s vs ~93 KB/s) | `RUN/X2/steady-queue.json` |
| Windows / ConPTY | a 1 MiB burst reaches the client as ~12 KB of composed stream — the Windows path cannot be byte-exact, at any layer we control | `RUN/X2/delivery.json` |
| POSIX | with no client polling, the child stalls at **12 288 B** and its `ESC[6n` is never answered; with the owner loop it completes 512 KiB in 0.93 s and the reply arrives | `RUN/X3/posix-idle.json` |
| both | the first client call pays for the entire backlog at once (`read_nonblocking` returned 301 763 B in 1.8 ms after 7.5 s of idleness) | `RUN/X2/steady-queue.json` |

The daemon's worker does not touch the PTY while the request queue is empty
(`tui.py` `worker()`: `jobs.get(timeout=0.2)` → `continue`), so "the agent is not asking" and "the
child is stalled" are the same state today. That is the defect; it is not a naming problem.

## 2. Proposed change, in three landable slices

Each slice keeps the observable contract of the daemon and the interleave behaviour; each has its own
failure test. Slices are ordered so the smallest useful behaviour lands first.

### Slice A — optional byte budget on the read path (2 files + 1 test)
* `smartcli_core/pty_backend.py`: `read_nonblocking(max_bytes: int | None = None)` — default `None`
  keeps today's drain-until-empty behaviour byte-for-byte, so no caller changes.
* `smartcli_core/session.py`: `pump(max_bytes: int | None = None)`; add a read-only
  `pending_bytes` (bytes read into the model but not yet parsed is 0 in the sync design — this
  instead reports what a budget-limited read left in the transport when the backend can tell us).
* test: `tests/test_a04_read_budget.py` (pure memory, fake backend): a budget-truncated read must not
  make `wait_*` report a stable screen; the unbudgeted call must behave exactly as before.
* Why a kwarg and not a new method: existing callers are untouched, and `--check`-style gates keep
  working.

### Slice B — idle service turn in the daemon (1 file + 1 test)
* `skills/drive-tui/scripts/tui.py`: the worker, on `queue.Empty`, runs one **bounded** `service_io()`
  turn (read with the Slice-A budget → `pump` → `drain_replies` → write replies) instead of
  `continue`. A per-turn byte budget and a per-turn interleave-job budget are both required; the
  existing `INTERLEAVE_OK` set and the `resize` exclusion stay untouched.
* test: `tests/test_daemon_idle_service.py` (fake session, loopback, no PTY): with no client request at
  all, the fake child's bytes reach the model and a device query is answered; removing the turn makes
  the test fail.
* Not in scope: a second long wait (still queued), any new thread.

### Slice C — bounded Windows backlog (1 file + 1 test) — **may need its own approval**
* `smartcli_core/pty_backend.py`: `WinptyBackend`'s reader writes into a byte-budgeted buffer
  (cap + high/low watermarks, stop-aware wait) instead of `queue.Queue()`, and holds the spawn's
  buffer/proc references rather than re-reading `self.*` after a respawn.
* test: `tests/test_a04_winpty_backlog.py` (fake `pywinpty` process object, no real ConPTY): the cap
  holds, a refused tail is re-offered, close is not blocked behind a full buffer.
* Honest limit to write into the code comment and the docs: **a bound here throttles pywinpty's
  reader, not the child**, because ConPTY has already buffered/composed the output. It fixes memory
  growth and makes the backlog visible; it cannot make the Windows path byte-exact.

Twins: `skills/drive-tui/_vendor/smartcli_core/{pty_backend,session}.py` must be re-generated for the
canonical files that change. Total: canonical 2 + vendor 2 + tests 3 + `tests/run_all.py` = **7 files**,
which is the cap; if the Owner wants a tighter diff, Slice C can be deferred (then 5 files).

## 3. Explicitly not fixed by this proposal

* **A05** (`tui.py:601-603` "64" is a filter, not a cap) and **A06** (`_reply` can stall the single
  worker for `POST_AUTH_TIMEOUT = 60 s`; `jobs`/`readers` are unbounded) — separate increments.
* Windows byte-exactness — impossible by measurement (see §1); the docs must say so.
* Multi-watcher product API — still one long wait; the A04-P model shows what a future design must
  prove, and `resize` must stay out of action-specific waits.

## 4. Acceptance for the whole slice

* All three failure tests red on the pre-change component and green after; the mutation for each is
  the removal of that slice's mechanism, run in an isolated copy (never `reset`/`stash` the tree).
* Existing gates stay green: `test_daemon_concurrency`, `test_wait_any`, `test_wait_change`,
  `test_visual_change`, `test_readiness`, `test_vendor_sync`, `test_terminal_fidelity`, plus the three
  new task-scoped tests from this round.
* `conformance.py --case all --consent-execute-reviewed-code` still exit 0.
* POSIX re-run of `X3/posix_idle_probe.py`: idle child must now complete **without** the test calling
  `pump()` itself (that is the acceptance the measurement in §1 defines).
* No commit, no push; receipts in `RUN/A04/{last.md,closure.json}` with hashes and NOT_RUN.

## 5. Risk and rollback

* Risk: an idle service turn raises CPU on an idle daemon. Mitigation: the turn is byte-budgeted and
  wake-driven; measure `turns/s` while idle before/after (a target to be set from the measurement, not
  asserted up front).
* Risk: Windows resend/duplication. Mitigation: the refused-tail test in Slice C plus a
  "bytes delivered once, in order" invariant on the fake transport.
* Rollback: each slice is independent; reverting one file pair restores the previous behaviour because
  every default path is `None`/unchanged.
